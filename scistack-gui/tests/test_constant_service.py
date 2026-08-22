"""
Unit tests for scistack_gui.services.constant_service.

Mirrors test_path_input_service.py's shape: GUI-created Constants are now
source-declared (``NAME = scidb.constant(value, description=...)``),
matching PathInput/Sweep/Variable's append-only pattern instead of the old
layout.json-only, valueless mechanism.
"""

from __future__ import annotations

import scistack_gui.registry as _registry
from scistack_gui.services.constant_service import create_constant


def _reset_registry_state():
    _registry._module_path = None
    _registry._config = None


class TestCreateConstantValidation:
    def test_empty_name_rejected(self):
        result = create_constant("")
        assert result["ok"] is False

    def test_non_identifier_rejected(self):
        result = create_constant("My-Const")
        assert result["ok"] is False

    def test_leading_underscore_rejected(self):
        result = create_constant("_Hidden")
        assert result["ok"] is False
        assert "underscore" in result["error"]

    def test_no_module_file_returns_error(self):
        _reset_registry_state()
        result = create_constant("CUTOFF_HZ")
        assert result["ok"] is False


class TestCreateConstantWrite:
    def setup_method(self):
        _reset_registry_state()

    def teardown_method(self):
        _reset_registry_state()

    def test_creates_declaration_in_empty_file(self, tmp_path):
        """No pre-existing imports -- ensure_scidb_import must add one, and
        the appended scidb.constant(...) call must resolve on re-scan."""
        module_file = tmp_path / "empty_entities.py"
        module_file.write_text("")
        _registry._module_path = module_file

        result = create_constant("CUTOFF_HZ")
        assert result["ok"] is True, result.get("error")
        content = module_file.read_text()
        assert "import scidb" in content
        assert "CUTOFF_HZ = scidb.constant(0, description='')" in content

        registered = _registry.get_constants_registry()
        assert "CUTOFF_HZ" in registered
        assert registered["CUTOFF_HZ"].value == 0

    def test_default_value_is_placeholder_zero(self, tmp_path):
        """The GUI's 'New constant' form only collects a name (same as
        create_sweep) -- a placeholder default is scaffolded rather than
        erroring, so the user hand-edits the real value afterward."""
        module_file = tmp_path / "entities.py"
        module_file.write_text("import scidb\n")
        _registry._module_path = module_file

        result = create_constant("PLACEHOLDER")
        assert result["ok"] is True, result.get("error")
        assert _registry.get_constants_registry()["PLACEHOLDER"].value == 0

    def test_explicit_value_and_description(self, tmp_path):
        module_file = tmp_path / "entities.py"
        module_file.write_text("import scidb\n")
        _registry._module_path = module_file

        result = create_constant("SAMPLE_RATE", value=1000, description="Hz")
        assert result["ok"] is True, result.get("error")
        obj = _registry.get_constants_registry()["SAMPLE_RATE"]
        assert obj.value == 1000
        assert obj.description == "Hz"

    def test_second_entity_does_not_duplicate_import(self, tmp_path):
        module_file = tmp_path / "empty_entities.py"
        module_file.write_text("")
        _registry._module_path = module_file

        create_constant("FIRST")
        create_constant("SECOND")

        content = module_file.read_text()
        assert content.count("import scidb") == 1

    def test_duplicate_name_rejected(self, tmp_path):
        module_file = tmp_path / "entities.py"
        module_file.write_text("import scidb\n")
        _registry._module_path = module_file

        create_constant("CUTOFF_HZ")
        result = create_constant("CUTOFF_HZ")
        assert result["ok"] is False
        assert "already exists" in result["error"]
