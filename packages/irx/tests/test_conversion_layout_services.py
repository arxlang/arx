"""
title: Resolved conversion and addressing without a compiler-wide visitor.
"""

from collections.abc import Callable

import astx
import pytest

from irx.analysis.module_symbols import qualified_struct_name
from irx.analysis.numeric_policy import (
    NumericConversion,
    NumericConversionKind,
)
from irx.analysis.resolved_nodes import SemanticInfo, SemanticSymbol
from irx.builder.services.conversions import NumericEmission
from irx.builder.services.layout import LayoutEmission
from irx.builder.services.representations import TypeLowering
from llvmlite import binding as llvm
from llvmlite import ir


def scalar_type(name: str) -> ir.Type:
    """
    title: Provide only the scalar representations used by these tests.
    parameters:
      name:
        type: str
    returns:
      type: ir.Type
    """
    return {
        "int8": ir.IntType(8),
        "uint8": ir.IntType(8),
        "int32": ir.IntType(32),
        "int64": ir.IntType(64),
        "uint128": ir.IntType(128),
        "float32": ir.FloatType(),
        "float64": ir.DoubleType(),
        "boolean": ir.IntType(1),
    }[name]


def no_evaluation(node: astx.AST) -> ir.Value:
    """
    title: >-
      Prove resolved storage and namespace lookup does not evaluate syntax.
    parameters:
      node:
        type: astx.AST
    returns:
      type: ir.Value
    """
    pytest.fail(f"unexpected evaluation of {type(node).__name__}")


def no_lifetime_operation(node: astx.AST, value: ir.Value) -> None:
    """
    title: Prove scalar storage does not request a class lifetime operation.
    parameters:
      node:
        type: astx.AST
      value:
        type: ir.Value
    """
    del node, value
    pytest.fail("unexpected class lifetime operation")


def identity(value: ir.Value) -> ir.Value:
    """
    title: Supply the unused raw-class representation dependency.
    parameters:
      value:
        type: ir.Value
    returns:
      type: ir.Value
    """
    return value


def layout_service(
    module: ir.Module,
    builder: ir.IRBuilder,
    types: TypeLowering,
    storage: Callable[[str], ir.Value | None],
) -> LayoutEmission:
    """
    title: Assemble explicit storage dependencies without a visitor owner.
    parameters:
      module:
        type: ir.Module
      builder:
        type: ir.IRBuilder
      types:
        type: TypeLowering
      storage:
        type: Callable[[str], ir.Value | None]
    returns:
      type: LayoutEmission
    """
    return LayoutEmission(
        module,
        lambda: builder,
        types,
        no_evaluation,
        storage,
        lambda name, type_: builder.alloca(type_, name=name),
        no_lifetime_operation,
        no_lifetime_operation,
        identity,
    )


def test_type_and_namespace_caches_belong_to_their_llvm_module() -> None:
    """
    title: Equal semantic identities never share storage between LLVM modules.
    """
    namespaces: list[ir.GlobalVariable] = []
    representations: list[ir.Type] = []
    for width in (8, 64):
        module = ir.Module(context=ir.Context())
        pair = module.context.get_identified_type("Pair")
        pair.set_body(ir.IntType(width))
        types = TypeLowering(
            {qualified_struct_name("demo", "Pair"): pair},
            scalar_type,
            ir.LiteralStructType([]),
        )
        function = ir.Function(
            module, ir.FunctionType(ir.IntType(32), []), "main"
        )
        builder = ir.IRBuilder(function.append_basic_block("entry"))
        service = layout_service(module, builder, types, lambda key: None)
        namespace = astx.NamespaceType("demo")
        first = service.namespace_global(namespace)
        assert service.namespace_global(namespace) is first
        assert first.parent is module
        namespaces.append(first)
        representation = types.llvm_type(
            astx.StructType(
                "Pair",
                module_key="demo",
                qualified_name=qualified_struct_name("demo", "Pair"),
            )
        )
        assert representation is pair
        assert (
            types.llvm_type(astx.StructType("Pair", module_key="demo")) is None
        )
        representations.append(pair)
        builder.ret(ir.Constant(ir.IntType(32), 0))
        llvm.parse_assembly(str(module)).verify()
    assert namespaces[0] is not namespaces[1]
    assert representations[0] is not representations[1]


def test_lvalue_storage_uses_resolved_identity_not_source_spelling() -> None:
    """
    title: Address emission cannot accidentally bind a shadowed source name.
    """
    module = ir.Module()
    function = ir.Function(module, ir.FunctionType(ir.IntType(32), []), "main")
    builder = ir.IRBuilder(function.append_basic_block("entry"))
    chosen = builder.alloca(ir.IntType(32), name="chosen")
    shadow = builder.alloca(ir.IntType(32), name="shadow")
    node = astx.Identifier("shadow")
    node.semantic = SemanticInfo(
        resolved_symbol=SemanticSymbol(
            "resolved.id",
            "declared",
            astx.Int32(),
            True,
            "local",
        )
    )
    types = TypeLowering({}, scalar_type, ir.LiteralStructType([]))
    service = layout_service(
        module,
        builder,
        types,
        {"resolved.id": chosen, "shadow": shadow}.get,
    )
    assert service.lvalue_address(node) is chosen
    builder.ret(ir.Constant(ir.IntType(32), 0))
    llvm.parse_assembly(str(module)).verify()


def test_numeric_emission_consumes_a_resolved_lossless_plan() -> None:
    """
    title: >-
      A scalar conversion needs only typed representation and guard
      dependencies.
    """
    module = ir.Module()
    function = ir.Function(
        module, ir.FunctionType(ir.IntType(64), [ir.IntType(8)]), "widen"
    )
    builder = ir.IRBuilder(function.append_basic_block("entry"))
    types = TypeLowering({}, scalar_type, ir.LiteralStructType([]))
    guards: list[str] = []

    def guard(
        node: astx.AST,
        condition: ir.Value,
        *,
        code: str,
        message: str,
        block_name: str,
        exception_role: str = "RuntimeError",
    ) -> None:
        """
        title: >-
          Record checks without introducing a second runtime implementation.
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
        del node, condition, message, block_name, exception_role
        guards.append(code)

    activated: list[str] = []
    service = NumericEmission(
        module, lambda: builder, types, guard, activated.append
    )
    plan = NumericConversion(
        astx.Int8(),
        astx.Int64(),
        NumericConversionKind.LOSSLESS,
        implicit=True,
        requires_range_check=False,
    )
    node = astx.Cast(astx.LiteralInt8(1), astx.Int64())
    result = service.numeric_cast(
        node, function.args[0], plan, astx.NumericMode.CHECKED
    )
    builder.ret(result)
    assert result.opname == "sext"
    assert not guards
    assert not activated
    llvm.parse_assembly(str(module)).verify()


@pytest.mark.parametrize(
    ("source", "target", "raw", "expected"),
    [
        (astx.Int8(), astx.Int64(), 255, -1),
        (astx.UInt8(), astx.Int64(), 255, 255),
        (astx.Int8(), astx.Float64(), 255, -1.0),
        (astx.UInt8(), astx.Float64(), 255, 255.0),
        (astx.Int64(), astx.Int8(), 511, -1),
        (astx.Float32(), astx.Float64(), 1.25, 1.25),
        (astx.Float32(), astx.Float64(), 3.14, 3.140000104904175),
        (
            astx.UInt128(),
            astx.Float32(),
            2**100 + 2**76 + 1,
            float(2**100 + 2**77),
        ),
        (astx.Float64(), astx.Boolean(), float("nan"), False),
        (astx.Boolean(), astx.Int64(), True, 1),
    ],
)
def test_scalar_constants_use_semantic_signedness(
    source: astx.DataType,
    target: astx.DataType,
    raw: int | float,
    expected: int | float,
) -> None:
    """
    title: Explicit scalar representations remain constants with correct bits.
    parameters:
      source:
        type: astx.DataType
      target:
        type: astx.DataType
      raw:
        type: int | float
      expected:
        type: int | float
    """
    module = ir.Module()
    types = TypeLowering({}, scalar_type, ir.LiteralStructType([]))
    source_llvm = types.llvm_type(source)
    target_llvm = types.llvm_type(target)
    assert source_llvm is not None and target_llvm is not None

    def no_builder() -> ir.IRBuilder:
        """
        title: Constant conversion must not emit function instructions.
        returns:
          type: ir.IRBuilder
        """
        pytest.fail("constant conversion requested an instruction builder")

    def no_guard(
        node: astx.AST,
        condition: ir.Value,
        *,
        code: str,
        message: str,
        block_name: str,
        exception_role: str = "RuntimeError",
    ) -> None:
        """
        title: Representation adaptation does not choose range policy.
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
        pytest.fail("constant representation adaptation requested a guard")

    service = NumericEmission(
        module, no_builder, types, no_guard, lambda feature: None
    )
    result = service.aggregate_scalar(
        ir.Constant(source_llvm, raw), source_type=source, target_type=target
    )
    assert isinstance(result, ir.Constant)
    assert result.type == target_llvm
    assert result.constant == expected
