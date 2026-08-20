"""
Tests for scistack_gui.pipeline_discovery — Direction 1 of the source<->GUI
pipeline translation (source -> GUI import). See
docs/claude/code-discovery-categories.md and
.claude/plan-pathinput-sweep-submodule-source-of-truth.md.
"""

from __future__ import annotations

from scidb import BaseVariable, Pipeline
from scistack_gui import pipeline_store as ps
from scistack_gui.pipeline_discovery import discover_and_seed_pipelines


class RawA(BaseVariable):
    pass


class FilteredA(BaseVariable):
    pass


def _bandpass(signal, low_hz):
    return signal


def _register_step(pipe, fn, inputs, outputs):
    """Directly append a StepSpec, bypassing for_each's ambient-pipeline
    detection — the unit under test only cares about the resulting
    Pipeline.steps/.uses shape, not how they got there."""
    pipe.register_call(
        fn=fn, inputs=inputs, outputs=outputs, metadata_iterables={}, options={}
    )


class TestDiscoverAndSeedPipelines:
    def test_creates_pipeline_with_function_node_and_edges(self, populated_db):
        db = populated_db
        pipe = Pipeline("gait_analysis")
        _register_step(pipe, _bandpass, {"signal": RawA, "low_hz": 20}, [FilteredA])

        result = discover_and_seed_pipelines(db)
        assert result["created"] == ["gait_analysis"]
        assert result["skipped"] == []

        pipelines = {p["name"]: p["pipeline_id"] for p in ps.list_pipelines(db)}
        assert "gait_analysis" in pipelines
        pid = pipelines["gait_analysis"]

        nodes = ps.get_manual_nodes(db, pid)
        fn_nodes = [n for n in nodes.values() if n["type"] == "functionNode"]
        assert len(fn_nodes) == 1
        assert fn_nodes[0]["label"] == "_bandpass"

        # Manual variable/constant nodes are required, not just edges --
        # build_variable_nodes/build_constant_nodes only render from DB
        # history, so a never-run type/constant needs a manual node to
        # show up at all (see _seed_step's docstring).
        by_id = {**nodes}
        assert by_id["var__RawA"]["type"] == "variableNode"
        assert by_id["var__FilteredA"]["type"] == "variableNode"
        assert by_id["const__low_hz"]["type"] == "constantNode"

        edges = ps.get_manual_edges(db)
        sources = {e["source"] for e in edges}
        assert "var__RawA" in sources
        assert "const__low_hz" in sources
        assert any(e["target"] == "var__FilteredA" for e in edges)

    def test_discarded_from_scidb_bookkeeping_after_seeding(self, populated_db):
        from scidb.pipeline import _all_pipelines

        db = populated_db
        pipe = Pipeline("p1")
        _register_step(pipe, _bandpass, {"signal": RawA, "low_hz": 20}, [FilteredA])
        assert pipe in _all_pipelines

        discover_and_seed_pipelines(db)
        assert pipe not in _all_pipelines

    def test_second_call_finds_nothing_new(self, populated_db):
        db = populated_db
        pipe = Pipeline("p2")
        _register_step(pipe, _bandpass, {"signal": RawA, "low_hz": 20}, [FilteredA])
        discover_and_seed_pipelines(db)

        result = discover_and_seed_pipelines(db)
        assert result == {"created": [], "skipped": []}

    def test_existing_local_pipeline_is_skipped_not_overwritten(self, populated_db):
        """'Create once' — matches create_variable/create_path_input's
        precedent, never overwrites hand-edited GUI state."""
        db = populated_db
        ps.create_pipeline(db, "existing")

        pipe = Pipeline("existing")
        _register_step(pipe, _bandpass, {"signal": RawA, "low_hz": 20}, [FilteredA])

        result = discover_and_seed_pipelines(db)
        assert result == {"created": [], "skipped": ["existing"]}

        pipelines = ps.list_pipelines(db)
        assert len([p for p in pipelines if p["name"] == "existing"]) == 1
        pid = next(p["pipeline_id"] for p in pipelines if p["name"] == "existing")
        assert ps.get_manual_nodes(db, pid) == {}  # untouched, no nodes seeded

    def test_compiled_pipeline_with_db_is_never_a_discovery_candidate(
        self, populated_db
    ):
        """execution_service.build_backend_pipeline's own per-request
        compiled Pipelines always set db= -- must never be mistaken for a
        source-authored pipeline (see module docstring)."""
        db = populated_db
        pipe = Pipeline("compiled_lookalike", db=db)
        _register_step(pipe, _bandpass, {"signal": RawA, "low_hz": 20}, [FilteredA])

        result = discover_and_seed_pipelines(db)
        assert result == {"created": [], "skipped": []}
        pipe.discard()

    def test_scalar_constant_wired_with_pending_value(self, populated_db):
        db = populated_db
        pipe = Pipeline("const_pipe")
        _register_step(pipe, _bandpass, {"signal": RawA, "low_hz": 42}, [FilteredA])

        discover_and_seed_pipelines(db)

        pending = ps.get_pending_constants(db)
        assert "42" in pending.get("low_hz", set())
        edges = ps.get_manual_edges(db)
        assert any(e["source"] == "const__low_hz" for e in edges)

    def test_recursive_uses_creates_child_and_binding(self, populated_db):
        db = populated_db
        child = Pipeline("loading")
        _register_step(child, _bandpass, {"signal": RawA, "low_hz": 20}, [FilteredA])

        Pipeline("analysis", uses=[child])

        result = discover_and_seed_pipelines(db)
        assert set(result["created"]) == {"loading", "analysis"}

        pipelines = {p["name"]: p["pipeline_id"] for p in ps.list_pipelines(db)}
        uses = ps.get_pipeline_uses(db, pipelines["analysis"])
        assert len(uses) == 1
        assert uses[0]["child_pipeline_id"] == pipelines["loading"]

    def test_use_of_already_local_child_reuses_it(self, populated_db):
        """A used pipeline that already exists locally is reused by id, not
        recreated -- the parent's use edge still gets wired correctly."""
        db = populated_db
        existing_child_id = ps.create_pipeline(db, "shared_prep")

        child = Pipeline("shared_prep")
        Pipeline("analysis3", uses=[child])

        result = discover_and_seed_pipelines(db)
        assert result["created"] == ["analysis3"]
        assert result["skipped"] == ["shared_prep"]

        pipelines = {p["name"]: p["pipeline_id"] for p in ps.list_pipelines(db)}
        uses = ps.get_pipeline_uses(db, pipelines["analysis3"])
        assert uses[0]["child_pipeline_id"] == existing_child_id

    def test_bound_use_carries_key_map_and_iterate_into_binding(self, populated_db):
        db = populated_db
        child = Pipeline("loading2")
        _register_step(child, _bandpass, {"signal": RawA, "low_hz": 20}, [FilteredA])

        Pipeline(
            "analysis2",
            uses=[
                child.bind(
                    key_map={"subject": "participant"},
                    iterate={"participant": ["1", "2"]},
                )
            ],
        )

        discover_and_seed_pipelines(db)

        pipelines = {p["name"]: p["pipeline_id"] for p in ps.list_pipelines(db)}
        uses = ps.get_pipeline_uses(db, pipelines["analysis2"])
        assert uses[0]["binding"]["key_map"] == {"subject": "participant"}
        assert uses[0]["binding"]["iterate"] == {"participant": ["1", "2"]}

    def test_named_pathinput_wires_by_registered_name_not_param(self, populated_db):
        from scidb import PathInput
        from scistack_gui import registry

        db = populated_db
        raw_emg = PathInput("{subject}/{trial}.mat")
        registry._path_inputs["RAW_EMG"] = raw_emg
        registry._path_input_sources["RAW_EMG"] = "test"

        def _loader(filepath):
            return filepath

        pipe = Pipeline("loader_pipe")
        _register_step(pipe, _loader, {"filepath": raw_emg}, [FilteredA])

        discover_and_seed_pipelines(db)

        edges = ps.get_manual_edges(db)
        assert any(e["source"] == "pathInput__RAW_EMG" for e in edges)

    def test_unnamed_pathinput_falls_back_to_param_name(self, populated_db):
        from scidb import PathInput

        db = populated_db

        def _loader(filepath):
            return filepath

        pipe = Pipeline("loader_pipe2")
        _register_step(
            pipe, _loader, {"filepath": PathInput("{subject}.mat")}, [FilteredA]
        )

        discover_and_seed_pipelines(db)

        edges = ps.get_manual_edges(db)
        assert any(e["source"] == "pathInput__filepath" for e in edges)

    def test_named_sweep_wires_by_registered_name(self, populated_db):
        from scidb import Sweep
        from scistack_gui import registry

        db = populated_db
        window = Sweep(10, 20, 30)
        registry._sweeps["WINDOW"] = window
        registry._sweep_sources["WINDOW"] = "test"

        def _fn(window_seconds):
            return window_seconds

        pipe = Pipeline("sweep_pipe")
        _register_step(pipe, _fn, {"window_seconds": window}, [FilteredA])

        discover_and_seed_pipelines(db)

        edges = ps.get_manual_edges(db)
        assert any(e["source"] == "sweep__WINDOW" for e in edges)

    def test_no_candidates_is_a_cheap_noop(self, populated_db):
        result = discover_and_seed_pipelines(populated_db)
        assert result == {"created": [], "skipped": []}
