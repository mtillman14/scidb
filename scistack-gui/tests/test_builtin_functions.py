"""Tests for scistack_gui.services.builtin_function_service — manual
built-in/library function references (numpy.mean, MATLAB builtins, ...)."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scistack_gui import registry
from scistack_gui.services import builtin_function_service as svc


@pytest.fixture(autouse=True)
def _clean_matlab_registry():
    from scistack_gui import matlab_registry

    matlab_registry._matlab_functions.clear()
    matlab_registry._matlab_variables.clear()
    yield
    matlab_registry._matlab_functions.clear()
    matlab_registry._matlab_variables.clear()


# ---------------------------------------------------------------------------
# Python — validation-only paths (no DB needed, never reach _persist_builtin)
# ---------------------------------------------------------------------------


class TestPythonBuiltinValidation:
    def test_disallowed_installed_module_rejected(self):
        # duckdb is a real, always-installed dependency here (scidb wraps
        # it) but is neither stdlib nor numpy/pandas — the policy must
        # reject it even though it's importable, not just reject packages
        # that don't exist at all (see test_uninstalled_package_rejected).
        result = svc.create_builtin_function("python", "duckdb.connect")
        assert result["ok"] is False
        assert "not allowed" in result["error"]
        assert "duckdb.connect" not in registry._functions

    def test_nonexistent_attribute_rejected(self):
        result = svc.create_builtin_function("python", "math.not_a_real_function")
        assert result["ok"] is False

    def test_not_callable_rejected(self):
        result = svc.create_builtin_function("python", "math.pi")
        assert result["ok"] is False
        assert "not callable" in result["error"]

    def test_uninstalled_package_rejected(self):
        result = svc.create_builtin_function("python", "totally_not_a_real_package_xyz.foo")
        assert result["ok"] is False
        assert "not installed" in result["error"]

    def test_invalid_syntax_rejected(self):
        result = svc.create_builtin_function("python", "not a valid ref!")
        assert result["ok"] is False

    def test_empty_reference_rejected(self):
        result = svc.create_builtin_function("python", "   ")
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# Python — successful registration (needs a real DB for persistence)
# ---------------------------------------------------------------------------


class TestPythonBuiltinRegistration:
    def test_stdlib_bare_name(self, populated_db):
        result = svc.create_builtin_function("python", "len")
        assert result["ok"] is True
        assert result["name"] == "len"
        assert registry.get_function("len") is len

    def test_stdlib_dotted_module(self, populated_db):
        import math

        result = svc.create_builtin_function("python", "math.sqrt")
        assert result["ok"] is True
        assert result["name"] == "math.sqrt"
        assert registry.get_function("math.sqrt") is math.sqrt

    def test_numpy_allowed(self, populated_db):
        result = svc.create_builtin_function("python", "numpy.mean")
        assert result["ok"] is True
        assert result["name"] == "numpy.mean"
        assert callable(registry.get_function("numpy.mean"))

    def test_pandas_allowed(self, populated_db):
        result = svc.create_builtin_function("python", "pandas.read_csv")
        assert result["ok"] is True
        assert result["name"] == "pandas.read_csv"

    def test_persisted_and_replayed(self, populated_db):
        """A registered builtin survives registry.load_from_config's
        .clear() when replayed from the persisted store."""
        svc.create_builtin_function("python", "numpy.mean")
        registry._functions.clear()
        registry._function_sources.clear()
        assert "numpy.mean" not in registry._functions

        replay_result = svc.replay_persisted_builtins(populated_db)
        assert replay_result["counts"]["python"] == 1
        assert callable(registry.get_function("numpy.mean"))


# ---------------------------------------------------------------------------
# MATLAB
# ---------------------------------------------------------------------------


class TestMatlabBuiltin:
    def test_invalid_identifier_rejected(self):
        result = svc.create_builtin_function("matlab", "not valid!")
        assert result["ok"] is False
        assert "identifier" in result["error"]

    def test_matlab_not_on_path_rejected(self, monkeypatch):
        monkeypatch.setattr(svc.shutil, "which", lambda name: None)
        result = svc.create_builtin_function("matlab", "mean")
        assert result["ok"] is False
        assert "PATH" in result["error"]

    def test_valid_builtin_registers(self, monkeypatch, populated_db):
        monkeypatch.setattr(svc.shutil, "which", lambda name: "/usr/local/bin/matlab")

        class FakeResult:
            stdout = "5\n"

        monkeypatch.setattr(svc.subprocess, "run", lambda *a, **k: FakeResult())

        result = svc.create_builtin_function("matlab", "mean")
        assert result["ok"] is True
        assert result["name"] == "mean"

        from scistack_gui import matlab_registry

        assert matlab_registry.is_matlab_function("mean")
        info = matlab_registry.get_matlab_function("mean")
        assert info.file_path is None

    def test_unknown_function_rejected(self, monkeypatch):
        monkeypatch.setattr(svc.shutil, "which", lambda name: "/usr/local/bin/matlab")

        class FakeResult:
            stdout = "0\n"

        monkeypatch.setattr(svc.subprocess, "run", lambda *a, **k: FakeResult())

        result = svc.create_builtin_function("matlab", "not_a_real_fn")
        assert result["ok"] is False

        from scistack_gui import matlab_registry

        assert not matlab_registry.is_matlab_function("not_a_real_fn")

    def test_timeout_rejected(self, monkeypatch):
        monkeypatch.setattr(svc.shutil, "which", lambda name: "/usr/local/bin/matlab")

        def raise_timeout(*a, **k):
            raise subprocess.TimeoutExpired(cmd="matlab", timeout=30)

        monkeypatch.setattr(svc.subprocess, "run", raise_timeout)

        result = svc.create_builtin_function("matlab", "mean")
        assert result["ok"] is False
        assert "Timed out" in result["error"]

    def test_reference_never_reaches_subprocess_before_identifier_check(self, monkeypatch):
        """Security regression: a reference that fails the identifier
        check must never reach subprocess.run — no shell-injection
        surface via a crafted 'name'."""
        monkeypatch.setattr(svc.shutil, "which", lambda name: "/usr/local/bin/matlab")

        def fail_if_called(*a, **k):
            raise AssertionError("subprocess.run must not be called for an invalid identifier")

        monkeypatch.setattr(svc.subprocess, "run", fail_if_called)

        result = svc.create_builtin_function("matlab", "mean'); !rm -rf /; disp('")
        assert result["ok"] is False

    def test_persisted_and_replayed_without_reinvoking_matlab(self, monkeypatch, populated_db):
        """Replay must NOT shell out to MATLAB again — it trusts the
        already-validated persisted reference (slow/fragile to re-check
        on every refresh)."""
        monkeypatch.setattr(svc.shutil, "which", lambda name: "/usr/local/bin/matlab")

        class FakeResult:
            stdout = "5\n"

        monkeypatch.setattr(svc.subprocess, "run", lambda *a, **k: FakeResult())
        svc.create_builtin_function("matlab", "mean")

        from scistack_gui import matlab_registry

        matlab_registry._matlab_functions.clear()
        assert not matlab_registry.is_matlab_function("mean")

        def fail_if_called(*a, **k):
            raise AssertionError("replay must not shell out to MATLAB again")

        monkeypatch.setattr(svc.subprocess, "run", fail_if_called)

        replay_result = svc.replay_persisted_builtins(populated_db)
        assert replay_result["counts"]["matlab"] == 1
        assert matlab_registry.is_matlab_function("mean")
