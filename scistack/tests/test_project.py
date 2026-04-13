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

    def test_cli_project_new_happy_path(self, tmp_path):
        from scistack.__main__ import main

        ret = main([
            "project", "new", "cli_study",
            "--schema-keys", "subject", "session",
            "--parent-dir", str(tmp_path),
            "--no-uv-sync",
        ])
        assert ret == 0
        assert (tmp_path / "cli_study" / "pyproject.toml").is_file()
        assert (tmp_path / "cli_study" / "src" / "cli_study" / "__init__.py").is_file()

    def test_cli_existing_dir_returns_1(self, tmp_path):
        from scistack.__main__ import main

        (tmp_path / "dup_study").mkdir()
        ret = main([
            "project", "new", "dup_study",
            "--schema-keys", "subject",
            "--parent-dir", str(tmp_path),
            "--no-uv-sync",
        ])
        assert ret == 1

    def test_cli_project_subcommand_without_new_returns_1(self):
        from scistack.__main__ import main

        assert main(["project"]) == 1


# ---------------------------------------------------------------------------
# scaffold_project — schema keys edge cases
# ---------------------------------------------------------------------------
class TestScaffoldSchemaKeys:
    def test_single_schema_key(self, tmp_path):
        root = scaffold_project(
            parent_dir=tmp_path,
            name="single_key",
            schema_keys=["subject"],
            run_uv_sync=False,
            configure_db=False,
        )
        readme = (root / "README.md").read_text()
        assert "['subject']" in readme

    def test_many_schema_keys(self, tmp_path):
        keys = ["subject", "session", "run", "condition"]
        root = scaffold_project(
            parent_dir=tmp_path,
            name="many_keys",
            schema_keys=keys,
            run_uv_sync=False,
            configure_db=False,
        )
        readme = (root / "README.md").read_text()
        for key in keys:
            assert key in readme

    def test_readme_schema_keys_repr(self, tmp_path):
        """README must embed the schema keys in a valid Python repr."""
        root = scaffold_project(
            parent_dir=tmp_path,
            name="repr_study",
            schema_keys=["subject", "session"],
            run_uv_sync=False,
            configure_db=False,
        )
        readme = (root / "README.md").read_text()
        assert "['subject', 'session']" in readme

    def test_init_template_has_project_name(self, tmp_path):
        root = scaffold_project(
            parent_dir=tmp_path,
            name="init_study",
            schema_keys=["subject"],
            run_uv_sync=False,
            configure_db=False,
        )
        text = (root / "src" / "init_study" / "__init__.py").read_text()
        assert "init_study" in text


# ---------------------------------------------------------------------------
# scaffold_project — validate_project_name edge cases
# ---------------------------------------------------------------------------
class TestValidateProjectNameEdgeCases:
    def test_underscores_only_after_first_char_rejected(self):
        with pytest.raises(ValueError, match="Invalid project name"):
            validate_project_name("_leading")

    def test_single_letter_valid(self):
        validate_project_name("x")  # should not raise

    def test_long_name_valid(self):
        validate_project_name("a" * 100)  # should not raise

    def test_trailing_underscore_valid(self):
        validate_project_name("study_")  # should not raise

    def test_only_digits_after_letter_valid(self):
        validate_project_name("a123")  # should not raise


# ---------------------------------------------------------------------------
# scaffold_project — template content correctness
# ---------------------------------------------------------------------------
class TestTemplateContent:
    @pytest.fixture
    def project_root(self, tmp_path):
        return scaffold_project(
            parent_dir=tmp_path,
            name="tmpl_study",
            schema_keys=["subject", "session"],
            run_uv_sync=False,
            configure_db=False,
        )

    def test_pyproject_hatch_packages_path(self, project_root):
        """Hatch build target must point at src/{name}."""
        with open(project_root / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        pkgs = data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
        assert pkgs == ["src/tmpl_study"]

    def test_gitignore_contains_wal(self, project_root):
        text = (project_root / ".gitignore").read_text()
        assert "*.duckdb.wal" in text

    def test_gitignore_contains_pycache(self, project_root):
        text = (project_root / ".gitignore").read_text()
        assert "__pycache__/" in text

    def test_project_toml_has_version(self, project_root):
        text = (project_root / ".scistack" / "project.toml").read_text()
        assert 'version = "0.1.0"' in text

    def test_project_toml_created_is_iso_date(self, project_root):
        text = (project_root / ".scistack" / "project.toml").read_text()
        # ISO dates contain "T" and "+00:00" or "Z"
        assert "created" in text
        # Just verify it parses as a date
        import datetime
        for line in text.splitlines():
            if "created" in line:
                date_str = line.split("=", 1)[1].strip().strip('"')
                dt = datetime.datetime.fromisoformat(date_str)
                assert dt.tzinfo is not None
