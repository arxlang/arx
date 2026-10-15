// Copyright IRx contributors.
// Count direct generated/runtime malloc/free calls, not libc's internal caches.
#include <stdio.h>
#include <stdlib.h>

static long live;
void* __real_malloc(size_t size);
void __real_free(void* pointer);

void* __wrap_malloc(size_t size) {
  void* pointer = __real_malloc(size);
  if (pointer != NULL) ++live;
  return pointer;
}

void __wrap_free(void* pointer) {
  if (pointer != NULL) --live;
  __real_free(pointer);
}

__attribute__((destructor)) static void check_owners(void) {
  if (live != 0) {
    fprintf(stderr, "unreleased generated owners: %ld\n", live);
    _Exit(99);
  }
}
