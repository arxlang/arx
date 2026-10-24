#include "irx_list_runtime.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define IRX_LIST_MIN_CAPACITY 4

static int32_t irx_list_next_capacity(
    int64_t current_capacity,
    int64_t* out_capacity) {
  if (out_capacity == NULL || current_capacity < 0) {
    return IRX_LIST_INVALID_ARGUMENT;
  }
  if (current_capacity < IRX_LIST_MIN_CAPACITY) {
    *out_capacity = IRX_LIST_MIN_CAPACITY;
    return IRX_LIST_OK;
  }
  if (current_capacity > INT64_MAX / 2) {
    return IRX_LIST_CAPACITY_OVERFLOW;
  }
  *out_capacity = current_capacity * 2;
  return IRX_LIST_OK;
}

int32_t irx_list_append(irx_list* list, const void* value) {
  if (list == NULL) {
    return IRX_LIST_INVALID_ARGUMENT;
  }
  if (value == NULL) {
    return IRX_LIST_INVALID_ARGUMENT;
  }
  if (list->element_size <= 0 || list->length < 0 || list->capacity < 0 ||
      list->length > list->capacity || (list->capacity && !list->data)) {
    return IRX_LIST_INVALID_ARGUMENT;
  }

  if (list->length >= list->capacity) {
    int64_t new_capacity = 0;
    int32_t capacity_status =
        irx_list_next_capacity(list->capacity, &new_capacity);
    if (capacity_status != IRX_LIST_OK) {
      return capacity_status;
    }
    if ((uint64_t)new_capacity >
        (uint64_t)SIZE_MAX / (uint64_t)list->element_size) {
      return IRX_LIST_CAPACITY_OVERFLOW;
    }
    size_t new_size =
        (size_t)new_capacity * (size_t)list->element_size;
    void* new_data = realloc(list->data, new_size);
    if (new_data == NULL) {
      return IRX_LIST_ALLOCATION_FAILED;
    }
    list->data = (uint8_t*)new_data;
    list->capacity = new_capacity;
  }

  memcpy(
      list->data + ((size_t)list->length * (size_t)list->element_size),
      value,
      (size_t)list->element_size);
  list->length += 1;
  return IRX_LIST_OK;
}

int32_t irx_list_at(const irx_list* list, int64_t index, void** out) {
  if (out) *out = NULL;
  if (!list || !out || list->length < 0 || list->capacity < list->length ||
      list->element_size <= 0) return IRX_LIST_INVALID_ARGUMENT;
  if (index < 0 || index >= list->length) return IRX_LIST_OUT_OF_RANGE;
  if (!list->data) return IRX_LIST_INVALID_ARGUMENT;
  if ((uint64_t)index > SIZE_MAX / (uint64_t)list->element_size)
    return IRX_LIST_CAPACITY_OVERFLOW;
  *out = list->data + ((size_t)index * (size_t)list->element_size);
  return IRX_LIST_OK;
}

void irx_list_destroy(irx_list* list) {
  if (list == NULL) {
    return;
  }
  free(list->data);
  list->data = NULL;
  list->length = 0;
  list->capacity = 0;
}

const char* irx_list_status_message(int32_t status) {
  switch (status) {
    case IRX_LIST_OK: return "";
    case IRX_LIST_INVALID_ARGUMENT:
      return "dynamic list operation received an invalid argument";
    case IRX_LIST_CAPACITY_OVERFLOW: return "dynamic list capacity overflow";
    case IRX_LIST_ALLOCATION_FAILED: return "dynamic list allocation failed";
    case IRX_LIST_OUT_OF_RANGE: return "dynamic list index out of range";
    default: return "dynamic list operation returned an unknown status";
  }
}
