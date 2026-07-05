"""Read-side observability facade + CLI for scidb databases.

`Inspector` is the one read API the CLI, GUI, and MATLAB bridge consume; it
computes nothing new — it only shapes what provenance_query, state, and the
core tables already encode (see docs/claude/observability-api-design.md).
"""

from .api import (
    DbOverview,
    Inspector,
    RecordSummary,
    SchemaNode,
    SchemaTree,
    VariableDetail,
    VariableSummary,
)

__all__ = [
    "Inspector",
    "DbOverview",
    "VariableSummary",
    "VariableDetail",
    "SchemaNode",
    "SchemaTree",
    "RecordSummary",
]
