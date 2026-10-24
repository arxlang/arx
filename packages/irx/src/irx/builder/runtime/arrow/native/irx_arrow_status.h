#ifndef IRX_ARROW_STATUS_H
#define IRX_ARROW_STATUS_H
#include "irx_native_status.h"
#include <arrow/status.h>
#include <new>
#include <stdexcept>
namespace irx {
inline int native_exception_status(const std::exception& error) {
    if (dynamic_cast<const std::bad_alloc*>(&error)) return IRX_ERR_ALLOC;
    if (dynamic_cast<const std::out_of_range*>(&error)) return IRX_ERR_OOB;
    if (dynamic_cast<const std::invalid_argument*>(&error)) return IRX_ERR_INVALID;
    if (dynamic_cast<const std::overflow_error*>(&error)) return IRX_ERR_OVERFLOW;
    return IRX_ERR_ARROW;
}
inline int record_batch_status(const arrow::Status &status) {
    if (status.IsOutOfMemory()) return IRX_ERR_ALLOC;
    if (status.IsCapacityError()) return IRX_ERR_OVERFLOW;
    if (status.IsIndexError()) return IRX_ERR_OOB;
    if (status.IsTypeError()) return IRX_ERR_TYPE;
    if (status.IsIOError()) return IRX_ERR_IO;
    if (status.IsInvalid()) return IRX_ERR_INVALID;
    return IRX_ERR_ARROW;
}
}
#endif
