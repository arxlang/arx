"""
title: Phase-lazy descriptor for the migrated table I/O call family.
"""

from public import private

from irx.extensions.providers import FeatureDescriptor, PhaseProvider
from irx.typecheck import typechecked


@private
@typechecked
def descriptor() -> FeatureDescriptor:
    """
    title: Describe table handlers without importing analysis or LLVM.
    returns:
      type: FeatureDescriptor
    """
    return FeatureDescriptor(
        identity="irx.table_io",
        source="irx.extensions.builtin.table_io:descriptor",
        providers=(
            PhaseProvider(
                "analysis",
                "irx.analysis.table_io:analysis_contributions",
                ("table.read", "table.write", "table.auxiliary"),
            ),
            PhaseProvider(
                "lowering",
                "irx.builder.lowering.table_io:lowering_contributions",
                ("table.emit",),
            ),
        ),
    )
