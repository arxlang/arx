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
  /* 0: trivial value; 1: independently owned NUL-free string pointer. */
  int32_t element_kind;
} irx_list;

typedef enum irx_list_status {
  IRX_LIST_OK = 0,
  IRX_LIST_INVALID_ARGUMENT = 1,
  IRX_LIST_CAPACITY_OVERFLOW = 2,
  IRX_LIST_ALLOCATION_FAILED = 3,
  IRX_LIST_OUT_OF_RANGE = 4
} irx_list_status;

/* Borrows value; string elements are copied. Failure never publishes an item.
   Destroy drops every initialized string, then the backing allocation. */
int32_t irx_list_append(irx_list* list, const void* value);
/* Output remains NULL on failure; callers may dereference only on success. */
int32_t irx_list_at(const irx_list* list, int64_t index, void** out);
/* Borrowed sequence callback: size is the exact scalar byte width (1..8).
 * Success publishes zero-extended raw bits and validity 1; failure clears both.
 * No element conversion, ownership transfer, or mutation is performed. */
int32_t irx_list_sequence_read(const void* source, int64_t index, int32_t size,
                              uint64_t* bits, int32_t* valid);
void irx_list_destroy(irx_list* list);
const char* irx_list_status_message(int32_t status);

#ifdef __cplusplus
}
#endif

#endif
