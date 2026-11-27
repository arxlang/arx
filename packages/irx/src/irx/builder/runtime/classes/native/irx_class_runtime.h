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
 * Final strong release expires the token before invoking the drop callback
 * and frees the payload even on error. The implicit weak reference is held
 * through the callback, and the last weak release frees the token.
 * Counts are synchronous, non-atomic; cycles and resurrection are unsupported.
 */
typedef int32_t (*irx_class_drop)(void* context, void* payload, char* error);
int32_t irx_class_create(size_t size, irx_class_drop drop, void** output,
                         char* error);
int32_t irx_class_retain(void* payload, char* error);
int32_t irx_class_release(void* context, void* payload, char* error);
/* A successful downgrade owns one token reference. Upgrade returns an owned
 * payload reference or NULL for an empty/expired token. Both output slots are
 * NULL on error. Null weak retains/releases are no-ops. */
int32_t irx_class_downgrade(void* payload, void** output, char* error);
int32_t irx_class_upgrade(void* token, void** output, char* error);
int32_t irx_class_weak_retain(void* token, char* error);
void irx_class_weak_release(void* token);
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
