"""SciHist (deprecated) — thin shim over the consolidated scidb API.

Lineage-tracked batch execution, the node-staleness API, and lineage-aware
save now live in **scidb** (``scidb.for_each`` tracks lineage by default).
This package remains only as a backward-compatible shim for existing imports
(e.g. ``scistack-gui`` and the MATLAB ``+scihist`` bridge). Prefer importing
from ``scidb`` directly; ``scihist`` will be removed in a future release.

Behavioral nuances preserved by the shim:
- ``scihist.for_each`` defaults ``skip_computed=True`` (scidb defaults False).
- ``scihist.configure_database`` registers the DB as scilineage's cache backend.
"""

import warnings as _warnings

_warnings.warn(
    "scihist is deprecated; its functionality has moved to scidb. "
    "Import from scidb instead (e.g. `from scidb import for_each, save, "
    "configure_database`).",
    DeprecationWarning,
    stacklevel=2,
)

# Core batch execution + lineage-aware save (shimmed to preserve scihist defaults)
from .foreach import for_each, save
from .database import configure_database, find_by_lineage
from .state import check_combo_state, check_node_state, check_multiple_nodes_state

# Re-export DB wrappers from scidb
from scidb import Fixed, Merge, ColumnSelection, ForEachConfig

# Re-export scifor helpers
from scifor import Col, set_schema, get_schema, PathInput

# Re-export scilineage system
from scilineage import lineage_fcn, LineageFcn, LineageFcnResult, LineageFcnInvocation

__version__ = "0.1.0"

__all__ = [
    # Core batch execution
    "for_each",
    "save",
    # Configuration
    "configure_database",
    # Lineage query
    "find_by_lineage",
    # Node staleness
    "check_combo_state",
    "check_node_state",
    "check_multiple_nodes_state",
    # DB wrappers
    "Fixed",
    "Merge",
    "ColumnSelection",
    "ForEachConfig",
    "PathInput",
    # Schema helpers
    "Col",
    "set_schema",
    "get_schema",
    # Lineage system
    "lineage_fcn",
    "LineageFcn",
    "LineageFcnResult",
    "LineageFcnInvocation",
]
