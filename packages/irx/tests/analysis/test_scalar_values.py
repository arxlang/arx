"""
title: Fail-closed scalar resolver and managed aggregate boundaries.
"""

import astx
import pytest

from irx.analysis import analyze
from irx.analysis.scalar_values import scalar_constructor, scalar_query
from irx.analysis.schema_types import columnar_type_diagnostic
from irx.diagnostics import SemanticError
from typeguard import TypeCheckError


def test_scalar_resolver_validates_arity_and_collection_items() -> None:
    """
    title: Public resolver calls cannot bypass arity or item validation.
    """
    type_ = astx.ScalarType(astx.LogicalType(astx.LogicalKind.STRING))
    with pytest.raises(ValueError, match="argument count"):
        scalar_constructor(type_, (), (astx.String(),))
    with pytest.raises(ValueError, match="argument count"):
        scalar_query(astx.ScalarOperation.TEXT, (), (type_,))
    with pytest.raises(TypeCheckError):
        scalar_constructor(type_, (None,), ())  # type: ignore[arg-type]


def test_scalar_struct_field_requires_managed_destruction() -> None:
    """
    title: Native struct storage must not silently leak a scalar owner.
    """
    module = astx.Module()
    module.block.append(
        astx.StructDefStmt(
            name="Owner",
            attributes=[
                astx.VariableDeclaration(
                    "value",
                    astx.ScalarType(astx.LogicalType(astx.LogicalKind.STRING)),
                ),
            ],
        )
    )
    with pytest.raises(
        SemanticError, match="struct fields require destruction"
    ):
        analyze(module)


def test_scalar_nullable_marker_is_not_an_owner_union() -> None:
    """
    title: Require an explicit owner union instead of scalar element validity.
    """
    type_ = astx.ScalarType(
        astx.LogicalType(astx.LogicalKind.STRING), nullable=True
    )
    assert columnar_type_diagnostic(type_) is not None
