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
    expected = config_mod._normalize(tmp_path / "scistack_variables.py")
    assert target == expected
    assert expected.exists()
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
