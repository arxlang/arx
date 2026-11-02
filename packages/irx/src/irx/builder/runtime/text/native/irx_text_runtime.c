#include "irx_text_runtime.h"

#include <stddef.h>
#include <stdlib.h>
#include <string.h>

/* Locale-independent Unicode White_Space plus U+001C..U+001F, matching
 * Python str.isspace: 0009..000D, 001C..0020, 0085, 00A0, 1680,
 * 2000..200A, 2028..2029, 202F, 205F, 3000. No normalization is performed. */
static int text_space(uint32_t cp) {
  return (cp >= 9 && cp <= 13) || (cp >= 0x1c && cp <= 0x20) ||
      cp == 0x85 || cp == 0xa0 || cp == 0x1680 ||
      (cp >= 0x2000 && cp <= 0x200a) || cp == 0x2028 || cp == 0x2029 ||
      cp == 0x202f || cp == 0x205f || cp == 0x3000;
}

static int32_t text_decode(const char* data, size_t length, size_t* offset,
                           uint32_t* codepoint) {
  size_t i = *offset;
  if (i >= length) return IRX_TEXT_ENCODING;
  unsigned char first = (unsigned char)data[i++];
  uint32_t cp, minimum;
  size_t remaining;
  if (first > 0 && first < 0x80) {
    cp = first; minimum = 0; remaining = 0;
  } else if (first >= 0xc2 && first <= 0xdf) {
    cp = first & 0x1f; minimum = 0x80; remaining = 1;
  } else if (first >= 0xe0 && first <= 0xef) {
    cp = first & 0x0f; minimum = 0x800; remaining = 2;
  } else if (first >= 0xf0 && first <= 0xf4) {
    cp = first & 7; minimum = 0x10000; remaining = 3;
  } else {
    return IRX_TEXT_ENCODING;
  }
  if (remaining > length - i) return IRX_TEXT_ENCODING;
  while (remaining-- > 0) {
    unsigned char next = (unsigned char)data[i++];
    if ((next & 0xc0) != 0x80) return IRX_TEXT_ENCODING;
    cp = (cp << 6) | (next & 0x3f);
  }
  if (cp < minimum || cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff))
    return IRX_TEXT_ENCODING;
  *offset = i;
  *codepoint = cp;
  return IRX_TEXT_OK;
}

int32_t irx_text_validate(const char* data, int64_t bytes, int64_t* count) {
  if (count) *count = 0;
  if (!data || !count || bytes < 0) return IRX_TEXT_INVALID_ARGUMENT;
  if ((uint64_t)bytes > SIZE_MAX) return IRX_TEXT_OVERFLOW;
  size_t offset = 0;
  int64_t total = 0;
  while (offset < (size_t)bytes) {
    uint32_t cp;
    int32_t status = text_decode(data, (size_t)bytes, &offset, &cp);
    if (status) return status;
    ++total; /* A code point consumes at least one of at most INT64_MAX bytes. */
  }
  *count = total;
  return IRX_TEXT_OK;
}

static int32_t text_measure(const char* text, size_t* bytes, int64_t* count) {
  if (!text) return IRX_TEXT_INVALID_ARGUMENT;
  size_t length = strlen(text);
  if ((uint64_t)length > INT64_MAX) return IRX_TEXT_OVERFLOW;
  int32_t status = irx_text_validate(text, (int64_t)length, count);
  if (!status) *bytes = length;
  return status;
}

static int32_t text_copy(const char* text, size_t start, size_t end, char** out) {
  size_t length = end - start;
  if (length == SIZE_MAX) return IRX_TEXT_OVERFLOW;
  char* copy = (char*)malloc(length + 1);
  if (!copy) return IRX_TEXT_ALLOCATION_FAILED;
  memcpy(copy, text + start, length);
  copy[length] = '\0';
  *out = copy;
  return IRX_TEXT_OK;
}

int32_t irx_text_len(const char* text, int64_t* out) {
  if (!out) return IRX_TEXT_INVALID_ARGUMENT;
  *out = 0;
  size_t bytes = 0;
  return text_measure(text, &bytes, out);
}

int32_t irx_text_ord(const char* text, int64_t* out) {
  if (!out) return IRX_TEXT_INVALID_ARGUMENT;
  *out = 0;
  size_t bytes = 0, offset = 0;
  int64_t count = 0;
  int32_t status = text_measure(text, &bytes, &count);
  if (status) return status;
  if (count != 1) return IRX_TEXT_INVALID_ARGUMENT;
  uint32_t cp;
  status = text_decode(text, bytes, &offset, &cp);
  if (!status) *out = cp;
  return status;
}

int32_t irx_text_slice(const char* text, int64_t start, int64_t stop,
                       int64_t step, char** out) {
  if (!out) return IRX_TEXT_INVALID_ARGUMENT;
  *out = NULL;
  if (start < 0 || stop < 0 || step != 1) return IRX_TEXT_INVALID_ARGUMENT;
  size_t bytes = 0;
  int64_t count = 0;
  int32_t status = text_measure(text, &bytes, &count);
  if (status) return status;
  if (start > count) start = count;
  if (stop > count) stop = count;
  if (stop < start) stop = start;
  size_t offset = 0, begin = 0;
  int64_t index = 0;
  while (index < stop) {
    if (index == start) begin = offset;
    uint32_t cp;
    text_decode(text, bytes, &offset, &cp); /* Already validated in full. */
    ++index;
  }
  if (start == stop) begin = offset;
  return text_copy(text, begin, offset, out);
}

int32_t irx_text_index(const char* text, int64_t index, char** out) {
  if (!out) return IRX_TEXT_INVALID_ARGUMENT;
  *out = NULL;
  size_t bytes = 0, offset = 0, begin = 0;
  int64_t count = 0;
  int32_t status = text_measure(text, &bytes, &count);
  if (status) return status;
  if (index < 0 || index >= count) return IRX_TEXT_OUT_OF_RANGE;
  for (int64_t i = 0; i <= index; ++i) {
    uint32_t cp;
    begin = offset;
    text_decode(text, bytes, &offset, &cp);
  }
  return text_copy(text, begin, offset, out);
}

static int text_member(uint32_t cp, const char* chars, size_t bytes) {
  if (!chars) return text_space(cp);
  size_t offset = 0;
  while (offset < bytes) {
    uint32_t candidate;
    text_decode(chars, bytes, &offset, &candidate);
    if (candidate == cp) return 1;
  }
  return 0;
}

static void text_trim(const char* text, size_t bytes, const char* chars,
                       size_t chars_bytes, size_t* start, size_t* stop) {
  size_t offset = 0;
  *start = bytes;
  *stop = bytes;
  while (offset < bytes) {
    size_t before = offset;
    uint32_t cp;
    text_decode(text, bytes, &offset, &cp);
    if (!text_member(cp, chars, chars_bytes)) {
      if (*start == bytes) *start = before;
      *stop = offset;
    }
  }
}

int32_t irx_text_strip(const char* text, const char* chars, char** out) {
  if (!out) return IRX_TEXT_INVALID_ARGUMENT;
  *out = NULL;
  size_t bytes = 0, chars_bytes = 0, start, stop;
  int64_t count = 0;
  int32_t status = text_measure(text, &bytes, &count);
  if (status) return status;
  if (chars) {
    status = text_measure(chars, &chars_bytes, &count);
    if (status) return status;
  }
  text_trim(text, bytes, chars, chars_bytes, &start, &stop);
  return text_copy(text, start, stop, out);
}

static int32_t text_add(irx_list* list, const char* text,
                        size_t start, size_t end) {
  if (list->length == INT64_MAX) return IRX_TEXT_OVERFLOW;
  if (list->length == list->capacity) {
    if (list->capacity > INT64_MAX / 2) return IRX_TEXT_OVERFLOW;
    int64_t capacity = list->capacity ? list->capacity * 2 : 4;
    if ((uint64_t)capacity > SIZE_MAX / sizeof(char*)) return IRX_TEXT_OVERFLOW;
    void* resized = realloc(list->data, (size_t)capacity * sizeof(char*));
    if (!resized) return IRX_TEXT_ALLOCATION_FAILED;
    list->data = (uint8_t*)resized;
    list->capacity = capacity;
  }
  char* copy = NULL;
  int32_t status = text_copy(text, start, end, &copy);
  if (status) return status;
  memcpy(list->data + (size_t)list->length * sizeof(copy), &copy, sizeof(copy));
  ++list->length;
  return IRX_TEXT_OK;
}

static size_t text_skip_space(const char* text, size_t bytes, size_t offset) {
  while (offset < bytes) {
    size_t before = offset;
    uint32_t cp;
    text_decode(text, bytes, &offset, &cp);
    if (!text_space(cp)) return before;
  }
  return offset;
}

int32_t irx_text_split(const char* text, const char* sep, int64_t maxsplit,
                       irx_list* out) {
  if (!out) return IRX_TEXT_INVALID_ARGUMENT;
  irx_list result = {NULL, 0, 0, sizeof(char*), 1};
  *out = result;
  size_t bytes = 0, sep_bytes = 0;
  int64_t count = 0;
  int32_t status = text_measure(text, &bytes, &count);
  if (status) return status;
  if (sep) {
    status = text_measure(sep, &sep_bytes, &count);
    if (status) return status;
    if (!sep_bytes) return IRX_TEXT_INVALID_ARGUMENT;
  }
  size_t start = sep ? 0 : text_skip_space(text, bytes, 0);
  while (sep || start < bytes) {
    size_t end = bytes, next = bytes;
    if (maxsplit < 0 || result.length < maxsplit) {
      if (sep) {
        const char* found = strstr(text + start, sep);
        if (found) {
          end = (size_t)(found - text);
          next = end + sep_bytes;
        }
      } else {
        size_t offset = start;
        while (offset < bytes) {
          size_t before = offset;
          uint32_t cp;
          text_decode(text, bytes, &offset, &cp);
          if (text_space(cp)) {
            end = before;
            next = text_skip_space(text, bytes, offset);
            break;
          }
        }
      }
    }
    status = text_add(&result, text, start, end);
    if (status) {
      irx_list_destroy(&result);
      return status;
    }
    if (end == bytes) break;
    start = next;
  }
  *out = result;
  return IRX_TEXT_OK;
}

int32_t irx_text_int(const char* text, int64_t base, int64_t* out) {
  if (!out) return IRX_TEXT_INVALID_ARGUMENT;
  *out = 0;
  if (base < 2 || base > 36) return IRX_TEXT_INVALID_ARGUMENT;
  size_t bytes = 0, start, stop;
  int64_t count = 0;
  int32_t status = text_measure(text, &bytes, &count);
  if (status) return status;
  text_trim(text, bytes, NULL, 0, &start, &stop);
  int negative = start < stop && text[start] == '-';
  if (start < stop && (text[start] == '+' || text[start] == '-')) ++start;
  if (start == stop) return IRX_TEXT_INVALID_ARGUMENT;
  uint64_t value = 0;
  uint64_t limit = negative ? (uint64_t)INT64_MAX + 1 : (uint64_t)INT64_MAX;
  for (size_t i = start; i < stop; ++i) {
    unsigned char c = (unsigned char)text[i];
    uint64_t digit;
    if (c >= '0' && c <= '9') digit = c - '0';
    else if (c >= 'a' && c <= 'z') digit = c - 'a' + 10;
    else if (c >= 'A' && c <= 'Z') digit = c - 'A' + 10;
    else return IRX_TEXT_INVALID_ARGUMENT;
    if (digit >= (uint64_t)base) return IRX_TEXT_INVALID_ARGUMENT;
    if (value > (limit - digit) / (uint64_t)base) return IRX_TEXT_OVERFLOW;
    value = value * (uint64_t)base + digit;
  }
  *out = negative ? (value == (uint64_t)INT64_MAX + 1 ? INT64_MIN : -(int64_t)value)
                  : (int64_t)value;
  return IRX_TEXT_OK;
}

const char* irx_text_status_message(int32_t status) {
  switch (status) {
    case IRX_TEXT_OK: return "";
    case IRX_TEXT_INVALID_ARGUMENT: return "invalid text argument or option";
    case IRX_TEXT_OVERFLOW: return "text result exceeds supported size or i64 range";
    case IRX_TEXT_ALLOCATION_FAILED: return "text allocation failed";
    case IRX_TEXT_OUT_OF_RANGE: return "text code-point index out of range";
    case IRX_TEXT_ENCODING: return "text requires valid NUL-free UTF-8";
    default: return "unknown text runtime status";
  }
}
