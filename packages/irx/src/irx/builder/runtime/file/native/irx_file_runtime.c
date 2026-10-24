#include "irx_file_runtime.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#error "The file runtime currently supports POSIX targets only"
#endif

struct irx_file {
  FILE* stream;
  int readable;
};

static int32_t irx_file_error(char* error, int32_t status, const char* message) {
  if (error != NULL) snprintf(error, IRX_FILE_ERROR_CAPACITY, "%s", message);
  return status;
}

static int32_t irx_file_system_error(char* error, const char* operation) {
  int saved_errno = errno;
  if (error != NULL)
    snprintf(error, IRX_FILE_ERROR_CAPACITY, "%s: %s", operation,
             saved_errno ? strerror(saved_errno) : "I/O failure");
  return IRX_FILE_OS_ERROR | (saved_errno & 65535);
}

static void irx_file_clear_error(char* error) {
  if (error != NULL) error[0] = '\0';
}

/* Strict UTF-8: reject NUL, overlong forms, surrogates, and values > U+10FFFF.
 */
static int32_t irx_file_utf8(const unsigned char* data, size_t length,
                             int64_t* count, char* error) {
  size_t i = 0;
  int64_t chars = 0;
  while (i < length) {
    uint32_t cp;
    uint32_t minimum;
    size_t continuation;
    unsigned char first = data[i++];
    if (first == 0)
      return irx_file_error(error, IRX_FILE_ENCODING, "text containing NUL is unsupported");
    if (first < 0x80) {
      cp = first;
      continuation = 0;
      minimum = 0;
    } else if (first >= 0xc2 && first <= 0xdf) {
      cp = first & 0x1f;
      continuation = 1;
      minimum = 0x80;
    } else if (first >= 0xe0 && first <= 0xef) {
      cp = first & 0x0f;
      continuation = 2;
      minimum = 0x800;
    } else if (first >= 0xf0 && first <= 0xf4) {
      cp = first & 7;
      continuation = 3;
      minimum = 0x10000;
    } else
      return irx_file_error(error, IRX_FILE_ENCODING, "invalid UTF-8 text");
    if (continuation > length - i)
      return irx_file_error(error, IRX_FILE_ENCODING, "incomplete UTF-8 text");
    while (continuation-- > 0) {
      unsigned char next = data[i++];
      if ((next & 0xc0) != 0x80)
        return irx_file_error(error, IRX_FILE_ENCODING, "invalid UTF-8 text");
      cp = (cp << 6) | (next & 0x3f);
    }
    if (cp < minimum || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff))
      return irx_file_error(error, IRX_FILE_ENCODING, "invalid UTF-8 code point");
    if (chars == INT64_MAX)
      return irx_file_error(error, IRX_FILE_OVERFLOW, "text character count overflow");
    chars++;
  }
  *count = chars;
  return 0;
}

int32_t irx_file_open(const char* path, const char* mode, irx_file** out,
                      char* error) {
  char canonical[2] = {0, 0};
  irx_file* handle;
  irx_file_clear_error(error);
  if (out != NULL) *out = NULL;
  if (out == NULL || path == NULL || mode == NULL)
    return irx_file_error(error, IRX_FILE_INVALID_ARGUMENT, "open requires a path, mode, and output");
  if (!strcmp(mode, "r") || !strcmp(mode, "rt"))
    canonical[0] = 'r';
  else if (!strcmp(mode, "w") || !strcmp(mode, "wt"))
    canonical[0] = 'w';
  else if (!strcmp(mode, "a") || !strcmp(mode, "at"))
    canonical[0] = 'a';
  else
    return irx_file_error(error, IRX_FILE_MODE, "open supports only r, w, a, rt, wt, at modes");
  handle = malloc(sizeof(*handle));
  if (handle == NULL) return irx_file_error(error, IRX_FILE_ALLOCATION, "file allocation failed");
  errno = 0;
  handle->stream = fopen(path, canonical);
  if (handle->stream == NULL) {
    int32_t status = irx_file_system_error(error, "open failed");
    free(handle);
    return status;
  }
  handle->readable = canonical[0] == 'r';
  *out = handle;
  return 0;
}

int32_t irx_file_read(irx_file* handle, char** out, char* error) {
  size_t used = 0, capacity = 4096, source, target;
  int64_t count;
  char* buffer;
  irx_file_clear_error(error);
  if (out != NULL) *out = NULL;
  if (out == NULL) return irx_file_error(error, IRX_FILE_INVALID_ARGUMENT, "read requires an output");
  if (handle == NULL || handle->stream == NULL)
    return irx_file_error(error, IRX_FILE_CLOSED, "read on a closed file");
  if (!handle->readable) return irx_file_error(error, IRX_FILE_MODE, "file is not readable");
  buffer = malloc(capacity);
  if (buffer == NULL) return irx_file_error(error, IRX_FILE_ALLOCATION, "read allocation failed");
  for (;;) {
    size_t received;
    if (capacity - used <= 1) {
      char* grown;
      if (capacity > SIZE_MAX / 2) {
        free(buffer);
        return irx_file_error(error, IRX_FILE_OVERFLOW, "read size overflow");
      }
      capacity *= 2;
      grown = realloc(buffer, capacity);
      if (grown == NULL) {
        free(buffer);
        return irx_file_error(error, IRX_FILE_ALLOCATION, "read allocation failed");
      }
      buffer = grown;
    }
    errno = 0;
    received = fread(buffer + used, 1, capacity - used - 1, handle->stream);
    used += received;
    if (ferror(handle->stream)) {
      int32_t status = irx_file_system_error(error, "read failed");
      free(buffer);
      return status;
    }
    if (feof(handle->stream)) break;
    if (received == 0) {
      free(buffer);
      return irx_file_error(error, IRX_FILE_NO_PROGRESS, "read made no progress");
    }
  }
  {
    int32_t status = irx_file_utf8((const unsigned char*)buffer, used, &count, error);
    if (status) { free(buffer); return status; }
  }
  for (source = 0, target = 0; source < used; source++) {
    if (buffer[source] == '\r') {
      buffer[target++] = '\n';
      if (source + 1 < used && buffer[source + 1] == '\n') source++;
    } else
      buffer[target++] = buffer[source];
  }
  buffer[target] = '\0';
  *out = buffer;
  return 0;
}

int32_t irx_file_write(irx_file* handle, const char* text, int64_t* out,
                       char* error) {
  size_t length;
  int64_t count;
  irx_file_clear_error(error);
  if (out != NULL) *out = 0;
  if (out == NULL || text == NULL)
    return irx_file_error(error, IRX_FILE_INVALID_ARGUMENT, "write requires text and output");
  if (handle == NULL || handle->stream == NULL)
    return irx_file_error(error, IRX_FILE_CLOSED, "write on a closed file");
  if (handle->readable) return irx_file_error(error, IRX_FILE_MODE, "file is not writable");
  length = strlen(text);
  {
    int32_t status = irx_file_utf8((const unsigned char*)text, length, &count, error);
    if (status) return status;
  }
  errno = 0;
  if (fwrite(text, 1, length, handle->stream) != length)
    return irx_file_system_error(error, "write failed");
  *out = count;
  return 0;
}

int32_t irx_file_flush(irx_file* handle, char* error) {
  irx_file_clear_error(error);
  if (handle == NULL || handle->stream == NULL)
    return irx_file_error(error, IRX_FILE_CLOSED, "flush on a closed file");
  /* fflush on an input stream is not portable C; there is nothing to write. */
  if (handle->readable) return 0;
  errno = 0;
  if (fflush(handle->stream) != 0)
    return irx_file_system_error(error, "flush failed");
  return 0;
}

int32_t irx_file_close(irx_file* handle, char* error) {
  FILE* stream;
  irx_file_clear_error(error);
  if (handle == NULL) return irx_file_error(error, IRX_FILE_INVALID_ARGUMENT, "close requires a file");
  stream = handle->stream;
  if (stream == NULL) return 0;
  handle->stream = NULL;
  errno = 0;
  if (fclose(stream) != 0) return irx_file_system_error(error, "close failed");
  return 0;
}

int32_t irx_file_release(irx_file* handle, char* error) {
  int32_t status;
  irx_file_clear_error(error);
  if (handle == NULL) return 0;
  status = irx_file_close(handle, error);
  free(handle);
  return status;
}
