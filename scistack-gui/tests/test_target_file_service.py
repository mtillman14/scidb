"""
Tests for scistack_gui.services.target_file_service.get_or_create_target_file.

Regression coverage for the bug where creating a PathInput/Sweep/Variable
from the GUI silently failed (or, for Variable, surfaced a confusing
"--module not passed" error) whenever a project-mode config had no
``variable_file`` set -- there was no GUI way to configure one. See
.claude/pathinput-sweep-variable-creation-fixes.md.
"""

from __future__ import annotations

from pathlib import Path

import scistack_gui.registry as _registry
from scistack_gui import config as config_mod
from scistack_gui.services.target_file_service import get_or_create_target_file


def test_legacy_module_path_used_directly(populated_db, tmp_path):
    module_path = tmp_path / "pipeline.py"
    module_path.write_text("")
    _registry._module_path = module_path
    _registry._config = None

    target, err = get_or_create_target_file()

    assert err is None
    assert target == module_path


def test_already_configured_variable_file_used_directly(populated_db, tmp_path):
    from scistack_gui.db import get_db_path

    explicit = tmp_path / "vars.py"
    config_mod.set_variable_file(get_db_path(), explicit)
    _registry._config = config_mod.load_config(None, get_db_path())
    _registry._module_path = None

    target, err = get_or_create_target_file()

    assert err is None
    assert target == config_mod._normalize(explicit)
    # No reload was needed -- the toml is untouched beyond the setup call.
    toml_path = tmp_path / "scistack.toml"
    assert toml_path.exists()


def test_auto_creates_default_when_config_present_but_unset(populated_db, tmp_path):
    from scistack_gui.db import get_db_path

    # Folder-scan config: valid project, but no variable_file configured
    # (the common case -- server.py's auto-discovery path when no
    # --module/--project flag was passed).
    _registry._config = config_mod.load_config(None, get_db_path())
    _registry._module_path = None
    assert _registry._config.variable_file is None

    target, err = get_or_create_target_file()

    assert err is None
    expected = config_mod._normalize(tmp_path / "src" / "scistack_entities.py")
    assert target == expected
    assert expected.exists()
    assert "import scidb" in expected.read_text()
    # In-memory config was refreshed so subsequent calls see it too.
    assert _registry._config.variable_file == expected

    target2, err2 = get_or_create_target_file()
    assert err2 is None
    assert target2 == expected


def test_packaged_project_returns_hand_edit_error(populated_db, tmp_path):
    from scistack_gui.db import get_db_path

    (tmp_path / "pyproject.toml").write_text("[tool.scistack]\n")
    _registry._config = config_mod.load_config(None, get_db_path())
    _registry._module_path = None

    target, err = get_or_create_target_file()

    assert target is None
    assert "pyproject.toml" in err


def test_no_config_and_no_module_returns_original_error():
    _registry._config = None
    _registry._module_path = None

    target, err = get_or_create_target_file()

    assert target is None
    assert "No module file was loaded at startup" in err


# ---------------------------------------------------------------------------
# update_declaration — in-place rewriting (plan Stage 5)
# ---------------------------------------------------------------------------


class TestUpdateDeclaration:
    """Editing a declaration writes to source; the guards make sure it can
    only ever touch the entities file, never over a concurrent change, and
    never leaves a file the scanner can't read."""

    def _project(self, tmp_path, body):
        """Configure a loose project whose entities file contains *body*."""
        from scistack_gui.db import get_db_path

        entities = tmp_path / "entities.py"
        entities.write_text(body)
        config_mod.set_variable_file(get_db_path(), entities)
        _registry._module_path = None
        _registry.load_from_config(config_mod.load_config(None, get_db_path()))
        return entities

    def test_rewrites_a_constant_value(self, populated_db, tmp_path):
        """The registry assertion is the important one: an edit that changes
        neither the file's SIZE nor its whole-second mtime (30 -> 45) will
        re-execute stale bytecode unless the write invalidates it, leaving
        the GUI showing the old value with nothing logged anywhere."""
        from scistack_gui.services.parameter_service import update_parameter

        entities = self._project(
            tmp_path, "import scidb\n\nWINDOW = scidb.Parameter(30, description='w')\n"
        )

        result = update_parameter("WINDOW", [45], "w")

        assert result["ok"], result
        assert "scidb.Parameter(45, description='w')" in entities.read_text()
        assert _registry.get_parameters_registry()["WINDOW"].value == 45

    def test_same_length_edit_is_not_served_from_stale_bytecode(
        self, populated_db, tmp_path
    ):
        """Regression for the above, made explicit: several same-size edits
        in quick succession must each be visible to the next scan."""
        from scistack_gui.services.parameter_service import update_parameter

        self._project(
            tmp_path, "import scidb\n\nWINDOW = scidb.Parameter(11, description='')\n"
        )

        for value in (22, 33, 44):
            assert update_parameter("WINDOW", [value])["ok"]
            assert _registry.get_parameters_registry()["WINDOW"].value == value

    def test_rewrites_a_sweep(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import update_parameter

        entities = self._project(
            tmp_path, "import scidb\n\nW = scidb.Parameter(1, 2)\n"
        )

        assert update_parameter("W", [3, 4, 5])["ok"]
        assert "scidb.Parameter(3, 4, 5, description='')" in entities.read_text()
        assert list(_registry.get_parameters_registry()["W"].alternatives) == [3, 4, 5]

    def test_rewrites_a_path_input(self, populated_db, tmp_path):
        from scistack_gui.services.path_input_service import update_path_input

        entities = self._project(
            tmp_path, "import scidb\n\nRAW = scidb.PathInput('a.csv')\n"
        )

        assert update_path_input("RAW", "{subject}/b.csv")["ok"]
        assert "scidb.PathInput('{subject}/b.csv')" in entities.read_text()

    def test_adding_a_value_is_the_same_splice(self, populated_db, tmp_path):
        """Adding a second value is adding an argument -- no change of form,
        no change of kind, no special case. The span covers the whole RHS,
        so it is the identical splice a value edit performs."""
        from scidb.source_edit import render_parameter

        from scistack_gui.matlab_parser import render_matlab_parameter
        from scistack_gui.services.target_file_service import update_declaration

        entities = self._project(
            tmp_path, "import scidb\n\nW = scidb.Parameter(30, description='')\n"
        )

        result = update_declaration(
            "parameter",
            "W",
            python_expr=render_parameter([30, 45]),
            matlab_expr=render_matlab_parameter([30, 45]),
        )

        assert result["ok"], result
        assert "W = scidb.Parameter(30, 45, description='')" in entities.read_text()
        assert list(_registry.get_parameters_registry()["W"].alternatives) == [30, 45]

    def test_surrounding_content_is_untouched(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import update_parameter

        entities = self._project(
            tmp_path,
            "import scidb\n"
            "\n"
            "# keep me\n"
            "WINDOW = scidb.Parameter(30, description='')  # and me\n"
            "OTHER = scidb.Parameter(1, description='')\n",
        )

        assert update_parameter("WINDOW", [45])["ok"]
        text = entities.read_text()
        assert "# keep me" in text
        assert "# and me" in text
        assert "OTHER = scidb.Parameter(1, description='')" in text

    def test_refuses_a_declaration_outside_the_entities_file(
        self, populated_db, tmp_path
    ):
        """The confinement rule: read-only, with the exact location so the UI
        can point at it instead of a generic hint."""
        from scistack_gui.db import get_db_path
        from scistack_gui.services.parameter_service import update_parameter

        other = tmp_path / "params.py"
        other.write_text("import scidb\n\nOUTSIDE = scidb.Parameter(7, description='')\n")
        entities = tmp_path / "entities.py"
        entities.write_text("import scidb\n")
        config_mod.set_variable_file(get_db_path(), entities)
        config_mod.add_path(get_db_path(), tmp_path)
        _registry._module_path = None
        _registry.load_from_config(config_mod.load_config(None, get_db_path()))

        result = update_parameter("OUTSIDE", [9])

        assert not result["ok"]
        assert result["reason"] == "read_only"
        assert result["file"] == str(other)
        assert result["line"] == 3
        assert "params.py" in result["error"]
        # ...and the file really was not touched.
        assert "scidb.Parameter(7" in other.read_text()

    def test_stale_file_is_refused_not_clobbered(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import update_parameter

        entities = self._project(
            tmp_path, "import scidb\n\nWINDOW = scidb.Parameter(30, description='')\n"
        )
        # Someone edits the file behind the GUI's back.
        entities.write_text(
            "import scidb\n\nWINDOW = scidb.Parameter(99, description='')\n"
        )

        result = update_parameter("WINDOW", [45])

        assert not result["ok"]
        assert result["reason"] == "stale"
        assert "Refresh Code" in result["error"]
        assert "scidb.Parameter(99" in entities.read_text()

    def test_unknown_entity_is_reported(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import update_parameter

        self._project(tmp_path, "import scidb\n")
        result = update_parameter("NOPE", [1])
        assert not result["ok"]
        assert "NOPE" in result["error"]

    def test_empty_sweep_is_rejected(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import update_parameter

        entities = self._project(tmp_path, "import scidb\n\nW = scidb.Parameter(1)\n")
        result = update_parameter("W", [])
        assert not result["ok"]
        assert "scidb.Parameter(1)" in entities.read_text()

    def test_no_op_write_is_reported_as_unchanged(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import update_parameter

        self._project(
            tmp_path, "import scidb\n\nWINDOW = scidb.Parameter(30, description='')\n"
        )
        result = update_parameter("WINDOW", [30])
        assert result["ok"]
        assert result.get("unchanged")


class TestPathInputHistory:
    """D7: a GUI template edit must not detach the runs recorded against the
    old template. Written from exactly one place — just before a write-back
    overwrites one — so nothing is recorded until an edit actually happens.
    """

    def _project(self, tmp_path, body):
        from scistack_gui.db import get_db_path

        entities = tmp_path / "entities.py"
        entities.write_text(body)
        config_mod.set_variable_file(get_db_path(), entities)
        _registry._module_path = None
        _registry.load_from_config(config_mod.load_config(None, get_db_path()))
        return entities

    def test_nothing_is_recorded_until_an_edit_happens(self, populated_db, tmp_path):
        """Merely loading a project writes nothing — the table exists for
        edits, not as a log of every scan."""
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db

        self._project(tmp_path, "import scidb\n\nRAW = scidb.PathInput('a.csv')\n")

        assert pipeline_store.list_path_input_history(get_db()) == []

    def test_old_template_still_resolves_after_an_edit(self, populated_db, tmp_path):
        """The whole point: a run recorded against 'a.csv' can still be
        attributed to RAW instead of collapsing into __unresolved__."""
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db
        from scistack_gui.services.path_input_service import update_path_input

        self._project(tmp_path, "import scidb\n\nRAW = scidb.PathInput('a.csv')\n")

        assert update_path_input("RAW", "b.csv")["ok"]

        assert pipeline_store.lookup_path_input_name(get_db(), "a.csv") == "RAW"

    def test_repeated_edits_accumulate(self, populated_db, tmp_path):
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db
        from scistack_gui.services.path_input_service import update_path_input

        self._project(tmp_path, "import scidb\n\nRAW = scidb.PathInput('a.csv')\n")
        assert update_path_input("RAW", "b.csv")["ok"]
        assert update_path_input("RAW", "c.csv")["ok"]

        db = get_db()
        assert pipeline_store.lookup_path_input_name(db, "a.csv") == "RAW"
        assert pipeline_store.lookup_path_input_name(db, "b.csv") == "RAW"

    def test_recording_is_idempotent(self, populated_db, tmp_path):
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db

        self._project(tmp_path, "import scidb\n")
        db = get_db()
        pipeline_store.record_path_input_value(db, "RAW", "a.csv")
        pipeline_store.record_path_input_value(db, "RAW", "a.csv")

        assert len(pipeline_store.list_path_input_history(db, "RAW")) == 1

    def test_unknown_template_returns_none(self, populated_db, tmp_path):
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db

        self._project(tmp_path, "import scidb\n")

        assert pipeline_store.lookup_path_input_name(get_db(), "never.csv") is None

    def test_root_folder_is_part_of_the_key(self, populated_db, tmp_path):
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db

        self._project(tmp_path, "import scidb\n")
        db = get_db()
        pipeline_store.record_path_input_value(db, "RAW", "a.csv", "/data")

        assert pipeline_store.lookup_path_input_name(db, "a.csv", "/data") == "RAW"
        assert pipeline_store.lookup_path_input_name(db, "a.csv") is None
