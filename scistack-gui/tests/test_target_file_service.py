"""
Tests for scistack_gui.services.target_file_service.get_or_create_target_file.

Regression coverage for the bug where creating a PathInput/Parameter/Variable
from the GUI silently failed (or, for Variable, surfaced a confusing
"--module not passed" error) whenever a project-mode config had no entities
file set -- there was no GUI way to configure one. See
.claude/pathinput-sweep-variable-creation-fixes.md.

``TestUpdateDeclaration`` below still configures a ``.py`` entities file and
asserts Python splices: ``update_declaration``'s grammar dispatch moves to
TOML in Stage 4 of ``.claude/plan-entities-toml-26-08-31.md``, and these
tests move with it. The *policy* they cover -- confinement, staleness,
rollback -- is format-independent and does not change.
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


def test_already_configured_entities_file_used_directly(populated_db, tmp_path):
    from scistack_gui.db import get_db_path

    explicit = tmp_path / "entities.toml"
    config_mod.set_entities_file(get_db_path(), explicit)
    _registry._config = config_mod.load_config(None, get_db_path())
    _registry._module_path = None

    target, err = get_or_create_target_file()

    assert err is None
    assert target == config_mod._normalize(explicit)
    # No reload was needed -- the toml is untouched beyond the setup call.
    toml_path = tmp_path / "scistack.toml"
    assert toml_path.exists()


def test_entities_file_wins_over_a_legacy_variable_file(populated_db, tmp_path):
    """A project with BOTH keys writes to the TOML. The .py file's
    declarations are still discovered -- they are just read-only now."""
    from scistack_gui.db import get_db_path

    legacy = tmp_path / "legacy_vars.py"
    legacy.write_text("import scidb\n")
    entities = tmp_path / "entities.toml"
    (tmp_path / "scistack.toml").write_text(
        f'variable_file = "{legacy.name}"\nentities_file = "{entities.name}"\n'
    )
    entities.write_text("[parameters]\n")
    _registry._config = config_mod.load_config(None, get_db_path())
    _registry._module_path = None

    target, err = get_or_create_target_file()

    assert err is None
    assert target == config_mod._normalize(entities)
    # ...and the legacy file is still scanned, via modules.
    assert config_mod._normalize(legacy) in _registry._config.modules


def test_auto_creates_default_when_config_present_but_unset(populated_db, tmp_path):
    from scistack_gui.db import get_db_path

    # Folder-scan config: valid project, but no entities_file configured
    # (the common case -- server.py's auto-discovery path when no
    # --module/--project flag was passed).
    _registry._config = config_mod.load_config(None, get_db_path())
    _registry._module_path = None
    assert _registry._config.entities_file is None

    target, err = get_or_create_target_file()

    assert err is None
    expected = config_mod._normalize(tmp_path / "src" / "scistack_entities.toml")
    assert target == expected
    assert expected.exists()
    assert "variables = []" in expected.read_text()
    # In-memory config was refreshed so subsequent calls see it too.
    assert _registry._config.entities_file == expected

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
# Creation — writing a NEW declaration into the TOML entities file
# (.claude/plan-entities-toml-26-08-31.md Stage 4)
# ---------------------------------------------------------------------------


class TestCreateWritesToml:
    """The create path writes TOML entries, and the result parses back."""

    def _project(self, tmp_path):
        from scistack_gui.db import get_db_path

        entities = config_mod.set_entities_file(get_db_path(), None)
        _registry._module_path = None
        _registry.load_from_config(config_mod.load_config(None, get_db_path()))
        return entities

    def test_create_parameter_writes_a_scalar(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import create_parameter

        entities = self._project(tmp_path)

        assert create_parameter("RATE", [1000])["ok"]

        assert "RATE = 1000" in entities.read_text()
        assert _registry.get_parameters_registry()["RATE"].value == 1000

    def test_create_parameter_writes_an_array(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import create_parameter

        entities = self._project(tmp_path)

        assert create_parameter("WINDOW", [10, 20, 30])["ok"]

        assert "WINDOW = [10, 20, 30]" in entities.read_text()
        assert _registry.get_parameters_registry()["WINDOW"].values == [10, 20, 30]

    def test_create_path_input_with_root_writes_a_table(self, populated_db, tmp_path):
        from scistack_gui.services.path_input_service import create_path_input

        entities = self._project(tmp_path)

        assert create_path_input("RAW", "{subject}/raw.csv", "/data")["ok"]

        text = entities.read_text()
        assert 'RAW = { template = "{subject}/raw.csv", root_folder = "/data" }' in text
        assert _registry.get_path_inputs_registry()["RAW"].path_template == (
            "{subject}/raw.csv"
        )

    def test_create_variable_appends_to_the_array(self, populated_db, tmp_path):
        from scidb import BaseVariable

        from scistack_gui.services.variable_service import create_variable

        entities = self._project(tmp_path)

        assert create_variable("StepLength")["ok"]

        assert '"StepLength"' in entities.read_text()
        assert "StepLength" in BaseVariable._all_subclasses

    def test_two_creates_land_in_one_valid_file(self, populated_db, tmp_path):
        """Each write re-parses the whole file, so a second create must not
        corrupt what the first wrote."""
        from scidb.entities import load

        from scistack_gui.services.parameter_service import create_parameter
        from scistack_gui.services.path_input_service import create_path_input
        from scistack_gui.services.variable_service import create_variable

        entities = self._project(tmp_path)

        assert create_parameter("A", [1])["ok"]
        assert create_path_input("P", "x/{s}.csv")["ok"]
        assert create_variable("V")["ok"]
        assert create_parameter("B", ["01", "02"])["ok"]

        result = load(entities)
        assert result.errors == []
        assert result.parameters["A"].value == 1
        assert result.parameters["B"].values == ["01", "02"]
        assert result.path_inputs["P"].path_template == "x/{s}.csv"
        assert "V" in result.variables

    def test_description_is_dropped_with_a_warning(
        self, populated_db, tmp_path, caplog
    ):
        """The TOML format has no description field (plan D4). Dropping it
        silently would be worse than not offering it."""
        import logging

        from scistack_gui.services.parameter_service import create_parameter

        self._project(tmp_path)

        with caplog.at_level(logging.WARNING):
            assert create_parameter("RATE", [1000], "Recording rate")["ok"]

        assert any("Dropping description" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# update_declaration — in-place rewriting (plan Stage 5)
# ---------------------------------------------------------------------------


class TestUpdateDeclaration:
    """Editing a declaration writes to source; the guards make sure it can
    only ever touch the entities file, never over a concurrent change, and
    never leaves a file the scanner can't read."""

    def _project(self, tmp_path, body):
        """Configure a loose project whose TOML entities file contains
        *body*."""
        from scistack_gui.db import get_db_path

        entities = tmp_path / "entities.toml"
        entities.write_text(body)
        config_mod.set_entities_file(get_db_path(), entities)
        _registry._module_path = None
        _registry.load_from_config(config_mod.load_config(None, get_db_path()))
        return entities

    def test_rewrites_a_parameter_value(self, populated_db, tmp_path):
        """The registry assertion is the important one: the edit has to be
        visible to the next scan, not just on disk.

        The ``.py`` entities file this replaces had a nasty failure mode
        here -- an edit changing neither the file's SIZE nor its
        whole-second mtime (30 -> 45) re-executed STALE BYTECODE, so the GUI
        kept showing the old value with nothing logged anywhere. TOML is
        parsed, never imported, so that entire class of bug is gone by
        construction rather than by remembering to invalidate a cache.
        """
        from scistack_gui.services.parameter_service import update_parameter

        entities = self._project(tmp_path, "[parameters]\nWINDOW = 30\n")

        result = update_parameter("WINDOW", [45])

        assert result["ok"], result
        assert "WINDOW = 45" in entities.read_text()
        assert _registry.get_parameters_registry()["WINDOW"].value == 45

    def test_repeated_same_length_edits_are_each_visible(
        self, populated_db, tmp_path
    ):
        """Several same-size edits in quick succession must each reach the
        registry -- the scenario that used to be served from stale bytecode."""
        from scistack_gui.services.parameter_service import update_parameter

        self._project(tmp_path, "[parameters]\nWINDOW = 11\n")

        for value in (22, 33, 44):
            assert update_parameter("WINDOW", [value])["ok"]
            assert _registry.get_parameters_registry()["WINDOW"].value == value

    def test_rewrites_a_multi_valued_parameter(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import update_parameter

        entities = self._project(tmp_path, "[parameters]\nW = [1, 2]\n")

        assert update_parameter("W", [3, 4, 5])["ok"]
        assert "W = [3, 4, 5]" in entities.read_text()
        assert list(_registry.get_parameters_registry()["W"].alternatives) == [3, 4, 5]

    def test_rewrites_a_path_input(self, populated_db, tmp_path):
        from scistack_gui.services.path_input_service import update_path_input

        entities = self._project(tmp_path, '[path_inputs]\nRAW = "a.csv"\n')

        assert update_path_input("RAW", "{subject}/b.csv")["ok"]
        assert 'RAW = "{subject}/b.csv"' in entities.read_text()

    def test_zero_padded_value_survives_an_edit(self, populated_db, tmp_path):
        """The property the format exists for: no eval, no literal re-parse,
        so "01" comes back a string (feedback_zero_padded_schema_keys)."""
        from scistack_gui.services.parameter_service import update_parameter

        entities = self._project(tmp_path, '[parameters]\nSUBJECTS = ["01"]\n')

        assert update_parameter("SUBJECTS", ["01", "02"])["ok"]
        assert 'SUBJECTS = ["01", "02"]' in entities.read_text()
        assert _registry.get_parameters_registry()["SUBJECTS"].values == ["01", "02"]

    def test_adding_a_value_is_the_same_splice(self, populated_db, tmp_path):
        """Adding a second value changes the RHS from a scalar to an array --
        a change of form, but the identical splice a value edit performs, and
        no change of kind, node or history (D6)."""
        from scidb.entities import render_parameter_value
        from scidb.source_edit import render_parameter

        from scistack_gui.matlab_parser import render_matlab_parameter
        from scistack_gui.services.target_file_service import update_declaration

        entities = self._project(tmp_path, "[parameters]\nW = 30\n")

        result = update_declaration(
            "parameter",
            "W",
            python_expr=render_parameter([30, 45]),
            matlab_expr=render_matlab_parameter([30, 45]),
            toml_expr=render_parameter_value([30, 45]),
        )

        assert result["ok"], result
        assert "W = [30, 45]" in entities.read_text()
        assert list(_registry.get_parameters_registry()["W"].alternatives) == [30, 45]

    def test_surrounding_content_is_untouched(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import update_parameter

        entities = self._project(
            tmp_path,
            "# keep me\n"
            "[parameters]\n"
            "WINDOW = 30  # and me\n"
            "OTHER = 1\n",
        )

        assert update_parameter("WINDOW", [45])["ok"]
        text = entities.read_text()
        assert "# keep me" in text
        assert "# and me" in text
        assert "OTHER = 1" in text

    def test_refuses_a_declaration_outside_the_entities_file(
        self, populated_db, tmp_path
    ):
        """The confinement rule: read-only, with the exact location so the UI
        can point at it instead of a generic hint."""
        from scistack_gui.db import get_db_path
        from scistack_gui.services.parameter_service import update_parameter

        other = tmp_path / "params.py"
        other.write_text("import scidb\n\nOUTSIDE = scidb.Parameter(7, description='')\n")
        entities = tmp_path / "entities.toml"
        entities.write_text("[parameters]\n")
        config_mod.set_entities_file(get_db_path(), entities)
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

        entities = self._project(tmp_path, "[parameters]\nWINDOW = 30\n")
        # Someone edits the file behind the GUI's back.
        entities.write_text("[parameters]\nWINDOW = 99\n")

        result = update_parameter("WINDOW", [45])

        assert not result["ok"]
        assert result["reason"] == "stale"
        assert "Refresh Code" in result["error"]
        assert "WINDOW = 99" in entities.read_text()

    def test_unknown_entity_is_reported(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import update_parameter

        self._project(tmp_path, "[parameters]\n")
        result = update_parameter("NOPE", [1])
        assert not result["ok"]
        assert "NOPE" in result["error"]

    def test_empty_parameter_is_rejected(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import update_parameter

        entities = self._project(tmp_path, "[parameters]\nW = 1\n")
        result = update_parameter("W", [])
        assert not result["ok"]
        assert "W = 1" in entities.read_text()

    def test_no_op_write_is_reported_as_unchanged(self, populated_db, tmp_path):
        from scistack_gui.services.parameter_service import update_parameter

        self._project(tmp_path, "[parameters]\nWINDOW = 30\n")
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

        entities = tmp_path / "entities.toml"
        entities.write_text(body)
        config_mod.set_entities_file(get_db_path(), entities)
        _registry._module_path = None
        _registry.load_from_config(config_mod.load_config(None, get_db_path()))
        return entities

    def test_nothing_is_recorded_until_an_edit_happens(self, populated_db, tmp_path):
        """Merely loading a project writes nothing — the table exists for
        edits, not as a log of every scan."""
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db

        self._project(tmp_path, '[path_inputs]\nRAW = "a.csv"\n')

        assert pipeline_store.list_path_input_history(get_db()) == []

    def test_old_template_still_resolves_after_an_edit(self, populated_db, tmp_path):
        """The whole point: a run recorded against 'a.csv' can still be
        attributed to RAW instead of collapsing into __unresolved__."""
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db
        from scistack_gui.services.path_input_service import update_path_input

        self._project(tmp_path, '[path_inputs]\nRAW = "a.csv"\n')

        assert update_path_input("RAW", "b.csv")["ok"]

        assert pipeline_store.lookup_path_input_name(get_db(), "a.csv") == "RAW"

    def test_repeated_edits_accumulate(self, populated_db, tmp_path):
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db
        from scistack_gui.services.path_input_service import update_path_input

        self._project(tmp_path, '[path_inputs]\nRAW = "a.csv"\n')
        assert update_path_input("RAW", "b.csv")["ok"]
        assert update_path_input("RAW", "c.csv")["ok"]

        db = get_db()
        assert pipeline_store.lookup_path_input_name(db, "a.csv") == "RAW"
        assert pipeline_store.lookup_path_input_name(db, "b.csv") == "RAW"

    def test_recording_is_idempotent(self, populated_db, tmp_path):
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db

        self._project(tmp_path, "[path_inputs]\n")
        db = get_db()
        pipeline_store.record_path_input_value(db, "RAW", "a.csv")
        pipeline_store.record_path_input_value(db, "RAW", "a.csv")

        assert len(pipeline_store.list_path_input_history(db, "RAW")) == 1

    def test_unknown_template_returns_none(self, populated_db, tmp_path):
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db

        self._project(tmp_path, "[path_inputs]\n")

        assert pipeline_store.lookup_path_input_name(get_db(), "never.csv") is None

    def test_root_folder_is_part_of_the_key(self, populated_db, tmp_path):
        from scistack_gui import pipeline_store
        from scistack_gui.db import get_db

        self._project(tmp_path, "[path_inputs]\n")
        db = get_db()
        pipeline_store.record_path_input_value(db, "RAW", "a.csv", "/data")

        assert pipeline_store.lookup_path_input_name(db, "a.csv", "/data") == "RAW"
        assert pipeline_store.lookup_path_input_name(db, "a.csv") is None
