#include "irx_buffer_runtime.h"

#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

struct irx_buffer_owner_handle {
  int64_t refcount;
  void* context;
  irx_buffer_owner_release_fn release;
};

static const char* irx_buffer_error = "";

static int32_t irx_buffer_set_error(const char* message) {
  irx_buffer_error = message;
  return -1;
}

const char* irx_buffer_last_error(void) { return irx_buffer_error; }

int32_t irx_buffer_checked_offset(const irx_buffer_view* view,
                                  const int64_t* indices, int32_t rank,
                                  int64_t item_size, int64_t* out) {
  if (out == NULL) return 1;
  *out = 0;
  if (view == NULL || rank < 0 || view->ndim != rank || item_size <= 0 ||
      view->data == NULL ||
      (rank && (!indices || !view->shape || !view->strides)))
    return 1;
  int64_t offset = view->offset_bytes;
  for (int32_t axis = 0; axis < rank; ++axis) {
    int64_t index = indices[axis], stride = view->strides[axis];
    if (view->shape[axis] < 0) return 1;
    if (index < 0 || index >= view->shape[axis]) return 4;
    if (index && (stride > INT64_MAX / index || stride < INT64_MIN / index))
      return 2;
    int64_t scaled = index * stride;
    if ((scaled > 0 && offset > INT64_MAX - scaled) ||
        (scaled < 0 && offset < INT64_MIN - scaled))
      return 2;
    offset += scaled;
  }
  if (offset < 0 || offset > INT64_MAX - item_size ||
      (uint64_t)offset > UINTPTR_MAX - (uintptr_t)view->data ||
      (uint64_t)(item_size - 1) >
          UINTPTR_MAX - ((uintptr_t)view->data + (uint64_t)offset))
    return 2;
  *out = offset;
  return 0;
}

int32_t irx_buffer_sequence_read(const void* source, int64_t index,
                                 int32_t size, uint64_t* bits,
                                 int32_t* valid) {
  if (bits) *bits = 0;
  if (valid) *valid = 0;
  if (!bits || !valid || size < 1 || size > 8) return 1;
  const irx_buffer_view* view = (const irx_buffer_view*)source;
  int64_t offset = 0;
  int32_t status = irx_buffer_checked_offset(view, &index, 1, size, &offset);
  if (status) return status;
  /* Load at the native width before extending; preserve big-endian hosts. */
  switch (size) {
    case 1: {
      uint8_t v;
      memcpy(&v, (const uint8_t*)view->data + offset, 1);
      *bits = v;
      break;
    }
    case 2: {
      uint16_t v;
      memcpy(&v, (const uint8_t*)view->data + offset, 2);
      *bits = v;
      break;
    }
    case 4: {
      uint32_t v;
      memcpy(&v, (const uint8_t*)view->data + offset, 4);
      *bits = v;
      break;
    }
    case 8:
      memcpy(bits, (const uint8_t*)view->data + offset, 8);
      break;
    default:
      return 1;
  }
  *valid = 1;
  return 0;
}

int32_t irx_buffer_owner_external_new(
    void* context,
    irx_buffer_owner_release_fn release,
    irx_buffer_owner_handle** out_owner) {
  if (out_owner == NULL) {
    return irx_buffer_set_error("out_owner must not be NULL");
  }
  *out_owner = NULL;

  irx_buffer_owner_handle* owner =
      (irx_buffer_owner_handle*)malloc(sizeof(*owner));
  if (owner == NULL) {
    return irx_buffer_set_error("failed to allocate buffer owner handle");
  }

  owner->refcount = 1;
  owner->context = context;
  owner->release = release;
  *out_owner = owner;
  irx_buffer_error = "";
  return 0;
}

int32_t irx_buffer_owner_retain(irx_buffer_owner_handle* owner) {
  if (owner == NULL) {
    irx_buffer_error = "";
    return 0;
  }
  if (owner->refcount <= 0) {
    return irx_buffer_set_error("cannot retain a released buffer owner");
  }
  owner->refcount += 1;
  irx_buffer_error = "";
  return 0;
}

int32_t irx_buffer_owner_release(irx_buffer_owner_handle* owner) {
  if (owner == NULL) {
    irx_buffer_error = "";
    return 0;
  }
  if (owner->refcount <= 0) {
    return irx_buffer_set_error("cannot release a released buffer owner");
  }
  owner->refcount -= 1;
  if (owner->refcount == 0) {
    irx_buffer_owner_release_fn release = owner->release;
    void* context = owner->context;
    free(owner);
    if (release != NULL) {
      release(context);
    }
  }
  irx_buffer_error = "";
  return 0;
}

int32_t irx_buffer_view_retain(const irx_buffer_view* view) {
  if (view == NULL) {
    return irx_buffer_set_error("view must not be NULL");
  }
  return irx_buffer_owner_retain(view->owner);
}

int32_t irx_buffer_view_release(irx_buffer_view* view) {
  if (view == NULL) {
    return irx_buffer_set_error("view must not be NULL");
  }
  int32_t code = irx_buffer_owner_release(view->owner);
  if (code == 0) {
    view->owner = NULL;
  }
  return code;
}
