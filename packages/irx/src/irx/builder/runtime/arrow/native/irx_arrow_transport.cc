// Copyright IRx contributors.
#include "irx_arrow_transport.h"
#include <arrow/buffer.h>
#include <arrow/io/api.h>
#include <cerrno>
#include <cstring>

#ifndef _WIN32
#include <fcntl.h>
#include <netdb.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

namespace {
arrow::Status io_error(const char *operation) {
    return arrow::Status::IOError(operation, ": ", std::strerror(errno));
}
class Socket {
  public:
    explicit Socket(int fd) : fd(fd) {}
    ~Socket() { (void)close(); }
    arrow::Status close() {
        if (fd < 0)
            return arrow::Status::OK();
        int previous = fd;
        fd = -1;
        if (::close(previous) != 0)
            return io_error("close");
        return arrow::Status::OK();
    }
    int fd;
    int64_t position{0};
};
class SocketInput final : public arrow::io::InputStream {
  public:
    explicit SocketInput(int fd, bool is_socket = true)
        : socket_(fd), is_socket_(is_socket) {}
    arrow::Status Close() override { return socket_.close(); }
    bool closed() const override { return socket_.fd < 0; }
    arrow::Result<int64_t> Tell() const override { return socket_.position; }
    arrow::Result<int64_t> Read(int64_t n, void *out) override {
        if (n < 0 || closed())
            return arrow::Status::Invalid("invalid socket read");
        int64_t total = 0;
        while (total < n) {
            auto chunk =
                static_cast<size_t>(std::min<int64_t>(n - total, 65536));
            auto destination = static_cast<char *>(out) + total;
            auto count = is_socket_ ? ::recv(socket_.fd, destination, chunk, 0)
                                    : ::read(socket_.fd, destination, chunk);
            if (count < 0) {
                if (errno == EINTR)
                    continue;
                return io_error("recv");
            }
            if (count == 0)
                break;
            total += count;
            socket_.position += count;
        }
        return total;
    }
    arrow::Result<std::shared_ptr<arrow::Buffer>> Read(int64_t n) override {
        ARROW_ASSIGN_OR_RAISE(auto buffer, arrow::AllocateResizableBuffer(n));
        ARROW_ASSIGN_OR_RAISE(auto count, Read(n, buffer->mutable_data()));
        ARROW_RETURN_NOT_OK(buffer->Resize(count, false));
        return std::shared_ptr<arrow::Buffer>(std::move(buffer));
    }

  private:
    Socket socket_;
    bool is_socket_;
};
class SocketOutput final : public arrow::io::OutputStream {
  public:
    explicit SocketOutput(int fd) : socket_(fd) {
        set_mode(arrow::io::FileMode::WRITE);
    }
    arrow::Status Close() override { return socket_.close(); }
    bool closed() const override { return socket_.fd < 0; }
    arrow::Result<int64_t> Tell() const override { return socket_.position; }
    arrow::Status Write(const void *data, int64_t n) override {
        if (n < 0 || closed())
            return arrow::Status::Invalid("invalid socket write");
        int64_t total = 0;
        while (total < n) {
#ifdef MSG_NOSIGNAL
            constexpr int flags = MSG_NOSIGNAL;
#else
            constexpr int flags = 0; // SO_NOSIGPIPE is configured on Darwin.
#endif
            auto count =
                ::send(socket_.fd, static_cast<const char *>(data) + total,
                       static_cast<size_t>(std::min<int64_t>(n - total, 65536)),
                       flags);
            if (count < 0) {
                if (errno == EINTR)
                    continue;
                return io_error("send");
            }
            if (count == 0)
                return arrow::Status::IOError("send made no progress");
            total += count;
            socket_.position += count;
        }
        return arrow::Status::OK();
    }

  private:
    Socket socket_;
};
arrow::Result<int> connect_socket(const char *host, int port, int timeout) {
    if (!host || port < 1 || port > 65535 || timeout <= 0)
        return arrow::Status::Invalid("TCP requires a numeric address, port "
                                      "1..65535 and positive timeout");
    addrinfo hints{};
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_flags = AI_NUMERICHOST | AI_NUMERICSERV;
    addrinfo *raw = nullptr;
    int code = getaddrinfo(host, std::to_string(port).c_str(), &hints, &raw);
    if (code != 0)
        return arrow::Status::IOError("TCP address: ", gai_strerror(code));
    std::unique_ptr<addrinfo, decltype(&freeaddrinfo)> addresses(raw,
                                                                 freeaddrinfo);
    arrow::Status last = arrow::Status::IOError("no TCP addresses");
    for (auto address = raw; address; address = address->ai_next) {
        Socket socket(::socket(address->ai_family, SOCK_STREAM, 0));
        if (socket.fd < 0) {
            last = io_error("socket");
            continue;
        }
        if (fcntl(socket.fd, F_SETFD, FD_CLOEXEC) < 0 ||
            fcntl(socket.fd, F_SETFL, O_NONBLOCK) < 0)
            return io_error("fcntl");
        int result =
            ::connect(socket.fd, address->ai_addr, address->ai_addrlen);
        if (result < 0 && errno != EINPROGRESS) {
            last = io_error("connect");
            continue;
        }
        if (result < 0) {
            pollfd pending{socket.fd, POLLOUT, 0};
            result = poll(&pending, 1, timeout);
            if (result <= 0) {
                last = result == 0
                           ? arrow::Status::IOError("TCP connect timeout")
                           : io_error("poll");
                continue;
            }
            int error = 0;
            socklen_t size = sizeof(error);
            if (getsockopt(socket.fd, SOL_SOCKET, SO_ERROR, &error, &size) < 0)
                return io_error("getsockopt");
            if (error != 0) {
                errno = error;
                last = io_error("connect");
                continue;
            }
        }
        timeval deadline{timeout / 1000, (timeout % 1000) * 1000};
        if (fcntl(socket.fd, F_SETFL, 0) < 0 ||
            setsockopt(socket.fd, SOL_SOCKET, SO_RCVTIMEO, &deadline,
                       sizeof(deadline)) < 0 ||
            setsockopt(socket.fd, SOL_SOCKET, SO_SNDTIMEO, &deadline,
                       sizeof(deadline)) < 0)
            return io_error("socket timeout");
#ifdef SO_NOSIGPIPE
        int enabled = 1;
        if (setsockopt(socket.fd, SOL_SOCKET, SO_NOSIGPIPE, &enabled,
                       sizeof(enabled)) < 0)
            return io_error("SO_NOSIGPIPE");
#endif
        int fd = socket.fd;
        socket.fd = -1;
        return fd;
    }
    return last;
}
} // namespace
#endif
namespace irx {
arrow::Result<std::shared_ptr<arrow::io::InputStream>>
tcp_input(const char *host, int port, int timeout_ms) {
#ifndef _WIN32
    ARROW_ASSIGN_OR_RAISE(auto fd, connect_socket(host, port, timeout_ms));
    return std::make_shared<SocketInput>(fd);
#else
    return arrow::Status::NotImplemented("TCP transport requires POSIX");
#endif
}
arrow::Result<std::shared_ptr<arrow::io::OutputStream>>
tcp_output(const char *host, int port, int timeout_ms) {
#ifndef _WIN32
    ARROW_ASSIGN_OR_RAISE(auto fd, connect_socket(host, port, timeout_ms));
    return std::make_shared<SocketOutput>(fd);
#else
    return arrow::Status::NotImplemented("TCP transport requires POSIX");
#endif
}
arrow::Result<std::shared_ptr<arrow::io::InputStream>> fd_input(int fd) {
#ifndef _WIN32
    int copy = fcntl(fd, F_DUPFD_CLOEXEC, 0);
    if (copy < 0)
        return io_error("dup");
    return std::make_shared<SocketInput>(copy, false);
#else
    return arrow::Status::NotImplemented("fd transport requires POSIX");
#endif
}
arrow::Result<std::shared_ptr<arrow::io::OutputStream>> fd_output(int fd) {
#ifndef _WIN32
    int copy = fcntl(fd, F_DUPFD_CLOEXEC, 0);
    if (copy < 0)
        return io_error("dup");
    auto result = arrow::io::FileOutputStream::Open(copy);
    if (!result.ok()) {
        ::close(copy);
        return result.status();
    }
    return *result;
#else
    return arrow::Status::NotImplemented("fd transport requires POSIX");
#endif
}
} // namespace irx
