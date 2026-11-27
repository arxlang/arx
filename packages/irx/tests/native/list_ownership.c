/* Exercise the list ABI with deterministic allocation failure and drop counts. */
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static void* allocations[128];
static int live = 0;
static int fail_after = -1;
static int text_measurements = 0;

static size_t checked_strlen(const char* value) {
  ++text_measurements;
  return strlen(value);
}

static int should_fail(void) {
  if (fail_after < 0) return 0;
  if (fail_after == 0) return 1;
  --fail_after;
  return 0;
}

static void* checked_malloc(size_t size) {
  if (should_fail()) return NULL;
  void* result = malloc(size);
  assert(result != NULL && live < 128);
  allocations[live++] = result;
  return result;
}

static void checked_free(void* value) {
  if (value == NULL) return;
  int index = 0;
  while (index < live && allocations[index] != value) ++index;
  assert(index < live); /* Detect borrowed drops and repeated frees. */
  allocations[index] = allocations[--live];
  free(value);
}

static void* checked_realloc(void* value, size_t size) {
  if (value == NULL) return checked_malloc(size);
  if (should_fail()) return NULL;
  int index = 0;
  while (index < live && allocations[index] != value) ++index;
  assert(index < live);
  void* result = realloc(value, size);
  assert(result != NULL);
  allocations[index] = result;
  return result;
}

#define malloc checked_malloc
#define realloc checked_realloc
#define free checked_free
#define strlen checked_strlen
#include "irx_list_runtime.c"
#include "irx_text_runtime.c"
#undef malloc
#undef realloc
#undef free
#undef strlen

int main(void) {
  irx_list numbers = {0};
  int32_t number = 7;
  numbers.element_size = sizeof(number);
  assert(irx_list_append(NULL, &number) == IRX_LIST_INVALID_ARGUMENT);
  assert(irx_list_append(&numbers, &number) == IRX_LIST_OK);
  void* item = NULL;
  assert(irx_list_at(&numbers, 0, &item) == IRX_LIST_OK);
  assert(*(int32_t*)item == 7);
  numbers.element_kind = 2;
  assert(irx_list_at(&numbers, 0, &item) == IRX_LIST_INVALID_ARGUMENT);
  assert(item == NULL);
  numbers.element_kind = 0;
  assert(irx_list_at(&numbers, 1, &item) == IRX_LIST_OUT_OF_RANGE);
  assert(item == NULL);
  assert(irx_list_at(&numbers, -1, &item) == IRX_LIST_OUT_OF_RANGE);
  irx_list copy = {0};
  assert(irx_list_clone(&numbers, &numbers) == IRX_LIST_INVALID_ARGUMENT);
  assert(irx_list_clone(NULL, &copy) == IRX_LIST_INVALID_ARGUMENT);
  assert(irx_list_clone(&numbers, NULL) == IRX_LIST_INVALID_ARGUMENT);
  fail_after = 0;
  assert(irx_list_clone(&numbers, &copy) == IRX_LIST_ALLOCATION_FAILED);
  assert(copy.data == NULL && copy.length == 0 && live == 1);
  fail_after = -1;
  assert(irx_list_clone(&numbers, &copy) == IRX_LIST_OK);
  assert(copy.data != numbers.data && copy.length == 1 && live == 2);
  assert(irx_list_clone(&numbers, &copy) == IRX_LIST_INVALID_ARGUMENT);
  assert(copy.length == 1 && live == 2);
  irx_list_destroy(&numbers);
  assert(irx_list_at(&copy, 0, &item) == IRX_LIST_OK);
  assert(*(int32_t*)item == 7);
  irx_list_destroy(&copy);
  fail_after = 0;
  assert(irx_list_clone(&numbers, &copy) == IRX_LIST_OK);
  assert(copy.element_size == sizeof(number) && copy.data == NULL);
  fail_after = -1;
  assert(irx_list_append(&copy, &number) == IRX_LIST_OK);
  irx_list_destroy(&copy);
  irx_list_destroy(&numbers);
  assert(live == 0 && numbers.data == NULL && numbers.length == 0);

  char source[] = "hello";
  char* borrowed = source;
  irx_list strings = {0};
  strings.element_size = sizeof(char*);
  strings.element_kind = 1;
  assert(irx_list_append(&strings, &borrowed) == IRX_LIST_OK);
  source[0] = 'H';
  assert(irx_list_at(&strings, 0, &item) == IRX_LIST_OK);
  assert(strcmp(*(char**)item, "hello") == 0);
  assert(*(char**)item != borrowed && live == 2);
  fail_after = 0; /* Element allocation fails; the old list is unchanged. */
  assert(irx_list_append(&strings, &borrowed) == IRX_LIST_ALLOCATION_FAILED);
  assert(strings.length == 1 && live == 2);
  fail_after = -1;
  for (int index = 0; index < 3; ++index)
    assert(irx_list_append(&strings, &borrowed) == IRX_LIST_OK);
  assert(strings.length == 4 && live == 5);
  fail_after = 1; /* Clone succeeds, growth fails: roll back the clone. */
  assert(irx_list_append(&strings, &borrowed) == IRX_LIST_ALLOCATION_FAILED);
  assert(strings.length == 4 && strings.capacity == 4 && live == 5);
  for (int budget = 0; budget < 5; ++budget) {
    fail_after = budget;
    assert(irx_list_clone(&strings, &copy) == IRX_LIST_ALLOCATION_FAILED);
    assert(copy.data == NULL && copy.length == 0 && copy.capacity == 0);
    assert(strings.length == 4 && live == 5);
    assert(irx_list_at(&strings, 0, &item) == IRX_LIST_OK);
    assert(strcmp(*(char**)item, "hello") == 0);
  }
  fail_after = -1;
  assert(irx_list_clone(&strings, &copy) == IRX_LIST_OK);
  void* copied_item = NULL;
  assert(irx_list_at(&copy, 0, &copied_item) == IRX_LIST_OK);
  assert(*(char**)copied_item != *(char**)item && live == 10);
  irx_list_destroy(&strings);
  irx_list_destroy(&strings);
  assert(strcmp(*(char**)copied_item, "hello") == 0);
  irx_list_destroy(&copy);
  assert(live == 0);

  borrowed = "";
  fail_after = -1;
  assert(irx_list_append(&strings, &borrowed) == IRX_LIST_OK);
  assert(irx_list_at(&strings, 0, &item) == IRX_LIST_OK);
  assert(strcmp(*(char**)item, "") == 0 && *(char**)item != borrowed);
  borrowed = NULL;
  assert(irx_list_append(&strings, &borrowed) == IRX_LIST_INVALID_ARGUMENT);
  assert(strings.length == 1);
  irx_list_destroy(&strings);
  assert(live == 0);

  /* Capacity arithmetic must fail before touching these synthetic buffers. */
  irx_list huge = {(uint8_t*)&number, INT64_MAX, INT64_MAX, 1, 0};
  assert(irx_list_append(&huge, &number) == IRX_LIST_CAPACITY_OVERFLOW);
  huge.length = 0;
  huge.element_size = INT64_MAX;
  assert(irx_list_append(&huge, &number) == IRX_LIST_CAPACITY_OVERFLOW);
  assert(irx_list_clone(&huge, &copy) == IRX_LIST_CAPACITY_OVERFLOW);
  assert(copy.data == NULL && copy.length == 0);
  assert(live == 0);

  /* Every allocation frontier of split must release the entire partial list.
   * Reuse the list allocator instrumentation to detect leaks/double drops. */
  int succeeded = 0;
  for (int budget = 0; budget < 12; ++budget) {
    fail_after = budget;
    irx_list output = {0};
    int32_t status = irx_text_split("a,b,c,d,e,f,g", ",", -1, &output);
    if (status == IRX_TEXT_OK) {
      assert(output.length == 7 && live == 8);
      ++succeeded;
    } else {
      assert(status == IRX_TEXT_ALLOCATION_FAILED);
      assert(output.data == NULL && output.length == 0 && live == 0);
    }
    irx_list_destroy(&output);
    irx_list_destroy(&output);
    assert(live == 0);
  }
  assert(succeeded > 0);
  fail_after = -1;
  irx_text_cache* cache = NULL;
  int64_t count = 0;
  char* text = NULL;
  char mixed[97];
  for (size_t i = 0; i < 32; ++i) memcpy(mixed + i * 3, "\xc3\xa9x", 3);
  mixed[96] = '\0';
  text_measurements = 0;
  assert(irx_text_cached_len(mixed, &cache, &count) == IRX_TEXT_OK);
  assert(count == 64 && live == 1 && text_measurements == 1);
  for (int64_t i = 31; i < 64; ++i) {
    assert(irx_text_cached_index(mixed, i, &cache, &text) == IRX_TEXT_OK);
    assert(strcmp(text, i % 2 ? "x" : "\xc3\xa9") == 0);
    checked_free(text);
  }
  assert(live == 2 && text_measurements == 1);
  assert(irx_text_cached_index(mixed, 64, &cache, &text) ==
         IRX_TEXT_OUT_OF_RANGE && text == NULL);
  irx_text_cache_clear(&cache);
  irx_text_cache_clear(&cache);
  assert(live == 0 && cache == NULL);
  assert(irx_text_cached_len("\xff", &cache, &count) == IRX_TEXT_ENCODING);
  assert(count == 0 && cache == NULL);
  fail_after = 0;
  assert(irx_text_cached_len("abc", &cache, &count) == IRX_TEXT_OK);
  assert(count == 3 && cache == NULL);
  assert(irx_text_strip(" value ", NULL, &text) == IRX_TEXT_ALLOCATION_FAILED);
  assert(text == NULL && live == 0);
  assert(irx_text_index("value", 0, &text) == IRX_TEXT_ALLOCATION_FAILED);
  assert(text == NULL && live == 0);
  assert(irx_text_slice("value", 0, 1, 1, &text) == IRX_TEXT_ALLOCATION_FAILED);
  assert(text == NULL && live == 0);
  fail_after = -1;
  char mutable_text[] = "left,right";
  assert(irx_text_split(mutable_text, ",", -1, &strings) == IRX_TEXT_OK);
  mutable_text[0] = 'L';
  assert(irx_list_at(&strings, 0, &item) == IRX_LIST_OK);
  assert(strcmp(*(char**)item, "left") == 0);
  irx_list_destroy(&strings);
  huge.length = huge.capacity = INT64_MAX;
  assert(text_add(&huge, "", 0, 0) == IRX_TEXT_OVERFLOW);
  assert(live == 0);
  return 0;
}
