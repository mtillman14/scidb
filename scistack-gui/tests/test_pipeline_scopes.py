"""
Tests for nested-pipeline persistence (plan-gui-nested-pipelines.md Part A1).

Scoping model: every node belongs to one pipeline scope (root = 'main',
always exists; pre-scoping documents migrate into it). A pipeline placed on
a parent canvas is one _pipeline_uses row whose use_id IS the canvas
node_id (G1: same child twice = two nodes; bindings live on the use edge).
Layout positions are per-scope in the JSON file.
"""

import json

import pytest

from scistack_gui import layout as layout_store
from scistack_gui import pipeline_store as ps
from scistack_gui.db import get_db


# ---------------------------------------------------------------------------
# Pipeline scopes (CRUD + root guarantees)
# ---------------------------------------------------------------------------

class TestPipelineScopes:
    def test_root_always_exists(self, layout_path):
        pipes = ps.list_pipelines(get_db())
        assert pipes[0] == {"pipeline_id": "main", "name": "main"}

    def test_create_rename_delete(self, layout_path):
        db = get_db()
        pid = ps.create_pipeline(db, "loading")
        assert pid.startswith("pipe_")
        assert {"pipeline_id": pid, "name": "loading"} in ps.list_pipelines(db)

        ps.rename_pipeline(db, pid, "loading_v2")
        names = {p["pipeline_id"]: p["name"] for p in ps.list_pipelines(db)}
        assert names[pid] == "loading_v2"

        ps.delete_pipeline(db, pid)
        assert pid not in {p["pipeline_id"] for p in ps.list_pipelines(db)}

    def test_duplicate_name_rejected(self, layout_path):
        db = get_db()
        ps.create_pipeline(db, "loading")
        with pytest.raises(ValueError, match="already exists"):
            ps.create_pipeline(db, "loading")

    def test_root_cannot_be_renamed_or_deleted(self, layout_path):
        db = get_db()
        with pytest.raises(ValueError, match="root"):
            ps.rename_pipeline(db, "main", "other")
        with pytest.raises(ValueError, match="root"):
            ps.delete_pipeline(db, "main")

    def test_delete_used_pipeline_rejected(self, layout_path):
        db = get_db()
        child = ps.create_pipeline(db, "loading")
        ps.add_pipeline_use(db, "main", child)
        with pytest.raises(ValueError, match="still used by"):
            ps.delete_pipeline(db, child)

    def test_delete_cascades_own_contents(self, layout_path):
        db = get_db()
        pid = ps.create_pipeline(db, "loading")
        ps.write_manual_node(db, "n1", "functionNode", "fn_a", pid)
        ps.write_manual_node(db, "n2", "variableNode", "VarB", pid)
        ps.write_manual_edge(db, {"id": "e1", "source": "n1", "target": "n2"})

        ps.delete_pipeline(db, pid)

        assert ps.get_manual_nodes(db, pid) == {}
        assert all(e["id"] != "e1" for e in ps.get_manual_edges(db))


# ---------------------------------------------------------------------------
# Scoped nodes
# ---------------------------------------------------------------------------

class TestScopedNodes:
    def test_default_scope_is_root(self, layout_path):
        db = get_db()
        ps.write_manual_node(db, "n1", "functionNode", "fn_a")
        assert ps.get_manual_nodes(db)["n1"]["pipeline_id"] == "main"

    def test_scope_filtering(self, layout_path):
        db = get_db()
        pid = ps.create_pipeline(db, "loading")
        ps.write_manual_node(db, "root_node", "functionNode", "fn_a", "main")
        ps.write_manual_node(db, "sub_node", "functionNode", "fn_b", pid)

        assert set(ps.get_manual_nodes(db, "main")) == {"root_node"}
        assert set(ps.get_manual_nodes(db, pid)) == {"sub_node"}
        assert set(ps.get_manual_nodes(db)) == {"root_node", "sub_node"}


# ---------------------------------------------------------------------------
# Pipeline uses (pipeline-as-node)
# ---------------------------------------------------------------------------

class TestPipelineUses:
    def test_use_creates_row_and_canvas_node(self, layout_path):
        db = get_db()
        child = ps.create_pipeline(db, "loading")
        use_id = ps.add_pipeline_use(db, "main", child)

        (use,) = ps.get_pipeline_uses(db, "main")
        assert use == {"use_id": use_id, "parent_pipeline_id": "main",
                       "child_pipeline_id": child, "binding": {}}
        node = ps.get_manual_nodes(db, "main")[use_id]
        assert node["type"] == "pipelineNode"
        assert node["label"] == "loading"  # child's name

    def test_same_child_twice_is_two_nodes(self, layout_path):
        db = get_db()
        child = ps.create_pipeline(db, "loading")
        u1 = ps.add_pipeline_use(db, "main", child,
                                 binding={"params": {"low_hz": 20}})
        u2 = ps.add_pipeline_use(db, "main", child,
                                 binding={"params": {"low_hz": 30}})

        assert u1 != u2
        uses = {u["use_id"]: u for u in ps.get_pipeline_uses(db, "main")}
        assert uses[u1]["binding"] == {"params": {"low_hz": 20}}
        assert uses[u2]["binding"] == {"params": {"low_hz": 30}}
        nodes = ps.get_manual_nodes(db, "main")
        assert nodes[u1]["type"] == "pipelineNode"
        assert nodes[u2]["type"] == "pipelineNode"

    def test_cycle_rejected_direct_and_transitive(self, layout_path):
        db = get_db()
        a = ps.create_pipeline(db, "a")
        b = ps.create_pipeline(db, "b")
        c = ps.create_pipeline(db, "c")
        ps.add_pipeline_use(db, a, b)
        ps.add_pipeline_use(db, b, c)

        with pytest.raises(ValueError, match="cycle"):
            ps.add_pipeline_use(db, c, a)   # transitive: a -> b -> c -> a
        with pytest.raises(ValueError, match="cycle"):
            ps.add_pipeline_use(db, a, a)   # self

    def test_unknown_pipeline_rejected(self, layout_path):
        db = get_db()
        with pytest.raises(ValueError, match="unknown pipeline_id"):
            ps.add_pipeline_use(db, "main", "pipe_nonexistent")

    def test_remove_use_cleans_node_and_edges(self, layout_path):
        db = get_db()
        child = ps.create_pipeline(db, "loading")
        use_id = ps.add_pipeline_use(db, "main", child)
        ps.write_manual_node(db, "v1", "variableNode", "VarA", "main")
        ps.write_manual_edge(db, {"id": "e1", "source": use_id, "target": "v1"})

        ps.remove_pipeline_use(db, use_id)

        assert ps.get_pipeline_uses(db, "main") == []
        assert use_id not in ps.get_manual_nodes(db)
        assert all(e["id"] != "e1" for e in ps.get_manual_edges(db))

    def test_update_binding_validates_keys(self, layout_path):
        db = get_db()
        child = ps.create_pipeline(db, "loading")
        use_id = ps.add_pipeline_use(db, "main", child)

        ps.update_use_binding(db, use_id, {"key_map": {"session": "subject"}})
        (use,) = ps.get_pipeline_uses(db, "main")
        assert use["binding"] == {"key_map": {"session": "subject"}}

        with pytest.raises(ValueError, match="unknown binding key"):
            ps.update_use_binding(db, use_id, {"bogus": 1})

    def test_rename_child_updates_canvas_labels(self, layout_path):
        db = get_db()
        child = ps.create_pipeline(db, "loading")
        use_id = ps.add_pipeline_use(db, "main", child)

        ps.rename_pipeline(db, child, "loading_v2")

        assert ps.get_manual_nodes(db, "main")[use_id]["label"] == "loading_v2"


# ---------------------------------------------------------------------------
# Scoped layout positions
# ---------------------------------------------------------------------------

class TestScopedPositions:
    def test_positions_are_per_scope(self, layout_path):
        db = get_db()
        pid = ps.create_pipeline(db, "loading")
        layout_store.write_node_position("n1", 1.0, 2.0)               # root
        layout_store.write_node_position("n2", 3.0, 4.0, pipeline_id=pid)

        root = layout_store.read_layout()
        sub = layout_store.read_layout(pipeline_id=pid)
        assert root["positions"] == {"n1": {"x": 1.0, "y": 2.0}}
        assert sub["positions"] == {"n2": {"x": 3.0, "y": 4.0}}
        assert sub["pipeline_id"] == pid

    def test_flat_positions_migrate_to_root_scope(self, layout_path):
        # A pre-scoping layout file: flat node_id -> {x, y} positions.
        layout_path.write_text(json.dumps({
            "positions": {"var__RawSignal": {"x": 10.0, "y": 20.0}},
            "pipeline_db_migrated": True,
        }))

        result = layout_store.read_layout()

        assert result["positions"]["var__RawSignal"] == {"x": 10.0, "y": 20.0}
        # And the migration is scope-shaped on disk after the next write.
        layout_store.write_node_position("n_new", 1.0, 1.0)
        on_disk = json.loads(layout_path.read_text())
        assert on_disk["positions_scoped"] is True
        assert on_disk["positions"]["main"]["var__RawSignal"] == {"x": 10.0, "y": 20.0}
        assert on_disk["positions"]["main"]["n_new"] == {"x": 1.0, "y": 1.0}

    def test_scoped_manual_node_write_and_read(self, layout_path):
        db = get_db()
        pid = ps.create_pipeline(db, "loading")
        layout_store.write_manual_node("m1", 5.0, 6.0, "functionNode",
                                       "fn_a", pipeline_id=pid)

        sub = layout_store.read_layout(pipeline_id=pid)
        assert sub["positions"]["m1"] == {"x": 5.0, "y": 6.0}
        assert sub["manual_nodes"]["m1"]["pipeline_id"] == pid
        # Root scope does not see it.
        assert "m1" not in layout_store.read_layout()["manual_nodes"]

    def test_delete_node_clears_position_in_any_scope(self, layout_path):
        db = get_db()
        pid = ps.create_pipeline(db, "loading")
        layout_store.write_manual_node("m1", 5.0, 6.0, "functionNode",
                                       "fn_a", pipeline_id=pid)

        layout_store.delete_node("m1")

        assert "m1" not in layout_store.read_layout(pipeline_id=pid)["positions"]
        assert "m1" not in ps.get_manual_nodes(db)


# ---------------------------------------------------------------------------
# Checkpoint 2: scope services + API (scoped graph, scope CRUD endpoints)
# ---------------------------------------------------------------------------

class TestScopeApi:
    def test_list_and_create_pipelines(self, client):
        r = client.get("/api/pipelines")
        assert r.status_code == 200
        assert r.json()["pipelines"][0]["pipeline_id"] == "main"

        r = client.post("/api/pipelines", json={"name": "loading"})
        assert r.status_code == 200
        pid = r.json()["pipeline_id"]
        assert pid.startswith("pipe_")

        # Duplicate name -> 400 with the store's message.
        r = client.post("/api/pipelines", json={"name": "loading"})
        assert r.status_code == 400
        assert "already exists" in r.json()["detail"]

    def test_root_guards_are_400(self, client):
        assert client.delete("/api/pipelines/main").status_code == 400
        r = client.put("/api/pipelines/main", json={"name": "x"})
        assert r.status_code == 400

    def test_use_flow_and_pipeline_node_on_parent_canvas(self, client):
        pid = client.post("/api/pipelines",
                          json={"name": "loading"}).json()["pipeline_id"]

        r = client.post(f"/api/pipelines/main/uses",
                        json={"child_pipeline_id": pid,
                              "binding": {"params": {"low_hz": 30}},
                              "x": 10.0, "y": 20.0})
        assert r.status_code == 200
        use_id = r.json()["use_id"]

        graph = client.get("/api/pipeline").json()
        pipeline_nodes = [n for n in graph["nodes"]
                          if n["type"] == "pipelineNode"]
        assert [n["id"] for n in pipeline_nodes] == [use_id]
        data = pipeline_nodes[0]["data"]
        assert data["label"] == "loading"
        assert data["binding"] == {"params": {"low_hz": 30}}
        assert data["child_pipeline_id"] == pid
        # Its position landed in the parent scope.
        layout = client.get("/api/layout").json()
        assert layout["positions"][use_id] == {"x": 10.0, "y": 20.0}

    def test_cycle_and_binding_validation_are_400(self, client):
        a = client.post("/api/pipelines", json={"name": "a"}).json()["pipeline_id"]
        b = client.post("/api/pipelines", json={"name": "b"}).json()["pipeline_id"]
        client.post(f"/api/pipelines/{a}/uses", json={"child_pipeline_id": b})

        r = client.post(f"/api/pipelines/{b}/uses", json={"child_pipeline_id": a})
        assert r.status_code == 400
        assert "cycle" in r.json()["detail"]

        use_id = client.get("/api/pipelines").json()["uses"][0]["use_id"]
        r = client.put(f"/api/pipeline-uses/{use_id}/binding",
                       json={"binding": {"bogus": 1}})
        assert r.status_code == 400

    def test_remove_use_clears_node_and_position(self, client):
        pid = client.post("/api/pipelines",
                          json={"name": "loading"}).json()["pipeline_id"]
        use_id = client.post(f"/api/pipelines/main/uses",
                             json={"child_pipeline_id": pid,
                                   "x": 5.0, "y": 5.0}).json()["use_id"]

        assert client.delete(f"/api/pipeline-uses/{use_id}").status_code == 200

        graph = client.get("/api/pipeline").json()
        assert all(n["id"] != use_id for n in graph["nodes"])
        assert use_id not in client.get("/api/layout").json()["positions"]


class TestScopedGraph:
    def test_root_graph_excludes_sub_scope_manual_nodes(self, client):
        # Label with NO DB-derived counterpart, so the node stays manual
        # (a label matching one DB node would GRADUATE — separate test).
        pid = client.post("/api/pipelines",
                          json={"name": "loading"}).json()["pipeline_id"]
        client.put("/api/layout/sub_fn_node",
                   json={"x": 0, "y": 0, "node_type": "functionNode",
                         "label": "my_custom_fn", "pipeline_id": pid})

        root_ids = {n["id"] for n in
                    client.get("/api/pipeline").json()["nodes"]}
        sub_ids = {n["id"] for n in
                   client.get("/api/pipeline",
                              params={"pipeline_id": pid}).json()["nodes"]}

        assert "sub_fn_node" not in root_ids
        assert "sub_fn_node" in sub_ids
        # DB-derived nodes (no saved position anywhere) default to root.
        assert "var__RawSignal" in root_ids
        assert "var__RawSignal" not in sub_ids

    def test_graduation_preserves_sub_scope_membership(self, client):
        """A manual node whose label matches exactly one DB-derived node
        GRADUATES into it — and because the position transfer is
        scope-aware, the canonical node inherits the sub-scope membership
        (it moves off the root canvas onto the sub canvas)."""
        pid = client.post("/api/pipelines",
                          json={"name": "loading"}).json()["pipeline_id"]
        client.put("/api/layout/sub_fn_node",
                   json={"x": 0, "y": 0, "node_type": "functionNode",
                         "label": "bandpass_filter", "pipeline_id": pid})

        root_ids = {n["id"] for n in
                    client.get("/api/pipeline").json()["nodes"]}
        sub_ids = {n["id"] for n in
                   client.get("/api/pipeline",
                              params={"pipeline_id": pid}).json()["nodes"]}

        canonical = {i for i in (root_ids | sub_ids)
                     if i.startswith("fn__bandpass_filter__")}
        assert len(canonical) == 1
        assert canonical <= sub_ids, \
            "graduated node must live on the sub canvas (position scope)"
        assert not (canonical & root_ids)
        assert "sub_fn_node" not in (root_ids | sub_ids)  # replaced

    def test_position_moves_db_derived_node_between_scopes(self, client):
        """Dragging a DB-derived node onto a sub-canvas (position write in
        that scope) IS the membership record."""
        pid = client.post("/api/pipelines",
                          json={"name": "loading"}).json()["pipeline_id"]
        client.put("/api/layout/var__RawSignal",
                   json={"x": 1.0, "y": 2.0, "pipeline_id": pid})

        root_ids = {n["id"] for n in
                    client.get("/api/pipeline").json()["nodes"]}
        sub_ids = {n["id"] for n in
                   client.get("/api/pipeline",
                              params={"pipeline_id": pid}).json()["nodes"]}

        assert "var__RawSignal" not in root_ids
        assert "var__RawSignal" in sub_ids

    def test_edges_filtered_by_scope_membership(self, client):
        """The seeded bandpass edges stay on root; a sub-scope canvas sees
        none of them."""
        pid = client.post("/api/pipelines",
                          json={"name": "empty"}).json()["pipeline_id"]

        root = client.get("/api/pipeline").json()
        sub = client.get("/api/pipeline",
                         params={"pipeline_id": pid}).json()

        assert len(root["edges"]) > 0
        assert sub["edges"] == []
        assert sub["pipeline_id"] == pid


class TestDocumentInterface:
    def test_interface_from_manual_document(self, client):
        """var -> fn -> var wired inside a sub-scope: consumed-not-produced
        in, produced out."""
        pid = client.post("/api/pipelines",
                          json={"name": "loading"}).json()["pipeline_id"]
        client.put("/api/layout/mv_in",
                   json={"x": 0, "y": 0, "node_type": "variableNode",
                         "label": "RawSignal", "pipeline_id": pid})
        client.put("/api/layout/mf_proc",
                   json={"x": 0, "y": 0, "node_type": "functionNode",
                         "label": "bandpass_filter", "pipeline_id": pid})
        client.put("/api/layout/mv_out",
                   json={"x": 0, "y": 0, "node_type": "variableNode",
                         "label": "FilteredSignal", "pipeline_id": pid})
        client.put("/api/edges/e_in", json={"source": "mv_in",
                                            "target": "mf_proc"})
        client.put("/api/edges/e_out", json={"source": "mf_proc",
                                             "target": "mv_out"})

        iface = client.get(f"/api/pipelines/{pid}/interface").json()

        assert iface == {"inputs": ["RawSignal"], "outputs": ["FilteredSignal"]}

        # The pipeline node on the root canvas carries the same ports.
        use_id = client.post("/api/pipelines/main/uses",
                             json={"child_pipeline_id": pid}).json()["use_id"]
        graph = client.get("/api/pipeline").json()
        node = next(n for n in graph["nodes"] if n["id"] == use_id)
        assert node["data"]["inputs"] == ["RawSignal"]
        assert node["data"]["outputs"] == ["FilteredSignal"]
