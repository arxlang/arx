"""
title: Byte-oriented LLVM string loop emission.
summary: >-
  The compiler core owns and initializes LLVM state. Functions are cached in
  that state's module; copy loops emit into the caller-provided builder. These
  helpers never replace the core's active builder. Byte length is distinct from
  the language's Unicode string length operation.
"""

from typing import cast

from llvmlite import ir
from public import private

from irx.builder.types import VariablesLLVM
from irx.typecheck import typechecked

__all__: list[str] = []


@private
@typechecked
class StringIRMixin:
    """
    title: Emit string byte loops using existing compiler-owned LLVM state.
    summary: No constructor, callbacks, dispatch registrations, or new state.
    attributes:
      _llvm:
        type: VariablesLLVM
    """

    _llvm: VariablesLLVM

    def _generate_strcpy(
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

        index = builder.alloca(self._llvm.SIZE_T_TYPE, name="strcpy_index")
        builder.store(ir.Constant(self._llvm.SIZE_T_TYPE, 0), index)
        builder.branch(loop_bb)

        builder.position_at_start(loop_bb)
        idx_val = builder.load(index, "idx_val")
        src_char_ptr = builder.gep(src, [idx_val], inbounds=True)
        char_val = builder.load(src_char_ptr, "char_val")
        dest_char_ptr = builder.gep(dest, [idx_val], inbounds=True)
        builder.store(char_val, dest_char_ptr)

        is_null = builder.icmp_signed(
            "==", char_val, ir.Constant(self._llvm.INT8_TYPE, 0)
        )
        next_idx = builder.add(idx_val, ir.Constant(self._llvm.SIZE_T_TYPE, 1))
        builder.store(next_idx, index)
        builder.cbranch(is_null, end_bb, loop_bb)
        builder.position_at_start(end_bb)

    def _create_strcmp_inline(self) -> ir.Function:
        """
        title: Create strcmp inline.
        returns:
          type: ir.Function
        """
        func_name = "strcmp_inline"
        if func_name in self._llvm.module.globals:
            return cast(ir.Function, self._llvm.module.get_global(func_name))

        func_type = ir.FunctionType(
            self._llvm.BOOLEAN_TYPE,
            [
                self._llvm.INT8_TYPE.as_pointer(),
                self._llvm.INT8_TYPE.as_pointer(),
            ],
        )
        func = ir.Function(self._llvm.module, func_type, func_name)

        entry = func.append_basic_block("entry")
        loop = func.append_basic_block("loop")
        not_equal = func.append_basic_block("not_equal")
        equal = func.append_basic_block("equal")
        builder = ir.IRBuilder(entry)

        index = builder.alloca(self._llvm.SIZE_T_TYPE, name="index")
        builder.store(ir.Constant(self._llvm.SIZE_T_TYPE, 0), index)
        builder.branch(loop)

        builder.position_at_start(loop)
        idx_val = builder.load(index, "idx_val")
        char1_ptr = builder.gep(func.args[0], [idx_val], inbounds=True)
        char2_ptr = builder.gep(func.args[1], [idx_val], inbounds=True)
        char1 = builder.load(char1_ptr, "char1")
        char2 = builder.load(char2_ptr, "char2")
        chars_equal = builder.icmp_signed("==", char1, char2)
        char1_null = builder.icmp_signed(
            "==", char1, ir.Constant(self._llvm.INT8_TYPE, 0)
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
        next_idx = builder.add(idx_val, ir.Constant(self._llvm.SIZE_T_TYPE, 1))
        builder.store(next_idx, index)
        builder.branch(loop)

        builder.position_at_start(not_equal)
        builder.ret(ir.Constant(self._llvm.BOOLEAN_TYPE, 0))
        builder.position_at_start(equal)
        builder.ret(ir.Constant(self._llvm.BOOLEAN_TYPE, 1))
        return func

    def _create_strlen_inline(self) -> ir.Function:
        """
        title: Create strlen inline.
        returns:
          type: ir.Function
        """
        func_name = "strlen_inline"
        if func_name in self._llvm.module.globals:
            return cast(ir.Function, self._llvm.module.get_global(func_name))

        func_type = ir.FunctionType(
            self._llvm.SIZE_T_TYPE,
            [self._llvm.INT8_TYPE.as_pointer()],
        )
        func = ir.Function(self._llvm.module, func_type, func_name)

        entry = func.append_basic_block("entry")
        loop = func.append_basic_block("loop")
        end = func.append_basic_block("end")
        builder = ir.IRBuilder(entry)

        counter = builder.alloca(self._llvm.SIZE_T_TYPE, name="counter")
        builder.store(ir.Constant(self._llvm.SIZE_T_TYPE, 0), counter)
        builder.branch(loop)

        builder.position_at_start(loop)
        count_val = builder.load(counter, "count_val")
        char_ptr = builder.gep(func.args[0], [count_val], inbounds=True)
        char_val = builder.load(char_ptr, "char_val")
        is_null = builder.icmp_signed(
            "==", char_val, ir.Constant(self._llvm.INT8_TYPE, 0)
        )

        next_count = builder.add(
            count_val,
            ir.Constant(self._llvm.SIZE_T_TYPE, 1),
        )
        builder.store(next_count, counter)
        builder.cbranch(is_null, end, loop)

        builder.position_at_start(end)
        builder.ret(count_val)
        return func
