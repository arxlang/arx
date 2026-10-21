// Copyright IRx contributors. Byte transports, independent of IPC encoding.
#ifndef IRX_ARROW_TRANSPORT_H
#define IRX_ARROW_TRANSPORT_H
#include <arrow/io/interfaces.h>
#include <arrow/result.h>
#include <memory>

namespace irx {
// Connects to a numeric IPv4/IPv6 address. Positive timeout covers connect and
// each blocking I/O call. The returned stream owns its socket.
arrow::Result<std::shared_ptr<arrow::io::InputStream>>
tcp_input(const char *host, int port, int timeout_ms);
arrow::Result<std::shared_ptr<arrow::io::OutputStream>>
tcp_output(const char *host, int port, int timeout_ms);
// Duplicate a borrowed descriptor; closing the stream never closes the caller's
// descriptor. Descriptors share their underlying offset. Do not mix readers.
arrow::Result<std::shared_ptr<arrow::io::InputStream>> fd_input(int fd);
arrow::Result<std::shared_ptr<arrow::io::OutputStream>> fd_output(int fd);
} // namespace irx
#endif
