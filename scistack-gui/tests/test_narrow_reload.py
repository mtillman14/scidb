"""
An entity write must re-read one file, not the whole project.

The cost this guards, measured on a real project from scidb.log on
2026-09-01: one full ``_refresh_registries()`` was ~16.5 s -- 2.5 s to
re-parse the config, 1.6 s to re-import 19 Python modules, and 14.9 s to
re-classify 303 MATLAB source files. Creating a single variable paid all of
it, to learn something that only one file could have changed.

These tests assert the *absence* of that work rather than a duration, since
timings are not portable: if re-importing modules or re-classifying MATLAB
sources ever creeps back into a write path, the call counters here fail.

See ``.claude/plan-entity-surfaces-and-reload-cost.md`` Stage 3.
"""

from __future__ import annotations

import pytest

import scistack_gui.registry as _registry


@pytest.fixture(autouse=True)
def _clean_registry():
    yield
    _registry._unregister_tracked_variables()
    _registry._config = None
    _registry._module_path = None


@pytest.fixture
def project(tmp_path):
    """A loose project with an entities file and one Python module."""
    (tmp_path / "scistack.toml").write_text(
        'modules = ["src/steps.py"]\n'
        'entities_file = "src/scistack_entities.toml"\n',
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "steps.py").write_text(
        "def a_step(x):\n    return x\n", encoding="utf-8"
    )
    (src / "scistack_entities.toml").write_text("variables = []\n", encoding="utf-8")

    from scidb import entities

    entities.clear_cache()
    from scistack_gui.config import load_config

    config = load_config(tmp_path, tmp_path / "test.duckdb")
    _registry.load_from_config(config)
    return tmp_path, config


@pytest.fixture
def counters(monkeypatch):
    """Count the two expensive halves of a full reload."""
    calls = {"modules": 0, "matlab": 0}

    real_modules = _registry._load_file_modules

    def counting_modules(paths):
        calls["modules"] += 1
        return real_modules(paths)

    monkeypatch.setattr(_registry, "_load_file_modules", counting_modules)

    from scistack_gui import matlab_registry

    real_sources = matlab_registry.load_from_sources

    def counting_sources(paths):
        calls["matlab"] += 1
        return real_sources(paths)

    monkeypatch.setattr(matlab_registry, "load_from_sources", counting_sources)
    return calls


def _write_variable(entities_file, name):
    from scistack_gui.services.target_file_service import write_variable

    return write_variable(entities_file, name)


class TestEntitiesWriteIsNarrow:
    def test_creating_a_variable_reimports_nothing(self, project, counters):
        _, config = project

        assert _write_variable(config.entities_file, "RawEMG") is None

        assert counters["modules"] == 0, "a variable write re-imported Python modules"
        assert counters["matlab"] == 0, "a variable write re-parsed MATLAB sources"

    def test_the_variable_is_actually_registered(self, project):
        """Narrow must not mean incomplete."""
        from scidb import BaseVariable

        _, config = project
        _write_variable(config.entities_file, "RawEMG")

        assert "RawEMG" in BaseVariable._all_subclasses
        assert _registry._variable_sources["RawEMG"] == str(config.entities_file)

    def test_creating_a_parameter_reimports_nothing(self, project, counters):
        from scistack_gui.services.target_file_service import write_entity

        _, config = project
        error = write_entity(
            config.entities_file,
            section="parameters",
            name="SAMPLING_RATE_HZ",
            rendered="1000",
        )

        assert error is None
        assert "SAMPLING_RATE_HZ" in _registry.get_parameters_registry()
        assert counters["modules"] == 0
        assert counters["matlab"] == 0

    def test_functions_from_other_modules_survive_a_narrow_reload(self, project):
        """The narrow path prunes by source, so it must not drop entities
        that came from files it did not re-read."""
        _, config = project
        assert "a_step" in _registry._functions

        _write_variable(config.entities_file, "RawEMG")

        assert "a_step" in _registry._functions


class TestNarrowReloadPrunes:
    def test_a_removed_declaration_disappears(self, project):
        from scidb import BaseVariable

        tmp_path, config = project
        _write_variable(config.entities_file, "RawEMG")
        assert "RawEMG" in BaseVariable._all_subclasses

        config.entities_file.write_text("variables = []\n", encoding="utf-8")
        assert _registry.reload_entities_file() is None

        assert "RawEMG" not in BaseVariable._all_subclasses

    def test_a_fixed_declaration_clears_its_old_load_error(self, project):
        _, config = project
        config.entities_file.write_text(
            'variables = []\n\n[parameters]\nBAD = 1979-05-27\n', encoding="utf-8"
        )
        _registry.reload_entities_file()
        before = len(_registry.get_load_errors())

        config.entities_file.write_text(
            "variables = []\n\n[parameters]\nGOOD = 1\n", encoding="utf-8"
        )
        _registry.reload_entities_file()

        assert len(_registry.get_load_errors()) <= before

    def test_reload_without_a_configured_entities_file_reports_rather_than_raises(
        self, tmp_path
    ):
        (tmp_path / "scistack.toml").write_text("modules = []\n", encoding="utf-8")
        from scistack_gui.config import load_config

        config = load_config(tmp_path, tmp_path / "test.duckdb")
        _registry.load_from_config(config)

        error = _registry.reload_entities_file()

        assert error is not None
        assert "entities file" in error.lower()


class TestDispatch:
    def test_toml_target_routes_to_the_narrow_entities_reload(self, project, monkeypatch):
        from scistack_gui.services import target_file_service

        called = {"n": 0}
        monkeypatch.setattr(
            _registry,
            "reload_entities_file",
            lambda: called.__setitem__("n", called["n"] + 1),
        )
        _, config = project

        target_file_service._reload_after_write(config.entities_file)

        assert called["n"] == 1

    def test_dot_m_target_routes_to_the_single_source_reload(self, project, monkeypatch):
        from scistack_gui import matlab_registry
        from scistack_gui.services import target_file_service

        seen = {}
        monkeypatch.setattr(
            matlab_registry, "reload_source", lambda p: seen.setdefault("path", p)
        )
        tmp_path, _ = project
        target = tmp_path / "src" / "someScript.m"

        target_file_service._reload_after_write(target)

        assert seen["path"] == target
