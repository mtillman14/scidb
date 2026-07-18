"""Integration tests: canvas nodes group for_each call sites by WIRING.

Since 2026-07-18 (user decision), the same function invoked with different
constant values renders as ONE canvas node (fn + loadable inputs + outputs
= the wiring), with each call site as a variant row carrying its OWN state
chip. The 2026-07-16 no-blur guarantee ("a partial run for one constant
value degrades only that call site") is preserved — it moved from separate
nodes to separate chips: scidb call_id semantics and per-call-site state
computation are untouched, only the presentation groups.

Sits at the same layer as test_api.py (TestClient + populated_db).
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

import scistack_gui.db as _gui_db
from scidb import configure_database, for_each
from scidb.database import _local
from scistack_gui import registry as _registry
from scistack_gui.app import create_app
from scistack_gui.domain.graph_builder import fn_node_id, wiring_id

from conftest import RawSignal, FilteredSignal, bandpass_filter


@pytest.fixture
def two_call_sites_client(tmp_path):
    """A DB with two for_each call sites for bandpass_filter (low_hz=20 and 50)."""
    if hasattr(_local, "database"):
        delattr(_local, "database")
    _gui_db._db = None

    db = configure_database(tmp_path / "twosite.duckdb", ["subject", "session"])
    for subj in [1, 2]:
        for sess in ["pre", "post"]:
            RawSignal.save(np.random.randn(10), subject=subj, session=sess)

    for_each(
        bandpass_filter,
        inputs={"signal": RawSignal, "low_hz": 20},
        outputs=[FilteredSignal],
        subject=[1, 2],
        session=["pre", "post"],
    )
    for_each(
        bandpass_filter,
        inputs={"signal": RawSignal, "low_hz": 50},
        outputs=[FilteredSignal],
        subject=[1, 2],
        session=["pre", "post"],
    )

    _gui_db._db = db
    _gui_db._db_path = tmp_path / "twosite.duckdb"
    _registry._functions["bandpass_filter"] = bandpass_filter

    from scistack_gui import pipeline_store
    pipeline_store._ensure_tables(db)

    with TestClient(create_app()) as c:
        yield c

    db.close()


def _bp_group_node_id() -> str:
    """Both call sites share one wiring (same fn, loadable inputs, outputs),
    so they group into a single node id."""
    return fn_node_id(
        "bandpass_filter",
        wiring_id("bandpass_filter", {"signal": "RawSignal"},
                  {"FilteredSignal"}),
    )


def _bp_nodes(nodes) -> list[dict]:
    return [n for n in nodes
            if n.get("type") == "functionNode"
            and n["data"]["label"] == "bandpass_filter"]


def test_two_call_sites_group_into_one_node(two_call_sites_client):
    nodes = two_call_sites_client.get("/api/pipeline").json()["nodes"]
    bp_nodes = _bp_nodes(nodes)
    assert len(bp_nodes) == 1, (
        f"expected ONE wiring-grouped bandpass_filter node, got "
        f"{[n['id'] for n in bp_nodes]}"
    )
    assert bp_nodes[0]["id"] == _bp_group_node_id()


def test_grouped_node_carries_both_variants_with_states(two_call_sites_client):
    nodes = two_call_sites_client.get("/api/pipeline").json()["nodes"]
    node = _bp_nodes(nodes)[0]
    variants = node["data"]["variants"]
    by_low_hz = {v["constants"]["low_hz"]: v for v in variants
                 if "low_hz" in v.get("constants", {})}
    assert set(by_low_hz) == {20, 50}
    # Both fully run → both chips green; the composite id suffix is the
    # wiring id, and each row keeps its own call_id.
    assert by_low_hz[20]["state"] == "green"
    assert by_low_hz[50]["state"] == "green"
    assert by_low_hz[20]["call_id"] != by_low_hz[50]["call_id"]
    assert node["id"].endswith("__" + node["data"]["call_id"])


def test_grouped_node_has_single_edge_set(two_call_sites_client):
    """RawSignal/const/output edges target the ONE grouped node (deduped)."""
    graph = two_call_sites_client.get("/api/pipeline").json()
    nid = _bp_group_node_id()

    in_edges = [e for e in graph["edges"]
                if e["source"] == "var__RawSignal" and e["target"] == nid]
    const_edges = [e for e in graph["edges"]
                   if e["source"] == "const__low_hz" and e["target"] == nid]
    out_edges = [e for e in graph["edges"]
                 if e["source"] == nid and e["target"] == "var__FilteredSignal"]
    assert len(in_edges) == 1
    assert len(const_edges) == 1
    assert len(out_edges) == 1


def test_grouped_node_state_is_green_when_all_variants_current(two_call_sites_client):
    nodes = two_call_sites_client.get("/api/pipeline").json()["nodes"]
    assert _bp_nodes(nodes)[0]["data"]["run_state"] == "green"


def test_partial_run_reddens_only_its_own_variant_chip(tmp_path):
    """A partial run for one constant value degrades ONLY that variant's
    chip (the no-blur behavior the user asked for on 2026-07-16, now at
    chip level); the node border shows the worst member state."""
    if hasattr(_local, "database"):
        delattr(_local, "database")
    _gui_db._db = None

    db = configure_database(tmp_path / "split.duckdb", ["subject", "session"])
    for subj in [1, 2]:
        for sess in ["pre", "post"]:
            RawSignal.save(np.random.randn(10), subject=subj, session=sess)

    # Variant A: fully run.
    for_each(
        bandpass_filter,
        inputs={"signal": RawSignal, "low_hz": 20},
        outputs=[FilteredSignal],
        subject=[1, 2], session=["pre", "post"],
    )
    # Variant B: only subject=1 (partial).
    for_each(
        bandpass_filter,
        inputs={"signal": RawSignal, "low_hz": 50},
        outputs=[FilteredSignal],
        subject=[1], session=["pre", "post"],
    )

    _gui_db._db = db
    _gui_db._db_path = tmp_path / "split.duckdb"
    _registry._functions["bandpass_filter"] = bandpass_filter
    from scistack_gui import pipeline_store
    pipeline_store._ensure_tables(db)

    try:
        with TestClient(create_app()) as c:
            nodes = c.get("/api/pipeline").json()["nodes"]
    finally:
        db.close()

    node = _bp_nodes(nodes)[0]
    by_low_hz = {v["constants"]["low_hz"]: v for v in node["data"]["variants"]
                 if "low_hz" in v.get("constants", {})}
    assert by_low_hz[20]["state"] == "green", \
        "fully-run variant chip must remain green"
    assert by_low_hz[50]["state"] == "red", \
        "partial variant chip must be red (binary call-site state)"
    assert node["data"]["run_state"] == "red", \
        "node border shows the worst member state"


def test_legacy_call_site_position_is_adopted(two_call_sites_client):
    """One-time migration: a position saved under a pre-grouping
    per-call-site node id is adopted by the group node (same scope) and the
    legacy key is dropped."""
    from scidb.foreach_config import ForEachConfig
    from scistack_gui import layout as layout_store

    cid = ForEachConfig(
        fn=bandpass_filter, inputs={"signal": RawSignal, "low_hz": 20},
    ).to_call_id()
    legacy_id = fn_node_id("bandpass_filter", cid)
    group_id = _bp_group_node_id()

    # Simulate a pre-grouping document: position keyed by the call-site id.
    layout_store.write_node_position(legacy_id, 123.0, 456.0,
                                     pipeline_id="main")
    layout_store.drop_node_positions(group_id)

    # A graph build runs the migration.
    two_call_sites_client.get("/api/pipeline")

    positions = layout_store.read_positions_by_scope()
    main_positions = positions.get("main", {})
    assert legacy_id not in main_positions, "legacy key must be dropped"
    assert main_positions.get(group_id) == {"x": 123.0, "y": 456.0}
