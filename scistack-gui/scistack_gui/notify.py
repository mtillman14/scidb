"""
Push notifications to the VS Code extension host via stdout.

Replaces ws.py's push_message/broadcast for the JSON-RPC server mode.
In standalone (FastAPI) mode, ws.py is used instead.

All output is newline-delimited JSON on stdout. User code stdout is captured
by redirect_stdout in run.py, so it never leaks into the JSON-RPC stream.
"""

import json
import sys
import threading

_lock = threading.Lock()
_enabled = False


def enable():
    """Enable JSON-RPC notification output on stdout."""
    global _enabled
    _enabled = True


def notify(method: str, params: dict) -> None:
    """
    Write a JSON-RPC notification to stdout (thread-safe).

    This is the JSON-RPC equivalent of ws.push_message / ws.broadcast.
    Called from background threads (e.g. run.py) and async handlers.
    """
    if not _enabled:
        return
    msg = json.dumps({"jsonrpc": "2.0", "method": method, "params": params})
    with _lock:
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()


def push_message(msg: dict) -> None:
    """
    Compatibility shim: translates the old ws.push_message format
    ({"type": "run_output", ...}) into a JSON-RPC notification.

    This allows run.py and pipeline.py to work with both the FastAPI
    WebSocket path (ws.push_message) and the JSON-RPC path (notify)
    without changing their call sites.
    """
    msg_type = msg.pop("type", "message")
    notify(msg_type, msg)
