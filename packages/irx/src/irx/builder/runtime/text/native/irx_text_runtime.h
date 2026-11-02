#ifndef IRX_TEXT_RUNTIME_H
#define IRX_TEXT_RUNTIME_H

#include <stdint.h>
#include "irx_list_runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Borrowed inputs are accessible, NUL-terminated UTF-8 strings. Embedded NUL
 * is not representable in this ABI: producers must reject it before conversion
 * (use validate for length-delimited input). No operation retains its inputs.
 * Output slots must not contain live owners. On failure scalars are zero,
 * pointers NULL, and lists empty. Read outputs only after status == OK.
 * Successful string/list outputs are independent malloc-owned copies, released
 * with free / irx_list_destroy respectively, including empty strings. */
typedef enum irx_text_status {
  IRX_TEXT_OK = 0,
  IRX_TEXT_INVALID_ARGUMENT = 1,
  IRX_TEXT_OVERFLOW = 2,
  IRX_TEXT_ALLOCATION_FAILED = 3,
  IRX_TEXT_OUT_OF_RANGE = 4,
  IRX_TEXT_ENCODING = 5
} irx_text_status;

/* Bounded validation rejects NUL, overlong encodings, surrogates, truncation,
 * and scalars above U+10FFFF. Count is Unicode scalars, not bytes/graphemes. */
int32_t irx_text_validate(const char* data, int64_t bytes, int64_t* count);
int32_t irx_text_len(const char* text, int64_t* out);
int32_t irx_text_ord(const char* text, int64_t* out);
int32_t irx_text_index(const char* text, int64_t index, char** out);
/* Nonnegative, clipped half-open bounds; step must be 1. Omitted stop is
 * INT64_MAX. Inverted ranges return an owned empty string. */
int32_t irx_text_slice(const char* text, int64_t start, int64_t stop,
                       int64_t step, char** out);
/* NULL separator means whitespace splitting; any negative maxsplit is
 * unlimited. Explicit nonempty separators preserve empty fields. */
int32_t irx_text_split(const char* text, const char* sep, int64_t maxsplit,
                       irx_list* out);
/* NULL chars uses the whitespace set; otherwise chars is a code-point set. */
int32_t irx_text_strip(const char* text, const char* chars, char** out);
/* Strict ASCII digits/letters, optional ASCII sign and surrounding whitespace.
 * Bases 2..36 only; no prefixes, underscores, Unicode digits, or partial parse.
 * Result must fit signed i64. */
int32_t irx_text_int(const char* text, int64_t base, int64_t* out);
const char* irx_text_status_message(int32_t status);

#ifdef __cplusplus
}
#endif

#endif
