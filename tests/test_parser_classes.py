"""
title: Tests for annotation-based class parsing.
"""

from textwrap import dedent

import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx import astx


def _parse_module(code: str) -> astx.Module:
    """
    title: Parse one snippet into an AST module.
    parameters:
      code:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(code)
    return Parser().parse(Lexer().lex())


def test_parse_complex_class_module_with_irx_class_nodes() -> None:
    """
    title: Parse complex class syntax directly into IRx-owned nodes.
    """
    tree = _parse_module(
        dedent(
            """
            @[public, abstract]
            class Shape:
              @[public, abstract]
              fn area(self) -> int32

            class BaseCounter:
              @[public, mutable]
              value: int32 = 41

              @[protected]
              fn read_seed(self) -> int32:
                return self.value

            class Counter(BaseCounter):
              @[public, static, constant]
              version: int32 = 3

              @[private, mutable]
              internal: int32 = 5

              @[protected]
              fn internal_total(self) -> int32:
                return self.internal + self.value

              @[public]
              fn get(self) -> int32:
                return self.value

              @[public]
              fn read_internal(self) -> int32:
                return self.internal_total()

            class CounterFactory:
              @[public, static]
              fn make() -> Counter:
                return Counter()

              @[public, static]
              fn version_value() -> int32:
                return Counter.version

            fn take_counter(counter: Counter) -> int32:
              return counter.get() + counter.value + counter.read_internal()

            fn main() -> int32:
              var direct: Counter = Counter()
              var built: Counter = CounterFactory.make()
              var total: int32 = take_counter(direct) + built.get()
              return total + CounterFactory.version_value() + Counter.version
            """
        ).lstrip()
    )

    assert len(tree.nodes) == 6

    shape = tree.nodes[0]
    assert isinstance(shape, astx.ClassDefStmt)
    assert shape.name == "Shape"
    assert shape.visibility is astx.VisibilityKind.public
    assert getattr(shape, "explicit_visibility") is (
        astx.VisibilityKind.public
    )
    assert getattr(shape, "is_abstract", False) is True
    area = shape.methods.nodes[0]
    assert isinstance(area, astx.FunctionDef)
    assert area.prototype.name == "area"
    assert area.prototype.args.nodes == []
    assert isinstance(area.prototype.return_type, astx.Int32)
    assert getattr(area.prototype, "is_abstract", False) is True
    assert area.body.nodes == []

    base_counter = tree.nodes[1]
    assert isinstance(base_counter, astx.ClassDefStmt)
    assert base_counter.name == "BaseCounter"
    assert [base.name for base in base_counter.bases.nodes] == []
    assert [field.name for field in base_counter.attributes.nodes] == ["value"]
    value = base_counter.attributes.nodes[0]
    assert value.visibility is astx.VisibilityKind.public
    assert value.mutability is astx.MutabilityKind.mutable
    assert getattr(value, "explicit_visibility") is (
        astx.VisibilityKind.public
    )
    assert getattr(value, "explicit_mutability") is (
        astx.MutabilityKind.mutable
    )
    assert not getattr(value, "is_static", False)
    read_seed = base_counter.methods.nodes[0]
    assert isinstance(read_seed, astx.FunctionDef)
    assert read_seed.prototype.visibility is astx.VisibilityKind.protected
    seed_return = read_seed.body.nodes[0]
    assert isinstance(seed_return, astx.FunctionReturn)
    assert isinstance(seed_return.value, astx.FieldAccess)
    assert isinstance(seed_return.value.value, astx.Identifier)
    assert seed_return.value.value.name == "self"
    assert seed_return.value.field_name == "value"

    counter = tree.nodes[2]
    assert isinstance(counter, astx.ClassDefStmt)
    assert counter.name == "Counter"
    assert [base.name for base in counter.bases.nodes] == ["BaseCounter"]
    assert [field.name for field in counter.attributes.nodes] == [
        "version",
        "internal",
    ]
    assert [method.name for method in counter.methods.nodes] == [
        "internal_total",
        "get",
        "read_internal",
    ]

    version = counter.attributes.nodes[0]
    assert version.visibility is astx.VisibilityKind.public
    assert version.mutability is astx.MutabilityKind.constant
    assert getattr(version, "explicit_visibility") is (
        astx.VisibilityKind.public
    )
    assert getattr(version, "explicit_mutability") is (
        astx.MutabilityKind.constant
    )
    assert getattr(version, "is_static", False) is True
    assert isinstance(version.type_, astx.Int32)
    assert isinstance(version.value, astx.LiteralInt32)

    internal = counter.attributes.nodes[1]
    assert internal.visibility is astx.VisibilityKind.private
    assert internal.mutability is astx.MutabilityKind.mutable
    assert getattr(internal, "explicit_visibility") is (
        astx.VisibilityKind.private
    )
    assert getattr(internal, "explicit_mutability") is (
        astx.MutabilityKind.mutable
    )
    assert not getattr(internal, "is_static", False)
    assert isinstance(internal.type_, astx.Int32)
    assert isinstance(internal.value, astx.LiteralInt32)

    internal_total = counter.methods.nodes[0]
    assert isinstance(internal_total, astx.FunctionDef)
    assert internal_total.prototype.visibility is (
        astx.VisibilityKind.protected
    )
    protected_return = internal_total.body.nodes[0]
    assert isinstance(protected_return, astx.FunctionReturn)
    assert isinstance(protected_return.value, astx.BinaryOp)
    assert protected_return.value.op_code == "+"
    assert isinstance(protected_return.value.lhs, astx.FieldAccess)
    assert protected_return.value.lhs.field_name == "internal"
    assert isinstance(protected_return.value.rhs, astx.FieldAccess)
    assert protected_return.value.rhs.field_name == "value"

    read_internal = counter.methods.nodes[2]
    assert isinstance(read_internal, astx.FunctionDef)
    read_internal_return = read_internal.body.nodes[0]
    assert isinstance(read_internal_return, astx.FunctionReturn)
    assert isinstance(read_internal_return.value, astx.MethodCall)
    assert isinstance(read_internal_return.value.receiver, astx.Identifier)
    assert read_internal_return.value.receiver.name == "self"
    assert read_internal_return.value.method_name == "internal_total"
    assert read_internal_return.value.args == ()

    factory = tree.nodes[3]
    assert isinstance(factory, astx.ClassDefStmt)
    assert factory.name == "CounterFactory"
    assert factory.attributes.nodes == []
    assert [method.name for method in factory.methods.nodes] == [
        "make",
        "version_value",
    ]
    make = factory.methods.nodes[0]
    assert isinstance(make, astx.FunctionDef)
    assert getattr(make.prototype, "is_static", False) is True
    assert make.prototype.args.nodes == []
    assert isinstance(make.prototype.return_type, astx.ClassType)
    assert make.prototype.return_type.name == "Counter"
    make_return = make.body.nodes[0]
    assert isinstance(make_return, astx.FunctionReturn)
    assert isinstance(make_return.value, astx.ClassConstruct)
    assert make_return.value.class_name == "Counter"

    version_value = factory.methods.nodes[1]
    assert isinstance(version_value, astx.FunctionDef)
    assert getattr(version_value.prototype, "is_static", False) is True
    version_return = version_value.body.nodes[0]
    assert isinstance(version_return, astx.FunctionReturn)
    assert isinstance(version_return.value, astx.StaticFieldAccess)
    assert version_return.value.class_name == "Counter"
    assert version_return.value.field_name == "version"

    take_counter = tree.nodes[4]
    assert isinstance(take_counter, astx.FunctionDef)
    assert take_counter.prototype.name == "take_counter"
    assert len(take_counter.prototype.args.nodes) == 1
    counter_arg = take_counter.prototype.args.nodes[0]
    assert counter_arg.name == "counter"
    assert isinstance(counter_arg.type_, astx.ClassType)
    assert counter_arg.type_.name == "Counter"
    assert isinstance(take_counter.prototype.return_type, astx.Int32)
    take_counter_return = take_counter.body.nodes[0]
    assert isinstance(take_counter_return, astx.FunctionReturn)
    assert isinstance(take_counter_return.value, astx.BinaryOp)
    assert take_counter_return.value.op_code == "+"
    assert isinstance(take_counter_return.value.lhs, astx.BinaryOp)
    assert isinstance(take_counter_return.value.lhs.lhs, astx.MethodCall)
    assert take_counter_return.value.lhs.lhs.method_name == "get"
    assert isinstance(take_counter_return.value.lhs.rhs, astx.FieldAccess)
    assert take_counter_return.value.lhs.rhs.field_name == "value"
    assert isinstance(take_counter_return.value.rhs, astx.MethodCall)
    assert take_counter_return.value.rhs.method_name == "read_internal"

    main_fn = tree.nodes[5]
    assert isinstance(main_fn, astx.FunctionDef)
    assert main_fn.prototype.name == "main"
    assert len(main_fn.body.nodes) == 4

    direct = main_fn.body.nodes[0]
    assert isinstance(direct, astx.VariableDeclaration)
    assert direct.name == "direct"
    assert isinstance(direct.type_, astx.ClassType)
    assert direct.type_.name == "Counter"
    assert isinstance(direct.value, astx.ClassConstruct)
    assert direct.value.class_name == "Counter"

    built = main_fn.body.nodes[1]
    assert isinstance(built, astx.VariableDeclaration)
    assert built.name == "built"
    assert isinstance(built.type_, astx.ClassType)
    assert built.type_.name == "Counter"
    assert isinstance(built.value, astx.StaticMethodCall)
    assert built.value.class_name == "CounterFactory"
    assert built.value.method_name == "make"
    assert built.value.args == ()

    total = main_fn.body.nodes[2]
    assert isinstance(total, astx.VariableDeclaration)
    assert total.name == "total"
    assert isinstance(total.type_, astx.Int32)
    assert isinstance(total.value, astx.BinaryOp)
    assert isinstance(total.value.lhs, astx.FunctionCall)
    assert total.value.lhs.fn == "take_counter"
    assert isinstance(total.value.lhs.args[0], astx.Identifier)
    assert total.value.lhs.args[0].name == "direct"
    assert isinstance(total.value.rhs, astx.MethodCall)
    assert total.value.rhs.method_name == "get"
    assert isinstance(total.value.rhs.receiver, astx.Identifier)
    assert total.value.rhs.receiver.name == "built"

    main_return = main_fn.body.nodes[3]
    assert isinstance(main_return, astx.FunctionReturn)
    assert isinstance(main_return.value, astx.BinaryOp)
    assert isinstance(main_return.value.lhs, astx.BinaryOp)
    assert isinstance(main_return.value.lhs.lhs, astx.Identifier)
    assert main_return.value.lhs.lhs.name == "total"
    assert isinstance(main_return.value.lhs.rhs, astx.StaticMethodCall)
    assert main_return.value.lhs.rhs.class_name == "CounterFactory"
    assert main_return.value.lhs.rhs.method_name == "version_value"
    assert isinstance(main_return.value.rhs, astx.StaticFieldAccess)
    assert main_return.value.rhs.class_name == "Counter"
    assert main_return.value.rhs.field_name == "version"


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (
            dedent(
                """
                @[ ]
                class Bad:
                  value: int32 = 0
                """
            ).lstrip(),
            "empty annotation is not allowed",
        ),
        (
            dedent(
                """
                class Bad:
                  @[public, public]
                  value: int32 = 0
                """
            ).lstrip(),
            "duplicate modifier 'public'",
        ),
        (
            dedent(
                """
                class Bad:
                  @[public, private]
                  value: int32 = 0
                """
            ).lstrip(),
            "conflicting visibility modifiers",
        ),
        (
            dedent(
                """
                class Bad:
                  @[constant, mutable]
                  value: int32 = 0
                """
            ).lstrip(),
            "conflicting mutability modifiers",
        ),
        (
            dedent(
                """
                class Bad:
                  @[abstract]
                  value: int32 = 0
                """
            ).lstrip(),
            "field cannot use 'abstract'",
        ),
        (
            dedent(
                """
                class Bad:
                  @[override]
                  value: int32 = 0
                """
            ).lstrip(),
            "unknown modifier 'override'",
        ),
        (
            dedent(
                """
                class Bad:
                  @[public]
                """
            ).lstrip(),
            "annotation must be followed by a declaration",
        ),
        (
            dedent(
                """
                class Bad:
                  @[public] value: int32 = 0
                """
            ).lstrip(),
            "annotation must appear on its own line",
        ),
        (
            dedent(
                """
                class Bad:
                  fn area(self) -> float64
                """
            ).lstrip(),
            "method declaration without a body requires "
            "'abstract' or 'extern'",
        ),
        (
            dedent(
                """
                class Bad:
                  @[static]
                  fn helper(self) -> int32:
                    return 1
                """
            ).lstrip(),
            "static method cannot declare implicit receiver 'self'",
        ),
        (
            dedent(
                """
                class Counter:
                  value: int32 = 0

                fn main() -> int32:
                  var counter: Counter = Counter(1)
                  return 0
                """
            ).lstrip(),
            "class construction does not accept arguments",
        ),
        (
            dedent(
                """
                fn main() -> int32:
                  var counter: Missing = 0
                  return 0
                """
            ).lstrip(),
            "Parser: Unknown type 'Missing'",
        ),
    ],
)
def test_parse_class_modifier_errors(code: str, message: str) -> None:
    """
    title: Reject invalid annotation and class-member modifier combinations.
    parameters:
      code:
        type: str
      message:
        type: str
    """
    with pytest.raises(ParserException, match=message):
        _parse_module(code)
