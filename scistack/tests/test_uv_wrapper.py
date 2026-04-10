"""Tests for :mod:`scistack.uv_wrapper`.

Splits into two groups:

* **Mock-based tests** for result-object construction and error handling,
  using ``monkeypatch`` on :func:`subprocess.run` and :func:`shutil.which`.
  These run in any environment.
* **Integration tests** for the real ``uv`` CLI, marked with
  ``@pytest.mark.requires_uv``. They run in a temporary project directory
  and are skipped automatically if ``uv`` is not on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from scistack.uv_wrapper import (
    AddResult,
    LockedPackage,
    RemoveResult,
    SyncResult,
    UvNotFoundError,
    _canonicalize,
    _hash_mapping,
    _run_uv,
    add,
    is_lockfile_stale,
    read_lockfile,
    remove,
    sync,
)


# ---------------------------------------------------------------------------
# requires-uv marker + auto-skip
# ---------------------------------------------------------------------------
requires_uv = pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="`uv` CLI not installed — integration test skipped",
)


# ---------------------------------------------------------------------------
# Fake subprocess.run for mock-based tests
# ---------------------------------------------------------------------------
class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def fake_uv(monkeypatch):
    """
    Patch ``shutil.which`` (for ``_find_uv``) and ``subprocess.run`` (for
    ``_run_uv``). Returns a controller object so tests can set the next
    fake result and inspect the recorded calls.
    """

    class Controller:
        def __init__(self):
            self.next_result = _FakeCompletedProcess(0, "", "")
            self.calls: list[dict] = []
            self.raise_uv_missing = False

        def set_result(self, returncode: int, stdout: str = "", stderr: str = ""):
            self.next_result = _FakeCompletedProcess(returncode, stdout, stderr)

    ctl = Controller()

    def fake_which(name):
        if ctl.raise_uv_missing:
            return None
        return "/fake/bin/uv" if name == "uv" else shutil.which(name)

    def fake_run(cmd, **kwargs):
        ctl.calls.append({"cmd": tuple(cmd), "kwargs": kwargs})
        return ctl.next_result

    monkeypatch.setattr("scistack.uv_wrapper.shutil.which", fake_which)
    monkeypatch.setattr("scistack.uv_wrapper.subprocess.run", fake_run)
    return ctl


# ---------------------------------------------------------------------------
# Helper to build a minimal project directory for lockfile / mtime tests
# ---------------------------------------------------------------------------
@pytest.fixture
def minimal_project(tmp_path):
    """Create a pyproject.toml and return the project root."""
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "my_study"
            version = "0.1.0"
            dependencies = ["scidb"]
            """
        )
    )
    return tmp_path


# ---------------------------------------------------------------------------
# _run_uv and error handling
# ---------------------------------------------------------------------------
class TestRunUv:
    def test_uv_not_found_raises(self, fake_uv, tmp_path):
        fake_uv.raise_uv_missing = True
        with pytest.raises(UvNotFoundError):
            _run_uv(("sync",), tmp_path)

    def test_command_is_passed_through(self, fake_uv, tmp_path):
        fake_uv.set_result(0, "ok", "")
        _run_uv(("sync",), tmp_path)
        call = fake_uv.calls[0]
        assert call["cmd"][0] == "/fake/bin/uv"
        assert call["cmd"][1:] == ("sync",)
        assert call["kwargs"]["cwd"] == str(tmp_path)

    def test_no_progress_env_var_set(self, fake_uv, tmp_path):
        fake_uv.set_result(0)
        _run_uv(("sync",), tmp_path)
        env = fake_uv.calls[0]["kwargs"]["env"]
        assert env.get("UV_NO_PROGRESS") == "1"


# ---------------------------------------------------------------------------
# sync(), add(), remove() — mock-based
# ---------------------------------------------------------------------------
class TestSyncMocked:
    def test_sync_success(self, fake_uv, tmp_path):
        fake_uv.set_result(0, "Resolved 42 packages", "")
        result = sync(tmp_path)
        assert isinstance(result, SyncResult)
        assert result.ok
        assert result.returncode == 0
        assert "Resolved" in result.stdout
        assert fake_uv.calls[0]["cmd"][1:] == ("sync",)

    def test_sync_failure_captures_stderr(self, fake_uv, tmp_path):
        fake_uv.set_result(1, "", "error: no pyproject.toml found")
        result = sync(tmp_path)
        assert not result.ok
        assert result.returncode == 1
        assert "no pyproject.toml" in result.stderr
        assert "no pyproject.toml" in result.combined_output

    def test_sync_no_raise_on_failure(self, fake_uv, tmp_path):
        fake_uv.set_result(1, "", "something broke")
        # Must NOT raise — callers want to surface errors structurally.
        sync(tmp_path)


class TestAddMocked:
    def test_add_without_version(self, fake_uv, tmp_path):
        fake_uv.set_result(0)
        result = add(tmp_path, "numpy")
        assert isinstance(result, AddResult)
        assert result.ok
        assert result.package == "numpy"
        assert result.version is None
        assert fake_uv.calls[0]["cmd"][1:] == ("add", "numpy")

    def test_add_with_version(self, fake_uv, tmp_path):
        fake_uv.set_result(0)
        result = add(tmp_path, "numpy", version="2.0.0")
        assert result.version == "2.0.0"
        assert fake_uv.calls[0]["cmd"][1:] == ("add", "numpy==2.0.0")

    def test_add_with_index(self, fake_uv, tmp_path):
        fake_uv.set_result(0)
        add(tmp_path, "mylab", index="https://example.com/simple")
        assert fake_uv.calls[0]["cmd"][1:] == (
            "add",
            "mylab",
            "--index",
            "https://example.com/simple",
        )

    def test_add_dev(self, fake_uv, tmp_path):
        fake_uv.set_result(0)
        add(tmp_path, "pytest", dev=True)
        assert fake_uv.calls[0]["cmd"][1:] == ("add", "pytest", "--dev")

    def test_add_failure_surfaces_error(self, fake_uv, tmp_path):
        fake_uv.set_result(2, "", "error: version conflict: numpy<2 vs >=2")
        result = add(tmp_path, "numpy", version="1.26.0")
        assert not result.ok
        assert "version conflict" in result.stderr


class TestRemoveMocked:
    def test_remove_success(self, fake_uv, tmp_path):
        fake_uv.set_result(0)
        result = remove(tmp_path, "numpy")
        assert isinstance(result, RemoveResult)
        assert result.ok
        assert result.package == "numpy"
        assert fake_uv.calls[0]["cmd"][1:] == ("remove", "numpy")

    def test_remove_failure(self, fake_uv, tmp_path):
        fake_uv.set_result(1, "", "package not found")
        result = remove(tmp_path, "ghost")
        assert not result.ok
        assert "not found" in result.stderr


# ---------------------------------------------------------------------------
# read_lockfile
# ---------------------------------------------------------------------------
class TestReadLockfile:
    def test_missing_lockfile_returns_empty(self, tmp_path):
        assert read_lockfile(tmp_path) == []

    def test_parses_packages(self, tmp_path):
        (tmp_path / "uv.lock").write_text(
            textwrap.dedent(
                """
                version = 1

                [[package]]
                name = "numpy"
                version = "2.0.0"
                source = { registry = "https://pypi.org/simple" }

                [[package]]
                name = "mylab-preprocessing"
                version = "0.2.1"
                source = { registry = "https://github.com/mylab/index" }

                [[package]]
                name = "my_study"
                version = "0.1.0"
                source = { editable = "." }

                [[package]]
                name = "dev"
                version = "0"
                source = { virtual = "." }
                """
            )
        )
        pkgs = read_lockfile(tmp_path)
        assert len(pkgs) == 4
        by_name = {p.name: p for p in pkgs}

        assert by_name["numpy"].version == "2.0.0"
        assert by_name["numpy"].is_registry
        assert not by_name["numpy"].is_editable
        assert by_name["numpy"].registry_url == "https://pypi.org/simple"

        assert by_name["mylab-preprocessing"].registry_url.startswith("https://github.com")
        assert by_name["my_study"].is_editable
        assert by_name["dev"].is_virtual

    def test_invalid_toml_raises_valueerror(self, tmp_path):
        (tmp_path / "uv.lock").write_text("!!! not toml !!!")
        with pytest.raises(ValueError, match="Failed to parse"):
            read_lockfile(tmp_path)

    def test_malformed_package_table_raises(self, tmp_path):
        (tmp_path / "uv.lock").write_text(
            textwrap.dedent(
                """
                version = 1
                package = "not a list"
                """
            )
        )
        with pytest.raises(ValueError, match="is not a list"):
            read_lockfile(tmp_path)

    def test_skips_nameless_entries(self, tmp_path):
        (tmp_path / "uv.lock").write_text(
            textwrap.dedent(
                """
                version = 1

                [[package]]
                version = "1.0"

                [[package]]
                name = "real_package"
                version = "2.0"
                """
            )
        )
        pkgs = read_lockfile(tmp_path)
        assert len(pkgs) == 1
        assert pkgs[0].name == "real_package"


# ---------------------------------------------------------------------------
# is_lockfile_stale
# ---------------------------------------------------------------------------
class TestIsLockfileStale:
    def test_missing_lockfile_is_stale(self, minimal_project):
        assert is_lockfile_stale(minimal_project) is True

    def test_missing_pyproject_is_not_stale(self, tmp_path):
        (tmp_path / "uv.lock").write_text("version = 1\n")
        assert is_lockfile_stale(tmp_path) is False

    def test_fresh_lockfile_not_stale(self, minimal_project):
        import time

        # Lockfile newer than pyproject.toml, no content hash stored.
        time.sleep(0.01)
        (minimal_project / "uv.lock").write_text("version = 1\n")
        assert is_lockfile_stale(minimal_project) is False

    def test_pyproject_newer_than_lockfile_is_stale(self, minimal_project):
        import time

        (minimal_project / "uv.lock").write_text("version = 1\n")
        time.sleep(0.01)
        # Re-touch pyproject so it's newer.
        (minimal_project / "pyproject.toml").write_text(
            (minimal_project / "pyproject.toml").read_text() + "\n# edit\n"
        )
        assert is_lockfile_stale(minimal_project) is True

    def test_content_hash_mismatch_is_stale(self, minimal_project):
        import time

        (minimal_project / "uv.lock").write_text(
            textwrap.dedent(
                """
                version = 1

                [manifest]
                content-hash = "some-hash-that-does-not-match"
                """
            )
        )
        # Make sure lockfile mtime is newer than pyproject so the mtime
        # check passes but the hash check fails.
        time.sleep(0.01)
        (minimal_project / "uv.lock").touch()
        assert is_lockfile_stale(minimal_project) is True

    def test_content_hash_match_not_stale(self, minimal_project):
        import time
        import tomllib

        # Build the relevant subset just like the checker does, hash it,
        # and embed that hash in the lockfile.
        with open(minimal_project / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        relevant = {
            "project": data.get("project", {}),
            "dependency-groups": data.get("dependency-groups", {}),
            "tool.uv": data.get("tool", {}).get("uv", {}),
        }
        content_hash = _hash_mapping(relevant)

        (minimal_project / "uv.lock").write_text(
            f'version = 1\n\n[manifest]\ncontent-hash = "{content_hash}"\n'
        )
        time.sleep(0.01)
        (minimal_project / "uv.lock").touch()
        assert is_lockfile_stale(minimal_project) is False


# ---------------------------------------------------------------------------
# _canonicalize helper
# ---------------------------------------------------------------------------
class TestCanonicalize:
    def test_dict_key_order_stable(self):
        a = {"b": 1, "a": 2}
        b = {"a": 2, "b": 1}
        assert _canonicalize(a) == _canonicalize(b)

    def test_distinct_values_produce_distinct_hashes(self):
        assert _hash_mapping({"a": 1}) != _hash_mapping({"a": 2})

    def test_nested(self):
        assert _canonicalize({"x": [1, 2, {"y": 3}]}) == "{x=[1,2,{y=3}]}"

    def test_none_bool(self):
        assert _canonicalize(None) == "null"
        assert _canonicalize(True) == "true"
        assert _canonicalize(False) == "false"


# ---------------------------------------------------------------------------
# Integration tests with the real uv CLI
# ---------------------------------------------------------------------------
@requires_uv
class TestUvIntegration:
    @pytest.fixture
    def uv_project(self, tmp_path):
        """Create a minimal project and return its root."""
        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent(
                """
                [project]
                name = "integration_study"
                version = "0.1.0"
                requires-python = ">=3.9"
                dependencies = []

                [build-system]
                requires = ["hatchling"]
                build-backend = "hatchling.build"

                [tool.hatch.build.targets.wheel]
                packages = ["src/integration_study"]
                """
            )
        )
        (tmp_path / "src" / "integration_study").mkdir(parents=True)
        (tmp_path / "src" / "integration_study" / "__init__.py").write_text("")
        return tmp_path

    def test_sync_creates_lockfile(self, uv_project):
        result = sync(uv_project, timeout=120)
        # It's OK if sync fails (network issues, etc.) — we just need the
        # function to return structurally.
        assert isinstance(result, SyncResult)
        if result.ok:
            assert (uv_project / "uv.lock").exists()
            # Lockfile should be parseable even if empty (zero deps).
            pkgs = read_lockfile(uv_project)
            assert isinstance(pkgs, list)

    def test_sync_reports_failure_on_bad_project(self, tmp_path):
        """Running sync in a directory with no pyproject.toml must surface an error."""
        result = sync(tmp_path, timeout=30)
        assert not result.ok
        assert result.combined_output != ""
