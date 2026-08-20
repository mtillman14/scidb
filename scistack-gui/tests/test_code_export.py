"""
Tests for scistack_gui.services.code_export_service (to-do #6: translate
pipelines to Python/MATLAB — plan-pipeline-to-code-export.md).

Python generator tests exercise the real thing end-to-end against
conftest's seeded bandpass_filter wiring. MATLAB generator tests register
a FAKE MATLAB function (matlab_registry is just a plain dict — no real
MATLAB environment needed to exercise the resolution/serialization code
paths) since this sandbox has no MATLAB to verify against; the pure
serialization/topo-sort helpers also get direct unit coverage since
they're the genuinely new (not-reused-from-execution_service) code.
"""

from __future__ import annotations

import pytest
from scistack_gui.db import get_db
from scistack_gui.services.code_export_service import (
    _matlab_literal,
    _matlab_struct,
    _py_literal,
    _topo_sort_targets,
    export_pipeline_to_code,
)


class TestPythonCodeExport:
    def test_generates_for_each_call_matching_seeded_wiring(self, client):
        result = export_pipeline_to_code(get_db(), "main")
        assert result["language"] == "python"
        assert result["warnings"] == []

        script = result["script"]
        assert "configure_database(" in script
        assert "for_each(bandpass_filter, " in script
        assert "'signal': RawSignal" in script
        assert "'low_hz': 20" in script
        assert "[FilteredSignal]" in script
        # Iteration kwargs: the seeded schema (subject in {1,2}, session in {pre,post}).
        assert "'subject':" in script
        assert "'session':" in script

    def test_disconnected_wiring_becomes_a_skip_comment(self, client):
        """Hiding the seeded bandpass_filter's input edge must not vanish
        the step from the script silently — see gui-export-to-plain-
        python.md's warn-comment recommendation, reused verbatim via
        execution_service.disconnected_report_entries."""
        db = get_db()
        graph = client.get("/api/pipeline").json()
        edge = next(
            e for e in graph["edges"]
            if any(n["id"] == e["source"] and n["data"]["label"] == "RawSignal" for n in graph["nodes"])
        )
        r = client.delete(f"/api/edges/{edge['id']}")
        assert r.status_code == 200

        result = export_pipeline_to_code(db, "main")
        assert "for_each(bandpass_filter" not in result["script"]
        assert "SKIPPED: 'bandpass_filter'" in result["script"]
        assert len(result["warnings"]) == 1
        assert "bandpass_filter" in result["warnings"][0]

    def test_writes_file_to_exports_dir(self, client):
        from pathlib import Path

        result = export_pipeline_to_code(get_db(), "main")
        path = Path(result["path"])
        assert path.exists()
        assert path.parent.name == "exports"
        assert path.suffix == ".py"
        assert path.read_text() == result["script"]


class TestMixedLanguageUnsupported:
    def test_mixed_python_and_matlab_raises(self, client):
        from pathlib import Path

        from scistack_gui import matlab_registry
        from scistack_gui.matlab_parser import MatlabFunctionInfo

        matlab_registry._matlab_functions["matlab_proc"] = MatlabFunctionInfo(
            name="matlab_proc", file_path=Path("matlab_proc.m"),
            params=["signal"], source_hash="deadbeef",
        )
        try:
            client.put("/api/layout/mv_x", json={
                "x": 0, "y": 0, "node_type": "variableNode", "label": "FilteredSignal",
            })
            client.put("/api/layout/mf_x", json={
                "x": 10, "y": 0, "node_type": "functionNode", "label": "matlab_proc",
            })
            client.put("/api/layout/mv_y", json={
                "x": 20, "y": 0, "node_type": "variableNode", "label": "MatlabOutput",
            })
            client.put("/api/edges/e_x_in", json={"source": "mv_x", "target": "mf_x"})
            client.put("/api/edges/e_x_out", json={"source": "mf_x", "target": "mv_y"})

            with pytest.raises(ValueError, match="mixed-language"):
                export_pipeline_to_code(get_db(), "main")
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)

    def test_mixed_language_is_400_via_api(self, client):
        from pathlib import Path

        from scistack_gui import matlab_registry
        from scistack_gui.matlab_parser import MatlabFunctionInfo

        matlab_registry._matlab_functions["matlab_proc"] = MatlabFunctionInfo(
            name="matlab_proc", file_path=Path("matlab_proc.m"),
            params=["signal"], source_hash="deadbeef",
        )
        try:
            client.put("/api/layout/mv_x", json={
                "x": 0, "y": 0, "node_type": "variableNode", "label": "FilteredSignal",
            })
            client.put("/api/layout/mf_x", json={
                "x": 10, "y": 0, "node_type": "functionNode", "label": "matlab_proc",
            })
            client.put("/api/layout/mv_y", json={
                "x": 20, "y": 0, "node_type": "variableNode", "label": "MatlabOutput",
            })
            client.put("/api/edges/e_x_in", json={"source": "mv_x", "target": "mf_x"})
            client.put("/api/edges/e_x_out", json={"source": "mf_x", "target": "mv_y"})

            r = client.get("/api/pipelines/main/export-code")
            assert r.status_code == 400
            assert "mixed-language" in r.json()["detail"]
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)


class TestMatlabCodeExport:
    """No real MATLAB environment in this sandbox — matlab_registry is
    just a plain dict, so a fake registration exercises the real
    resolution/serialization code paths without needing one."""

    def test_all_matlab_pipeline_generates_native_script(self, client):
        """Uses a fresh scope, not 'main' — 'main' always carries the
        conftest-seeded (Python) bandpass_filter, which would make this a
        mixed-language closure instead of the all-MATLAB case under test."""
        from pathlib import Path

        from scidb import BaseVariable
        from scistack_gui import matlab_registry
        from scistack_gui.matlab_parser import MatlabFunctionInfo

        class MatlabOutput(BaseVariable):
            pass

        matlab_registry._matlab_functions["matlab_proc"] = MatlabFunctionInfo(
            name="matlab_proc", file_path=Path("matlab_proc.m"),
            params=["signal", "gain"], source_hash="deadbeef",
        )
        try:
            pid = client.post("/api/pipelines", json={"name": "matlab_only"}).json()["pipeline_id"]
            client.put("/api/layout/mv_in", json={
                "x": 0, "y": 0, "node_type": "variableNode", "label": "RawSignal", "pipeline_id": pid,
            })
            client.put("/api/layout/mf_a", json={
                "x": 10, "y": 0, "node_type": "functionNode", "label": "matlab_proc", "pipeline_id": pid,
            })
            client.put("/api/layout/mv_out", json={
                "x": 20, "y": 0, "node_type": "variableNode", "label": "MatlabOutput", "pipeline_id": pid,
            })
            client.put("/api/edges/e_in", json={"source": "mv_in", "target": "mf_a"})
            client.put("/api/edges/e_out", json={"source": "mf_a", "target": "mv_out"})
            # A pending value ALONE isn't enough — derive_target_for_node's
            # never-run-fallback resolves constants from WIRING
            # (edge_resolver.resolve_function_edges: an edge from a
            # constantNode into the function), not just a staged pending
            # value with no edge at all.
            client.put("/api/layout/mc_gain", json={
                "x": 5, "y": 5, "node_type": "constantNode", "label": "gain", "pipeline_id": pid,
            })
            client.put("/api/edges/e_gain", json={"source": "mc_gain", "target": "mf_a"})
            client.put("/api/constants/gain/pending/2.5")

            result = export_pipeline_to_code(get_db(), pid)
            assert result["language"] == "matlab"
            script = result["script"]
            assert "scidb.configure_database(" in script
            assert "scidb.for_each(@matlab_proc, " in script
            assert "'signal', RawSignal()" in script
            assert "'gain', 2.5" in script
            assert "{MatlabOutput()}" in script
        finally:
            matlab_registry._matlab_functions.pop("matlab_proc", None)


class TestSerializationHelpers:
    """Pure functions — the genuinely NEW code this feature adds (target/
    input resolution itself is reused from execution_service)."""

    def test_py_literal_bare_class_vs_scalar(self):
        class RawSignal:
            pass

        assert _py_literal(RawSignal) == "RawSignal"
        assert _py_literal(20) == "20"
        assert _py_literal("x") == "'x'"
        assert _py_literal(True) == "True"

    def test_matlab_literal_class_becomes_constructed_instance(self):
        class RawSignal:
            pass

        assert _matlab_literal(RawSignal) == "RawSignal()"

    def test_matlab_literal_scalar_and_string(self):
        assert _matlab_literal(20) == "20"
        assert _matlab_literal(2.5) == "2.5"
        assert _matlab_literal(True) == "true"
        assert _matlab_literal(False) == "false"
        assert _matlab_literal("A") == '"A"'

    def test_matlab_literal_each_of(self):
        class EachOfStub:
            def __init__(self, *alts):
                self.alternatives = list(alts)

        class RawSignal:
            pass

        each = EachOfStub(RawSignal, 20)
        assert _matlab_literal(each) == "scifor.EachOf(RawSignal(), 20)"

    def test_matlab_literal_real_sweep_duck_types_as_each_of(self):
        """A real scidb.Sweep (not a stub) -- confirms the new Sweep class
        needed zero changes here: it duck-types via .alternatives exactly
        like a bare EachOf, so it renders as scifor.EachOf(...) (de-sugared
        -- Sweep has no distinct MATLAB literal form, same as Python's own
        repr(), see docs/claude/code-discovery-categories.md)."""
        from scidb import Sweep

        window = Sweep(10, 20, 30)
        assert _matlab_literal(window) == "scifor.EachOf(10, 20, 30)"

    def test_matlab_literal_real_path_input(self):
        from scidb import PathInput

        pi = PathInput("{subject}/{trial}.mat")
        assert (
            _matlab_literal(pi) == 'scifor.PathInput("{subject}/{trial}.mat")'
        )

    def test_matlab_literal_real_path_input_with_root_folder(self):
        from scidb import PathInput

        pi = PathInput("{subject}.mat", root_folder="/data")
        assert (
            _matlab_literal(pi)
            == 'scifor.PathInput("{subject}.mat", \'root_folder\', "/data")'
        )

    def test_py_literal_real_sweep_reprs_as_each_of(self):
        """Same de-sugaring on the Python side -- repr(Sweep(...)) prints
        "EachOf(...)" (Sweep doesn't override __repr__), which is still
        perfectly valid, runnable Python since EachOf is already imported
        in every generated script's header."""
        from scidb import Sweep

        window = Sweep(10, 20, 30)
        assert _py_literal(window) == "EachOf(10, 20, 30)"

    def test_py_literal_real_path_input(self):
        from scidb import PathInput

        pi = PathInput("{subject}/{trial}.mat")
        assert _py_literal(pi) == repr(pi)
        assert "PathInput" in _py_literal(pi)
        assert "{subject}/{trial}.mat" in _py_literal(pi)

    def test_matlab_struct_empty_and_nonempty(self):
        assert _matlab_struct({}) == "struct()"
        assert _matlab_struct({"low_hz": 20}) == "struct('low_hz', 20)"

    def test_topo_sort_orders_by_type_dependency(self):
        # fn_b consumes what fn_a produces -> fn_a must come first.
        steps = [
            ("fn_b", {"input_types": {"x": "Produced"}, "output_type": "Final", "constants": {}}),
            ("fn_a", {"input_types": {"x": "Raw"}, "output_type": "Produced", "constants": {}}),
        ]
        order = _topo_sort_targets(steps)
        names_in_order = [steps[i][0] for i in order]
        assert names_in_order.index("fn_a") < names_in_order.index("fn_b")

    def test_topo_sort_raises_on_cycle(self):
        steps = [
            ("fn_a", {"input_types": {"x": "B"}, "output_type": "A", "constants": {}}),
            ("fn_b", {"input_types": {"x": "A"}, "output_type": "B", "constants": {}}),
        ]
        with pytest.raises(ValueError, match="cycle"):
            _topo_sort_targets(steps)
