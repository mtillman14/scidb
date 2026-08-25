"""
Tests for execution_service's hidden-constant-value filtering (see
.claude/plan-constant-source-of-truth-26-08-22.md item 3).

The ConstantNode.tsx checkbox persists a hidden (const_name, value) pair
via pipeline_store.hide_parameter_value. This must actually stop the
combo(s) it implies from running, not just hide it from display -- both
derive_fn_targets (name-scoped, used for pipeline Run and the node_id-less
per-node Run) and derive_target_for_node (node-scoped, used for the
node_id-specific per-node Run and pipeline compilation) must filter it out,
for both a combo with real DB history and one that's never been run.
"""

from __future__ import annotations

import numpy as np
from scidb import BaseVariable

from scistack_gui import pipeline_store
from scistack_gui.db import get_db
from scistack_gui.services.execution_service import (
    derive_fn_targets,
    derive_target_for_node,
)


class TestDeriveFnTargetsHiddenConstantValues:
    def test_no_hidden_values_returns_real_history(self, populated_db):
        targets = derive_fn_targets(populated_db, "bandpass_filter")
        assert len(targets) == 1
        assert targets[0]["constants"] == {"low_hz": 20}

    def test_hidden_value_excludes_matching_target(self, populated_db):
        pipeline_store.hide_parameter_value(populated_db, "low_hz", "20")
        assert derive_fn_targets(populated_db, "bandpass_filter") == []

    def test_hidden_unrelated_value_keeps_target(self, populated_db):
        pipeline_store.hide_parameter_value(populated_db, "low_hz", "99")
        targets = derive_fn_targets(populated_db, "bandpass_filter")
        assert len(targets) == 1

    def test_unhide_restores_target(self, populated_db):
        pipeline_store.hide_parameter_value(populated_db, "low_hz", "20")
        pipeline_store.unhide_parameter_value(populated_db, "low_hz", "20")
        assert len(derive_fn_targets(populated_db, "bandpass_filter")) == 1


class TestDeriveTargetForNodeHiddenConstantValues:
    def test_no_hidden_values_returns_real_history(self, populated_db, bp_node_id):
        targets = derive_target_for_node(populated_db, bp_node_id)
        assert len(targets) == 1
        assert targets[0]["constants"] == {"low_hz": 20}

    def test_hidden_value_excludes_matching_target(self, populated_db, bp_node_id):
        pipeline_store.hide_parameter_value(populated_db, "low_hz", "20")
        assert derive_target_for_node(populated_db, bp_node_id) == []


class OtherSignal(BaseVariable):
    pass


class OtherFiltered(BaseVariable):
    pass


class TestNeverRunComboHiddenConstantValue:
    """A wiring that has never itself been run infers its constant's value
    from OTHER real call sites of the same function (see
    execution_service._infer_wired_constants) -- a hidden value must be
    excluded from that inferred combo too, not just from real DB history.
    """

    def test_inferred_known_value_excluded_when_hidden(self, client):
        OtherSignal.save(np.zeros(5), subject=1, session="pre")
        client.put(
            "/api/layout/mv_other_in",
            json={"x": 0, "y": 0, "node_type": "variableNode", "label": "OtherSignal"},
        )
        client.put(
            "/api/layout/mf_bp2",
            json={
                "x": 10,
                "y": 0,
                "node_type": "functionNode",
                "label": "bandpass_filter",
            },
        )
        client.put(
            "/api/layout/mv_other_out",
            json={"x": 20, "y": 0, "node_type": "variableNode", "label": "OtherFiltered"},
        )
        client.put(
            "/api/layout/mc_low_hz",
            json={"x": 5, "y": 5, "node_type": "parameterNode", "label": "low_hz"},
        )
        # Input edges name the parameter they feed; only output edges may
        # omit a handle (the target variable node IS the binding).
        client.put("/api/edges/e_in2", json={
            "source": "mv_other_in", "target": "mf_bp2", "target_handle": "in__signal",
        })
        client.put("/api/edges/e_out2", json={"source": "mf_bp2", "target": "mv_other_out"})
        client.put("/api/edges/e_low_hz", json={
            "source": "mc_low_hz", "target": "mf_bp2", "target_handle": "in__low_hz",
        })

        db = get_db()
        targets = derive_target_for_node(db, "mf_bp2")
        assert targets and targets[0]["constants"] == {"low_hz": 20}

        pipeline_store.hide_parameter_value(db, "low_hz", "20")
        assert derive_target_for_node(db, "mf_bp2") == []


class TestDbHistoryPathInputBinding:
    """A PathInput-driven function that has ALREADY RUN has no manual edge
    on the canvas — its PathInput→fn edge is synthesised from DB history by
    graph_builder.build_edges. So the run path cannot get its binding from
    manual edges alone, and (since name matching is gone) it would otherwise
    have nothing to resolve from at all.

    _db_path_input_params inverts get_aggregated_variants()["path_inputs"]
    (keyed by PARAM name, carrying the recorded spec) into per-call-site
    {param_name: declared_name}, reusing convert_scidb_path_inputs' existing
    spec→declared-name resolution. This is what keeps every already-run
    project working across the clean break.
    """

    @staticmethod
    def _with_path_input_history(db, monkeypatch, template: str, root_folder=None):
        """*db* with ONE recorded PathInput in its aggregated history.

        Patches the real database rather than substituting a stub: this code
        path also reads the D7 name history via pipeline_store, so a fake
        exposing only get_aggregated_variants isn't enough (and a stub that
        grew to cover both would just be a second, drifting implementation
        of the store).
        """
        monkeypatch.setattr(
            db,
            "get_aggregated_variants",
            lambda *a, **k: {
                "path_inputs": {
                    "filepath_or_buffer": {
                        "template": template,
                        "root_folder": root_folder,
                        "functions": [("read_csv_like", "call1")],
                    }
                }
            },
        )
        return db

    def test_declared_name_is_recovered_from_the_recorded_spec(
        self, populated_db, monkeypatch
    ):
        from scidb import PathInput

        from scistack_gui import registry
        from scistack_gui.services.execution_service import _db_path_input_params

        monkeypatch.setattr(
            registry,
            "get_path_inputs_registry",
            lambda: {"test_pi": PathInput("{subject}/data.csv")},
        )

        by_call = _db_path_input_params(
            self._with_path_input_history(populated_db, monkeypatch, "{subject}/data.csv"),
            "read_csv_like",
        )

        # The param it filled is remembered, and the spec resolves back to
        # the name it is declared under in source.
        assert by_call == {"call1": {"filepath_or_buffer": "test_pi"}}

    def test_other_functions_call_sites_are_not_included(
        self, populated_db, monkeypatch
    ):
        from scidb import PathInput

        from scistack_gui import registry
        from scistack_gui.services.execution_service import _db_path_input_params

        monkeypatch.setattr(
            registry,
            "get_path_inputs_registry",
            lambda: {"test_pi": PathInput("{subject}/data.csv")},
        )

        by_call = _db_path_input_params(
            self._with_path_input_history(populated_db, monkeypatch, "{subject}/data.csv"),
            "some_other_fn",
        )

        assert by_call == {}

    def test_history_targets_are_given_their_bindings(
        self, populated_db, monkeypatch
    ):
        from scidb import PathInput

        from scistack_gui import registry
        from scistack_gui.services.execution_service import _attach_db_path_inputs

        monkeypatch.setattr(
            registry,
            "get_path_inputs_registry",
            lambda: {"test_pi": PathInput("{subject}/data.csv")},
        )

        targets = [
            {"input_types": {}, "output_type": "Out", "constants": {}, "call_id": "call1"},
            {"input_types": {}, "output_type": "Out", "constants": {}, "call_id": "other"},
        ]
        result = _attach_db_path_inputs(
            self._with_path_input_history(populated_db, monkeypatch, "{subject}/data.csv"),
            "read_csv_like",
            targets,
        )

        from scistack_gui.domain.edge_resolver import (
            BINDING_PARAMETER,
            BINDING_PATHINPUT,
            bindings_of_kind,
        )

        assert bindings_of_kind(result[0]["bindings"], BINDING_PATHINPUT) == {
            "filepath_or_buffer": "test_pi"
        }
        # A call site with no recorded PathInput gets an empty binding, not
        # another call site's.
        assert bindings_of_kind(result[1]["bindings"], BINDING_PATHINPUT) == {}
        # History targets carry concrete recorded constants, so nothing needs
        # looking up in the Parameter registry.
        assert all(
            bindings_of_kind(t["bindings"], BINDING_PARAMETER) == {} for t in result
        )
