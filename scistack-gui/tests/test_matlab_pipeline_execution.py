"""
Tests for whole-pipeline MATLAB execution routing
(plan-matlab-pipeline-execution.md, Stages 1-4):

- matlab_command_service.generate_matlab_pipeline_command (Stage 1's
  service-layer wrapper — DB-backed resolution feeding the pure-string
  generator already unit-tested in test_matlab.py).
- execution_service.pipeline_has_matlab_steps + start_pipeline_run's
  MATLAB routing, both the VS Code/JSON-RPC signal path (Stage 2) and the
  standalone-sidecar path (Stage 3; MatlabSidecar itself is unit-tested
  separately in test_matlab_sidecar.py — here it's mocked at the
  get_sidecar() seam to verify start_pipeline_run wires it correctly).
- start_matlab_sidecar_run (Stage 4's fallback-ladder Tier 3, called from
  dagPanel.ts when the MathWorks terminal isn't available).

No real MATLAB environment in this sandbox — matlab_registry is just a
plain dict, so a fake registration exercises the real resolution code
paths without needing one (same approach as test_code_export.py).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from scidb import BaseVariable
from scistack_gui import matlab_registry
from scistack_gui.db import get_db
from scistack_gui.matlab_parser import MatlabFunctionInfo


def _wait_for_threads(prefix: str, timeout: float = 2.0) -> None:
    """Wait for any background run threads to finish before DB teardown
    (mirrors test_api.py's helper — a MATLAB-routed run must NOT spawn one
    of these; a Python-only run still does)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        live = [t for t in threading.enumerate() if t.name.startswith(prefix)]
        if not live:
            break
        time.sleep(0.05)


class MatlabOutput(BaseVariable):
    pass


def _register_fake_matlab_fn(name: str, params: list[str]) -> None:
    matlab_registry._matlab_functions[name] = MatlabFunctionInfo(
        name=name, file_path=Path(f"{name}.m"), params=params, source_hash="deadbeef",
    )


def _build_matlab_only_scope(client, pid: str, fn_name: str = "matlab_proc") -> None:
    """Mirrors test_code_export.py's TestMatlabCodeExport setup: a fresh
    scope with one MATLAB function node, wired and given a real target
    (constant edge + pending value) so derive_target_for_node resolves it."""
    client.put("/api/layout/mv_in", json={
        "x": 0, "y": 0, "node_type": "variableNode", "label": "RawSignal", "pipeline_id": pid,
    })
    client.put(f"/api/layout/mf_a", json={
        "x": 10, "y": 0, "node_type": "functionNode", "label": fn_name, "pipeline_id": pid,
    })
    client.put("/api/layout/mv_out", json={
        "x": 20, "y": 0, "node_type": "variableNode", "label": "MatlabOutput", "pipeline_id": pid,
    })
    client.put("/api/edges/e_in", json={"source": "mv_in", "target": "mf_a"})
    client.put("/api/edges/e_out", json={"source": "mf_a", "target": "mv_out"})
    client.put("/api/layout/mc_gain", json={
        "x": 5, "y": 5, "node_type": "constantNode", "label": "gain", "pipeline_id": pid,
    })
    client.put("/api/edges/e_gain", json={"source": "mc_gain", "target": "mf_a"})
    client.put("/api/constants/gain/pending/2.5")


class TestPipelineHasMatlabSteps:
    def test_pure_python_scope_is_false(self, client):
        from scistack_gui.services.execution_service import pipeline_has_matlab_steps

        assert pipeline_has_matlab_steps(get_db(), "main") is False

    def test_matlab_scope_is_true(self, client):
        from scistack_gui.services.execution_service import pipeline_has_matlab_steps

        _register_fake_matlab_fn("matlab_proc", ["signal", "gain"])
        try:
            pid = client.post(
                "/api/pipelines", json={"name": "matlab_only"}
            ).json()["pipeline_id"]
            _build_matlab_only_scope(client, pid)
            assert pipeline_has_matlab_steps(get_db(), pid) is True
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)

    def test_used_child_pipeline_with_matlab_step_detected(self, client):
        """A MATLAB step buried in a `uses`-composed child scope must still
        be detected — build_backend_pipeline recursively compiles used
        pipelines too, so the routing check must match that closure."""
        from scistack_gui.services.execution_service import pipeline_has_matlab_steps

        _register_fake_matlab_fn("matlab_proc", ["signal", "gain"])
        try:
            child_pid = client.post(
                "/api/pipelines", json={"name": "matlab_child"}
            ).json()["pipeline_id"]
            _build_matlab_only_scope(client, child_pid)

            parent_pid = client.post(
                "/api/pipelines", json={"name": "parent"}
            ).json()["pipeline_id"]
            r = client.post(
                f"/api/pipelines/{parent_pid}/uses",
                json={"child_pipeline_id": child_pid},
            )
            assert r.status_code == 200

            assert pipeline_has_matlab_steps(get_db(), parent_pid) is True
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
class TestStartPipelineRunMatlabRouting:
    def test_matlab_pipeline_returns_host_execution_required(self, client):
        from scistack_gui.api.run import start_pipeline_run

        _register_fake_matlab_fn("matlab_proc", ["signal", "gain"])
        try:
            pid = client.post(
                "/api/pipelines", json={"name": "matlab_only"}
            ).json()["pipeline_id"]
            _build_matlab_only_scope(client, pid)

            result = start_pipeline_run(
                pid, mode="all", run_id="rid_matlab", host_can_dispatch_matlab=True
            )
            assert result == {
                "run_id": "rid_matlab",
                "host_execution_required": True,
                "language": "matlab",
            }
            # No background thread spawned for the MATLAB-routed path.
            live = [t for t in threading.enumerate() if t.name.startswith("Thread-")]
            assert live == []
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)

    def test_matlab_pipeline_show_mode_rejected(self, client):
        from scistack_gui.api.run import start_pipeline_run

        _register_fake_matlab_fn("matlab_proc", ["signal", "gain"])
        try:
            pid = client.post(
                "/api/pipelines", json={"name": "matlab_only"}
            ).json()["pipeline_id"]
            _build_matlab_only_scope(client, pid)

            with pytest.raises(ValueError, match="show"):
                start_pipeline_run(pid, mode="show", target="matlab_proc")
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)

    def test_pure_python_pipeline_unaffected(self, client):
        """The existing Python pipeline-run path (main, conftest-seeded
        bandpass_filter) must still spawn its normal background thread —
        this routing change must not regress it."""
        from scistack_gui.api.run import start_pipeline_run

        result = start_pipeline_run("main", mode="all", run_id="rid_python")
        assert result == {"run_id": "rid_python"}
        _wait_for_threads("Thread-")


class TestGenerateMatlabPipelineCommandService:
    """matlab_command_service.generate_matlab_pipeline_command — the
    DB-backed resolution layer feeding api.matlab_command's pure string
    generator (already unit-tested directly in test_matlab.py)."""

    def test_resolves_matlab_scope_into_pipeline_wrapped_script(self, client):
        from scistack_gui.services.matlab_command_service import (
            generate_matlab_pipeline_command,
        )

        _register_fake_matlab_fn("matlab_proc", ["signal", "gain"])
        try:
            pid = client.post(
                "/api/pipelines", json={"name": "matlab_only"}
            ).json()["pipeline_id"]
            _build_matlab_only_scope(client, pid)

            result = generate_matlab_pipeline_command(pid, get_db(), {"mode": "all"})
            assert result["warnings"] == []
            cmd = result["command"]
            assert f"pipe = scidb.Pipeline('{pid}');" in cmd
            assert "scidb.for_each(@matlab_proc, " in cmd
            assert "'signal', RawSignal()" in cmd
            assert "'gain', 2.5" in cmd
            assert "{MatlabOutput()}" in cmd
            assert "pipe.run_all(" in cmd
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)

    def test_python_nodes_in_scope_reported_as_warnings(self, client):
        """A Python function node co-scoped with a MATLAB one must be
        excluded from the script (not silently mis-registered) and
        surfaced back to the caller as a warning."""
        from scistack_gui.services.matlab_command_service import (
            generate_matlab_pipeline_command,
        )

        _register_fake_matlab_fn("matlab_proc", ["signal", "gain"])
        try:
            pid = client.post(
                "/api/pipelines", json={"name": "mixed"}
            ).json()["pipeline_id"]
            _build_matlab_only_scope(client, pid)
            # bandpass_filter is registered as a real Python function by
            # conftest — add it to the same scope, wired independently.
            client.put("/api/layout/pv_in", json={
                "x": 0, "y": 40, "node_type": "variableNode", "label": "RawSignal", "pipeline_id": pid,
            })
            client.put("/api/layout/pf_a", json={
                "x": 10, "y": 40, "node_type": "functionNode", "label": "bandpass_filter", "pipeline_id": pid,
            })
            client.put("/api/layout/pv_out", json={
                "x": 20, "y": 40, "node_type": "variableNode", "label": "FilteredSignal", "pipeline_id": pid,
            })
            client.put("/api/edges/pe_in", json={"source": "pv_in", "target": "pf_a"})
            client.put("/api/edges/pe_out", json={"source": "pf_a", "target": "pv_out"})
            client.put("/api/layout/pc_low_hz", json={
                "x": 5, "y": 45, "node_type": "constantNode", "label": "low_hz", "pipeline_id": pid,
            })
            client.put("/api/edges/pe_low_hz", json={"source": "pc_low_hz", "target": "pf_a"})
            client.put("/api/constants/low_hz/pending/20")

            result = generate_matlab_pipeline_command(pid, get_db(), {"mode": "all"})
            assert len(result["warnings"]) == 1
            assert "bandpass_filter" in result["warnings"][0]
            cmd = result["command"]
            assert "@matlab_proc" in cmd
            assert "@bandpass_filter" not in cmd
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
class TestStandaloneSidecarRouting:
    """start_pipeline_run's default (host_can_dispatch_matlab=False) path —
    the browser/standalone counterpart to TestStartPipelineRunMatlabRouting
    above, which exercises the VS Code/JSON-RPC host_can_dispatch_matlab=True
    signal path. MatlabSidecar itself is unit-tested in
    test_matlab_sidecar.py; here it's mocked at the get_sidecar() seam to
    verify start_pipeline_run's wiring (script generation -> sidecar ->
    run_output/run_done)."""

    def test_default_routes_through_sidecar_thread(self, client, monkeypatch):
        from scistack_gui import matlab_sidecar
        from scistack_gui.api.run import start_pipeline_run

        _register_fake_matlab_fn("matlab_proc", ["signal", "gain"])
        try:
            pid = client.post(
                "/api/pipelines", json={"name": "matlab_only"}
            ).json()["pipeline_id"]
            _build_matlab_only_scope(client, pid)

            class FakeSidecar:
                def __init__(self):
                    self.started = False
                    self.commands: list[str] = []

                def start(self):
                    self.started = True
                    return True

                def run_command(self, command, on_line, timeout=None):
                    self.commands.append(command)
                    on_line("MATLAB output line\n")
                    return True

            fake = FakeSidecar()
            monkeypatch.setattr(matlab_sidecar, "get_sidecar", lambda: fake)

            result = start_pipeline_run(pid, mode="all", run_id="rid_sidecar")
            assert result == {"run_id": "rid_sidecar"}

            _wait_for_threads("Thread-")
            assert fake.started is True
            assert len(fake.commands) == 1
            assert "@matlab_proc" in fake.commands[0]
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)

    def test_matlab_unavailable_reports_error_without_crashing(self, client, monkeypatch):
        from scistack_gui import matlab_sidecar
        from scistack_gui.api.run import start_pipeline_run

        _register_fake_matlab_fn("matlab_proc", ["signal", "gain"])
        try:
            pid = client.post(
                "/api/pipelines", json={"name": "matlab_only"}
            ).json()["pipeline_id"]
            _build_matlab_only_scope(client, pid)

            class UnavailableSidecar:
                def start(self):
                    return False

            monkeypatch.setattr(
                matlab_sidecar, "get_sidecar", lambda: UnavailableSidecar()
            )

            result = start_pipeline_run(pid, mode="all", run_id="rid_unavailable")
            assert result == {"run_id": "rid_unavailable"}
            _wait_for_threads("Thread-")
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)

    def test_host_can_dispatch_matlab_skips_sidecar(self, client, monkeypatch):
        """The VS Code/JSON-RPC path (host_can_dispatch_matlab=True) must
        never touch the sidecar — dagPanel.ts owns dispatch there."""
        from scistack_gui import matlab_sidecar
        from scistack_gui.api.run import start_pipeline_run

        _register_fake_matlab_fn("matlab_proc", ["signal", "gain"])
        try:
            pid = client.post(
                "/api/pipelines", json={"name": "matlab_only"}
            ).json()["pipeline_id"]
            _build_matlab_only_scope(client, pid)

            def boom():
                raise AssertionError("get_sidecar should not be called")

            monkeypatch.setattr(matlab_sidecar, "get_sidecar", boom)

            result = start_pipeline_run(
                pid, mode="all", run_id="rid_host", host_can_dispatch_matlab=True
            )
            assert result == {
                "run_id": "rid_host",
                "host_execution_required": True,
                "language": "matlab",
            }
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
class TestStartMatlabSidecarRun:
    """Stage 4's fallback-ladder Tier 3: start_matlab_sidecar_run, called
    from dagPanel.ts's dispatchMatlabCommand when the MathWorks terminal
    isn't available (works for BOTH a single-function command and a
    whole-pipeline command — this function is transport-agnostic, just
    text)."""

    def test_reports_unavailable_without_spawning_a_thread(self, monkeypatch):
        from scistack_gui import matlab_sidecar
        from scistack_gui.api.run import start_matlab_sidecar_run

        monkeypatch.setattr(matlab_sidecar, "sidecar_capable", lambda: False)

        result = start_matlab_sidecar_run("disp('hi')", "rid_1")
        assert result == {"run_id": "rid_1", "sidecar_available": False}

        live = [t for t in threading.enumerate() if t.name.startswith("Thread-")]
        assert live == []

    def test_available_spawns_thread_and_drives_sidecar(self, monkeypatch):
        from scistack_gui import matlab_sidecar
        from scistack_gui.api.run import start_matlab_sidecar_run

        monkeypatch.setattr(matlab_sidecar, "sidecar_capable", lambda: True)

        class FakeSidecar:
            def __init__(self):
                self.commands: list[str] = []

            def start(self):
                return True

            def run_command(self, command, on_line, timeout=None):
                self.commands.append(command)
                on_line("MATLAB output\n")
                return True

        fake = FakeSidecar()
        monkeypatch.setattr(matlab_sidecar, "get_sidecar", lambda: fake)

        result = start_matlab_sidecar_run(
            "disp('hi')", "rid_2", warnings=["a python node was excluded"]
        )
        assert result == {"run_id": "rid_2", "sidecar_available": True}

        _wait_for_threads("Thread-")
        assert fake.commands == ["disp('hi')"]
