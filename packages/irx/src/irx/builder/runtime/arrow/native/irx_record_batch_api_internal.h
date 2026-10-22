// Copyright IRx contributors.
#ifndef IRX_RECORD_BATCH_API_INTERNAL_H
#define IRX_RECORD_BATCH_API_INTERNAL_H
#include "irx_record_batch_api.h"
namespace irx {
const IrxRbSchema *api_schema_value(IrxRbApiSchema *);
using ReaderFactory = int (*)(const char *, const IrxRbSchema *, const IrxParquetOptions *, IrxRbStreamReader **);
using WriterFactory = int (*)(const IrxRbSchema *, const char *, const IrxParquetOptions *, IrxRbStreamWriter **);
void api_open_read(IrxRbApiParquet *, const char *, IrxRbApiSchema *, const IrxParquetOptions *, ReaderFactory);
void api_open_write(IrxRbApiParquet *, const char *, IrxRbApiSchema *, const IrxParquetOptions *, WriterFactory);
}
#endif
