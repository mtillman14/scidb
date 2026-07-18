"""
WebSocket endpoint: /ws

A WebSocket is a persistent two-way connection between the browser and the
server — unlike HTTP where the browser asks and the server answers once,
a WebSocket stays open so the server can push messages at any time.

We use it here to stream for_each stdout back to the frontend in real time,
and to notify the frontend when the DAG should refresh.

Messages sent to the frontend are JSON objects with a "type" field:
  {"type": "run_output", "run_id": "...", "text": "..."}
  {"type": "run_done",   "run_id": "...", "success": true}
  {"type": "dag_updated"}

Delivery architecture (rewritten 2026-07-18 — the stuck-"Running…" bug):
each connection owns a PER-CLIENT outbox queue and a pump task that reads
ONLY that queue; the pump is explicitly cancelled on disconnect. The old
design shared ONE queue among every pump ever started, and disconnects
leaked their pump (gather doesn't cancel siblings) — so after any
reconnect, an orphaned pump could win the race for a message and consume
it on behalf of a dead connection, silently losing run_done/dag_updated
(regression-tested in tests/test_ws.py::test_push_after_reconnect_...).

Two entry points:
  1. ``broadcast()``   — from ASYNC endpoint handlers; sends directly.
  2. ``push_message()`` — from BACKGROUND RUN THREADS; hops onto the event
     loop via call_soon_threadsafe and fans out to every client's outbox.
Every drop point logs, so a delivery failure can be traced in scidb.log
via the [ws] lines.
"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# One outbox queue per connected client. Iterating the dict yields the
# WebSocket objects (dict keys), so `for client in list(_clients)` works.
_clients: dict[WebSocket, asyncio.Queue] = {}

# The running event loop — stored from async context so background threads
# can schedule work on it via call_soon_threadsafe.
# (asyncio.get_event_loop() raises RuntimeError in non-main threads in Python 3.10+)
_loop: asyncio.AbstractEventLoop | None = None


def _log_for(msg: dict):
    """run_output is per-stdout-line chatty → DEBUG; everything else INFO."""
    return logger.debug if msg.get("type") == "run_output" else logger.info


def push_message(msg: dict) -> None:
    """
    Thread-safe: called from a background thread to deliver a message to
    every connected client. Uses call_soon_threadsafe so the fan-out runs
    on the event loop thread rather than in the background thread.

    In JSON-RPC server mode (VS Code extension), delegates to notify.py
    instead of the WebSocket path.
    """
    from scistack_gui.notify import _enabled as _jsonrpc_mode
    if _jsonrpc_mode:
        from scistack_gui.notify import push_message as _jsonrpc_push
        _jsonrpc_push(dict(msg))  # copy to avoid mutating caller's dict
        return
    if _loop is None:
        # No WebSocket client has EVER connected — nowhere to schedule the
        # fan-out. This loses run_output/run_done/dag_updated, so say so.
        logger.warning(
            "[ws] DROPPED %s message (run_id=%s): no event loop captured — "
            "no WebSocket client has connected yet",
            msg.get("type"), msg.get("run_id"),
        )
        return
    _loop.call_soon_threadsafe(_fanout_nowait, dict(msg))


def _fanout_nowait(msg: dict) -> None:
    """Runs ON the event loop: copy the message into every client outbox."""
    if not _clients:
        logger.warning(
            "[ws] DROPPED %s message (run_id=%s): no clients connected",
            msg.get("type"), msg.get("run_id"),
        )
        return
    for outbox in _clients.values():
        outbox.put_nowait(msg)
    _log_for(msg)(
        "[ws] fanned out %s (run_id=%s) to %d client outbox(es)",
        msg.get("type"), msg.get("run_id"), len(_clients),
    )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global _loop
    _loop = asyncio.get_running_loop()   # capture from async context
    await websocket.accept()
    outbox: asyncio.Queue = asyncio.Queue()
    _clients[websocket] = outbox
    logger.info("[ws] client connected (%d total)", len(_clients))
    # The pump reads ONLY this connection's outbox and is ALWAYS reaped in
    # the finally below — a disconnect can never leak a competing consumer.
    pump = asyncio.create_task(_pump_outbox(websocket, outbox))
    try:
        # Keep the connection alive by consuming incoming messages (pings).
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("[ws] client disconnected")
    except Exception:
        logger.exception("[ws] connection handler failed")
    finally:
        pump.cancel()
        _clients.pop(websocket, None)
        logger.info("[ws] client removed (%d remaining)", len(_clients))


async def _pump_outbox(websocket: WebSocket, outbox: asyncio.Queue):
    """Forward this connection's outbox to its client until cancelled."""
    while True:
        msg = await outbox.get()
        try:
            await websocket.send_json(msg)
            _log_for(msg)(
                "[ws] delivered %s (run_id=%s)",
                msg.get("type"), msg.get("run_id"),
            )
        except Exception as exc:
            logger.warning(
                "[ws] send failed for %s message (%s); stopping pump for "
                "this client", msg.get("type"), exc,
            )
            break


async def broadcast(msg: dict) -> None:
    """Send a message to all connected clients from async context.

    In JSON-RPC server mode (VS Code extension), delegates to notify.py.
    """
    from scistack_gui.notify import _enabled as _jsonrpc_mode
    if _jsonrpc_mode:
        from scistack_gui.notify import push_message as _jsonrpc_push
        _jsonrpc_push(dict(msg))
        return
    delivered = 0
    for client in list(_clients):
        try:
            await client.send_json(msg)
            delivered += 1
        except Exception as exc:
            logger.warning("[ws] broadcast send failed for %s: %s",
                           msg.get("type"), exc)
    logger.info("[ws] broadcast %s to %d/%d client(s)",
                msg.get("type"), delivered, len(_clients))
