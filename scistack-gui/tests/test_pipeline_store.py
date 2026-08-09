"""
Unit tests for scistack_gui.pipeline_store's hidden-combo and hidden-edge
primitives.

Hiding must never delete data -- these tests confirm hide_combo/unhide_combo
compose with (not duplicate) the existing hide_node/unhide_node hidden-set,
and that the structural variant_key survives a hide/unhide round trip. The
hidden-edges table (hide_edge/unhide_edge) is its own independent set --
hiding an edge keeps the node itself on screen (red), unlike hiding a node.
"""

from scistack_gui import pipeline_store


class TestHiddenCombos:
    def test_hide_combo_lands_in_hidden_node_ids(self, populated_db):
        db = populated_db
        node_id = "fn__bandpass_filter__abc123"
        pipeline_store.hide_combo(db, node_id, "bandpass_filter", {"low_hz": "20"})
        assert node_id in pipeline_store.get_hidden_node_ids(db)

    def test_list_hidden_combos_round_trip(self, populated_db):
        db = populated_db
        node_id = "fn__bandpass_filter__abc123"
        pipeline_store.hide_combo(db, node_id, "bandpass_filter", {"low_hz": "20"})
        combos = pipeline_store.list_hidden_combos(db, "bandpass_filter")
        assert combos == [{"node_id": node_id, "variant_key": {"low_hz": "20"}}]

    def test_list_hidden_combos_scoped_to_function(self, populated_db):
        db = populated_db
        pipeline_store.hide_combo(
            db, "fn__bandpass_filter__abc123", "bandpass_filter", {"low_hz": "20"}
        )
        pipeline_store.hide_combo(db, "fn__other_fn__def456", "other_fn", {"k": "1"})
        combos = pipeline_store.list_hidden_combos(db, "bandpass_filter")
        assert len(combos) == 1
        assert combos[0]["node_id"] == "fn__bandpass_filter__abc123"

    def test_unhide_combo_removes_from_both_tables(self, populated_db):
        db = populated_db
        node_id = "fn__bandpass_filter__abc123"
        pipeline_store.hide_combo(db, node_id, "bandpass_filter", {"low_hz": "20"})
        pipeline_store.unhide_combo(db, node_id)
        assert node_id not in pipeline_store.get_hidden_node_ids(db)
        assert pipeline_store.list_hidden_combos(db, "bandpass_filter") == []

    def test_hide_combo_idempotent(self, populated_db):
        db = populated_db
        node_id = "fn__bandpass_filter__abc123"
        pipeline_store.hide_combo(db, node_id, "bandpass_filter", {"low_hz": "20"})
        pipeline_store.hide_combo(db, node_id, "bandpass_filter", {"low_hz": "20"})
        assert len(pipeline_store.list_hidden_combos(db, "bandpass_filter")) == 1

    def test_unhide_node_alone_leaves_stale_structural_row(self, populated_db):
        """Calling the OLD whole-node unhide_node directly (bypassing
        unhide_combo) doesn't clean up _pipeline_hidden_combos -- documents
        that callers must go through unhide_combo, not unhide_node, to
        restore a hidden combo."""
        db = populated_db
        node_id = "fn__bandpass_filter__abc123"
        pipeline_store.hide_combo(db, node_id, "bandpass_filter", {"low_hz": "20"})
        pipeline_store.unhide_node(db, node_id)
        assert node_id not in pipeline_store.get_hidden_node_ids(db)
        assert pipeline_store.list_hidden_combos(db, "bandpass_filter") == [
            {"node_id": node_id, "variant_key": {"low_hz": "20"}}
        ]


class TestHiddenEdges:
    """hide_edge/unhide_edge never delete data -- they're a completely
    separate table from hidden NODES (hiding an edge keeps the node on
    screen, red -- see graph_builder.hidden_wirings), so these tests also
    confirm the two hidden-sets don't leak into each other."""

    EDGE_ID = "e__RawSignal__bandpass_filter__abc123"

    def test_hide_edge_round_trip(self, populated_db):
        db = populated_db
        pipeline_store.hide_edge(
            db, self.EDGE_ID, "var__RawSignal", "fn__bandpass_filter__abc123"
        )
        assert self.EDGE_ID in pipeline_store.get_hidden_edge_ids(db)

    def test_hide_edge_does_not_touch_hidden_nodes(self, populated_db):
        db = populated_db
        pipeline_store.hide_edge(
            db, self.EDGE_ID, "var__RawSignal", "fn__bandpass_filter__abc123"
        )
        assert pipeline_store.get_hidden_node_ids(db) == set()

    def test_list_hidden_edges_round_trip(self, populated_db):
        db = populated_db
        pipeline_store.hide_edge(
            db,
            self.EDGE_ID,
            "var__RawSignal",
            "fn__bandpass_filter__abc123",
            source_handle=None,
            target_handle="in__signal",
        )
        edges = pipeline_store.list_hidden_edges(db)
        assert edges == [
            {
                "edge_id": self.EDGE_ID,
                "source": "var__RawSignal",
                "target": "fn__bandpass_filter__abc123",
                "source_handle": None,
                "target_handle": "in__signal",
            }
        ]

    def test_unhide_edge_removes_it(self, populated_db):
        db = populated_db
        pipeline_store.hide_edge(
            db, self.EDGE_ID, "var__RawSignal", "fn__bandpass_filter__abc123"
        )
        pipeline_store.unhide_edge(db, self.EDGE_ID)
        assert self.EDGE_ID not in pipeline_store.get_hidden_edge_ids(db)
        assert pipeline_store.list_hidden_edges(db) == []

    def test_hide_edge_idempotent(self, populated_db):
        db = populated_db
        pipeline_store.hide_edge(
            db, self.EDGE_ID, "var__RawSignal", "fn__bandpass_filter__abc123"
        )
        pipeline_store.hide_edge(
            db, self.EDGE_ID, "var__RawSignal", "fn__bandpass_filter__abc123"
        )
        assert len(pipeline_store.list_hidden_edges(db)) == 1

    def test_unhide_nonexistent_edge_is_a_noop(self, populated_db):
        db = populated_db
        pipeline_store.unhide_edge(db, "does_not_exist")  # must not raise
        assert pipeline_store.get_hidden_edge_ids(db) == set()

    def test_get_hidden_edge_ids_empty_by_default(self, populated_db):
        db = populated_db
        assert pipeline_store.get_hidden_edge_ids(db) == set()
