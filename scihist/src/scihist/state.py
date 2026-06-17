"""Deprecated shim — scihist.state moved into scidb.state.

Re-exports the pipeline node staleness API (and the private helpers some
existing tests import) from its new home in ``scidb.state``. Prefer importing
from ``scidb`` directly.
"""

from scidb.state import (  # noqa: F401 — re-exported for back-compat
    ComboState,
    NodeState,
    check_combo_state,
    check_node_state,
    check_multiple_nodes_state,
    _get_output_combos,
    _get_expected_combos,
)
