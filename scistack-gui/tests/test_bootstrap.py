"""
Tests for scistack_gui.bootstrap and the /api/bootstrap/* endpoints — the
browser-frontend project-creation wizard (mirrors the VS Code extension's
"SciStack: Open Pipeline" flow; see
docs/claude/scistack-gui-project-setup-guide.md §4/§5).
"""

from __future__ import annotations

import duckdb
import pytest
from fastapi.testclient import TestClient

from scistack_gui.app import create_app
from scistack_gui.bootstrap import open_or_create_project


@pytest.fixture
def api_client():
    """TestClient with no database loaded.

    conftest.py's autouse ``clear_db_state`` fixture resets
    ``scistack_gui.db._db``/``_db_path`` to None before and after every
    test, so a plain ``create_app()`` here (no ``populated_db``) starts
    with nothing open — the exact state the browser wizard is meant to
    bootstrap out of.
    """
    app = create_app()
    with TestClient(app) as c:
        yield c


def _make_existing_db(path, schema_key="subject"):
    con = duckdb.connect(str(path))
    con.execute(f"CREATE TABLE _schema (schema_id INTEGER, {schema_key} INTEGER)")
    con.close()


class TestOpenOrCreateProject:
    def test_create_new_database(self, tmp_path):
        db_path = tmp_path / "new.duckdb"
        result = open_or_create_project(db_path, schema_keys=["subject", "session"])
        assert db_path.exists()
        assert result.schema_keys == ["subject", "session"]
        assert result.db_name == "new.duckdb"

    def test_create_without_schema_keys_raises_file_not_found(self, tmp_path):
        db_path = tmp_path / "missing.duckdb"
        with pytest.raises(FileNotFoundError):
            open_or_create_project(db_path)

    def test_create_empty_schema_keys_raises_value_error(self, tmp_path):
        db_path = tmp_path / "new.duckdb"
        with pytest.raises(ValueError):
            open_or_create_project(db_path, schema_keys=[])

    def test_create_on_existing_path_raises_file_exists(self, tmp_path):
        db_path = tmp_path / "existing.duckdb"
        _make_existing_db(db_path)
        with pytest.raises(FileExistsError):
            open_or_create_project(db_path, schema_keys=["subject"])

    def test_open_existing_database(self, tmp_path):
        db_path = tmp_path / "existing.duckdb"
        _make_existing_db(db_path)
        result = open_or_create_project(db_path)
        assert result.schema_keys == ["subject"]

    def test_module_and_project_mutually_exclusive(self, tmp_path):
        db_path = tmp_path / "new.duckdb"
        with pytest.raises(ValueError):
            open_or_create_project(
                db_path,
                schema_keys=["subject"],
                module=tmp_path / "a.py",
                project=tmp_path,
            )


class TestCreateProjectEndpoint:
    def test_create_flips_db_loaded(self, api_client, tmp_path):
        resp = api_client.get("/api/info")
        assert resp.json() == {"db_loaded": False}

        resp = api_client.post(
            "/api/bootstrap/create",
            json={
                "folder": str(tmp_path),
                "filename": "study",
                "schema_keys": ["subject", "session"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["db_loaded"] is True
        assert data["db_name"] == "study.duckdb"
        assert (tmp_path / "study.duckdb").exists()

        resp = api_client.get("/api/info")
        assert resp.json()["db_loaded"] is True

    def test_create_appends_duckdb_extension(self, api_client, tmp_path):
        resp = api_client.post(
            "/api/bootstrap/create",
            json={
                "folder": str(tmp_path),
                "filename": "no_extension",
                "schema_keys": ["subject"],
            },
        )
        assert resp.status_code == 200
        assert (tmp_path / "no_extension.duckdb").exists()

    def test_create_on_existing_path_returns_409(self, api_client, tmp_path):
        _make_existing_db(tmp_path / "study.duckdb")

        resp = api_client.post(
            "/api/bootstrap/create",
            json={
                "folder": str(tmp_path),
                "filename": "study",
                "schema_keys": ["subject"],
            },
        )
        assert resp.status_code == 409

    def test_create_empty_schema_keys_returns_400(self, api_client, tmp_path):
        resp = api_client.post(
            "/api/bootstrap/create",
            json={"folder": str(tmp_path), "filename": "study", "schema_keys": []},
        )
        assert resp.status_code == 400

    def test_create_missing_folder_returns_404(self, api_client, tmp_path):
        resp = api_client.post(
            "/api/bootstrap/create",
            json={
                "folder": str(tmp_path / "does_not_exist"),
                "filename": "study",
                "schema_keys": ["subject"],
            },
        )
        assert resp.status_code == 404

    def test_create_filename_with_path_separator_returns_400(self, api_client, tmp_path):
        resp = api_client.post(
            "/api/bootstrap/create",
            json={
                "folder": str(tmp_path),
                "filename": "sub/study",
                "schema_keys": ["subject"],
            },
        )
        assert resp.status_code == 400


class TestOpenProjectEndpoint:
    def test_open_existing_database(self, api_client, tmp_path):
        db_path = tmp_path / "existing.duckdb"
        _make_existing_db(db_path)

        resp = api_client.post("/api/bootstrap/open", json={"db_path": str(db_path)})
        assert resp.status_code == 200
        data = resp.json()
        assert data["db_loaded"] is True
        assert data["db_name"] == "existing.duckdb"

    def test_open_nonexistent_path_returns_404(self, api_client, tmp_path):
        resp = api_client.post(
            "/api/bootstrap/open",
            json={"db_path": str(tmp_path / "missing.duckdb")},
        )
        assert resp.status_code == 404
