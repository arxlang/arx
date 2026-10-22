// Copyright IRx contributors.
#ifndef IRX_PARQUET_OPTIONS_H
#define IRX_PARQUET_OPTIONS_H
#include <cstdint>
#include <optional>
#include <string>
#include <vector>
#include <arrow/util/secure_string.h>

struct IrxParquetPredicate {
    std::string column, operation, value, type;
};
// Copied at open; changing or destroying options cannot alter an active session.
struct IrxParquetOptions {
    int64_t batch_size{65536}, row_group_size{1048576}, data_page_size{1048576};
    std::optional<int> compression_level;
    bool use_threads{false}, pre_buffer{false}, dataset{false}, hive{false};
    bool unify{false}, normalize{false}, atomic{false}, append{false};
    bool durable{false};
    bool reconstruct{false};
    std::string compression{"snappy"};
    std::vector<std::string> columns, partition_columns;
    std::vector<int> row_groups;
    std::vector<IrxParquetPredicate> predicates;
    // SecureString erases its owned key on destruction; keys never enter errors.
    arrow::util::SecureString key;
};
#endif
