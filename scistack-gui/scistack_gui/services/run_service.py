"""
Run service — single source of truth for pipeline execution.

Wraps the run thread logic from api/run.py. Called by both JSON-RPC
handlers (server.py) and FastAPI routes (api/run.py).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def cancel_run(run_id: str) -> dict:
    """Cooperatively cancel a running for_each."""
    from scistack_gui.api.run import cancel_run as _cancel
    return _cancel(run_id)


def force_cancel_run(run_id: str) -> dict:
    """Force-cancel a running for_each by injecting KeyboardInterrupt."""
    from scistack_gui.api.run import force_cancel_run as _force_cancel
    return _force_cancel(run_id)
