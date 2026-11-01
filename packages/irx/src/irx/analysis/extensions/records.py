"""
title: Nominal operation identity and resolved call-plan attachment boundary.
"""

from public import public

from irx.analysis.facts import FactKey, SemanticFact
from irx.typecheck import typechecked


@public
@typechecked
class CallOperation:
    """
    title: Trusted operation meaning, never inferred from user spelling.
    """


@public
@typechecked
class CallPlan(SemanticFact):
    """
    title: Feature-owned resolved behavior selected by call lowering.
    """


CALL_PLAN = FactKey("irx.calls", CallPlan)
