#ifndef IRX_CLASS_RUNTIME_H
#define IRX_CLASS_RUNTIME_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define IRX_CLASS_ERROR_CAPACITY 256
/* Payloads start with one opaque lifetime-token slot. Other layout is private
 * to generated code. create initializes both outputs on failure. Each owned
 * reference releases once; retain/release(NULL) are no-ops. The drop callback
 * consumes fields, not payload/control storage, and returns a checked status.
 * Final release frees both allocations even when the callback reports error.
 * Counts are synchronous, non-atomic; cycles and resurrection are unsupported.
 */
typedef int32_t (*irx_class_drop)(void* context, void* payload, char* error);
int32_t irx_class_create(size_t size, irx_class_drop drop, void** output,
                         char* error);
int32_t irx_class_retain(void* payload, char* error);
int32_t irx_class_release(void* context, void* payload, char* error);
/* require checks nullable field/receiver access. error is a caller-owned
 * IRX_CLASS_ERROR_CAPACITY buffer; successful checked operations clear it. */
int32_t irx_class_require(void* payload, char* error);
/* Compiler-only progress operations require a live, non-null payload. */
void irx_class_complete(void* payload);
int32_t irx_class_completed(void* payload);
/* Keep the first nonzero status/error while later fields are consumed. */
void irx_class_record(int32_t status, const char* error, int32_t* first_status,
                      char* first_error);
#ifdef __cplusplus
}
#endif
#endif
