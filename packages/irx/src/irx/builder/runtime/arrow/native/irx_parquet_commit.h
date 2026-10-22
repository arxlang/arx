// Copyright IRx contributors.
#ifndef IRX_PARQUET_COMMIT_H
#define IRX_PARQUET_COMMIT_H
#include <arrow/status.h>
#include <arrow/result.h>
#include <filesystem>
#include <memory>
#include <cerrno>
#include <cstring>
#ifndef _WIN32
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif

namespace irx {
// The persistent lock inode must never be unlinked: waiters may still own it.
// Advisory exclusion covers cooperating IRx writers to the same canonical path.
class LocalWriteLease {
 public:
    ~LocalWriteLease() {
#ifndef _WIN32
        if (fd_ >= 0) { (void)::flock(fd_, LOCK_UN); (void)::close(fd_); }
#endif
    }
    LocalWriteLease(const LocalWriteLease &) = delete;
    LocalWriteLease &operator=(const LocalWriteLease &) = delete;
    static arrow::Result<std::shared_ptr<LocalWriteLease>> Acquire(const std::string &path) {
#ifdef _WIN32
        return arrow::Status::NotImplemented("coordinated local Parquet writes require POSIX");
#else
        auto destination = std::filesystem::path(path);
        auto parent = std::filesystem::canonical(destination.parent_path());
        auto lock = parent / ("." + destination.filename().string() + ".irx.lock");
        int fd = ::open(lock.c_str(), O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);
        if (fd < 0) return arrow::Status::IOError("cannot open Parquet writer lock: ", std::strerror(errno));
        if (::flock(fd, LOCK_EX | LOCK_NB) != 0) {
            int error = errno;
            (void)::close(fd);
            return arrow::Status::IOError("Parquet destination is busy or cannot be locked: ", std::strerror(error));
        }
        return std::shared_ptr<LocalWriteLease>(new LocalWriteLease(fd));
#endif
    }
 private:
    explicit LocalWriteLease(int fd) : fd_(fd) {}
    int fd_;
};

inline arrow::Status sync_local_path(const std::filesystem::path &path, bool directory) {
#ifdef _WIN32
    return arrow::Status::NotImplemented("durable Parquet commits require POSIX");
#else
    int fd = ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NOFOLLOW | (directory ? O_DIRECTORY : 0));
    if (fd < 0) return arrow::Status::IOError("cannot open Parquet commit path for fsync: ", std::strerror(errno));
    int result;
    do { result = ::fsync(fd); } while (result != 0 && errno == EINTR);
    int error = errno;
    (void)::close(fd);
    if (result != 0) return arrow::Status::IOError("Parquet commit fsync failed: ", std::strerror(error));
    return arrow::Status::OK();
#endif
}
} // namespace irx
#endif
