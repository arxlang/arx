#ifndef IRX_FILE_RUNTIME_H
#define IRX_FILE_RUNTIME_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define IRX_FILE_ERROR_CAPACITY 256
typedef struct irx_file irx_file;
typedef enum irx_file_status {
  IRX_FILE_OK = 0, IRX_FILE_INVALID_ARGUMENT = 1, IRX_FILE_CLOSED = 2,
  IRX_FILE_ENCODING = 3, IRX_FILE_ALLOCATION = 4, IRX_FILE_OVERFLOW = 5,
  IRX_FILE_MODE = 6, IRX_FILE_NO_PROGRESS = 7,
  /* OS failures encode the captured POSIX errno in the low 16 bits. */
  IRX_FILE_OS_ERROR = 65536
} irx_file_status;
/* All errors are caller-owned buffers of IRX_FILE_ERROR_CAPACITY bytes.
 * Status 0 means success. Outputs are initialized even on failure and may only
 * be consumed on success. Read buffers belong to the caller and use free().
 * close is idempotent; release consumes the wrapper even if closing fails.
 * Handles are single-owner, synchronous, and not thread-safe. */
int32_t irx_file_open(const char* path, const char* mode, int32_t text_options,
                      irx_file** out_file, char* error);
int32_t irx_file_read(irx_file* file, char** out_text, char* error);
int32_t irx_file_write(irx_file* file, const char* text, int64_t* out_count,
                       char* error);
/* text_options is 0 or 1: non-None encoding/errors/newline are text-only.
 * Validation precedes fopen (including create/truncate). Byte methods require
 * binary mode even for zero size. Size must fit size_t and be nonnegative.
 * read_bytes returns independent malloc storage, NULL/0 at EOF, at most size.
 * write_bytes borrows data; NULL is valid only for zero size. Short progress is
 * retried; errors leave count zero but may have partially modified the file. */
int32_t irx_file_read_bytes(irx_file* file, int64_t size,
                            unsigned char** out_data, int64_t* out_count,
                            char* error);
int32_t irx_file_write_bytes(irx_file* file, const unsigned char* data,
                             int64_t size, int64_t* out_count, char* error);
int32_t irx_file_flush(irx_file* file, char* error);
int32_t irx_file_close(irx_file* file, char* error);
int32_t irx_file_release(irx_file* file, char* error);
#ifdef __cplusplus
}
#endif
#endif
