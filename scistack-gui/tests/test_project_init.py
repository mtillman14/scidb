"""
Opening a project must leave it with somewhere to declare entities.

Regression cover for the 2026-09-01 report: ``config.add_path`` created a
``scistack.toml`` with no ``entities_file`` key, and
``scidb.entities.entities_path`` only falls back to the conventional
``src/scistack_entities.toml`` when it already exists. The project therefore
had no writable declaration surface at all -- the log's summary line read
``entities_file=None (writable)`` -- so a variable placed on the canvas
could not be declared, and no MATLAB classdef could be materialized for it
(``scimatlab.stubs.variable_stub_dir`` returns ``None`` with no entities
file to sit beside). The run died as ``Unrecognized function or variable
'Raw_EMG'``.

See ``.claude/plan-entity-surfaces-and-reload-cost.md`` Stage 1.
"""

from __future__ import annotations

import pytest

from scistack_gui.services.project_init_service import (
    ensure_language_stubs,
    ensure_project_files,
)


@pytest.fixture(autouse=True)
def _clear_entities_cache():
    from scidb import entities

    entities.clear_cache()
    yield
    entities.clear_cache()


class TestEnsureProjectFiles:
    def test_creates_config_and_entities_file_in_a_bare_project(self, tmp_path):
        result = ensure_project_files(tmp_path / "data.duckdb")

        assert (tmp_path / "scistack.toml").exists()
        assert (tmp_path / "src" / "scistack_entities.toml").exists()
        assert result.entities_file == tmp_path / "src" / "scistack_entities.toml"
        assert len(result.created) == 2

    def test_the_created_config_actually_names_the_entities_file(self, tmp_path):
        """The exact gap that caused the bug: a config can exist and still
        leave the project with no writable surface."""
        ensure_project_files(tmp_path / "data.duckdb")

        from scistack_gui.config import load_config

        config = load_config(tmp_path, tmp_path / "data.duckdb")
        assert config.entities_file is not None
        assert config.entities_file.exists()

    def test_is_idempotent_and_does_not_rewrite_on_reopen(self, tmp_path):
        ensure_project_files(tmp_path / "data.duckdb")
        toml = tmp_path / "scistack.toml"
        before_text = toml.read_text()
        before_mtime = toml.stat().st_mtime_ns

        second = ensure_project_files(tmp_path / "data.duckdb")

        assert second.created == []
        assert toml.read_text() == before_text
        assert toml.stat().st_mtime_ns == before_mtime, (
            "reopening a project rewrote scistack.toml; that churns git status "
            "and bumps the mtime other staleness guards read"
        )

    def test_never_overwrites_an_existing_entities_file(self, tmp_path):
        (tmp_path / "scistack.toml").write_text(
            'entities_file = "src/scistack_entities.toml"\n', encoding="utf-8"
        )
        (tmp_path / "src").mkdir()
        declared = tmp_path / "src" / "scistack_entities.toml"
        declared.write_text('variables = ["Existing"]\n', encoding="utf-8")

        ensure_project_files(tmp_path / "data.duckdb")

        assert declared.read_text() == 'variables = ["Existing"]\n'

    def test_a_packaged_project_is_reported_not_written(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\n', encoding="utf-8"
        )
        before = (tmp_path / "pyproject.toml").read_text()

        result = ensure_project_files(tmp_path / "data.duckdb")

        assert (tmp_path / "pyproject.toml").read_text() == before
        assert not (tmp_path / "scistack.toml").exists()
        assert result.created == []
        assert any("pyproject.toml" in w for w in result.warnings)
        assert any("entities_file" in w for w in result.warnings)


class TestLanguageStubs:
    def _config(self, tmp_path):
        from scistack_gui.config import load_config

        ensure_project_files(tmp_path / "data.duckdb")
        from scidb import entities

        entities.clear_cache()
        return load_config(tmp_path, tmp_path / "data.duckdb")

    def test_python_project_gets_only_the_py_stub(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "steps.py").write_text("def a(x):\n    return x\n", encoding="utf-8")

        ensure_language_stubs(self._config(tmp_path))

        assert (src / "scistack_entities.py").exists()
        assert not (src / "scistack_entities.m").exists()

    def test_matlab_project_gets_the_m_stub(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "doThing.m").write_text(
            "function y = doThing(x)\ny = x;\nend\n", encoding="utf-8"
        )

        config = self._config(tmp_path)
        ensure_language_stubs(config)

        if config.has_matlab:
            assert (src / "scistack_entities.m").exists()

    def test_never_overwrites_a_hand_written_stub(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "steps.py").write_text("def a(x):\n    return x\n", encoding="utf-8")
        config = self._config(tmp_path)

        mine = src / "scistack_entities.py"
        mine.write_text("# mine\nimport scidb\n", encoding="utf-8")

        result = ensure_language_stubs(config)

        assert mine.read_text() == "# mine\nimport scidb\n"
        assert str(mine) not in result.created

    def test_the_python_stub_is_importable_and_declares_nothing(self, tmp_path):
        """It must be inert: a stub that broke on import would take out
        discovery for the whole file, silently."""
        src = tmp_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "steps.py").write_text("def a(x):\n    return x\n", encoding="utf-8")
        ensure_language_stubs(self._config(tmp_path))

        import ast

        tree = ast.parse((src / "scistack_entities.py").read_text())
        assert not [n for n in tree.body if isinstance(n, ast.ClassDef)]

    def test_no_stubs_without_an_entities_file(self, tmp_path):
        """A packaged project init refused: nothing to sit beside."""

        class _Config:
            entities_file = None
            modules = []
            packages = []
            has_matlab = False
            project_root = tmp_path

        assert ensure_language_stubs(_Config()).created == []
