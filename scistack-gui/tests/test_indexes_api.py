"""Tests for the /api/indexes/* and library management endpoints (Phase 7)."""

from __future__ import annotations

import shutil
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from scistack_gui.api import project as _project_mod


@pytest.fixture
def index_client(populated_db, tmp_path, monkeypatch):
    """
    FastAPI TestClient with a project directory, a tapped index with
    a packages.toml, and mocked uv operations.
    """
    from scistack_gui import registry as _registry
    from scistack_gui.app import create_app
    from fastapi.testclient import TestClient

    # Set up project structure
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "idx_project"\nversion = "0.1.0"\n'
        'dependencies = []\n'
    )
    src = tmp_path / "src" / "idx_project"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")

    # Set up a fake tap with packages.toml
    config_dir = tmp_path / ".scistack_test"
    config_dir.mkdir()
    tap_dir = config_dir / "taps" / "mylab"
    tap_dir.mkdir(parents=True)
    (tap_dir / "packages.toml").write_text(
        textwrap.dedent("""
            [[package]]
            name = "mylab-preprocessing"
            description = "Standard preprocessing pipeline"
            versions = ["0.3.0", "0.2.1", "0.1.0"]
            index_url = "https://github.com/mylab/index/simple"

            [[package]]
            name = "mylab-stats"
            description = "Statistical analysis helpers"
            versions = ["1.0.0"]
            index_url = "https://github.com/mylab/index/simple"
        """)
    )
    (config_dir / "config.toml").write_text(
        '[[tap]]\nname = "mylab"\nurl = "https://github.com/mylab/scistack-index.git"\n'
    )

    # Point user_config to our test config dir
    monkeypatch.setenv("SCISTACK_CONFIG_DIR", str(config_dir))

    # Clear cached scan results
    _project_mod._last_result = None

    app = create_app()
    with TestClient(app) as c:
        yield c

    _project_mod._last_result = None


class TestListIndexes:
    def test_returns_tapped_indexes(self, index_client):
        resp = index_client.get("/api/indexes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["indexes"]) == 1
        assert data["indexes"][0]["name"] == "mylab"
        assert data["indexes"][0]["exists_locally"] is True


class TestSearchIndexPackages:
    def test_returns_all_packages(self, index_client):
        resp = index_client.get("/api/indexes/mylab/packages")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["packages"]) == 2
        names = {p["name"] for p in data["packages"]}
        assert names == {"mylab-preprocessing", "mylab-stats"}

    def test_search_filters_by_query(self, index_client):
        resp = index_client.get("/api/indexes/mylab/packages?q=stats")
        data = resp.json()
        assert len(data["packages"]) == 1
        assert data["packages"][0]["name"] == "mylab-stats"

    def test_search_matches_description(self, index_client):
        resp = index_client.get("/api/indexes/mylab/packages?q=preprocessing")
        data = resp.json()
        assert len(data["packages"]) == 1
        assert data["packages"][0]["name"] == "mylab-preprocessing"

    def test_unknown_index_returns_error(self, index_client):
        resp = index_client.get("/api/indexes/nonexistent/packages")
        data = resp.json()
        assert "error" in data
        assert data["packages"] == []

    def test_package_has_versions_and_index_url(self, index_client):
        resp = index_client.get("/api/indexes/mylab/packages?q=preprocessing")
        pkg = resp.json()["packages"][0]
        assert pkg["versions"] == ["0.3.0", "0.2.1", "0.1.0"]
        assert "github.com" in pkg["index_url"]


class TestAddLibrary:
    def test_missing_name_returns_error(self, index_client):
        resp = index_client.post("/api/project/libraries", json={})
        data = resp.json()
        assert data["ok"] is False
        assert "name" in data["error"].lower() or "required" in data["error"].lower()

    def test_add_calls_uv_add(self, index_client, monkeypatch):
        """Mock uv_add to verify it gets called with the right args."""
        from scistack import uv_wrapper

        calls = []

        class FakeResult:
            ok = True
            combined_output = ""

        def fake_add(root, package, *, version=None, index=None, dev=False, timeout=None):
            calls.append({"package": package, "version": version, "index": index})
            return FakeResult()

        monkeypatch.setattr(uv_wrapper, "add", fake_add)
        # Also mock _run_scan to avoid side effects
        monkeypatch.setattr(_project_mod, "_run_scan", lambda: None)

        resp = index_client.post("/api/project/libraries", json={
            "name": "mylab-preprocessing",
            "version": "0.3.0",
            "index": "https://github.com/mylab/index/simple",
        })
        data = resp.json()
        assert data["ok"] is True
        assert len(calls) == 1
        assert calls[0]["package"] == "mylab-preprocessing"
        assert calls[0]["version"] == "0.3.0"
        assert calls[0]["index"] == "https://github.com/mylab/index/simple"

    def test_add_failure_surfaces_uv_error(self, index_client, monkeypatch):
        from scistack import uv_wrapper

        class FakeResult:
            ok = False
            combined_output = "error: version conflict: foo<2 vs >=2"

        def fake_add(root, package, **kw):
            return FakeResult()

        monkeypatch.setattr(uv_wrapper, "add", fake_add)

        resp = index_client.post("/api/project/libraries", json={"name": "foo"})
        data = resp.json()
        assert data["ok"] is False
        assert "version conflict" in data["error"]


class TestRemoveLibrary:
    def test_remove_calls_uv_remove(self, index_client, monkeypatch):
        from scistack import uv_wrapper

        calls = []

        class FakeResult:
            ok = True
            combined_output = ""

        def fake_remove(root, package, **kw):
            calls.append(package)
            return FakeResult()

        monkeypatch.setattr(uv_wrapper, "remove", fake_remove)
        monkeypatch.setattr(_project_mod, "_run_scan", lambda: None)

        resp = index_client.delete("/api/project/libraries/mylab-preprocessing")
        data = resp.json()
        assert data["ok"] is True
        assert calls == ["mylab-preprocessing"]
