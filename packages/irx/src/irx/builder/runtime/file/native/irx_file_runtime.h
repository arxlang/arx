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
int32_t irx_file_open(const char* path, const char* mode, irx_file** out_file,
                      char* error);
int32_t irx_file_read(irx_file* file, char** out_text, char* error);
int32_t irx_file_write(irx_file* file, const char* text, int64_t* out_count,
                       char* error);
int32_t irx_file_flush(irx_file* file, char* error);
int32_t irx_file_close(irx_file* file, char* error);
int32_t irx_file_release(irx_file* file, char* error);
#ifdef __cplusplus
}
#endif
#endif
