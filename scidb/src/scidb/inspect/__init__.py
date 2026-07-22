"""Read-side observability facade + CLI for scidb databases.

`Inspector` is the one read API the CLI, GUI, and MATLAB bridge consume; it
computes nothing new — it only shapes what provenance_query, state, and the
core tables already encode (see docs/claude/observability-api-design.md).
"""

from .api import (
    DbOverview,
    ExclusionRecord,
    Inspector,
    NodeStateSummary,
    PickCandidate,
    ProvenanceTree,
    RecordSummary,
    RunRecord,
    SchemaNode,
    SchemaTree,
    SqlResult,
    TraceEdge,
    TraceInput,
    TraceNode,
    VariableDetail,
    VariableSummary,
)
from .graph import (
    FunctionNode,
    PipelineEdge,
    PipelineGraph,
    VariableNode,
    VariantSummary,
)
from .mutate import MutationResult, Mutator
from .render import ASCII_STYLE, DEFAULT_STYLE, RenderStyle

__all__ = [
    "Inspector",
    "DbOverview",
    "VariableSummary",
    "VariableDetail",
    "SchemaNode",
    "SchemaTree",
    "RecordSummary",
    "PipelineGraph",
    "FunctionNode",
    "VariableNode",
    "PipelineEdge",
    "VariantSummary",
    "RenderStyle",
    "DEFAULT_STYLE",
    "ASCII_STYLE",
    "RunRecord",
    "ProvenanceTree",
    "TraceNode",
    "TraceEdge",
    "TraceInput",
    "NodeStateSummary",
    "SqlResult",
    "ExclusionRecord",
    "Mutator",
    "MutationResult",
    "PickCandidate",
]
