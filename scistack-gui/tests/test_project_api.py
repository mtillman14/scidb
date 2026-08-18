"""Tests for the /api/project/* endpoints (Phase 6)."""

from __future__ import annotations

import sys
import textwrap

import pytest
from scistack_gui.api import project as _project_mod


@pytest.fixture
def project_client(populated_db, tmp_path):
    """
    FastAPI TestClient with a scaffold project directory around the DB.

    The populated_db fixture creates test.duckdb in tmp_path and wires up
    scistack_gui.db._db_path. Here we add the rest of the project
    structure so the discovery scanner has something to find.
    """
    from fastapi.testclient import TestClient
    from scistack_gui.app import create_app

    project_name = "test_project"

    # pyproject.toml next to the database
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "{project_name}"\nversion = "0.1.0"\n'
    )

    # Source package with variables, functions, constants
    src = tmp_path / "src" / project_name
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "variables.py").write_text(
        textwrap.dedent("""
            from scidb import BaseVariable

            class ProjectVar(BaseVariable):
                schema_version = 1
        """)
    )
    (src / "functions.py").write_text(
        textwrap.dedent("""
            from scidb import scistack

            @scistack
            def project_fcn(x):
                return x + 1
        """)
    )
    (src / "constants.py").write_text(
        textwrap.dedent("""
            from scidb import constant

            PROJECT_RATE = constant(1000, description="Sample rate")
        """)
    )

    # Clear the cached scan result from previous tests.
    _project_mod._last_result = None

    app = create_app()
    with TestClient(app) as c:
        yield c

    # Clean up the dynamically imported modules.
    for mod_name in list(sys.modules):
        if mod_name == project_name or mod_name.startswith(project_name + "."):
            sys.modules.pop(mod_name, None)
    _project_mod._last_result = None


class TestGetProjectCode:
    def test_returns_exports(self, project_client):
        resp = project_client.get("/api/project/code")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test_project"
        assert data["variable_count"] >= 1
        # Check that ProjectVar was found
        all_vars = []
        for mod in data["modules"]:
            all_vars.extend(mod["variables"])
        assert "ProjectVar" in all_vars

    def test_finds_functions(self, project_client):
        resp = project_client.get("/api/project/code")
        data = resp.json()
        all_fns = []
        for mod in data["modules"]:
            all_fns.extend(mod["functions"])
        assert "project_fcn" in all_fns

    def test_finds_constants(self, project_client):
        resp = project_client.get("/api/project/code")
        data = resp.json()
        all_consts = []
        for mod in data["modules"]:
            all_consts.extend(c["name"] for c in mod["constants"])
        assert "PROJECT_RATE" in all_consts


class TestGetProjectLibraries:
    def test_returns_libraries_structure(self, project_client):
        resp = project_client.get("/api/project/libraries")
        assert resp.status_code == 200
        data = resp.json()
        assert "libraries" in data
        assert "total_libraries" in data
        assert "shown_libraries" in data
        assert isinstance(data["libraries"], dict)


class TestRefreshProject:
    def test_refresh_returns_ok(self, project_client):
        resp = project_client.post("/api/project/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "project_code" in data
        assert data["project_code"]["name"] == "test_project"

    def test_refresh_updates_cached_scan(self, project_client):
        # First call populates cache.
        project_client.post("/api/project/refresh")
        # Second call should still work (from cache or re-scan).
        resp = project_client.get("/api/project/code")
        assert resp.status_code == 200
        assert resp.json()["variable_count"] >= 1


# ---------------------------------------------------------------------------
# Loose-script / folder-scan projects (no pyproject.toml) — registry-backed
# discovery, added alongside the packaged-project scan_project path above.
# ---------------------------------------------------------------------------


@pytest.fixture
def loose_project_client(populated_db, tmp_path):
    """FastAPI TestClient for a loose-script project: no pyproject.toml,
    no src/{name}/ layout — just .py/.m files sitting next to the .duckdb.
    Mirrors what the folder-scan fallback (config.load_config) + the
    zero-config startup path (__main__.py/server.py) actually do: load the
    config, then feed it to both registries before the app starts serving.
    """
    from fastapi.testclient import TestClient
    from scistack_gui import matlab_registry, registry
    from scistack_gui.api import project as _project_mod
    from scistack_gui.app import create_app
    from scistack_gui.config import load_config

    (tmp_path / "good_module.py").write_text(
        textwrap.dedent("""
            def loose_fn(x):
                return x + 1
        """)
    )
    (tmp_path / "broken_module.py").write_text("def broken(:\n    pass\n")
    (tmp_path / "bandpass_filter.m").write_text(
        "function y = bandpass_filter(x)\ny = x;\nend\n"
    )
    (tmp_path / "LooseMatlabVar.m").write_text(
        "classdef LooseMatlabVar < scidb.BaseVariable\nend\n"
    )
    (tmp_path / "constants_module.py").write_text(
        textwrap.dedent("""
            from scidb import constant

            LOOSE_RATE = constant(500, description="Loose sample rate")
        """)
    )

    config = load_config(None, tmp_path / "test.duckdb")
    registry.load_from_config(config)
    matlab_registry.load_from_config(config)

    _project_mod._last_result = None

    app = create_app()
    with TestClient(app) as c:
        yield c

    for mod_name in list(sys.modules):
        if mod_name.startswith("scistack_user_"):
            sys.modules.pop(mod_name, None)
    registry._functions.clear()
    registry._function_sources.clear()
    registry._constants.clear()
    registry._constant_sources.clear()
    registry._module_paths.clear()
    registry._load_errors.clear()
    registry._config = None
    matlab_registry._matlab_functions.clear()
    matlab_registry._matlab_variables.clear()
    matlab_registry._load_errors.clear()
    matlab_registry._config = None
    _project_mod._last_result = None


class TestLooseProjectCode:
    def test_code_matches_registry_functions_and_variables(self, loose_project_client):
        registry_resp = loose_project_client.get("/api/registry").json()
        code_resp = loose_project_client.get("/api/project/code").json()

        all_fns = {f for mod in code_resp["modules"] for f in mod["functions"]}
        all_vars = {v for mod in code_resp["modules"] for v in mod["variables"]}

        assert set(registry_resp["functions"]) <= all_fns
        assert set(registry_resp["matlab_functions"]) <= all_fns
        assert set(registry_resp["variables"]) <= all_vars

    def test_broken_module_surfaces_as_error_not_silence(self, loose_project_client):
        code_resp = loose_project_client.get("/api/project/code").json()
        error_sources = [e["module_name"] for e in code_resp["errors"]]
        assert any("broken_module.py" in s for s in error_sources)

    def test_broken_module_error_also_in_registry_response(self, loose_project_client):
        # The primary palette (EditTab -> get_registry) must see the same
        # failure, not just the Discovered Code popup.
        registry_resp = loose_project_client.get("/api/registry").json()
        assert any(
            "broken_module.py" in e["source"] for e in registry_resp["load_errors"]
        )

    def test_matlab_function_and_variable_discovered(self, loose_project_client):
        code_resp = loose_project_client.get("/api/project/code").json()
        all_fns = {f for mod in code_resp["modules"] for f in mod["functions"]}
        all_vars = {v for mod in code_resp["modules"] for v in mod["variables"]}
        assert "bandpass_filter" in all_fns
        assert "LooseMatlabVar" in all_vars

    def test_constant_discovered(self, loose_project_client):
        # Full parity with scan_project's packaged-project behavior:
        # scidb.constant() instances in loose scripts must show up here too.
        code_resp = loose_project_client.get("/api/project/code").json()
        all_consts = [c["name"] for mod in code_resp["modules"] for c in mod["constants"]]
        assert "LOOSE_RATE" in all_consts

    def test_constant_value_and_description(self, loose_project_client):
        code_resp = loose_project_client.get("/api/project/code").json()
        entries = {
            c["name"]: c for mod in code_resp["modules"] for c in mod["constants"]
        }
        entry = entries["LOOSE_RATE"]
        assert entry["value"] == "500"
        assert entry["description"] == "Loose sample rate"

    def test_refresh_re_imports_from_disk(self, loose_project_client, tmp_path):
        # Fix the broken module, hit refresh, confirm it's picked up live —
        # this is the "Refresh" button's whole point for loose-script mode.
        (tmp_path / "broken_module.py").write_text("def now_fixed(x):\n    return x\n")

        resp = loose_project_client.post("/api/project/refresh")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        registry_resp = loose_project_client.get("/api/registry").json()
        assert "now_fixed" in registry_resp["functions"]
        assert registry_resp["load_errors"] == []
