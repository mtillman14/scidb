"""
Tests for scistack_gui.registry — function and variable-class registry.
"""

import types

import pytest
from scistack_gui import registry

from scidb import BaseVariable

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_module(**attrs) -> types.ModuleType:
    """Create a throwaway module with the given attributes.

    Callables are stamped with ``__module__`` matching this fake module's
    name, simulating a function actually *defined* there — otherwise they'd
    carry the real ``__module__`` of wherever they were written in the test
    file (e.g. ``tests.test_registry``), which is exactly the "imported,
    not defined" case the registry is now expected to filter out. Use
    ``_make_module_with_reexport`` to construct that case on purpose.
    """
    mod = types.ModuleType("test_pipeline_module")
    for k, v in attrs.items():
        if callable(v) and not isinstance(v, type):
            v.__module__ = mod.__name__
        setattr(mod, k, v)
    return mod


def _make_module_with_reexport(**attrs) -> types.ModuleType:
    """Like _make_module, but leaves __module__ untouched (simulates an import)."""
    mod = types.ModuleType("test_pipeline_module")
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


# Variable class only used in this test file
class RegistryTestVar(BaseVariable):
    pass


# ---------------------------------------------------------------------------
# register_module
# ---------------------------------------------------------------------------


class TestRegisterModule:
    def test_registers_top_level_callables(self):
        def my_fn(x):
            return x

        mod = _make_module(my_fn=my_fn)
        registry.register_module(mod)
        assert "my_fn" in registry._functions
        assert registry._functions["my_fn"] is my_fn

    def test_skips_private_callables(self):
        def _private(x):
            return x

        mod = _make_module(_private=_private)
        registry.register_module(mod)
        assert "_private" not in registry._functions

    def test_skips_classes(self):
        class MyClass:
            pass

        mod = _make_module(MyClass=MyClass)
        registry.register_module(mod)
        assert "MyClass" not in registry._functions

    def test_multiple_functions(self):
        def fn_a(x):
            return x

        def fn_b(x):
            return x

        mod = _make_module(fn_a=fn_a, fn_b=fn_b)
        registry.register_module(mod)
        assert "fn_a" in registry._functions
        assert "fn_b" in registry._functions

    def test_register_twice_overwrites(self):
        def fn_v1(x):
            return 1

        def fn_v2(x):
            return 2

        registry.register_module(_make_module(my_fn=fn_v1))
        registry.register_module(_make_module(my_fn=fn_v2))
        assert registry._functions["my_fn"] is fn_v2

    def test_skips_reexported_callables(self):
        # Simulates `from scidb import for_each` inside a user pipeline
        # file: the name is bound in the module's namespace, but the
        # function was defined elsewhere, so it shouldn't be treated as a
        # discoverable pipeline step.
        def helper(x):
            return x

        mod = _make_module_with_reexport(helper=helper)
        registry.register_module(mod)
        assert "helper" not in registry._functions

    def test_skips_real_scidb_reexports(self):
        # Regression test for the reported bug: `for_each` and
        # `configure_database` showing up as "discovered functions" because
        # a pipeline file does `from scidb import for_each,
        # configure_database`.
        from scidb import configure_database, for_each

        mod = _make_module_with_reexport(
            for_each=for_each,
            configure_database=configure_database,
        )
        registry.register_module(mod)
        assert "for_each" not in registry._functions
        assert "configure_database" not in registry._functions

    def test_locally_defined_function_still_registered_alongside_reexport(self):
        # The filter should only remove imports, not everything in a file
        # that also happens to import scidb helpers.
        from scidb import for_each

        def compute_thing(x):
            return x

        mod = _make_module_with_reexport(compute_thing=compute_thing, for_each=for_each)
        compute_thing.__module__ = mod.__name__  # simulate "defined in this file"
        registry.register_module(mod)
        assert "compute_thing" in registry._functions
        assert "for_each" not in registry._functions


# ---------------------------------------------------------------------------
# _scan_module_constants (via register_module)
# ---------------------------------------------------------------------------


class TestScanModuleConstants:
    def test_registers_constant(self):
        from scidb import constant

        rate = constant(1000, description="Sample rate")
        mod = _make_module(RATE=rate)
        registry.register_module(mod)
        assert "RATE" in registry._constants
        assert registry._constants["RATE"] is rate

    def test_get_constants_registry_returns_copy(self):
        from scidb import constant

        rate = constant(42)
        mod = _make_module(MY_CONST=rate)
        registry.register_module(mod)
        result = registry.get_constants_registry()
        assert result["MY_CONST"] is rate
        result["MY_CONST"] = "mutated"
        assert registry._constants["MY_CONST"] is rate

    def test_skips_private_constants(self):
        from scidb import constant

        mod = _make_module(_HIDDEN=constant(1))
        registry.register_module(mod)
        assert "_HIDDEN" not in registry._constants

    def test_skips_non_constant_values(self):
        mod = _make_module(PLAIN_NUMBER=42, PLAIN_STRING="hello")
        registry.register_module(mod)
        assert "PLAIN_NUMBER" not in registry._constants
        assert "PLAIN_STRING" not in registry._constants

    def test_constant_attributed_even_when_reexported(self):
        # Deliberately different from functions: a Constant doesn't
        # reliably expose __module__ (unknown attribute access proxies to
        # the wrapped value via __getattr__), so it's attributed wherever
        # its name is exposed — mirrors scidb.discover.discover_module's
        # same documented choice, not the functions' stricter filter.
        from scidb import constant

        rate = constant(7, description="shared")
        mod = _make_module_with_reexport(SHARED_RATE=rate)
        registry.register_module(mod)
        assert "SHARED_RATE" in registry._constants
        assert registry._constants["SHARED_RATE"] is rate

    def test_source_tracked(self):
        from pathlib import Path

        from scidb import constant

        mod = _make_module(RATE=constant(5))
        registry.register_module(mod, module_path=Path("/fake/pipeline.py"))
        assert registry._constant_sources["RATE"] == "/fake/pipeline.py"


# ---------------------------------------------------------------------------
# get_function
# ---------------------------------------------------------------------------


class TestGetFunction:
    def test_returns_registered_function(self):
        def compute(x):
            return x

        registry._functions["compute"] = compute
        assert registry.get_function("compute") is compute

    def test_raises_key_error_for_unknown_function(self):
        with pytest.raises(KeyError, match="not found in registry"):
            registry.get_function("does_not_exist")

    def test_error_message_includes_function_name(self):
        with pytest.raises(KeyError) as exc_info:
            registry.get_function("missing_fn")
        assert "missing_fn" in str(exc_info.value)


# ---------------------------------------------------------------------------
# get_variable_class
# ---------------------------------------------------------------------------


class TestGetVariableClass:
    def test_returns_registered_variable_class(self):
        # RegistryTestVar is defined at module level — auto-registered on import
        cls = registry.get_variable_class("RegistryTestVar")
        assert cls is RegistryTestVar

    def test_raises_key_error_for_unknown_class(self):
        with pytest.raises(KeyError, match="not found"):
            registry.get_variable_class("NonExistentVarClass")


# ---------------------------------------------------------------------------
# Discovery output suppression — a discovered file is actually *imported*
# (Python has no side-effect-free way to inspect a module), so a stray
# script with real top-level code would otherwise leak its print()s and
# tracebacks into the GUI's own console/log, reading as a GUI failure.
# See registry._suppress_user_code_output and _load_file_modules.
# ---------------------------------------------------------------------------


class TestDiscoveryOutputSuppression:
    def test_print_in_discovered_file_does_not_reach_console(
        self, tmp_path, capsys, caplog
    ):
        import logging

        f = tmp_path / "noisy.py"
        f.write_text(
            "print('hello from noisy module')\n\n"
            "def noisy_fn(x):\n"
            "    return x\n"
        )

        registry._functions.clear()
        registry._function_sources.clear()
        registry._load_errors.clear()
        with caplog.at_level(logging.DEBUG):
            registry._load_file_modules([f])

        captured = capsys.readouterr()
        assert "hello from noisy module" not in captured.out
        # Not discarded — recoverable via scidb.log at DEBUG if needed.
        assert "hello from noisy module" in caplog.text
        # The module still gets scanned normally despite the redirect.
        assert "noisy_fn" in registry._functions

    def test_failed_import_does_not_log_at_error_level(self, tmp_path, caplog):
        """A file that raises on import (e.g. an unguarded debug script with
        real top-level code) is routine during folder-scan discovery, not a
        GUI failure -- must not surface as an ERROR-level console line."""
        import logging

        f = tmp_path / "broken.py"
        f.write_text("raise RuntimeError('boom')\n")

        registry._load_errors.clear()
        with caplog.at_level(logging.DEBUG):
            registry._load_file_modules([f])

        assert not any(r.levelno >= logging.ERROR for r in caplog.records)
        # Still fully recorded for the 📁 Paths -> Discovered Code panel.
        errors = registry.get_load_errors()
        assert len(errors) == 1
        assert "boom" in errors[0]["error"]

    def test_failed_import_traceback_recoverable_at_debug(self, tmp_path, caplog):
        import logging

        f = tmp_path / "broken.py"
        f.write_text("raise RuntimeError('boom')\n")

        registry._load_errors.clear()
        with caplog.at_level(logging.DEBUG):
            registry._load_file_modules([f])

        assert "Failed to load module file" in caplog.text
        assert "RuntimeError: boom" in caplog.text

    def test_error_message_includes_class_name(self):
        with pytest.raises(KeyError) as exc_info:
            registry.get_variable_class("GhostClass")
        assert "GhostClass" in str(exc_info.value)
