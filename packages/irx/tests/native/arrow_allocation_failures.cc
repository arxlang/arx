// Copyright IRx contributors.
// Standalone so C++ allocation interposition cannot destabilize Python.
#include <arrow/api.h>
#include <arrow/c/bridge.h>

#include <cstdio>
#include <cstdlib>
#include <new>

#include "irx_arrow_abi_generated.h"

static thread_local int allocations_before_failure = -1;
static thread_local bool injected = false;

void* operator new(std::size_t size) {
  if (allocations_before_failure >= 0 && allocations_before_failure-- == 0) {
    injected = true;
    throw std::bad_alloc();
  }
  if (void* result = std::malloc(size == 0 ? 1 : size)) return result;
  throw std::bad_alloc();
}
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* pointer) noexcept { std::free(pointer); }
void operator delete[](void* pointer) noexcept { std::free(pointer); }
void operator delete(void* pointer, std::size_t) noexcept {
  std::free(pointer);
}
void operator delete[](void* pointer, std::size_t) noexcept {
  std::free(pointer);
}

#define CHECK(condition)                                           \
  do {                                                             \
    if (!(condition)) {                                            \
      std::fprintf(stderr, "line %d: %s\n", __LINE__, #condition); \
      return false;                                                \
    }                                                              \
  } while (false)
#define OK(call) CHECK((call) == IRX_ARROW_STATUS_OK)

static bool release_error(irx_arrow_error_handle** error) {
  irx_arrow_error_handle* release_failure = nullptr;
  OK(irx_arrow_error_release(error, &release_failure));
  CHECK(release_failure == nullptr);
  return true;
}

static bool check_array(irx_arrow_array_handle* array) {
  irx_arrow_error_handle* error = nullptr;
  ArrowArray exported{};
  ArrowSchema schema{};
  OK(irx_arrow_array_export(array, &exported, &schema, &error));
  auto imported = arrow::ImportArray(&exported, &schema);
  CHECK(imported.ok());
  auto values = std::static_pointer_cast<arrow::Int64Array>(*imported);
  CHECK(values->length() == 3);
  CHECK(values->Value(0) == 17 && values->IsNull(1) && values->Value(2) == 29);
  return true;
}

static bool sweep_array_finish() {
  constexpr int kLimit = 128;
  const int64_t baseline = arrow::default_memory_pool()->bytes_allocated();
  for (int index = 0; index < kLimit; ++index) {
    irx_arrow_error_handle* error = nullptr;
    irx_arrow_array_builder_handle* builder = nullptr;
    irx_arrow_array_handle* array = nullptr;
    OK(irx_arrow_array_builder_new(IRX_ARROW_TYPE_INT64, &builder, &error));
    OK(irx_arrow_array_builder_append_int(builder, 17, &error));
    OK(irx_arrow_array_builder_append_null(builder, 1, &error));
    OK(irx_arrow_array_builder_append_int(builder, 29, &error));
    auto* original = builder;
    injected = false;
    allocations_before_failure = index;
    const auto status =
        irx_arrow_array_builder_finish(&builder, &array, &error);
    allocations_before_failure = -1;
    const bool failed = injected;
    if (failed) {
      CHECK(status == IRX_ARROW_STATUS_OUT_OF_MEMORY);
      CHECK(builder == original && array == nullptr);
      CHECK(release_error(&error));
      OK(irx_arrow_array_builder_finish(&builder, &array, &error));
    } else {
      CHECK(status == IRX_ARROW_STATUS_OK);
    }
    CHECK(builder == nullptr && check_array(array));
    OK(irx_arrow_array_release(&array, &error));
    CHECK(arrow::default_memory_pool()->bytes_allocated() == baseline);
    if (!failed) {
      CHECK(index > 2);  // Includes allocations after both snapshot buffers.
      std::printf("array finish: %d allocation failures retried\n", index);
      return true;
    }
  }
  CHECK(false);  // Fail closed if the sweep's explicit bound was insufficient.
}

static bool sweep_tensor_finish() {
  constexpr int kLimit = 128;
  const int64_t baseline = arrow::default_memory_pool()->bytes_allocated();
  for (int index = 0; index < kLimit; ++index) {
    irx_arrow_error_handle* error = nullptr;
    irx_arrow_tensor_builder_handle* builder = nullptr;
    irx_arrow_tensor_handle* tensor = nullptr;
    const int64_t shape[] = {2};
    OK(irx_arrow_tensor_builder_new(IRX_ARROW_TYPE_INT64, 1, shape, nullptr,
                                    &builder, &error));
    OK(irx_arrow_tensor_builder_append_int(builder, 17, &error));
    OK(irx_arrow_tensor_builder_append_int(builder, 29, &error));
    auto* original = builder;
    injected = false;
    allocations_before_failure = index;
    const auto status =
        irx_arrow_tensor_builder_finish(&builder, &tensor, &error);
    allocations_before_failure = -1;
    const bool failed = injected;
    if (failed) {
      CHECK(status == IRX_ARROW_STATUS_OUT_OF_MEMORY);
      CHECK(builder == original && tensor == nullptr);
      CHECK(release_error(&error));
      OK(irx_arrow_tensor_builder_finish(&builder, &tensor, &error));
    } else {
      CHECK(status == IRX_ARROW_STATUS_OK);
    }
    CHECK(builder == nullptr);
    irx_buffer_view view{};
    OK(irx_arrow_tensor_borrow_buffer_view(tensor, &view, &error));
    auto* data = static_cast<const int64_t*>(view.data);
    CHECK(data[0] == 17 && data[1] == 29);
    OK(irx_arrow_tensor_release(&tensor, &error));
    CHECK(arrow::default_memory_pool()->bytes_allocated() == baseline);
    if (!failed) {
      CHECK(index > 2);  // Includes Tensor::Make and shape/stride cache copies.
      std::printf("tensor finish: %d allocation failures retried\n", index);
      return true;
    }
  }
  CHECK(false);
}

static void release_descriptor_source(ArrowSchema* schema) {
  schema->release = nullptr;
}

template <typename Handle, typename Import, typename Export, typename Release>
static bool sweep_descriptor_import(Import import, Export export_value,
                                    Release release) {
  ArrowSchema child{};
  child.format = "l";
  child.name = "value";
  child.flags = 2;
  child.release = release_descriptor_source;
  ArrowSchema* children[] = {&child};
  ArrowSchema source{};
  source.format = "+s";
  source.name = "descriptor";
  source.n_children = 1;
  source.children = children;
  source.release = release_descriptor_source;
  constexpr int kLimit = 128;
  for (int index = 0; index < kLimit; ++index) {
    Handle* owner = nullptr;
    irx_arrow_error_handle* error = nullptr;
    injected = false;
    allocations_before_failure = index;
    const auto status = import(&source, &owner, &error);
    allocations_before_failure = -1;
    const bool failed = injected;
    CHECK(source.release == release_descriptor_source);
    CHECK(child.release == release_descriptor_source);
    if (failed) {
      CHECK(status == IRX_ARROW_STATUS_OUT_OF_MEMORY);
      CHECK(owner == nullptr);
      CHECK(release_error(&error));
      OK(import(&source, &owner, &error));
    } else {
      CHECK(status == IRX_ARROW_STATUS_OK);
    }
    ArrowSchema output{};
    OK(export_value(owner, &output, &error));
    OK(release(&owner, &error));
    CHECK(output.release && output.n_children == 1);
    CHECK(output.children[0]->flags & 2);
    output.release(&output);
    if (!failed) {
      CHECK(index > 2);
      std::printf("descriptor import: %d allocation failures retried\n", index);
      return true;
    }
  }
  CHECK(false);
}

int main() {
  return sweep_array_finish() && sweep_tensor_finish() &&
                 sweep_descriptor_import<irx_arrow_type_handle>(
                     irx_arrow_type_import_copy, irx_arrow_type_export,
                     irx_arrow_type_release) &&
                 sweep_descriptor_import<irx_arrow_field_handle>(
                     irx_arrow_field_import_copy, irx_arrow_field_export,
                     irx_arrow_field_release)
             ? 0
             : 1;
}
