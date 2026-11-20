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
  IRX_COMPUTE_ABI_VERSION = 2,
  IRX_COMPUTE_SCALAR = 1,
  IRX_COMPUTE_SERIES = 2,
  IRX_COMPUTE_F64 = 12,  // Arrow logical type ID, NOT legacy storage ID 10.
  IRX_COMPUTE_NO_OPTIONS = 0,
};
enum irx_compute_operation {
#define IRX_COMPUTE_OPERATION(SYMBOL, ID, NAME, ARITY, DOMAIN, RESULT, ULPS) IRX_COMPUTE_##SYMBOL = ID,
#include "irx_arrow_compute_catalog.h"
#undef IRX_COMPUTE_OPERATION
};

/* Version 2 deliberately replaces the old unary-only ABI and string-based
 * column_compute entrypoints. All dtype IDs are Arrow logical IDs (zero is
 * opaque Series storage for is_null/count only), never legacy storage IDs.
 * Queries validate the exact revision, catalog ID/arity, zero options, common
 * input type, expected result type and result shape before touching handles.
 * Reductions use Arrow's typed defaults: skip nulls, min_count=1 (count=0).
 * Boolean and/or are strict eager null propagation, not scalar short circuit.
 */
uint32_t irx_arrow_compute_abi_version(void);
int32_t irx_arrow_compute_supports(uint32_t abi, int32_t operation,
    int32_t arity, int32_t options, int32_t type, int32_t shape,
    int32_t result_type);

/* Borrowed inputs: a non-NULL column is a live opaque Series handle whose
 * physical type must match its declared operand type; bits/valid must be zero.
 * A NULL column is a scalar: bits are exact bits of its declared primitive
 * type and validity is 0/1. Analyzed conversions of either scalar or Series
 * operands to the common type use Arrow safe casts. Math
 * sqrt/exp require f64 operands without implicit casts. Arity-one calls require
 * a zero/NULL RHS descriptor. Binary Series lengths must match; scalar inputs
 * broadcast without repeated arrays. Reductions require a Series.
 * Outputs are required/distinct, cleared before any failure, and read only
 * after IRX_OK. Scalar outputs publish exact bits+validity (null => zero bits).
 * A Series result owns one independent handle, preserving order/length, not
 * chunk boundaries; input and parent owners may be released first. Failed
 * compute/cast/update never publishes a partial result or mutates inputs.
 * Integer overflow and zero division have typed statuses, no message parsing.
 * Floating division is IEEE, matching primitive scalar arithmetic. No fast
 * math, C++ layouts, standalone portable Arrow Scalar ABI or untyped kernel
 * names are exposed. Accessible pointers/live handles are C caller obligations;
 * use-after-release and concurrent handle mutation are invalid C usage.
 */
int32_t irx_arrow_compute(uint32_t abi, int32_t operation, int32_t arity,
    int32_t options, int32_t type, int32_t shape,
    int32_t lhs_type, const irx_arrow_chunked_array_handle* lhs,
    uint64_t lhs_bits, int32_t lhs_valid,
    int32_t rhs_type, const irx_arrow_chunked_array_handle* rhs,
    uint64_t rhs_bits, int32_t rhs_valid, int32_t result_type,
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
