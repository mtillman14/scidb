"""Tests for :mod:`scistack.project` — the project scaffolder."""

from __future__ import annotations

import shutil
import sys
import textwrap
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

from scistack.project import scaffold_project, validate_project_name


# ---------------------------------------------------------------------------
# validate_project_name
# ---------------------------------------------------------------------------
class TestValidateProjectName:
    def test_valid_names(self):
        for name in ("my_study", "eeg_analysis", "experiment_2024", "x", "abc"):
            validate_project_name(name)  # should not raise

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_project_name("")

    def test_uppercase_rejected(self):
        with pytest.raises(ValueError, match="Invalid project name"):
            validate_project_name("My_Study")

    def test_starts_with_digit_rejected(self):
        with pytest.raises(ValueError, match="Invalid project name"):
            validate_project_name("1study")

    def test_hyphen_rejected(self):
        with pytest.raises(ValueError, match="Invalid project name"):
            validate_project_name("my-study")

    def test_spaces_rejected(self):
        with pytest.raises(ValueError, match="Invalid project name"):
            validate_project_name("my study")

    def test_dot_rejected(self):
        with pytest.raises(ValueError, match="Invalid project name"):
            validate_project_name("my.study")


# ---------------------------------------------------------------------------
# scaffold_project — file layout
# ---------------------------------------------------------------------------
class TestScaffoldLayout:
    """Verify that all expected files and directories are created."""

    @pytest.fixture
    def project_root(self, tmp_path):
        """Scaffold a project with uv sync and db creation disabled."""
        return scaffold_project(
            parent_dir=tmp_path,
            name="test_study",
            schema_keys=["subject", "session"],
            run_uv_sync=False,
            configure_db=False,
        )

    def test_returns_absolute_path(self, project_root):
        assert project_root.is_absolute()
        assert project_root.name == "test_study"

    def test_scistack_dir(self, project_root):
        assert (project_root / ".scistack" / "project.toml").is_file()
        assert (project_root / ".scistack" / "snapshots").is_dir()

    def test_project_toml_content(self, project_root):
        text = (project_root / ".scistack" / "project.toml").read_text()
        assert "scistack" in text
        assert "created" in text

    def test_pyproject_toml_exists(self, project_root):
        assert (project_root / "pyproject.toml").is_file()

    def test_pyproject_toml_content(self, project_root):
        with open(project_root / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        assert data["project"]["name"] == "test_study"
        assert data["project"]["version"] == "0.1.0"
        assert "scidb" in str(data["project"]["dependencies"])
        assert data["project"]["requires-python"] == ">=3.12"
        assert "scistack-gui" in str(data.get("dependency-groups", {}).get("dev", []))
        assert data["build-system"]["build-backend"] == "hatchling.build"

    def test_src_package_exists(self, project_root):
        assert (project_root / "src" / "test_study" / "__init__.py").is_file()

    def test_init_py_content(self, project_root):
        text = (project_root / "src" / "test_study" / "__init__.py").read_text()
        assert "test_study" in text

    def test_gitignore_exists(self, project_root):
        gitignore = project_root / ".gitignore"
        assert gitignore.is_file()
        text = gitignore.read_text()
        assert "*.duckdb" in text
        assert ".venv/" in text
        assert "data/" in text

    def test_readme_exists(self, project_root):
        readme = project_root / "README.md"
        assert readme.is_file()
        text = readme.read_text()
        assert "test_study" in text
        assert "subject" in text


# ---------------------------------------------------------------------------
# scaffold_project — error cases
# ---------------------------------------------------------------------------
class TestScaffoldErrors:
    def test_invalid_name_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid project name"):
            scaffold_project(
                parent_dir=tmp_path,
                name="My Study",
                schema_keys=["subject"],
                run_uv_sync=False,
                configure_db=False,
            )

    def test_existing_directory_raises(self, tmp_path):
        (tmp_path / "my_study").mkdir()
        with pytest.raises(FileExistsError, match="already exists"):
            scaffold_project(
                parent_dir=tmp_path,
                name="my_study",
                schema_keys=["subject"],
                run_uv_sync=False,
                configure_db=False,
            )

    def test_parent_dir_created_if_missing(self, tmp_path):
        """parent_dir doesn't need to exist — scaffold creates it."""
        deep = tmp_path / "a" / "b" / "c"
        root = scaffold_project(
            parent_dir=deep,
            name="nested_study",
            schema_keys=["subject"],
            run_uv_sync=False,
            configure_db=False,
        )
        assert root.exists()


# ---------------------------------------------------------------------------
# scaffold_project — database creation
# ---------------------------------------------------------------------------
class TestScaffoldDatabase:
    def test_duckdb_created(self, tmp_path):
        root = scaffold_project(
            parent_dir=tmp_path,
            name="db_study",
            schema_keys=["subject", "session"],
            run_uv_sync=False,
            configure_db=True,
        )
        db_path = root / "db_study.duckdb"
        assert db_path.is_file()

    def test_duckdb_has_schema_keys(self, tmp_path):
        """Verify that the DB is configured with the provided schema keys."""
        root = scaffold_project(
            parent_dir=tmp_path,
            name="schema_study",
            schema_keys=["subject", "session"],
            run_uv_sync=False,
            configure_db=True,
        )
        db_path = root / "schema_study.duckdb"
        # Re-open and verify the schema keys.
        from scidb import configure_database
        from scidb.database import _local

        db = configure_database(db_path, ["subject", "session"])
        assert db.dataset_schema_keys == ["subject", "session"]
        db.close()
        if hasattr(_local, "database"):
            delattr(_local, "database")

    def test_no_global_db_state_leaked(self, tmp_path):
        """Scaffolding must not leave a configured global database."""
        from scidb.database import _local

        scaffold_project(
            parent_dir=tmp_path,
            name="leak_study",
            schema_keys=["subject"],
            run_uv_sync=False,
            configure_db=True,
        )
        assert not hasattr(_local, "database")


# ---------------------------------------------------------------------------
# scaffold_project — uv sync integration
# ---------------------------------------------------------------------------
requires_uv = pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="`uv` CLI not installed — integration test skipped",
)


@requires_uv
class TestScaffoldUvSync:
    @staticmethod
    def _strip_unresolvable_deps(project_root: Path) -> None:
        """Replace dependencies with [] so uv sync works without PyPI access to scidb."""
        pyproject = project_root / "pyproject.toml"
        text = pyproject.read_text()
        # Clear the dependencies that can't be resolved in the test env.
        text = text.replace(
            'dependencies = [\n    "scidb",\n]',
            "dependencies = []",
        )
        # Also clear the dev dependency group.
        text = text.replace(
            'dev = [\n    "scistack-gui",\n]',
            "dev = []",
        )
        pyproject.write_text(text)

    def test_uv_sync_creates_lockfile(self, tmp_path):
        from scistack.uv_wrapper import sync

        root = scaffold_project(
            parent_dir=tmp_path,
            name="uv_study",
            schema_keys=["subject"],
            run_uv_sync=False,
            configure_db=False,
        )
        self._strip_unresolvable_deps(root)
        result = sync(root, timeout=120)
        assert result.ok, f"uv sync failed: {result.stderr}"
        assert (root / "uv.lock").exists()

    def test_scaffold_full_roundtrip(self, tmp_path):
        """Full scaffold: DB + uv sync + verify everything present."""
        from scistack.uv_wrapper import sync

        root = scaffold_project(
            parent_dir=tmp_path,
            name="full_study",
            schema_keys=["subject", "session"],
            run_uv_sync=False,
            configure_db=True,
        )
        self._strip_unresolvable_deps(root)
        result = sync(root, timeout=120)
        assert result.ok, f"uv sync failed: {result.stderr}"
        assert (root / "pyproject.toml").is_file()
        assert (root / "uv.lock").exists()
        assert (root / "full_study.duckdb").is_file()
        assert (root / "src" / "full_study" / "__init__.py").is_file()
        assert (root / ".scistack" / "project.toml").is_file()
        assert (root / ".gitignore").is_file()
        assert (root / "README.md").is_file()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
class TestCli:
    def test_cli_bad_name(self):
        from scistack.__main__ import main

        assert main(["project", "new", "Bad Name", "--schema-keys", "subject"]) == 1

    def test_cli_no_args_returns_1(self):
        from scistack.__main__ import main

        assert main([]) == 1
