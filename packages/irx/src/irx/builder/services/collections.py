"""
title: >-
  Raw constant-collection emission with explicit representation dependencies.
summary: >-
  These existing low-level primitives preserve literal set identity and exact
  dictionary key storage. Source legality and result typing remain analysis
  responsibilities. The service never discovers symbols or resolves a source
  operation. Dictionary comparison storage and conversions come from an
  immutable analysis fact; raw set operations retain explicit fixture storage.
"""

from collections.abc import Callable

from llvmlite import ir
from public import private

from irx.analysis.extensions.literals import DictionaryLookup
from irx.builder.services.conversions import NumericEmission
from irx.builder.services.values import ValueEmission
from irx.builder.types import is_fp_type
from irx.typecheck import typechecked


@private
@typechecked
class CollectionEmission:
    """
    title: Module-owned literal identity and raw dictionary lookup emission.
    attributes:
      values:
        type: ValueEmission
      numeric:
        type: NumericEmission
      symbol:
        type: Callable[[str, str], ir.Function]
      set_values:
        type: dict[int, ir.Value]
    """

    values: ValueEmission
    numeric: NumericEmission
    symbol: Callable[[str, str], ir.Function]
    set_values: dict[int, ir.Value]

    def __init__(
        self,
        values: ValueEmission,
        numeric: NumericEmission,
        symbol: Callable[[str, str], ir.Function],
    ) -> None:
        """
        title: Bind representation operations without a compiler owner.
        parameters:
          values:
            type: ValueEmission
          numeric:
            type: NumericEmission
          symbol:
            type: Callable[[str, str], ir.Function]
        """
        self.values = values
        self.numeric = numeric
        self.symbol = symbol
        self.set_values = {}

    def mark_set_value(self, value: ir.Value) -> ir.Value:
        """
        title: Mark set value.
        parameters:
          value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        self.set_values[id(value)] = value
        return value

    def is_set_value(self, value: ir.Value | None) -> bool:
        """
        title: Is set value.
        parameters:
          value:
            type: ir.Value | None
        returns:
          type: bool
        """
        if value is None:
            return False
        return self.set_values.get(id(value)) is value

    def try_set_binary_op(
        self,
        lhs: ir.Value | None,
        rhs: ir.Value | None,
        op_code: str,
    ) -> bool:
        """
        title: Try set binary op.
        parameters:
          lhs:
            type: ir.Value | None
          rhs:
            type: ir.Value | None
          op_code:
            type: str
        returns:
          type: bool
        """
        if op_code not in ("|", "&", "-", "^"):
            return False

        if not (self.is_set_value(lhs) and self.is_set_value(rhs)):
            return False

        if not (
            isinstance(lhs, ir.Constant)
            and isinstance(lhs.type, ir.ArrayType)
            and isinstance(lhs.type.element, ir.IntType)
            and isinstance(rhs, ir.Constant)
            and isinstance(rhs.type, ir.ArrayType)
            and isinstance(rhs.type.element, ir.IntType)
        ):
            return False

        lhs_values: set[int] = {element.constant for element in lhs.constant}
        rhs_values: set[int] = {element.constant for element in rhs.constant}

        if op_code == "|":
            result_vals = lhs_values | rhs_values
        elif op_code == "&":
            result_vals = lhs_values & rhs_values
        elif op_code == "-":
            result_vals = lhs_values - rhs_values
        else:
            result_vals = lhs_values ^ rhs_values

        widest = max(lhs.type.element.width, rhs.type.element.width)
        elem_ty = ir.IntType(widest)
        consts = [ir.Constant(elem_ty, value) for value in sorted(result_vals)]
        arr_ty = ir.ArrayType(elem_ty, len(consts))
        self.values.publish(self.mark_set_value(ir.Constant(arr_ty, consts)))
        return True

    def constant_subscript_key_matches(
        self,
        entry_key: ir.Constant,
        key_val: ir.Constant,
        plan: DictionaryLookup,
    ) -> bool:
        """
        title: Constant subscript key matches.
        parameters:
          entry_key:
            type: ir.Constant
          key_val:
            type: ir.Constant
          plan:
            type: DictionaryLookup
        returns:
          type: bool
        """
        lhs = self.numeric.aggregate_scalar(
            entry_key,
            source_type=plan.key_conversion.source_type,
            target_type=plan.comparison_type,
        )
        rhs = self.numeric.aggregate_scalar(
            key_val,
            source_type=plan.index_conversion.source_type,
            target_type=plan.comparison_type,
        )
        if not isinstance(lhs, ir.Constant) or not isinstance(
            rhs, ir.Constant
        ):
            raise TypeError(
                "constant dictionary comparison lost constant storage"
            )
        return bool(lhs.constant == rhs.constant)

    def emit_subscript_miss(self) -> None:
        """
        title: Emit subscript miss.
        """
        builder = self.values.builder()
        exit_fn = self.symbol("libc", "exit")
        builder.call(exit_fn, [ir.Constant(ir.IntType(32), 1)])
        builder.unreachable()

    def emit_runtime_subscript_lookup(
        self,
        dict_val: ir.Constant,
        key_val: ir.Value,
        plan: DictionaryLookup,
    ) -> None:
        """
        title: Emit runtime subscript lookup.
        parameters:
          dict_val:
            type: ir.Constant
          key_val:
            type: ir.Value
          plan:
            type: DictionaryLookup
        """
        key_val = self.numeric.aggregate_scalar(
            key_val,
            source_type=plan.index_conversion.source_type,
            target_type=plan.comparison_type,
        )

        if isinstance(key_val.type, ir.IntType):
            self.emit_integer_subscript_switch(dict_val, key_val, plan)
            return

        if is_fp_type(key_val.type):
            self.emit_float_subscript_select(dict_val, key_val, plan)
            return

        raise TypeError(
            "SubscriptExpr: runtime lookup supports only integer and "
            "floating-point dict keys"
        )

    def emit_integer_subscript_switch(
        self,
        dict_val: ir.Constant,
        key_val: ir.Value,
        plan: DictionaryLookup,
    ) -> None:
        """
        title: Emit integer subscript switch.
        parameters:
          dict_val:
            type: ir.Constant
          key_val:
            type: ir.Value
          plan:
            type: DictionaryLookup
        """
        builder = self.values.builder()
        function = builder.function
        count = dict_val.type.count
        val_type = dict_val.type.element.elements[1]

        miss_bb = function.append_basic_block("dict.miss")
        merge_bb = function.append_basic_block("dict.merge")

        case_blocks: list[tuple[ir.Constant, ir.Block]] = []
        for index in range(count):
            entry_key = dict_val.constant[index].constant[0]
            case_key = self.numeric.aggregate_scalar(
                entry_key,
                source_type=plan.key_conversion.source_type,
                target_type=plan.comparison_type,
            )
            case_bb = function.append_basic_block(f"dict.case.{index}")
            if not isinstance(case_key, ir.Constant):
                raise TypeError(
                    "integer dictionary case requires a constant key"
                )
            case_blocks.append((case_key, case_bb))

        switch = builder.switch(key_val, miss_bb)
        for case_key, case_bb in case_blocks:
            switch.add_case(case_key, case_bb)

        with builder.goto_block(miss_bb):
            self.emit_subscript_miss()

        for _, case_bb in case_blocks:
            with builder.goto_block(case_bb):
                builder.branch(merge_bb)

        builder.position_at_end(merge_bb)

        phi = builder.phi(val_type, name="dict.result")
        for index, (_, case_bb) in enumerate(case_blocks):
            entry_val = dict_val.constant[index].constant[1]
            phi.add_incoming(entry_val, case_bb)

        self.values.publish(phi)

    def emit_float_subscript_select(
        self,
        dict_val: ir.Constant,
        key_val: ir.Value,
        plan: DictionaryLookup,
    ) -> None:
        """
        title: Emit float subscript select.
        parameters:
          dict_val:
            type: ir.Constant
          key_val:
            type: ir.Value
          plan:
            type: DictionaryLookup
        """
        builder = self.values.builder()
        count = dict_val.type.count

        zero = ir.Constant(ir.IntType(32), 0)
        key_field = ir.Constant(ir.IntType(32), 0)
        val_field = ir.Constant(ir.IntType(32), 1)

        current_bb = builder.block
        builder.position_at_start(builder.function.entry_basic_block)
        arr_alloca = builder.alloca(dict_val.type, name="dict_arr")
        builder.position_at_end(current_bb)
        builder.store(dict_val, arr_alloca)

        last_idx = ir.Constant(ir.IntType(32), count - 1)
        last_key_ptr = builder.gep(
            arr_alloca, [zero, last_idx, key_field], inbounds=True
        )
        last_key = builder.load(last_key_ptr, name=f"k_{count - 1}")
        last_key = self.numeric.aggregate_scalar(
            last_key,
            source_type=plan.key_conversion.source_type,
            target_type=plan.comparison_type,
        )
        matched = builder.fcmp_ordered(
            "==", last_key, key_val, name=f"cmp_{count - 1}"
        )

        last_val_ptr = builder.gep(
            arr_alloca, [zero, last_idx, val_field], inbounds=True
        )
        result: ir.Value = builder.load(last_val_ptr, name=f"v_{count - 1}")

        for index in reversed(range(count - 1)):
            idx = ir.Constant(ir.IntType(32), index)
            key_ptr = builder.gep(
                arr_alloca, [zero, idx, key_field], inbounds=True
            )
            key_i = builder.load(key_ptr, name=f"k_{index}")
            key_i = self.numeric.aggregate_scalar(
                key_i,
                source_type=plan.key_conversion.source_type,
                target_type=plan.comparison_type,
            )
            cmp = builder.fcmp_ordered(
                "==", key_i, key_val, name=f"cmp_{index}"
            )
            val_ptr = builder.gep(
                arr_alloca, [zero, idx, val_field], inbounds=True
            )
            val_i = builder.load(val_ptr, name=f"v_{index}")
            result = builder.select(cmp, val_i, result, name=f"sel_{index}")
            matched = builder.or_(cmp, matched, name=f"match_{index}")

        found_bb = builder.function.append_basic_block("dict.found")
        miss_bb = builder.function.append_basic_block("dict.miss")
        builder.cbranch(matched, found_bb, miss_bb)

        with builder.goto_block(miss_bb):
            self.emit_subscript_miss()

        builder.position_at_end(found_bb)
        self.values.publish(result)
