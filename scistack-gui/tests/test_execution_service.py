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
        client.put("/api/edges/e_in2", json={"source": "mv_other_in", "target": "mf_bp2"})
        client.put("/api/edges/e_out2", json={"source": "mf_bp2", "target": "mv_other_out"})
        client.put("/api/edges/e_low_hz", json={"source": "mc_low_hz", "target": "mf_bp2"})

        db = get_db()
        targets = derive_target_for_node(db, "mf_bp2")
        assert targets and targets[0]["constants"] == {"low_hz": 20}

        pipeline_store.hide_parameter_value(db, "low_hz", "20")
        assert derive_target_for_node(db, "mf_bp2") == []
