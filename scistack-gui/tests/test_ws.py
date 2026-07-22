"""
Regression tests for the WebSocket push path (api/ws.py).

Background (2026-07-18): runs completed server-side in ~50ms but the GUI
stayed on "Running…" forever — run_output/run_done/dag_updated pushed by
the background run thread never reached the browser, while direct
``broadcast()`` calls from async endpoints did. The thread path
(``push_message`` → call_soon_threadsafe → asyncio queue → ``_pump_queue``)
has several silent drop points; these tests pin its contract:

  a message pushed from a plain background thread while a client is
  connected MUST reach that client.

No DB needed — a minimal FastAPI app with just the ws router.
"""

import asyncio
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from scistack_gui.api import ws as ws_mod


@pytest.fixture
def clean_ws_state():
    """Isolate the module-global loop/clients between tests."""
    ws_mod._loop = None
    ws_mod._clients.clear()
    yield
    ws_mod._loop = None
    ws_mod._clients.clear()


def _ws_app() -> FastAPI:
    app = FastAPI()
    app.include_router(ws_mod.router)
    return app


class TestPushMessageThreadPath:
    def test_push_from_thread_reaches_connected_client(self, clean_ws_state):
        client = TestClient(_ws_app())
        with client.websocket_connect("/ws") as sock:
            done = {"type": "run_done", "run_id": "abc12345", "success": True}
            t = threading.Thread(target=ws_mod.push_message, args=(done,))
            t.start()
            t.join()
            msg = sock.receive_json()
            assert msg == done

    def test_message_order_preserved(self, clean_ws_state):
        client = TestClient(_ws_app())
        with client.websocket_connect("/ws") as sock:
            msgs = [
                {"type": "run_output", "run_id": "r1", "text": "line 1\n"},
                {"type": "run_output", "run_id": "r1", "text": "line 2\n"},
                {"type": "run_done", "run_id": "r1", "success": True},
                {"type": "dag_updated"},
            ]

            def _push_all():
                for m in msgs:
                    ws_mod.push_message(m)

            t = threading.Thread(target=_push_all)
            t.start()
            t.join()
            received = [sock.receive_json() for _ in msgs]
            assert received == msgs

    def test_push_before_any_client_is_dropped_not_raised(self, clean_ws_state):
        # No client has ever connected: _loop is None. The message is lost
        # by design (logged as a WARNING) — but must never raise from the
        # run thread.
        ws_mod.push_message({"type": "run_done", "run_id": "orphan"})

    def test_push_reaches_all_connected_clients(self, clean_ws_state):
        """Fan-out: with two live connections (e.g. two browser tabs), a
        pushed message must reach BOTH — under the old shared-queue design
        one pump consumed each message and raced the other."""
        client = TestClient(_ws_app())
        with (
            client.websocket_connect("/ws") as s1,
            client.websocket_connect("/ws") as s2,
        ):
            done = {"type": "run_done", "run_id": "both", "success": True}
            t = threading.Thread(target=ws_mod.push_message, args=(done,))
            t.start()
            t.join()
            assert s1.receive_json() == done
            assert s2.receive_json() == done

    def test_push_after_reconnect_reaches_new_client(self, clean_ws_state):
        """The stuck-run scenario shape: first page connection goes away
        (reload), a second connects, then a run thread pushes. The pump
        task from the dead connection must not eat the message."""
        client = TestClient(_ws_app())
        with client.websocket_connect("/ws"):
            pass  # connect + immediately disconnect (page reload)
        with client.websocket_connect("/ws") as sock2:
            done = {"type": "run_done", "run_id": "second", "success": True}
            t = threading.Thread(target=ws_mod.push_message, args=(done,))
            t.start()
            t.join()
            msg = sock2.receive_json()
            assert msg == done


class TestBroadcastDirectPath:
    # _clients maps websocket -> outbox queue; broadcast iterates the KEYS
    # and sends directly, so stubs stand in for websockets here.

    def test_broadcast_reaches_stub_clients(self, clean_ws_state):
        sent = []

        class StubClient:
            async def send_json(self, msg):
                sent.append(msg)

        ws_mod._clients[StubClient()] = asyncio.Queue()
        asyncio.run(ws_mod.broadcast({"type": "dag_updated"}))
        assert sent == [{"type": "dag_updated"}]

    def test_broadcast_survives_one_dead_client(self, clean_ws_state):
        sent = []

        class DeadClient:
            async def send_json(self, msg):
                raise RuntimeError("socket closed")

        class LiveClient:
            async def send_json(self, msg):
                sent.append(msg)

        ws_mod._clients[DeadClient()] = asyncio.Queue()
        ws_mod._clients[LiveClient()] = asyncio.Queue()
        asyncio.run(ws_mod.broadcast({"type": "dag_updated"}))
        assert sent == [{"type": "dag_updated"}]
