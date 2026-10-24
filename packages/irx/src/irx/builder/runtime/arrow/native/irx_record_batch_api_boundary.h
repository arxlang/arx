// No C++ exception may cross a generated-code or ctypes C boundary.
#ifndef IRX_RECORD_BATCH_API_BOUNDARY_H
#define IRX_RECORD_BATCH_API_BOUNDARY_H
#include "irx_record_batch_api.h"
#include <cstdio>
#include <exception>
#include <new>
#include <stdexcept>
#include <string>
namespace irx {
// Intentionally not std::exception: legacy internal catches must not erase the
// structured category while translating an Arrow failure into this record.
struct ApiError { int status; std::string message; };
inline int api_error(char* error, int status, const char* message) noexcept {
    if (error) std::snprintf(error, IRX_RB_API_ERROR_CAPACITY, "%s", message);
    return status;
}
template <class F> int api_boundary(char* error, F action) noexcept {
    if (error) error[0] = 0;
    try { action(); return IRX_OK; }
    catch (const ApiError& failure) {
        return api_error(error, failure.status, failure.message.c_str());
    } catch (const std::bad_alloc&) {
        return api_error(error, IRX_ERR_ALLOC, "Arrow allocation failed");
    } catch (const std::out_of_range& failure) {
        return api_error(error, IRX_ERR_OOB, failure.what());
    } catch (const std::invalid_argument& failure) {
        return api_error(error, IRX_ERR_INVALID, failure.what());
    } catch (const std::overflow_error& failure) {
        return api_error(error, IRX_ERR_OVERFLOW, failure.what());
    } catch (const std::exception& failure) {
        return api_error(error, IRX_ERR_ARROW, failure.what());
    } catch (...) {
        return api_error(error, IRX_ERR_ARROW, "unknown native Arrow failure");
    }
}
}
#endif
