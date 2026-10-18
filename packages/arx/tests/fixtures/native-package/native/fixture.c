/* Generic package-boundary fixture, not a renderer or an encoder. */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "jpeg_payload.h"

#ifdef __cplusplus
extern "C" {
#endif

static int64_t current_token;
static int active;
static int released;

int64_t fixture_create(int32_t size) {
  if (size <= 0 || active || current_token == INT64_MAX)
    return 0;
  active = 1;
  return ++current_token;
}

int32_t fixture_note(int64_t token, double value, const char *label) {
  if (!active || token != current_token)
    return 1;
  if (!isfinite(value) || !label || !strlen(label))
    return 2;
  return 0;
}

int32_t fixture_write(int64_t token, const char *path, int32_t kind) {
  static const unsigned char binary[] = {0, 255, 128, 10, 13};
  if (!active || token != current_token)
    return 1;
  if (!path || (kind != 0 && kind != 1))
    return 2;
  FILE *output = fopen(path, "wb");
  if (!output)
    return 3;
  const unsigned char *data = kind == 0 ? jpeg_payload : binary;
  size_t size = kind == 0 ? sizeof(jpeg_payload) : sizeof(binary);
  int failed = fwrite(data, 1, size, output) != size;
  if (fclose(output))
    failed = 1;
  return failed ? 4 : 0;
}

int32_t fixture_release(int64_t token) {
  if (!active || token != current_token)
    return 1;
  active = 0;
  ++released;
  return 0;
}

int32_t fixture_alive(void) { return active; }
int32_t fixture_releases(void) { return released; }

#ifdef __cplusplus
}
#endif
