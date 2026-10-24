// Shared structured native error categories; messages never select a type.
#ifndef IRX_NATIVE_STATUS_H
#define IRX_NATIVE_STATUS_H
#define IRX_OK       0
#define IRX_EOF      1   /* non-error: reader has no more batches */
#define IRX_ERR_ARROW   -1
#define IRX_ERR_NULLPTR -2
#define IRX_ERR_OOB     -3  /* column / row index out of bounds */
#define IRX_ERR_TYPE    -4  /* type mismatch */
#define IRX_ERR_IO      -5
#define IRX_ERR_INVALID -6
#define IRX_ERR_ALLOC -7
#define IRX_ERR_OVERFLOW -8
#endif
