#ifndef IRX_LIST_RUNTIME_H
#define IRX_LIST_RUNTIME_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct irx_list {
  uint8_t* data;
  int64_t length;
  int64_t capacity;
  int64_t element_size;
} irx_list;

typedef enum irx_list_status {
  IRX_LIST_OK = 0,
  IRX_LIST_INVALID_ARGUMENT = 1,
  IRX_LIST_CAPACITY_OVERFLOW = 2,
  IRX_LIST_ALLOCATION_FAILED = 3
} irx_list_status;

int32_t irx_list_append(irx_list* list, const void* value);
void* irx_list_at(const irx_list* list, int64_t index);
void irx_list_destroy(irx_list* list);
void irx_list_require_ok(int32_t status);

#ifdef __cplusplus
}
#endif

#endif
