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
        from scidb import Parameter

        rate = Parameter(1000, description="Sample rate")
        mod = _make_module(RATE=rate)
        registry.register_module(mod)
        assert "RATE" in registry._parameters
        assert registry._parameters["RATE"] is rate

    def test_get_parameters_registry_returns_copy(self):
        from scidb import Parameter

        rate = Parameter(42)
        mod = _make_module(MY_CONST=rate)
        registry.register_module(mod)
        result = registry.get_parameters_registry()
        assert result["MY_CONST"] is rate
        result["MY_CONST"] = "mutated"
        assert registry._parameters["MY_CONST"] is rate

    def test_skips_private_constants(self):
        from scidb import Parameter

        mod = _make_module(_HIDDEN=Parameter(1))
        registry.register_module(mod)
        assert "_HIDDEN" not in registry._parameters

    def test_skips_non_constant_values(self):
        mod = _make_module(PLAIN_NUMBER=42, PLAIN_STRING="hello")
        registry.register_module(mod)
        assert "PLAIN_NUMBER" not in registry._parameters
        assert "PLAIN_STRING" not in registry._parameters

    def test_constant_attributed_even_when_reexported(self):
        # Deliberately different from functions: a Constant doesn't
        # reliably expose __module__ (unknown attribute access proxies to
        # the wrapped value via __getattr__), so it's attributed wherever
        # its name is exposed — mirrors scidb.discover.discover_module's
        # same documented choice, not the functions' stricter filter.
        from scidb import Parameter

        rate = Parameter(7, description="shared")
        mod = _make_module_with_reexport(SHARED_RATE=rate)
        registry.register_module(mod)
        assert "SHARED_RATE" in registry._parameters
        assert registry._parameters["SHARED_RATE"] is rate

    def test_source_tracked(self):
        from pathlib import Path

        from scidb import Parameter

        mod = _make_module(RATE=Parameter(5))
        registry.register_module(mod, module_path=Path("/fake/pipeline.py"))
        assert registry._parameter_sources["RATE"] == "/fake/pipeline.py"


# ---------------------------------------------------------------------------
# _scan_module_path_inputs — see docs/claude/code-discovery-categories.md
# ---------------------------------------------------------------------------


class TestScanModulePathInputs:
    def test_registers_path_input(self):
        from scidb import PathInput

        raw_emg = PathInput("{subject}/{trial}.mat")
        mod = _make_module(RAW_EMG=raw_emg)
        registry.register_module(mod)
        assert "RAW_EMG" in registry._path_inputs
        assert registry._path_inputs["RAW_EMG"] is raw_emg

    def test_get_path_inputs_registry_returns_copy(self):
        from scidb import PathInput

        pi = PathInput("{subject}.mat")
        mod = _make_module(MY_PATH=pi)
        registry.register_module(mod)
        result = registry.get_path_inputs_registry()
        assert result["MY_PATH"] is pi
        result["MY_PATH"] = "mutated"
        assert registry._path_inputs["MY_PATH"] is pi

    def test_get_path_input_looks_up_by_name(self):
        from scidb import PathInput

        pi = PathInput("{subject}.mat")
        mod = _make_module(MY_PATH=pi)
        registry.register_module(mod)
        assert registry.get_path_input("MY_PATH") is pi
        assert registry.get_path_input("NO_SUCH_NAME") is None

    def test_each_of_of_path_inputs_registered_as_alternate_templates(self):
        """EachOf(PathInput(...), PathInput(...)) bound to one name is how
        "alternate templates" express themselves now — no separate GUI
        concept, see docs/claude/code-discovery-categories.md."""
        from scidb import EachOf, PathInput

        alts = EachOf(PathInput("primary.mat"), PathInput("alt.mat"))
        mod = _make_module(GAIT_DATA=alts)
        registry.register_module(mod)
        assert registry._path_inputs["GAIT_DATA"] is alts

    def test_sweep_not_double_counted_as_path_input(self):
        """A Sweep is also an EachOf -- must not also register as a
        PathInput (disambiguated before the isinstance(EachOf) check)."""
        from scidb import Parameter

        mod = _make_module(WINDOW=Parameter(10, 20, 30))
        registry.register_module(mod)
        assert "WINDOW" not in registry._path_inputs

    def test_skips_private_and_non_path_input_values(self):
        from scidb import PathInput

        mod = _make_module(
            _HIDDEN=PathInput("{subject}.mat"), PLAIN_NUMBER=42, PLAIN_STRING="hello"
        )
        registry.register_module(mod)
        assert "_HIDDEN" not in registry._path_inputs
        assert "PLAIN_NUMBER" not in registry._path_inputs
        assert "PLAIN_STRING" not in registry._path_inputs

    def test_path_input_attributed_even_when_reexported(self):
        # Same reasoning as Constant: PathInput doesn't reliably expose a
        # __module__ that would let us filter re-exports out.
        from scidb import PathInput

        pi = PathInput("{subject}.mat")
        mod = _make_module_with_reexport(SHARED_PATH=pi)
        registry.register_module(mod)
        assert "SHARED_PATH" in registry._path_inputs
        assert registry._path_inputs["SHARED_PATH"] is pi

    def test_source_tracked(self):
        from pathlib import Path

        from scidb import PathInput

        mod = _make_module(RAW_EMG=PathInput("{subject}.mat"))
        registry.register_module(mod, module_path=Path("/fake/pipeline.py"))
        assert registry._path_input_sources["RAW_EMG"] == "/fake/pipeline.py"


# ---------------------------------------------------------------------------
# _scan_module_sweeps — see docs/claude/code-discovery-categories.md
# ---------------------------------------------------------------------------


class TestScanModuleSweeps:
    def test_registers_sweep(self):
        from scidb import Parameter

        window = Parameter(10, 20, 30)
        mod = _make_module(WINDOW_SECONDS=window)
        registry.register_module(mod)
        assert "WINDOW_SECONDS" in registry._parameters
        assert registry._parameters["WINDOW_SECONDS"] is window

    def test_get_parameters_registry_returns_copy(self):
        from scidb import Parameter

        sw = Parameter(1, 2)
        mod = _make_module(MY_SWEEP=sw)
        registry.register_module(mod)
        result = registry.get_parameters_registry()
        assert result["MY_SWEEP"] is sw
        result["MY_SWEEP"] = "mutated"
        assert registry._parameters["MY_SWEEP"] is sw

    def test_registry_lookup_by_name(self):
        from scidb import Parameter

        sw = Parameter(1, 2)
        mod = _make_module(MY_SWEEP=sw)
        registry.register_module(mod)
        assert registry.get_parameters_registry()["MY_SWEEP"] is sw
        assert "NO_SUCH_NAME" not in registry.get_parameters_registry()

    def test_bare_eachof_is_not_discovered(self):
        """Only a NAMED Sweep is GUI-visible -- a bare EachOf(...) used
        inline at a call site is not discovered, same as an unwrapped
        literal constant."""
        from scidb import EachOf

        mod = _make_module(NOT_A_SWEEP=EachOf(1, 2, 3))
        registry.register_module(mod)
        assert "NOT_A_SWEEP" not in registry._parameters

    def test_skips_private_and_non_sweep_values(self):
        from scidb import Parameter

        mod = _make_module(
            _HIDDEN=Parameter(1, 2), PLAIN_NUMBER=42, PLAIN_STRING="hello"
        )
        registry.register_module(mod)
        assert "_HIDDEN" not in registry._parameters
        assert "PLAIN_NUMBER" not in registry._parameters
        assert "PLAIN_STRING" not in registry._parameters

    def test_source_tracked(self):
        from pathlib import Path

        from scidb import Parameter

        mod = _make_module(WINDOW=Parameter(1, 2))
        registry.register_module(mod, module_path=Path("/fake/pipeline.py"))
        assert registry._parameter_sources["WINDOW"] == "/fake/pipeline.py"


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


# ---------------------------------------------------------------------------
# _load_packages — test-only submodules excluded from discovery
# ---------------------------------------------------------------------------
class TestLoadPackagesExcludesTestSubmodules:
    def test_tests_subpackage_excluded(self, tmp_path, monkeypatch, caplog):
        """A pip-installed package's tests/ subpackage must not leak its
        functions into discovery -- mirrors scidb.discover.scan_package's
        identical pkgutil.walk_packages exclusion."""
        import logging
        import sys

        pkg_name = "regpkgtest_fixture"
        pkg_dir = tmp_path / pkg_name
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "prod.py").write_text("def prod_fn(x):\n    return x\n")
        tests_dir = pkg_dir / "tests"
        tests_dir.mkdir()
        (tests_dir / "__init__.py").write_text("")
        (tests_dir / "helpers.py").write_text("def test_only_fn(x):\n    return x\n")

        monkeypatch.syspath_prepend(str(tmp_path))
        registry._functions.clear()
        registry._function_sources.clear()
        registry._load_errors.clear()
        try:
            with caplog.at_level(logging.DEBUG):
                registry._load_packages([pkg_name])

            assert "prod_fn" in registry._functions
            assert "test_only_fn" not in registry._functions
            assert "Skipping test module" in caplog.text
        finally:
            for name in list(sys.modules):
                if name == pkg_name or name.startswith(pkg_name + "."):
                    del sys.modules[name]

    def test_functions_constants_path_inputs_sweeps_all_registered(
        self, tmp_path, monkeypatch
    ):
        """Basic regression check: rebuilding _load_packages on
        scifor.discovery.walk_package must not change what gets discovered
        for a normal (non-test) package."""
        import sys

        pkg_name = "regpkgtest_full"
        pkg_dir = tmp_path / pkg_name
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "stuff.py").write_text(
            "from scidb import Parameter, PathInput\n"
            "def real_fn(x):\n    return x\n"
            "RATE = Parameter(1000)\n"
            "RAW = PathInput('{subject}.mat')\n"
            "WINDOW = Parameter(1, 2, 3)\n"
        )

        monkeypatch.syspath_prepend(str(tmp_path))
        registry._functions.clear()
        registry._function_sources.clear()
        registry._parameters.clear()
        registry._parameter_sources.clear()
        registry._path_inputs.clear()
        registry._path_input_sources.clear()
        registry._parameters.clear()
        registry._parameter_sources.clear()
        registry._load_errors.clear()
        try:
            registry._load_packages([pkg_name])

            assert "real_fn" in registry._functions
            assert "RATE" in registry._parameters
            assert "RAW" in registry._path_inputs
            assert "WINDOW" in registry._parameters
        finally:
            for name in list(sys.modules):
                if name == pkg_name or name.startswith(pkg_name + "."):
                    del sys.modules[name]


# ---------------------------------------------------------------------------
# Sibling imports in folder-scan (loose) projects.
#
# Loose files are imported by location, not by package name, so a bare
# ``import sibling`` inside one has no anchor unless the containing
# directories are on sys.path. Regression guard: a real project lost 6 of 13
# modules to ModuleNotFoundError purely because of this, and the failures were
# swallowed into the Discovered Code panel rather than raised.
# See registry._load_file_modules and scifor.discovery.sibling_import_dirs.
# ---------------------------------------------------------------------------


class TestSiblingImportsInLooseProjects:
    @pytest.fixture
    def loose_project(self, tmp_path):
        """Mirror the real-world layout: a helper at the scan root, another in
        a subdirectory, and importers pointing *both* directions across them."""
        import sys

        src = tmp_path / "src"
        sub = src / "plot_pt_measures"
        sub.mkdir(parents=True)

        (src / "apply_branding.py").write_text("def brand_axes(ax):\n    return ax\n")
        (sub / "df_parser.py").write_text("def parse_df_rom(df):\n    return df\n")
        # same-directory sibling
        (src / "plot_spm.py").write_text(
            "from apply_branding import brand_axes\n\ndef plot_spm(x):\n    return x\n"
        )
        # subdirectory importing from the parent directory
        (sub / "plotter.py").write_text(
            "from apply_branding import brand_axes\n\ndef plot_it(x):\n    return x\n"
        )
        # parent directory importing from a subdirectory
        (src / "main_plot_all.py").write_text(
            "from df_parser import parse_df_rom\n\ndef plot_all(x):\n    return x\n"
        )

        paths = [
            src / "apply_branding.py",
            src / "main_plot_all.py",
            src / "plot_spm.py",
            sub / "df_parser.py",
            sub / "plotter.py",
        ]

        before_modules = set(sys.modules)
        yield paths
        for name in set(sys.modules) - before_modules:
            sys.modules.pop(name, None)

    def _load(self, paths):
        registry._functions.clear()
        registry._function_sources.clear()
        registry._load_errors.clear()
        registry._module_paths.clear()
        registry._load_file_modules(paths)

    def test_same_directory_sibling_import_resolves(self, loose_project):
        self._load(loose_project)
        assert registry.get_load_errors() == []
        assert "plot_spm" in registry._functions

    def test_subdirectory_importing_parent_directory_resolves(self, loose_project):
        """plot_pt_measures/plotter.py does ``from apply_branding import ...``
        where apply_branding.py lives one level *up* -- the case a per-file
        "add my own parent dir" fix would still miss."""
        self._load(loose_project)
        assert registry.get_load_errors() == []
        assert "plot_it" in registry._functions

    def test_parent_directory_importing_subdirectory_resolves(self, loose_project):
        """src/main_plot_all.py does ``from df_parser import ...`` where
        df_parser.py lives in a *subdirectory*."""
        self._load(loose_project)
        assert registry.get_load_errors() == []
        assert "plot_all" in registry._functions

    def test_all_modules_load_without_errors(self, loose_project):
        self._load(loose_project)
        assert registry.get_load_errors() == []
        for fn in ("brand_axes", "parse_df_rom", "plot_spm", "plot_it", "plot_all"):
            assert fn in registry._functions

    def test_sys_path_restored_after_load(self, loose_project):
        import sys

        before = list(sys.path)
        self._load(loose_project)
        assert sys.path == before

    def test_sys_path_restored_even_when_a_module_raises(self, loose_project, tmp_path):
        """One bad file must not leave the scan directories stranded on
        sys.path -- that would silently change import resolution for every
        later scan in the same server process."""
        import sys

        boom = tmp_path / "src" / "boom.py"
        boom.write_text("raise RuntimeError('top-level explosion')\n")

        before = list(sys.path)
        self._load([*loose_project, boom])

        assert sys.path == before
        errors = registry.get_load_errors()
        assert len(errors) == 1
        assert errors[0]["source"] == str(boom)
        # The good modules alongside it still registered.
        assert "plot_spm" in registry._functions

    def test_search_dirs_logged_for_diagnosis(self, loose_project, caplog):
        """Putting user directories at the front of sys.path can shadow other
        modules; the added dirs must be visible in the log to diagnose that."""
        import logging

        with caplog.at_level(logging.INFO):
            self._load(loose_project)

        assert "sys.path for sibling imports" in caplog.text
        assert "plot_pt_measures" in caplog.text


# ---------------------------------------------------------------------------
# Top-level side-effect refusal.
#
# Discovery imports files to read their definitions, which also *runs* them. A
# real scan spent 13 of its 15 startup seconds rendering matplotlib figures
# from two unguarded plotting scripts before dying on a hardcoded output path.
# Files with module-level work are now refused, not executed.
# See registry._screen_for_side_effects and
# scifor.discovery.find_top_level_side_effects.
# ---------------------------------------------------------------------------


class TestTopLevelSideEffectRefusal:
    def _load(self, paths):
        registry._functions.clear()
        registry._function_sources.clear()
        registry._load_errors.clear()
        registry._module_paths.clear()
        registry._load_file_modules(paths)

    def test_side_effecting_file_is_never_executed(self, tmp_path):
        """The regression: top-level work must not run during a scan."""
        sentinel = tmp_path / "side_effect_happened.txt"
        f = tmp_path / "plot_gait_speeds.py"
        f.write_text(
            "from pathlib import Path\n\n"
            "def plot_gait(a, b, c):\n"
            f"    Path({str(sentinel)!r}).write_text('ran')\n"
            "    return a\n\n"
            "plot_gait(1, 2, 3)\n"
        )

        self._load([f])

        assert not sentinel.exists(), "top-level call executed during discovery"
        assert "plot_gait" not in registry._functions

    def test_assigned_local_call_is_never_executed(self, tmp_path):
        """``data = plot_gait(...)`` does the same work as a bare call --
        statement form alone can't tell it apart from ``RATE = Parameter(...)``,
        so the callee has to decide."""
        sentinel = tmp_path / "assigned_side_effect.txt"
        f = tmp_path / "plot_assigned.py"
        f.write_text(
            "from pathlib import Path\n\n"
            "def plot_gait(a, b, c):\n"
            f"    Path({str(sentinel)!r}).write_text('ran')\n"
            "    return a\n\n"
            "data = plot_gait(1, 2, 3)\n"
        )

        self._load([f])

        assert not sentinel.exists(), "assigned top-level call executed"
        errors = registry.get_load_errors()
        assert len(errors) == 1
        assert "defined in this file" in errors[0]["error"]

    def test_imported_callee_in_assignment_still_executes(self, tmp_path):
        """The other half: entity construction and ordinary module setup call
        *imported* names, so they must keep running."""
        f = tmp_path / "entities_and_setup.py"
        f.write_text(
            "import logging\n"
            "from pathlib import Path\n"
            "from scidb import Parameter, PathInput\n\n"
            "logger = logging.getLogger(__name__)\n"
            "HERE = Path(__file__).parent\n"
            "RATE = Parameter(1, 2, 3)\n"
            "RAW = PathInput('{subject}.mat')\n\n"
            "def use_it(x):\n"
            "    return x\n"
        )

        registry._parameters.clear()
        registry._path_inputs.clear()
        self._load([f])

        assert registry.get_load_errors() == []
        assert "RATE" in registry._parameters
        assert "RAW" in registry._path_inputs
        assert "use_it" in registry._functions

    def test_refusal_recorded_with_line_number_and_hint(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("def render():\n    return 1\n\nrender()\n")

        self._load([f])

        errors = registry.get_load_errors()
        assert len(errors) == 1
        assert errors[0]["source"] == str(f)
        assert "render() at line 4" in errors[0]["error"]
        assert "__main__" in errors[0]["error"]

    def test_main_guarded_file_still_loads(self, tmp_path):
        """The documented fix must actually work."""
        f = tmp_path / "guarded.py"
        f.write_text(
            "def plot_gait(a):\n"
            "    return a\n\n"
            'if __name__ == "__main__":\n'
            "    plot_gait(1)\n"
        )

        self._load([f])

        assert registry.get_load_errors() == []
        assert "plot_gait" in registry._functions

    def test_parameter_and_path_input_assignments_still_execute(self, tmp_path):
        """Module-level construction is an Assign, not a bare call -- it must
        keep running, since registering those objects is the point."""
        f = tmp_path / "entities.py"
        f.write_text(
            "from scidb import Parameter, PathInput\n\n"
            "RATE = Parameter(1, 2, 3)\n"
            "RAW = PathInput('{subject}.mat')\n\n"
            "def use_it(x):\n"
            "    return x\n"
        )

        registry._parameters.clear()
        registry._path_inputs.clear()
        self._load([f])

        assert registry.get_load_errors() == []
        assert "RATE" in registry._parameters
        assert "RAW" in registry._path_inputs

    def test_clean_file_alongside_refused_one_still_registers(self, tmp_path):
        good = tmp_path / "good.py"
        good.write_text("def good_fn(x):\n    return x\n")
        bad = tmp_path / "bad.py"
        bad.write_text("def bad_fn(x):\n    return x\n\nbad_fn(1)\n")

        self._load([good, bad])

        assert "good_fn" in registry._functions
        assert "bad_fn" not in registry._functions
        assert len(registry.get_load_errors()) == 1

    def test_unparseable_file_recorded_not_executed(self, tmp_path):
        f = tmp_path / "broken.py"
        f.write_text("def broken(\n")

        self._load([f])

        errors = registry.get_load_errors()
        assert len(errors) == 1
        assert "SyntaxError" in errors[0]["error"]

    def test_allowlisted_config_call_does_not_block_import(self, tmp_path):
        """A top-of-file backend/logging setting is configuration, not work."""
        f = tmp_path / "configured.py"
        f.write_text(
            "import logging\n"
            "logging.basicConfig()\n\n"
            "def real_fn(x):\n"
            "    return x\n"
        )

        self._load([f])

        assert registry.get_load_errors() == []
        assert "real_fn" in registry._functions

    def test_output_only_toplevel_code_does_not_block_import(self, tmp_path):
        """Console output is not work. Refusing over a debug print would cost
        every function the file defines, and the import already runs inside a
        stdout/stderr redirect that captures it."""
        f = tmp_path / "chatty.py"
        f.write_text(
            "import logging\n\n"
            "logger = logging.getLogger(__name__)\n"
            "print('loading chatty module')\n"
            "logger.info('chatty module loaded')\n\n"
            "def real_fn(x):\n"
            "    return x\n"
        )

        self._load([f])

        assert registry.get_load_errors() == []
        assert "real_fn" in registry._functions

    def test_refusal_logs_at_info_not_error(self, tmp_path, caplog):
        """A stray script in a folder-scanned tree is routine -- it must not
        read as a GUI failure on the console."""
        import logging

        f = tmp_path / "stray.py"
        f.write_text("def fn(x):\n    return x\n\nfn(1)\n")

        with caplog.at_level(logging.DEBUG):
            self._load([f])

        assert not any(
            r.levelno >= logging.WARNING and "Refusing to import" in r.getMessage()
            for r in caplog.records
        )
        assert "Refusing to import" in caplog.text
