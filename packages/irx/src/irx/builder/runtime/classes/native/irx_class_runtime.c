#include "irx_class_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  uint64_t references;
  int32_t completed;
  irx_class_drop drop;
} irx_class_owner;

static int32_t irx_class_error(char* error, const char* message) {
  if (error) snprintf(error, IRX_CLASS_ERROR_CAPACITY, "%s", message);
  return 1;
}
static irx_class_owner* irx_class_token(void* value) {
  irx_class_owner* owner;
  memcpy(&owner, value, sizeof(owner));
  return owner;
}
int32_t irx_class_create(size_t size, irx_class_drop drop, void** out,
                         char* error) {
  irx_class_owner* owner;
  void* value;
  if (error) error[0] = 0;
  if (out) *out = NULL;
  if (!out || !drop || size < sizeof(owner))
    return irx_class_error(error, "invalid class creation contract");
  owner = calloc(1, sizeof(*owner));
  if (!owner) return irx_class_error(error, "class allocation failed");
  value = calloc(1, size);
  if (!value) {
    free(owner);
    return irx_class_error(error, "class payload allocation failed");
  }
  owner->references = 1;
  owner->drop = drop;
  memcpy(value, &owner, sizeof(owner));
  *out = value;
  return 0;
}
int32_t irx_class_retain(void* value, char* error) {
  irx_class_owner* owner;
  if (error) error[0] = 0;
  if (!value) return 0;
  owner = irx_class_token(value);
  if (!owner->references || owner->references == UINT64_MAX)
    return irx_class_error(error, "invalid class retain or resurrection");
  owner->references++;
  return 0;
}
int32_t irx_class_release(void* value, char* error) {
  irx_class_owner* owner;
  int32_t status;
  if (error) error[0] = 0;
  if (!value) return 0;
  owner = irx_class_token(value);
  if (!owner->references)
    return irx_class_error(error, "class release during destruction");
  if (--owner->references) return 0;
  status = owner->drop(value, error);
  free(value);
  free(owner);
  return status;
}
int32_t irx_class_require(void* value, char* error) {
  if (error) error[0] = 0;
  return value ? 0 : irx_class_error(error, "access to an empty class value");
}
void irx_class_complete(void* value) { irx_class_token(value)->completed++; }
int32_t irx_class_completed(void* value) {
  return irx_class_token(value)->completed;
}
void irx_class_record(int32_t status, const char* error, int32_t* first,
                      char* first_error) {
  if (!status || *first) return;
  *first = status;
  if (first_error) snprintf(first_error, IRX_CLASS_ERROR_CAPACITY, "%s", error);
}
