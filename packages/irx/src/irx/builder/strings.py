"""
title: Module-owned LLVM string emission with explicit runtime dependencies.
summary: >-
  Strings are NUL-terminated UTF-8 bytes. Internal byte-length helpers are not
  the language's Unicode len operation. Heap-producing operations return owned
  pointers; callers retain responsibility for registering or transferring their
  cleanup. Services and caches never cross LLVM module boundaries.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable

import astx

from llvmlite import ir
from public import private

from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.types import is_int_type
from irx.typecheck import typechecked


@private
@runtime_checkable
class RuntimeGuard(Protocol):
    """
    title: Narrow checked control-transfer dependency for emitted operations.
    """

    def __call__(
        self,
        node: astx.AST,
        condition: ir.Value,
        *,
        code: str,
        message: str,
        block_name: str,
        exception_role: str = "RuntimeError",
    ) -> None:
        """
        title: Continue only when a runtime condition is true.
        parameters:
          node:
            type: astx.AST
          condition:
            type: ir.Value
          code:
            type: str
          message:
            type: str
          block_name:
            type: str
          exception_role:
            type: str
        """
        del node, condition, code, message, block_name, exception_role
        raise NotImplementedError


@private
@typechecked
class StringEmission:
    """
    title: Intern constants and emit string operations in one LLVM module.
    summary: >-
      Builder and runtime dependencies are supplied explicitly, not recovered
      from a visitor. Internal helper functions and globals use collision-safe
      module-local identities. Each instance owns its own immutable-value
      caches.
    attributes:
      module:
        type: ir.Module
      size_type:
        type: ir.IntType
      get_builder:
        type: Callable[[], ir.IRBuilder]
      symbol:
        type: Callable[[str, str], ir.Function]
      guard:
        type: RuntimeGuard
      constants:
        type: dict[tuple[str, str], ir.GlobalVariable]
      functions:
        type: dict[str, ir.Function]
    """

    module: ir.Module
    size_type: ir.IntType
    get_builder: Callable[[], ir.IRBuilder]
    symbol: Callable[[str, str], ir.Function]
    guard: RuntimeGuard
    constants: dict[tuple[str, str], ir.GlobalVariable]
    functions: dict[str, ir.Function]

    def __init__(
        self,
        module: ir.Module,
        size_type: ir.IntType,
        builder: Callable[[], ir.IRBuilder],
        symbol: Callable[[str, str], ir.Function],
        guard: RuntimeGuard,
    ) -> None:
        """
        title: Bind one module and typed emission dependencies.
        parameters:
          module:
            type: ir.Module
          size_type:
            type: ir.IntType
          builder:
            type: Callable[[], ir.IRBuilder]
          symbol:
            type: Callable[[str, str], ir.Function]
          guard:
            type: RuntimeGuard
        """
        self.module = module
        self.size_type = size_type
        self.get_builder = builder
        self.symbol = symbol
        self.guard = guard
        self.constants: dict[tuple[str, str], ir.GlobalVariable] = {}
        self.functions: dict[str, ir.Function] = {}

    @property
    def builder(self) -> ir.IRBuilder:
        """
        title: Obtain the currently active function builder.
        returns:
          type: ir.IRBuilder
        """
        return self.get_builder()

    def constant_global(
        self, text: str, *, name_hint: str
    ) -> ir.GlobalVariable:
        """
        title: >-
          Intern exact UTF-8 bytes without relying on Python hash identity.
        parameters:
          text:
            type: str
          name_hint:
            type: str
        returns:
          type: ir.GlobalVariable
        """
        key = (name_hint, text)
        cached = self.constants.get(key)
        if cached is not None:
            return cached
        data = bytearray(text.encode("utf-8") + b"\0")
        array_type = ir.ArrayType(ir.IntType(8), len(data))
        hint = "".join(c if c.isalnum() else "_" for c in name_hint)
        name = self.module.get_unique_name(hint.strip("_") or "cstring")
        global_ = ir.GlobalVariable(self.module, array_type, name)
        global_.linkage = "internal"
        global_.global_constant = True
        global_.initializer = ir.Constant(array_type, data)
        self.constants[key] = global_
        return global_

    def constant(self, text: str, *, name_hint: str) -> ir.Value:
        """
        title: Emit a pointer to one interned, module-lifetime constant.
        parameters:
          text:
            type: str
          name_hint:
            type: str
        returns:
          type: ir.Value
        """
        return self.builder.gep(
            self.constant_global(text, name_hint=name_hint),
            [ir.Constant(ir.IntType(32), 0), ir.Constant(ir.IntType(32), 0)],
            inbounds=True,
            name=f"{name_hint}_ptr",
        )

    def format_global(self, format_: str) -> ir.GlobalVariable:
        """
        title: Intern a compiler-selected printf format string.
        parameters:
          format_:
            type: str
        returns:
          type: ir.GlobalVariable
        """
        return self.constant_global(format_, name_hint="fmt")

    def guard_allocation(
        self,
        node: astx.AST,
        pointer: ir.Value,
        *,
        message: str,
    ) -> None:
        """
        title: Require one heap allocation to return a non-null pointer.
        parameters:
          node:
            type: astx.AST
          pointer:
            type: ir.Value
          message:
            type: str
        """
        non_null = self.builder.icmp_unsigned(
            "!=",
            pointer,
            ir.Constant(pointer.type, None),
            name="string_allocation_succeeded",
        )
        self.guard(
            node,
            non_null,
            code="ARX-RUNTIME-STRING-001",
            message=message,
            block_name="string.allocation",
        )

    def byte_length_function(self) -> ir.Function:
        """
        title: Create string length function.
        returns:
          type: ir.Function
        """
        func_name = "string_length"
        if func_name in self.functions:
            return self.functions[func_name]

        func_type = ir.FunctionType(
            self.size_type,
            [ir.IntType(8).as_pointer()],
        )
        func = ir.Function(
            self.module, func_type, self.module.get_unique_name(func_name)
        )
        func.linkage = "internal"
        self.functions[func_name] = func
        block = func.append_basic_block("entry")
        builder = ir.IRBuilder(block)
        strlen_func = self.length_function()
        result = builder.call(strlen_func, [func.args[0]], "len")
        builder.ret(result)
        return func

    def equality_function(self) -> ir.Function:
        """
        title: Create string equals function.
        returns:
          type: ir.Function
        """
        func_name = "string_equals"
        if func_name in self.functions:
            return self.functions[func_name]

        func_type = ir.FunctionType(
            ir.IntType(1),
            [ir.IntType(8).as_pointer(), ir.IntType(8).as_pointer()],
        )
        func = ir.Function(
            self.module, func_type, self.module.get_unique_name(func_name)
        )
        func.linkage = "internal"
        self.functions[func_name] = func
        block = func.append_basic_block("entry")
        builder = ir.IRBuilder(block)
        strcmp_func = self.comparison_function()
        result = builder.call(strcmp_func, [func.args[0], func.args[1]], "cmp")
        builder.ret(result)
        return func

    def concatenate(
        self,
        node: astx.AST,
        lhs: ir.Value,
        rhs: ir.Value,
    ) -> ir.Value:
        """
        title: Handle string concatenation.
        parameters:
          node:
            type: astx.AST
          lhs:
            type: ir.Value
          rhs:
            type: ir.Value
        returns:
          type: ir.Value
        """
        strcat_func = self.concatenation_function()
        result = self.builder.call(strcat_func, [lhs, rhs], "str_concat")
        self.guard_allocation(
            node,
            result,
            message="string concatenation allocation failed or overflowed",
        )
        return result

    def copy(
        self,
        node: astx.AST,
        pointer: ir.Value,
    ) -> ir.Value:
        """
        title: Copy one static string into caller-owned heap storage.
        parameters:
          node:
            type: astx.AST
          pointer:
            type: ir.Value
        returns:
          type: ir.Value
        """
        empty = self.constant(
            "",
            name_hint="string_copy_empty",
        )
        return self.concatenate(node, pointer, empty)

    def concatenation_function(self) -> ir.Function:
        """
        title: Create strcat inline.
        returns:
          type: ir.Function
        """
        func_name = "strcat_inline"
        if func_name in self.functions:
            return self.functions[func_name]

        func_type = ir.FunctionType(
            ir.IntType(8).as_pointer(),
            [
                ir.IntType(8).as_pointer(),
                ir.IntType(8).as_pointer(),
            ],
        )
        func = ir.Function(
            self.module, func_type, self.module.get_unique_name(func_name)
        )
        func.linkage = "internal"
        self.functions[func_name] = func

        entry = func.append_basic_block("entry")
        builder = ir.IRBuilder(entry)
        strlen_func = self.byte_length_function()
        len1 = builder.call(strlen_func, [func.args[0]], "len1")
        len2 = builder.call(strlen_func, [func.args[1]], "len2")

        max_size = ir.Constant(self.size_type, -1)
        remaining = builder.sub(max_size, len1, "remaining_after_lhs")
        overflows = builder.icmp_unsigned(
            ">=",
            len2,
            remaining,
            "string_length_overflows",
        )
        allocate_block = func.append_basic_block("allocate")
        failure_block = func.append_basic_block("allocation_failure")
        builder.cbranch(overflows, failure_block, allocate_block)

        builder.position_at_start(failure_block)
        builder.ret(ir.Constant(ir.IntType(8).as_pointer(), None))

        builder.position_at_start(allocate_block)
        total_len = builder.add(len1, len2, "total_len")
        total_len = builder.add(
            total_len,
            ir.Constant(self.size_type, 1),
            "total_len_with_null",
        )

        malloc = self.symbol("libc", "malloc")
        result_ptr = builder.call(malloc, [total_len], "result")
        allocation_failed = builder.icmp_unsigned(
            "==",
            result_ptr,
            ir.Constant(ir.IntType(8).as_pointer(), None),
        )
        copy_block = func.append_basic_block("copy")
        builder.cbranch(allocation_failed, failure_block, copy_block)

        builder.position_at_start(copy_block)

        self.emit_copy(builder, result_ptr, func.args[0])
        result_end = builder.gep(result_ptr, [len1], inbounds=True)
        self.emit_copy(builder, result_end, func.args[1])

        builder.ret(result_ptr)
        return func

    def emit_copy(
        self,
        builder: ir.IRBuilder,
        dest: ir.Value,
        src: ir.Value,
    ) -> None:
        """
        title: Generate strcpy.
        parameters:
          builder:
            type: ir.IRBuilder
          dest:
            type: ir.Value
          src:
            type: ir.Value
        """
        loop_bb = builder.function.append_basic_block("strcpy_loop")
        end_bb = builder.function.append_basic_block("strcpy_end")

        index = builder.alloca(self.size_type, name="strcpy_index")
        builder.store(ir.Constant(self.size_type, 0), index)
        builder.branch(loop_bb)

        builder.position_at_start(loop_bb)
        idx_val = builder.load(index, "idx_val")
        src_char_ptr = builder.gep(src, [idx_val], inbounds=True)
        char_val = builder.load(src_char_ptr, "char_val")
        dest_char_ptr = builder.gep(dest, [idx_val], inbounds=True)
        builder.store(char_val, dest_char_ptr)

        is_null = builder.icmp_signed(
            "==", char_val, ir.Constant(ir.IntType(8), 0)
        )
        next_idx = builder.add(idx_val, ir.Constant(self.size_type, 1))
        builder.store(next_idx, index)
        builder.cbranch(is_null, end_bb, loop_bb)
        builder.position_at_start(end_bb)

    def comparison_function(self) -> ir.Function:
        """
        title: Create strcmp inline.
        returns:
          type: ir.Function
        """
        func_name = "strcmp_inline"
        if func_name in self.functions:
            return self.functions[func_name]

        func_type = ir.FunctionType(
            ir.IntType(1),
            [
                ir.IntType(8).as_pointer(),
                ir.IntType(8).as_pointer(),
            ],
        )
        func = ir.Function(
            self.module, func_type, self.module.get_unique_name(func_name)
        )
        func.linkage = "internal"
        self.functions[func_name] = func

        entry = func.append_basic_block("entry")
        loop = func.append_basic_block("loop")
        not_equal = func.append_basic_block("not_equal")
        equal = func.append_basic_block("equal")
        builder = ir.IRBuilder(entry)

        index = builder.alloca(self.size_type, name="index")
        builder.store(ir.Constant(self.size_type, 0), index)
        builder.branch(loop)

        builder.position_at_start(loop)
        idx_val = builder.load(index, "idx_val")
        char1_ptr = builder.gep(func.args[0], [idx_val], inbounds=True)
        char2_ptr = builder.gep(func.args[1], [idx_val], inbounds=True)
        char1 = builder.load(char1_ptr, "char1")
        char2 = builder.load(char2_ptr, "char2")
        chars_equal = builder.icmp_signed("==", char1, char2)
        char1_null = builder.icmp_signed(
            "==", char1, ir.Constant(ir.IntType(8), 0)
        )

        builder.cbranch(
            chars_equal,
            builder.function.append_basic_block("check_null"),
            not_equal,
        )
        check_null_bb = builder.function.basic_blocks[-1]
        builder.position_at_start(check_null_bb)
        builder.cbranch(
            char1_null,
            equal,
            builder.function.append_basic_block("continue_loop"),
        )
        continue_bb = builder.function.basic_blocks[-1]
        builder.position_at_start(continue_bb)
        next_idx = builder.add(idx_val, ir.Constant(self.size_type, 1))
        builder.store(next_idx, index)
        builder.branch(loop)

        builder.position_at_start(not_equal)
        builder.ret(ir.Constant(ir.IntType(1), 0))
        builder.position_at_start(equal)
        builder.ret(ir.Constant(ir.IntType(1), 1))
        return func

    def length_function(self) -> ir.Function:
        """
        title: Create strlen inline.
        returns:
          type: ir.Function
        """
        func_name = "strlen_inline"
        if func_name in self.functions:
            return self.functions[func_name]

        func_type = ir.FunctionType(
            self.size_type,
            [ir.IntType(8).as_pointer()],
        )
        func = ir.Function(
            self.module, func_type, self.module.get_unique_name(func_name)
        )
        func.linkage = "internal"
        self.functions[func_name] = func

        entry = func.append_basic_block("entry")
        loop = func.append_basic_block("loop")
        end = func.append_basic_block("end")
        builder = ir.IRBuilder(entry)

        counter = builder.alloca(self.size_type, name="counter")
        builder.store(ir.Constant(self.size_type, 0), counter)
        builder.branch(loop)

        builder.position_at_start(loop)
        count_val = builder.load(counter, "count_val")
        char_ptr = builder.gep(func.args[0], [count_val], inbounds=True)
        char_val = builder.load(char_ptr, "char_val")
        is_null = builder.icmp_signed(
            "==", char_val, ir.Constant(ir.IntType(8), 0)
        )

        next_count = builder.add(
            count_val,
            ir.Constant(self.size_type, 1),
        )
        builder.store(next_count, counter)
        builder.cbranch(is_null, end, loop)

        builder.position_at_start(end)
        builder.ret(count_val)
        return func

    def compare(
        self,
        lhs: ir.Value,
        rhs: ir.Value,
        op: str,
    ) -> ir.Value:
        """
        title: Handle string comparison.
        parameters:
          lhs:
            type: ir.Value
          rhs:
            type: ir.Value
          op:
            type: str
        returns:
          type: ir.Value
        """
        if op == "==":
            equals_func = self.equality_function()
            return self.builder.call(equals_func, [lhs, rhs], "str_equals")
        if op == "!=":
            equals_func = self.equality_function()
            equals_result = self.builder.call(
                equals_func, [lhs, rhs], "str_equals"
            )
            return self.builder.xor(
                equals_result,
                ir.Constant(ir.IntType(1), 1),
                "str_not_equals",
            )
        raise_lowering_internal_error(
            f"String comparison operator {op} not implemented"
        )

    def integer_format(
        self,
        value: ir.Value,
        *,
        unsigned: bool = False,
    ) -> tuple[ir.Value, str]:
        """
        title: Normalize int for printf.
        parameters:
          value:
            type: ir.Value
          unsigned:
            type: bool
        returns:
          type: tuple[ir.Value, str]
        """
        int64_width = 64
        if not is_int_type(value.type):
            raise_lowering_internal_error("Expected integer value")
        width = value.type.width
        if width < int64_width:
            if width == 1 or unsigned:
                arg = self.builder.zext(value, ir.IntType(64))
                return arg, "%llu"
            arg = self.builder.sext(value, ir.IntType(64))
            return arg, "%lld"
        if width == int64_width:
            if unsigned:
                return value, "%llu"
            return value, "%lld"
        raise_lowering_internal_error(
            "Casting integers wider than 64 bits to string is not supported"
        )

    def format_heap(
        self,
        node: astx.AST,
        fmt_gv: ir.GlobalVariable,
        args: list[ir.Value],
    ) -> ir.Value:
        """
        title: Snprintf heap.
        parameters:
          node:
            type: astx.AST
          fmt_gv:
            type: ir.GlobalVariable
          args:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        snprintf = self.symbol("libc", "snprintf")
        malloc = self.symbol("libc", "malloc")

        zero_size = ir.Constant(self.size_type, 0)
        null_ptr = ir.Constant(ir.IntType(8).as_pointer(), None)
        fmt_ptr = self.builder.gep(
            fmt_gv,
            [
                ir.Constant(ir.IntType(32), 0),
                ir.Constant(ir.IntType(32), 0),
            ],
            inbounds=True,
        )

        needed_i32 = self.builder.call(
            snprintf, [null_ptr, zero_size, fmt_ptr, *args]
        )

        zero_i32 = ir.Constant(ir.IntType(32), 0)
        format_succeeded = self.builder.icmp_signed(
            ">=",
            needed_i32,
            zero_i32,
            name="string_format_size_succeeded",
        )
        self.guard(
            node,
            format_succeeded,
            code="ARX-RUNTIME-STRING-002",
            message="string formatting size query failed",
            block_name="string.format.size",
        )
        needed_size = self.builder.zext(
            needed_i32,
            self.size_type,
        )
        need_szt = self.builder.add(
            needed_size,
            ir.Constant(self.size_type, 1),
            name="string_format_allocation_size",
        )
        mem = self.builder.call(malloc, [need_szt])
        self.guard_allocation(
            node,
            mem,
            message="string formatting allocation failed",
        )
        written = self.builder.call(
            snprintf,
            [mem, need_szt, fmt_ptr, *args],
        )
        write_succeeded = self.builder.icmp_signed(
            ">=",
            written,
            zero_i32,
            name="string_format_write_succeeded",
        )
        # The caller cannot register ownership until this method returns.
        # Release the allocation before the checked failure path transfers out.
        write_failed = self.builder.not_(write_succeeded)
        with self.builder.if_then(write_failed):
            self.builder.call(self.symbol("libc", "free"), [mem])
        self.guard(
            node,
            write_succeeded,
            code="ARX-RUNTIME-STRING-002",
            message="string formatting write failed",
            block_name="string.format.write",
        )
        return mem
