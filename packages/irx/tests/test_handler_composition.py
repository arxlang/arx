"""
title: Isolated nominal handler composition through the public Plum boundary.
"""

from __future__ import annotations

import subprocess
import sys

from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import get_type_hints

import pytest

from irx.extensions import (
    ConfigurationError,
    HandlerConfiguration,
    ScopedDispatch,
    contribute,
)
from irx.typecheck import typechecked
from public import private
from typeguard import TypeCheckError


@private
@dataclass(frozen=True)
class Value:
    """
    title: Nominal input with recursion depth.
    attributes:
      depth:
        type: int
    """

    depth: int = 0


@private
class Narrow(Value):
    """
    title: A supported nominal subtype.
    attributes:
      depth:
        type: int
    """


@private
class Sibling(Value):
    """
    title: An independently registered nominal subtype.
    attributes:
      depth:
        type: int
    """


@private
class Combined(Narrow, Sibling):
    """
    title: A later multiple-inheritance overlap cannot be resolved statically.
    attributes:
      depth:
        type: int
    """


@private
@dataclass
class Context:
    """
    title: Mutable invocation state, never retained by a contribution.
    attributes:
      seen:
        type: list[str]
      dispatcher:
        type: ScopedDispatch | None
    """

    seen: list[str] = field(default_factory=list)
    dispatcher: ScopedDispatch | None = None


@private
class ExtraContext(Context):
    """
    title: A dependency not supplied by the ordinary context.
    attributes:
      seen:
        type: list[str]
      dispatcher:
        type: ScopedDispatch | None
    """


@private
class Provider:
    """
    title: Small inheritable provider with explicit contribution export.
    """

    @typechecked
    def visit(self, value: Value, context: Context) -> None:
        """
        title: Record visits and recurse through the same scoped dispatcher.
        parameters:
          value:
            type: Value
          context:
            type: Context
        """
        context.seen.append("parent")
        if value.depth:
            assert context.dispatcher is not None
            context.dispatcher.visit(Value(value.depth - 1), context)


@private
class Inherited(Provider):
    """
    title: Export an inherited method without scanning a class dictionary.
    """


@private
class Replacement(Provider):
    """
    title: Override an implementation without global class registration.
    """

    @typechecked
    def visit(self, value: Value, context: Context) -> None:
        """
        title: Supply a deliberately different implementation.
        parameters:
          value:
            type: Value
          context:
            type: Context
        """
        context.seen.append("child")


@typechecked
def narrow(value: Narrow, context: Context) -> None:
    """
    title: Implement a more specific nominal input.
    parameters:
      value:
        type: Narrow
      context:
        type: Context
    """
    context.seen.append("narrow")


@typechecked
def sibling(value: Sibling, context: Context) -> None:
    """
    title: Implement an incomparable input signature.
    parameters:
      value:
        type: Sibling
      context:
        type: Context
    """
    context.seen.append("sibling")


@typechecked
def extra(value: Value, context: ExtraContext) -> None:
    """
    title: Require a more specific context.
    parameters:
      value:
        type: Value
      context:
        type: ExtraContext
    """
    context.seen.append("extra")


def test_replacement_specificity_recursion_and_instance_isolation() -> None:
    """
    title: >-
      Derived configurations and later instances never mutate their parents.
    """
    provider = Inherited()
    original = contribute(
        "original", "test", "analysis", Value, Context, provider.visit
    )
    parent = HandlerConfiguration("analysis", (original,))
    first = ScopedDispatch(parent)
    child = parent.derive(
        contribute(
            "replacement",
            "test",
            "analysis",
            Value,
            Context,
            Replacement().visit,
            replaces="original",
        )
    )
    specialized = parent.derive(
        contribute("narrow", "test", "analysis", Narrow, Context, narrow)
    )
    for configuration, expected in (
        (child, "child"),
        (parent, "parent"),
        (specialized, "narrow"),
    ):
        context = Context()
        ScopedDispatch(configuration).visit(Narrow(), context)
        assert context.seen == [expected]
    context = Context(dispatcher=first)
    first.visit(Value(2), context)
    assert context.seen == ["parent"] * 3
    assert parent.contributions == (original,)
    assert child.contributions[0].replaces == "original"
    assert original.source.endswith("Provider.visit")
    assert get_type_hints(original.implementation) == get_type_hints(
        provider.visit
    )


def test_invalid_configurations_fail_before_dispatch() -> None:
    """
    title: >-
      Duplicates, missing replacements, phases and dependencies are errors.
    """
    item = contribute(
        "base", "test", "analysis", Value, Context, Provider().visit
    )
    parent = HandlerConfiguration("analysis", (item,))
    with pytest.raises(ConfigurationError, match="duplicate"):
        parent.derive(item)
    with pytest.raises(ConfigurationError, match="replacement"):
        HandlerConfiguration(
            "analysis",
            (
                contribute(
                    "child",
                    "test",
                    "analysis",
                    Value,
                    Context,
                    Replacement().visit,
                    replaces="base",
                ),
            ),
        )
    with pytest.raises(ConfigurationError, match="replacement"):
        parent.derive(
            contribute(
                "child",
                "test",
                "analysis",
                Value,
                Context,
                Replacement().visit,
                replaces="absent",
            )
        )
    with pytest.raises(ConfigurationError, match="wrong phase"):
        HandlerConfiguration("lowering", (item,))
    with pytest.raises((TypeCheckError, TypeError)):
        HandlerConfiguration("analysis", (item, object()))  # type: ignore[arg-type]
    with pytest.raises(
        ConfigurationError, match="unavailable phase dependencies"
    ):
        HandlerConfiguration(
            "analysis",
            (
                contribute(
                    "extra",
                    "test",
                    "analysis",
                    Value,
                    ExtraContext,
                    extra,
                ),
            ),
        ).validate_contract("analysis", Value, Context)
    with pytest.raises(ConfigurationError, match="expected"):
        contribute("wrong", "test", "analysis", Value, Context, narrow)  # type: ignore[arg-type]
    with pytest.raises(ConfigurationError, match="function or bound method"):
        contribute(
            "partial",
            "test",
            "analysis",
            Value,
            Context,
            partial(Provider().visit),
        )
    dispatcher = ScopedDispatch(parent)
    with pytest.raises(ConfigurationError, match="no analysis handler"):
        dispatcher.visit(Value(), object())
    with pytest.raises(TypeError, match="invalid arguments"):
        item.implementation(object(), Context())


def test_crossed_signatures_and_future_subtype_ambiguity_fail_explicitly() -> (
    None
):
    """
    title: >-
      Reject known overlap early and unresolved future overlap at invocation.
    """
    narrow_item = contribute(
        "narrow", "test", "analysis", Narrow, Context, narrow
    )
    with pytest.raises(ConfigurationError, match="crossed signatures"):
        HandlerConfiguration(
            "analysis",
            (
                narrow_item,
                contribute(
                    "extra", "test", "analysis", Value, ExtraContext, extra
                ),
            ),
        )
    configuration = HandlerConfiguration(
        "analysis",
        (
            narrow_item,
            contribute(
                "sibling", "test", "analysis", Sibling, Context, sibling
            ),
        ),
    )
    with pytest.raises(
        ConfigurationError, match="ambiguous analysis dispatch"
    ):
        ScopedDispatch(configuration).visit(Combined(), Context())


def test_metadata_and_analysis_composition_do_not_import_backends() -> None:
    """
    title: >-
      Descriptor imports are light and analysis composition is backend-free.
    """
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import irx.extensions; "
            "assert not any(name in sys.modules "
            "for name in ('llvmlite', 'pyarrow', 'arx')); "
            "from irx.analysis.extensions.calls "
            "import default_analysis_configuration; "
            "default_analysis_configuration(); "
            "assert not any(name in sys.modules "
            "for name in ('llvmlite', 'irx.builder', 'arx'))",
        ],
        check=True,
        timeout=60,
    )


def test_static_feature_contracts_accept_typed_lookup_and_reject_mismatches(
    tmp_path: Path,
) -> None:
    """
    title: >-
      Strict mypy verifies typed retrieval and rejects invalid contributions.
    parameters:
      tmp_path:
        type: Path
    """
    positive = tmp_path / "positive.py"
    source = """
from irx.analysis.facts import FactKey, SemanticFact, SemanticFacts
from irx.extensions import contribute
class Value(SemanticFact):
    pass
class Other(SemanticFact):
    pass
class Context:
    pass
def visit(value: Value, context: Context) -> None:
    pass
key = FactKey("test", Value)
facts = SemanticFacts().with_fact(key, Value())
value: Value = facts.require(key)
contribute("test", "test", "analysis", Value, Context, visit)
"""
    positive.write_text(source, encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "mypy",
        "--strict",
        "--follow-imports=silent",
    ]
    accepted = subprocess.run(
        [*command, str(positive)], capture_output=True, text=True, check=False
    )
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    negative = tmp_path / "negative.py"
    negative.write_text(
        source
        + """facts.with_fact(key, Other())
contribute("bad", "test", "analysis", Other, Context, visit)
wrong: Other = facts.require(key)
""",
        encoding="utf-8",
    )
    rejected = subprocess.run(
        [*command, str(negative)], capture_output=True, text=True, check=False
    )
    assert rejected.returncode == 1, rejected.stdout + rejected.stderr
    expected_errors = 3
    assert rejected.stdout.count("error:") == expected_errors, rejected.stdout
