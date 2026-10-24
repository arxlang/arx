#ifndef IRX_EXCEPTION_RUNTIME_H
#define IRX_EXCEPTION_RUNTIME_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct irx_exception_info irx_exception_info;
typedef struct irx_exception_context irx_exception_context;
typedef struct irx_exception_value irx_exception_value;
typedef struct irx_exception_scope irx_exception_scope;

/* All records are opaque, reference counted, synchronous and non-atomic.
 * Strings and ancestry entries are copied. Ancestry contains canonical semantic
 * identities, including the concrete class; display names never identify types.
 * create initializes *out to NULL, returns 0 only after full publication, and
 * returns -1 on invalid input/allocation failure. No output is read on failure.
 * Records do not own class payloads. The compiler-owned root class field owns
 * one record reference; pending/handled values own independent references and
 * class references. Immutable diagnostic snapshots cannot form reference cycles.
 */
int32_t irx_exception_info_create(const char* name, const char* message,
    const char* const* ancestry, int32_t ancestry_count,
    irx_exception_info** out);
void irx_exception_info_retain(irx_exception_info* info);
void irx_exception_info_release(irx_exception_info* info);
const char* irx_exception_info_message(const irx_exception_info* info);

int32_t irx_exception_context_create(irx_exception_context** out);
void irx_exception_context_destroy(irx_exception_context* context);

/* raise borrows payload/cause, retains payload for pending ownership, and
 * atomically replaces *object_slot with a new owned diagnostic snapshot.
 * mode: 0 implicit context; 1 explicit cause; 2 suppress context display.
 * Return 1 with a pending exception; -1 leaves inputs/state unchanged.
 * A pending exception must be moved aside before executing fallible cleanup.
 */
int32_t irx_exception_raise(irx_exception_context* context, void* payload,
    irx_exception_info** object_slot, irx_exception_info* cause, int32_t mode,
    const char* source, int32_t line, int32_t col, const char* code);
/* Bare re-raise preserves the origin. -1 means no active handled exception. */
int32_t irx_exception_reraise(irx_exception_context* context);
int32_t irx_exception_pending(const irx_exception_context* context);
int32_t irx_exception_matches(const irx_exception_context* context,
                             const char* semantic_identity);
void* irx_exception_handled_payload(const irx_exception_context* context);
irx_exception_info* irx_exception_pending_info(
    const irx_exception_context* context);

/* Scope tokens must leave in reverse entry order. Entry transfers pending
 * ownership without allocation of a new exception. Token allocation failure
 * and misuse are fatal internal/runtime-machinery failures, never silent NULL.
 * Handlers always consume their saved exception; finally restores it only on
 * preserve && no replacement. Implicit cleanup preserves the original failure,
 * recording subsequent failures as secondary diagnostics, but promotes a
 * cleanup failure when no original existed. Handled state is dynamically scoped.
 */
irx_exception_scope* irx_exception_handler_enter(irx_exception_context* context);
void irx_exception_handler_leave(irx_exception_context* context,
                                irx_exception_scope* scope);
irx_exception_scope* irx_exception_finally_enter(irx_exception_context* context);
void irx_exception_finally_leave(irx_exception_context* context,
                                irx_exception_scope* scope, int32_t preserve);
irx_exception_scope* irx_exception_cleanup_enter(irx_exception_context* context);
void irx_exception_cleanup_leave(irx_exception_context* context,
                                irx_exception_scope* scope);

/* take transfers an opaque owning pending value; restore/discard consume it.
 * restore requires an empty pending slot. NULL values are allowed. */
irx_exception_value* irx_exception_pending_take(irx_exception_context* context);
void irx_exception_pending_restore(irx_exception_context* context,
                                  irx_exception_value* value);
void irx_exception_pending_discard(irx_exception_context* context,
                                  irx_exception_value* value);

/* Trace append and reporting never replace a failure with allocation failure.
 * Diagnostics have bounded chain/trace depth and omit untrustworthy locations.
 * Only report prints; raising or catching is silent. */
void irx_exception_trace(irx_exception_context* context, const char* source,
                         int32_t line, int32_t col);
void irx_exception_report(const irx_exception_context* context);

#ifdef __cplusplus
}
#endif
#endif
