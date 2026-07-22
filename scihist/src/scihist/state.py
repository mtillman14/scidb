"""Deprecated shim — scihist.state moved into scidb.state.

Re-exports the pipeline node staleness API from its new home in ``scidb.state``.
Prefer importing from ``scidb`` directly.
"""

from scidb.state import (  # noqa: F401 — re-exported for back-compat
    ComboState,
    NodeState,
    check_combo_state,
    check_multiple_nodes_state,
    check_node_state,
    check_pathinput_node_state,
)
