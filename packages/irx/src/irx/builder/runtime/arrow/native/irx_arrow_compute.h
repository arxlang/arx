// Copyright IRx contributors.
#ifndef IRX_ARROW_COMPUTE_H
#define IRX_ARROW_COMPUTE_H
#include <stdint.h>
#include "irx_native_status.h"

#ifdef __cplusplus
extern "C" {
#endif
typedef struct irx_arrow_chunked_array_handle irx_arrow_chunked_array_handle;
enum {
  IRX_COMPUTE_ABI_VERSION = 1,
  IRX_COMPUTE_SCALAR = 1,
  IRX_COMPUTE_SERIES = 2,
  IRX_COMPUTE_F64 = 12,  // Arrow logical type ID, NOT legacy storage ID 10.
  IRX_COMPUTE_NO_OPTIONS = 0,
};
enum irx_compute_operation {
#define IRX_COMPUTE_OPERATION(SYMBOL, ID, NAME, ULPS) IRX_COMPUTE_##SYMBOL = ID,
#include "irx_arrow_compute_catalog.h"
#undef IRX_COMPUTE_OPERATION
};

/* Version/capability queries do not dereference handles. All calls require the
 * exact ABI revision and Arrow 26.0.1. Only unary f64 sqrt/exp, no options.
 * Returns IRX_OK or a typed IRX_ERR_*; EOF is never a compute result. */
uint32_t irx_arrow_compute_abi_version(void);
int32_t irx_arrow_compute_supports(uint32_t abi, int32_t operation,
    int32_t arity, int32_t options, int32_t arrow_type, int32_t shape);

/* Inputs are borrowed for the call and never consumed/mutated. SCALAR requires
 * a NULL column; bits are the exact IEEE f64 representation, validity is 0/1.
 * Invalid payloads are ignored. SERIES requires a live owned/borrowed chunked
 * handle of f64 dtype; scalar bits/validity must be zero. Other shapes fail.
 * All three output slots are required, distinct from inputs, and cleared even
 * on failure. Read them only after IRX_OK: scalar publishes bits/validity,
 * Series publishes one independently owned handle (including empty results).
 * Retain/release that handle normally; it survives input/parent release. Null
 * scalar outputs carry zero bits. Series length/order/validity are preserved;
 * chunk boundaries and NaN payloads are not guaranteed. No fast-math.
 * Callers must supply accessible pointers/live handles; arbitrary pointers,
 * use-after-release, and concurrent mutation of a handle are invalid C usage.
 * No new scalar/Datum handle or C++ layout crosses this ABI. */
int32_t irx_arrow_compute(uint32_t abi, int32_t operation, int32_t arity,
    int32_t options, int32_t arrow_type, int32_t shape,
    const irx_arrow_chunked_array_handle* column, uint64_t bits, int32_t valid,
    irx_arrow_chunked_array_handle** out_column, uint64_t* out_bits,
    int32_t* out_valid);
/* NULL retain/release are no-ops. Retain adds a reference; release consumes
 * exactly one. The last release destroys the handle and its Arrow owners.
 * Error text is thread-local, borrowed until the next Arrow bridge call. */
int irx_arrow_chunked_array_retain(irx_arrow_chunked_array_handle* column);
void irx_arrow_chunked_array_release(irx_arrow_chunked_array_handle* column);
const char* irx_arrow_last_error(void);
#ifdef __cplusplus
}
#endif
#endif
