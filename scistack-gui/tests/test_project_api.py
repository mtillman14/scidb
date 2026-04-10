"""Tests for the /api/project/* endpoints (Phase 6)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

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
    from scistack_gui import registry as _registry
    from scistack_gui.app import create_app
    from fastapi.testclient import TestClient

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
            from scilineage import lineage_fcn

            @lineage_fcn
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
