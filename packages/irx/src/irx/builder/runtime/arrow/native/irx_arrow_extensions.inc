// Extension values retain their logical identity; opaque codecs expose storage
// only. Domain-specific computation is intentionally not inferred from a name.
extern "C++" {
#include <arrow/extension/parquet_variant.h>
#include <arrow/extension_type.h>
namespace {
class OpaqueStorageExtension final : public arrow::ExtensionType {
public:
  OpaqueStorageExtension(std::shared_ptr<arrow::DataType> storage,
                         std::string name, std::string metadata)
      : ExtensionType(std::move(storage)), name_(std::move(name)),
        metadata_(std::move(metadata)) {}
  std::string extension_name() const override { return name_; }
  std::string Serialize() const override { return metadata_; }
  bool ExtensionEquals(const arrow::ExtensionType &other) const override {
    return name_ == other.extension_name() && metadata_ == other.Serialize() &&
           storage_type()->Equals(other.storage_type(), true);
  }
  std::shared_ptr<arrow::Array>
  MakeArray(std::shared_ptr<arrow::ArrayData> data) const override {
    return std::make_shared<arrow::ExtensionArray>(std::move(data));
  }
  arrow::Result<std::shared_ptr<arrow::DataType>>
  Deserialize(std::shared_ptr<arrow::DataType> storage,
              const std::string &metadata) const override {
    return std::make_shared<OpaqueStorageExtension>(std::move(storage), name_,
                                                    metadata);
  }

private:
  std::string name_;
  std::string metadata_;
};

arrow::Status register_storage_extensions(const ArrowSchema *schema) {
  // Copy validates the tree/depth first. Imports consume only these copies.
  ARROW_ASSIGN_OR_RAISE(auto borrowed, borrow_schema_tree(schema));
  for (int64_t i = 0; i < borrowed->schema.n_children; ++i)
    ARROW_RETURN_NOT_OK(
        register_storage_extensions(borrowed->schema.children[i]));
  if (borrowed->schema.dictionary)
    ARROW_RETURN_NOT_OK(
        register_storage_extensions(borrowed->schema.dictionary));
  ARROW_ASSIGN_OR_RAISE(auto field, arrow::ImportField(&borrowed->schema));
  if (!field->metadata() ||
      !field->metadata()->Contains(arrow::kExtensionTypeKeyName))
    return arrow::Status::OK();
  ARROW_ASSIGN_OR_RAISE(auto name,
                        field->metadata()->Get(arrow::kExtensionTypeKeyName));
  if (name.empty())
    return arrow::Status::Invalid("empty extension name");
  if (arrow::GetExtensionType(name))
    return arrow::Status::OK();
  std::shared_ptr<arrow::ExtensionType> prototype;
  if (name == "arrow.parquet.variant") {
    prototype = std::make_shared<arrow::extension::VariantExtensionType>(
        arrow::struct_({arrow::field("metadata", arrow::binary(), false),
                        arrow::field("value", arrow::binary(), false)}));
  } else {
    if (name.rfind("arrow.", 0) == 0)
      return arrow::Status::NotImplemented("unregistered canonical extension: ",
                                           name);
    prototype =
        std::make_shared<OpaqueStorageExtension>(arrow::null(), name, "");
  }
  auto registered = arrow::RegisterExtensionType(std::move(prototype));
  // Concurrent registration is safe: the subsequent import uses the winner's
  // Deserialize validation, never an erased or guessed storage layout.
  return !registered.ok() && !arrow::GetExtensionType(name)
             ? registered
             : arrow::Status::OK();
}
} // namespace
} // extern C++
