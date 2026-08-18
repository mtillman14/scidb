"""
Tests for scistack_gui.matlab_sidecar (Stage 3,
plan-matlab-pipeline-execution.md).

No real MATLAB in this sandbox — subprocess.Popen is mocked with a fake
process exposing writable stdin and a queue-backed stdout iterator, the
same style used for the MATLAB-existence subprocess check in
test_builtin_functions.py's TestMatlabBuiltin (monkeypatch the module's
own `shutil`/`subprocess` references).
"""

from __future__ import annotations

import queue

import pytest
from scistack_gui import matlab_sidecar as ms


class FakeStdin:
    def __init__(self):
        self.written: list[str] = []

    def write(self, s: str) -> None:
        self.written.append(s)

    def flush(self) -> None:
        pass


class FakeStdout:
    """Queue-backed line iterator — mirrors a real pipe: __next__ blocks
    until a line is pushed or close() signals EOF."""

    _CLOSED = object()

    def __init__(self):
        self._q: "queue.Queue[object]" = queue.Queue()

    def push(self, line: str) -> None:
        self._q.put(line)

    def close(self) -> None:
        self._q.put(self._CLOSED)

    def __iter__(self):
        return self

    def __next__(self):
        item = self._q.get()
        if item is self._CLOSED:
            raise StopIteration
        return item


class FakeProcess:
    def __init__(self):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout()
        self.pid = 4242
        self._returncode: int | None = None
        self.killed = False

    def poll(self):
        return self._returncode

    def kill(self):
        self.killed = True
        self._returncode = -9
        self.stdout.close()


@pytest.fixture(autouse=True)
def _reset_singleton():
    """The module-level sidecar singleton must not leak between tests."""
    ms._sidecar = None
    yield
    ms._sidecar = None


class TestStart:
    def test_returns_false_when_matlab_not_on_path(self, monkeypatch):
        monkeypatch.setattr(ms.shutil, "which", lambda name: None)
        called = []
        monkeypatch.setattr(ms.subprocess, "Popen", lambda *a, **k: called.append(1))

        sidecar = ms.MatlabSidecar()
        assert sidecar.start() is False
        assert called == []
        assert sidecar.is_running is False

    def test_launches_popen_with_expected_flags(self, monkeypatch):
        monkeypatch.setattr(ms.shutil, "which", lambda name: "/usr/local/bin/matlab")
        captured = {}

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return FakeProcess()

        monkeypatch.setattr(ms.subprocess, "Popen", fake_popen)

        sidecar = ms.MatlabSidecar()
        assert sidecar.start() is True
        assert sidecar.is_running is True
        assert captured["cmd"] == [
            "/usr/local/bin/matlab", "-nodesktop", "-nosplash", "-nodisplay",
        ]
        assert captured["kwargs"]["stdin"] == ms.subprocess.PIPE
        assert captured["kwargs"]["stdout"] == ms.subprocess.PIPE
        assert captured["kwargs"]["text"] is True

    def test_idempotent_while_running(self, monkeypatch):
        monkeypatch.setattr(ms.shutil, "which", lambda name: "/usr/local/bin/matlab")
        call_count = {"n": 0}

        def fake_popen(cmd, **kwargs):
            call_count["n"] += 1
            return FakeProcess()

        monkeypatch.setattr(ms.subprocess, "Popen", fake_popen)

        sidecar = ms.MatlabSidecar()
        assert sidecar.start() is True
        assert sidecar.start() is True
        assert call_count["n"] == 1


class TestRunCommand:
    def _started_sidecar(self, monkeypatch) -> tuple[ms.MatlabSidecar, FakeProcess]:
        monkeypatch.setattr(ms.shutil, "which", lambda name: "/usr/local/bin/matlab")
        proc_holder: list[FakeProcess] = []

        def fake_popen(cmd, **kwargs):
            proc = FakeProcess()
            proc_holder.append(proc)
            return proc

        monkeypatch.setattr(ms.subprocess, "Popen", fake_popen)
        sidecar = ms.MatlabSidecar()
        assert sidecar.start() is True
        return sidecar, proc_holder[0]

    def test_raises_when_not_started(self):
        sidecar = ms.MatlabSidecar()
        with pytest.raises(RuntimeError, match="not running"):
            sidecar.run_command("disp('hi')", lambda line: None)

    def test_writes_wrapped_command_to_stdin(self, monkeypatch):
        sidecar, proc = self._started_sidecar(monkeypatch)
        proc.stdout.push(f"{ms.DONE_SENTINEL}\n")

        ok = sidecar.run_command("disp('hi')", lambda line: None, timeout=2)
        assert ok is True

        written = "".join(proc.stdin.written)
        assert "try\n" in written
        assert "disp('hi')" in written
        assert f"disp('{ms.DONE_SENTINEL}');" in written
        assert "catch scistack_sidecar_err__" in written
        assert ms.ERROR_SENTINEL in written

    def test_success_relays_lines_and_stops_at_done_sentinel(self, monkeypatch):
        sidecar, proc = self._started_sidecar(monkeypatch)
        proc.stdout.push("line one\n")
        proc.stdout.push("line two\n")
        proc.stdout.push(f"{ms.DONE_SENTINEL}\n")
        proc.stdout.push("should not be relayed\n")  # never reached

        relayed: list[str] = []
        ok = sidecar.run_command("disp('hi')", relayed.append, timeout=2)

        assert ok is True
        assert relayed == ["line one\n", "line two\n"]

    def test_error_sentinel_relays_error_line_and_returns_false(self, monkeypatch):
        sidecar, proc = self._started_sidecar(monkeypatch)
        proc.stdout.push("line one\n")
        proc.stdout.push(f"{ms.ERROR_SENTINEL}: Undefined function.\n")

        relayed: list[str] = []
        ok = sidecar.run_command("bogus_call()", relayed.append, timeout=2)

        assert ok is False
        assert relayed == ["line one\n", f"{ms.ERROR_SENTINEL}: Undefined function.\n"]

    def test_process_exit_without_sentinel_raises(self, monkeypatch):
        sidecar, proc = self._started_sidecar(monkeypatch)
        proc.stdout.push("some output\n")
        proc.stdout.close()  # EOF with no sentinel — process died

        with pytest.raises(RuntimeError, match="exited before completion"):
            sidecar.run_command("disp('hi')", lambda line: None, timeout=2)

    def test_timeout_raises(self, monkeypatch):
        sidecar, _proc = self._started_sidecar(monkeypatch)
        # No output pushed at all — run_command must give up, not hang.
        with pytest.raises(TimeoutError):
            sidecar.run_command("disp('hi')", lambda line: None, timeout=0.05)


class TestStop:
    def test_stop_kills_process_and_clears_running_state(self, monkeypatch):
        monkeypatch.setattr(ms.shutil, "which", lambda name: "/usr/local/bin/matlab")
        proc_holder: list[FakeProcess] = []

        def fake_popen(cmd, **kwargs):
            proc = FakeProcess()
            proc_holder.append(proc)
            return proc

        monkeypatch.setattr(ms.subprocess, "Popen", fake_popen)

        sidecar = ms.MatlabSidecar()
        sidecar.start()
        assert sidecar.is_running is True

        sidecar.stop()
        assert sidecar.is_running is False
        assert proc_holder[0].killed is True

    def test_stop_on_never_started_sidecar_is_a_noop(self):
        sidecar = ms.MatlabSidecar()
        sidecar.stop()  # must not raise
        assert sidecar.is_running is False


class TestSingletonAndCapability:
    def test_get_sidecar_returns_same_instance(self):
        a = ms.get_sidecar()
        b = ms.get_sidecar()
        assert a is b

    def test_sidecar_capable_reflects_which(self, monkeypatch):
        monkeypatch.setattr(ms.shutil, "which", lambda name: None)
        assert ms.sidecar_capable() is False
        monkeypatch.setattr(ms.shutil, "which", lambda name: "/usr/local/bin/matlab")
        assert ms.sidecar_capable() is True
