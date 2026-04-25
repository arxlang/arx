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
              ```
              title: Shape
              summary: Declares one abstract area protocol for shape types.
              ```
              @[public]
              fn area(self) -> int32:
                ```
                title: area
                summary: >-
                    Returns one placeholder area value for parser coverage.
                ```
                return 0

            class BaseCounter:
              ```
              title: BaseCounter
              summary: Stores one inherited seed value for derived counters.
              ```
              @[public, mutable]
              value: int32 = 41

              @[protected]
              fn read_seed(self) -> int32:
                ```
                title: read_seed
                summary: Returns the inherited seed value.
                ```
                return self.value

            class Counter(BaseCounter):
              ```
              title: Counter
              summary: Extends BaseCounter with private state and helpers.
              ```
              @[public, static, constant]
              version: int32 = 3

              @[private, mutable]
              internal: int32 = 5

              @[protected]
              fn internal_total(self) -> int32:
                ```
                title: internal_total
                summary: Combines private and inherited counter state.
                ```
                return self.internal + self.value

              @[public]
              fn get(self) -> int32:
                ```
                title: get
                summary: Returns the inherited public counter value.
                ```
                return self.value

              @[public]
              fn read_internal(self) -> int32:
                ```
                title: read_internal
                summary: Exposes the protected internal helper result.
                ```
                return self.internal_total()

            class CounterFactory:
              ```
              title: CounterFactory
              summary: Builds counters and exposes static metadata.
              ```
              @[public, static]
              fn make() -> Counter:
                ```
                title: make
                summary: Constructs one default Counter instance.
                ```
                return Counter()

              @[public, static]
              fn version_value() -> int32:
                ```
                title: version_value
                summary: Returns the static Counter version constant.
                ```
                return Counter.version

            fn take_counter(counter: Counter) -> int32:
              ```
              title: take_counter
              summary: Combines method and attribute access on one counter.
              ```
              return counter.get() + counter.value + counter.read_internal()

            fn main() -> int32:
              ```
              title: main
              summary: Exercises class construction and static member access.
              ```
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
    assert getattr(area.prototype, "is_abstract", False) is False
    area_return = area.body.nodes[0]
    assert isinstance(area_return, astx.FunctionReturn)
    assert isinstance(area_return.value, astx.LiteralInt32)
    assert area_return.value.value == 0

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


def test_parse_visible_local_names_shadow_class_expressions() -> None:
    """
    title: Visible locals prevent class-name parsing in expression position.
    """
    tree = _parse_module(
        dedent(
            """
            class Counter:
              ```
              title: Counter
              summary: Defines one simple counter type for expression tests.
              ```
              @[public, static, constant]
              version: int32 = 3

              value: int32 = 0

            fn main() -> int32:
              ```
              title: main
              summary: Checks that visible locals shadow class expressions.
              ```
              var Counter: int32 = 1
              var next: int32 = Counter()
              return Counter.version
            """
        ).lstrip()
    )

    main_fn = tree.nodes[1]
    assert isinstance(main_fn, astx.FunctionDef)

    next_decl = main_fn.body.nodes[1]
    assert isinstance(next_decl, astx.VariableDeclaration)
    assert isinstance(next_decl.value, astx.FunctionCall)
    assert next_decl.value.fn == "Counter"

    result = main_fn.body.nodes[2]
    assert isinstance(result, astx.FunctionReturn)
    assert isinstance(result.value, astx.FieldAccess)
    assert isinstance(result.value.value, astx.Identifier)
    assert result.value.value.name == "Counter"
    assert result.value.field_name == "version"
    assert not isinstance(result.value, astx.StaticFieldAccess)


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (
            dedent(
                """
                @[ ]
                class Bad:
                  ```
                  title: Bad
                  summary: Holds one invalid annotation form for parser checks.
                  ```
                  value: int32 = 0
                """
            ).lstrip(),
            "empty annotation is not allowed",
        ),
        (
            dedent(
                """
                class Bad:
                  ```
                  title: Bad
                  summary: Holds one duplicate-visibility field declaration.
                  ```
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
                  ```
                  title: Bad
                  summary: Holds one conflicting-visibility field declaration.
                  ```
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
                  ```
                  title: Bad
                  summary: Holds one conflicting-mutability field declaration.
                  ```
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
                  ```
                  title: Bad
                  summary: Holds one invalid abstract field declaration.
                  ```
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
                  ```
                  title: Bad
                  summary: >-
                    Holds one field declaration with an unknown modifier.
                  ```
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
                  ```
                  title: Bad
                  summary: Holds one dangling annotation without a declaration.
                  ```
                  @[public]
                """
            ).lstrip(),
            "annotation must be followed by a declaration",
        ),
        (
            dedent(
                """
                class Bad:
                  ```
                  title: Bad
                  summary: Holds one inline annotation that should be rejected.
                  ```
                  @[public] value: int32 = 0
                """
            ).lstrip(),
            "annotation must appear on its own line",
        ),
        (
            dedent(
                """
                class Bad:
                  ```
                  title: Bad
                  summary: Holds one non-abstract method missing a body.
                  ```
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
                  ```
                  title: Bad
                  summary: >-
                    Holds one abstract method with an invalid statement body.
                  ```
                  @[abstract]
                  fn area(self) -> float64:
                    ```
                    title: area
                    summary: >-
                        Declares one abstract method with a non-docstring body.
                    ```
                    return 1
                """
            ).lstrip(),
            "abstract method body may only contain a docstring",
        ),
        (
            dedent(
                """
                class Bad:
                  ```
                  title: Bad
                  summary: Holds one invalid static helper method declaration.
                  ```
                  @[static]
                  fn helper(self) -> int32:
                    ```
                    title: helper
                    summary: Returns one constant while violating static rules.
                    ```
                    return 1
                """
            ).lstrip(),
            "static method cannot declare implicit receiver 'self'",
        ),
        (
            dedent(
                """
                class Counter:
                  ```
                  title: Counter
                  summary: Defines one class used by construction error tests.
                  ```
                  value: int32 = 0

                fn main() -> int32:
                  ```
                  title: main
                  summary: Triggers one invalid class-construction call.
                  ```
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
                  ```
                  title: main
                  summary: Triggers one missing-type parser error.
                  ```
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
