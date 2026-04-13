"""Unit tests for ``scidb.discover`` — the project / library scanner."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

from scidb import Constant
from scidb.discover import (
    DiscoveryResult,
    _dist_to_import_names,
    _read_project_name,
    _read_uv_lock_packages,
    scan_project,
)


# ---------------------------------------------------------------------------
# Fixture factory: build a throwaway scistack project on disk
# ---------------------------------------------------------------------------
@pytest.fixture
def project_factory(tmp_path: Path):
    """
    Factory that scaffolds a throwaway project under tmp_path and cleans
    up sys.modules after the test so repeated imports don't collide.

    Usage::

        def test_x(project_factory):
            root = project_factory(
                package_name="my_fixture",
                files={
                    "variables.py": "from scidb import BaseVariable\\n"
                                    "class Raw(BaseVariable): schema_version = 1\\n",
                },
                uv_lock_packages=["numpy"],
            )
    """
    created_packages: list[str] = []

    def _make(
        package_name: str,
        files: dict[str, str] | None = None,
        uv_lock_packages: list[str] | None = None,
        pyproject_extra: str = "",
    ) -> Path:
        project_root = tmp_path / package_name
        src_pkg = project_root / "src" / package_name
        src_pkg.mkdir(parents=True)

        (project_root / "pyproject.toml").write_text(
            f'[project]\nname = "{package_name}"\nversion = "0.1.0"\n{pyproject_extra}'
        )

        # Ensure the package has an __init__.py even if none is supplied.
        (src_pkg / "__init__.py").write_text("")

        files = files or {}
        for rel, content in files.items():
            full = src_pkg / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(textwrap.dedent(content))

        if uv_lock_packages is not None:
            lock_lines = ["version = 1\n"]
            for name in uv_lock_packages:
                lock_lines.append(
                    f'\n[[package]]\nname = "{name}"\nversion = "0.0.0"\n'
                )
            (project_root / "uv.lock").write_text("".join(lock_lines))

        created_packages.append(package_name)
        return project_root

    yield _make

    # Teardown: drop any imported modules from the fixture projects.
    for name in created_packages:
        prefix = name + "."
        for mod_name in list(sys.modules):
            if mod_name == name or mod_name.startswith(prefix):
                sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# discover_module: pure, per-module scanner
# ---------------------------------------------------------------------------
class TestDiscoverModule:
    def test_finds_base_variable_subclass(self, project_factory):
        root = project_factory(
            package_name="fix_vars",
            files={
                "variables.py": """
                    from scidb import BaseVariable
                    class RawSignal(BaseVariable):
                        schema_version = 1
                """,
            },
        )
        result = scan_project(root)
        all_vars = [v for m in result.project_code.modules for v in m.variables]
        assert len(all_vars) == 1
        assert all_vars[0].__name__ == "RawSignal"
        # Also check that discover_module attributes it to the right module.
        by_module = {m.module_name: m for m in result.project_code.modules}
        assert "fix_vars.variables" in by_module
        assert len(by_module["fix_vars.variables"].variables) == 1

    def test_finds_lineage_fcn(self, project_factory):
        root = project_factory(
            package_name="fix_fns",
            files={
                "functions.py": """
                    from scilineage import lineage_fcn

                    @lineage_fcn
                    def preprocess(x):
                        return x + 1
                """,
            },
        )
        result = scan_project(root)
        all_fns = [f for m in result.project_code.modules for f in m.functions]
        assert len(all_fns) == 1
        assert all_fns[0].fcn.__name__ == "preprocess"

    def test_finds_constants(self, project_factory):
        root = project_factory(
            package_name="fix_consts",
            files={
                "constants.py": """
                    from scidb import constant

                    SAMPLING_RATE_HZ = constant(1000, description="Hz")
                    DEFAULT_BANDPASS = constant((1.0, 40.0), description="LFP band")
                """,
            },
        )
        result = scan_project(root)
        all_constants = [
            c for m in result.project_code.modules for c in m.constants
        ]
        assert len(all_constants) == 2
        names = {name for name, _ in all_constants}
        assert names == {"SAMPLING_RATE_HZ", "DEFAULT_BANDPASS"}

        by_name = dict(all_constants)
        assert isinstance(by_name["SAMPLING_RATE_HZ"], Constant)
        assert by_name["SAMPLING_RATE_HZ"] == 1000
        assert by_name["DEFAULT_BANDPASS"].description == "LFP band"

    def test_ignores_reexports_of_variables(self, project_factory):
        """A BaseVariable re-imported into another module must not be double-counted."""
        root = project_factory(
            package_name="fix_reexport",
            files={
                "variables.py": """
                    from scidb import BaseVariable
                    class RawSignal(BaseVariable):
                        schema_version = 1
                """,
                "pipeline.py": """
                    # Re-export should NOT count as a second discovery
                    from fix_reexport.variables import RawSignal  # noqa: F401
                """,
            },
        )
        result = scan_project(root)
        all_vars = [v for m in result.project_code.modules for v in m.variables]
        names = [v.__name__ for v in all_vars]
        assert names == ["RawSignal"]  # exactly once, in variables.py

    def test_ignores_reexports_of_lineage_fcn(self, project_factory):
        root = project_factory(
            package_name="fix_fn_reexport",
            files={
                "functions.py": """
                    from scilineage import lineage_fcn

                    @lineage_fcn
                    def preprocess(x):
                        return x + 1
                """,
                "pipeline.py": """
                    from fix_fn_reexport.functions import preprocess  # noqa: F401
                """,
            },
        )
        result = scan_project(root)
        all_fns = [f for m in result.project_code.modules for f in m.functions]
        assert len(all_fns) == 1

    def test_ignores_private_names(self, project_factory):
        root = project_factory(
            package_name="fix_private",
            files={
                "pipeline.py": """
                    from scidb import constant
                    _PRIVATE = constant(42)
                    PUBLIC = constant(43)
                """,
            },
        )
        result = scan_project(root)
        constants = [
            (name, c) for m in result.project_code.modules for name, c in m.constants
        ]
        names = {name for name, _ in constants}
        assert "PUBLIC" in names
        assert "_PRIVATE" not in names


# ---------------------------------------------------------------------------
# scan_project: project-level scan end-to-end
# ---------------------------------------------------------------------------
class TestScanProject:
    def test_full_project_scan(self, project_factory):
        root = project_factory(
            package_name="full_study",
            files={
                "variables.py": """
                    from scidb import BaseVariable
                    class RawSignal(BaseVariable):
                        schema_version = 1
                    class FilteredSignal(BaseVariable):
                        schema_version = 1
                """,
                "functions.py": """
                    from scilineage import lineage_fcn

                    @lineage_fcn
                    def preprocess(x):
                        return x

                    @lineage_fcn
                    def analyze(x):
                        return x
                """,
                "constants.py": """
                    from scidb import constant
                    SAMPLING_RATE_HZ = constant(1000)
                """,
            },
        )
        result = scan_project(root)
        assert isinstance(result, DiscoveryResult)
        assert result.project_code.name == "full_study"
        assert result.project_code.variable_count == 2
        assert result.project_code.function_count == 2
        assert result.project_code.constant_count == 1
        assert result.project_code.is_empty is False
        assert result.libraries == {}  # no uv.lock

    def test_import_error_captured_not_thrown(self, project_factory):
        root = project_factory(
            package_name="fix_broken",
            files={
                "good.py": """
                    from scidb import constant
                    GOOD = constant(1)
                """,
                "broken.py": """
                    raise ImportError("intentional test failure")
                """,
            },
        )
        # scan_project should NOT raise — it should capture the error.
        result = scan_project(root)
        assert result.project_code.constant_count == 1

        # The broken module should show up as an error.
        broken_errors = [
            e for e in result.project_code.errors if "broken" in e.module_name
        ]
        assert len(broken_errors) == 1
        assert "intentional test failure" in broken_errors[0].traceback

    def test_syntax_error_captured_not_thrown(self, project_factory):
        root = project_factory(
            package_name="fix_syntax",
            files={
                "good.py": """
                    from scidb import constant
                    GOOD = constant(1)
                """,
                "bad_syntax.py": """
                    def broken(:
                """,
            },
        )
        result = scan_project(root)
        assert result.project_code.constant_count == 1
        syntax_errors = [
            e for e in result.project_code.errors if "bad_syntax" in e.module_name
        ]
        assert len(syntax_errors) == 1

    def test_missing_pyproject_toml(self, tmp_path):
        """scan_project with no pyproject.toml returns empty project_code gracefully."""
        (tmp_path / "some_file.txt").write_text("not a project")
        result = scan_project(tmp_path)
        assert result.project_code.is_empty
        assert result.project_code.name == "<unknown>"
        assert result.libraries == {}

    def test_missing_src_directory(self, project_factory):
        """pyproject.toml present but no src/{name}/ — graceful empty result."""
        root = project_factory(package_name="fix_no_src", files={})
        # Remove the scaffolded src/ to simulate a pre-src project.
        import shutil

        shutil.rmtree(root / "src")
        result = scan_project(root)
        assert result.project_code.is_empty
        assert result.project_code.name == "fix_no_src"

    def test_missing_uv_lock(self, project_factory):
        """No uv.lock → no libraries, no error."""
        root = project_factory(
            package_name="fix_no_lock",
            files={
                "constants.py": "from scidb import constant\nX = constant(1)\n",
            },
        )
        result = scan_project(root)
        assert result.libraries == {}
        assert result.project_code.constant_count == 1

    def test_unicode_in_source(self, project_factory):
        """Non-ASCII in source should not break the scanner."""
        root = project_factory(
            package_name="fix_unicode",
            files={
                "constants.py": """
                    # coding: utf-8
                    from scidb import constant
                    GREEK = constant("αβγ", description="Greek letters: αβγ")
                """,
            },
        )
        result = scan_project(root)
        assert result.project_code.constant_count == 1


# ---------------------------------------------------------------------------
# uv.lock integration: real scan of an installed package
# ---------------------------------------------------------------------------
class TestUvLockIntegration:
    def test_scans_library_from_uv_lock(self, project_factory):
        """
        Put scidb itself in uv.lock. The scanner should import it and
        find non-empty exports (scidb's own test_variables if any, or at
        minimum zero-error scan).
        """
        root = project_factory(
            package_name="fix_lib_scan",
            files={},
            uv_lock_packages=["scilineage"],  # scilineage is importable in test env
        )
        result = scan_project(root)
        assert "scilineage" in result.libraries
        scilineage_result = result.libraries["scilineage"]
        # No hard claim about exports — just that it scanned without fatal error
        # at the top-level package. There may be errors for individual submodules
        # that do optional imports, but the package itself should import.
        assert scilineage_result.name == "scilineage"

    def test_zero_export_library_returned_not_filtered(self, project_factory):
        """
        Scanner returns zero-export libraries unchanged. The panel layer
        (Phase 6) is responsible for filtering them.
        """
        # We'll use ``json`` — it's a stdlib module but we can still fake
        # it as a "library" by listing something installed that has no
        # scistack exports. Use "pytest" — installed in the test env,
        # definitely no BaseVariable subclasses.
        root = project_factory(
            package_name="fix_zero_export",
            files={},
            uv_lock_packages=["pytest"],
        )
        result = scan_project(root)
        assert "pytest" in result.libraries
        # pytest has zero scistack exports — it should be returned but empty.
        assert result.libraries["pytest"].is_empty
        # And the ``non_empty_libraries`` view should hide it.
        assert "pytest" not in result.non_empty_libraries()

    def test_missing_library_captured_as_error(self, project_factory):
        """
        A distribution listed in uv.lock but not installed is reported
        as a single error entry, not a thrown exception.
        """
        root = project_factory(
            package_name="fix_missing_lib",
            files={},
            uv_lock_packages=["nonexistent_package_xyz_12345"],
        )
        result = scan_project(root)
        assert "nonexistent_package_xyz_12345" in result.libraries
        pkg = result.libraries["nonexistent_package_xyz_12345"]
        assert len(pkg.errors) >= 1
        assert pkg.is_empty

    def test_skip_dists_filter(self, project_factory):
        """``skip_dists`` parameter skips named distributions entirely."""
        root = project_factory(
            package_name="fix_skip",
            files={},
            uv_lock_packages=["pytest", "scilineage"],
        )
        result = scan_project(root, skip_dists=["pytest"])
        assert "pytest" not in result.libraries
        assert "scilineage" in result.libraries

    def test_library_filter_callable(self, project_factory):
        root = project_factory(
            package_name="fix_filter",
            files={},
            uv_lock_packages=["pytest", "scilineage"],
        )
        result = scan_project(
            root,
            library_filter=lambda name: name.startswith("sci"),
        )
        assert "scilineage" in result.libraries
        assert "pytest" not in result.libraries

    def test_project_name_skipped_from_libraries(self, project_factory):
        """If the project name shows up in its own uv.lock, it's skipped."""
        root = project_factory(
            package_name="fix_self",
            files={},
            uv_lock_packages=["fix_self", "scilineage"],
        )
        result = scan_project(root)
        assert "fix_self" not in result.libraries
        assert "scilineage" in result.libraries


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
class TestHelpers:
    def test_read_project_name(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "my_study"\nversion = "0.1.0"\n'
        )
        assert _read_project_name(tmp_path) == "my_study"

    def test_read_project_name_missing_file(self, tmp_path):
        assert _read_project_name(tmp_path) is None

    def test_read_project_name_missing_section(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires = []\n")
        assert _read_project_name(tmp_path) is None

    def test_read_uv_lock_packages(self, tmp_path):
        (tmp_path / "uv.lock").write_text(
            textwrap.dedent(
                """
                version = 1

                [[package]]
                name = "numpy"
                version = "2.0.0"

                [[package]]
                name = "pandas"
                version = "2.0.0"
                """
            )
        )
        names = _read_uv_lock_packages(tmp_path)
        assert names == ["numpy", "pandas"]

    def test_read_uv_lock_missing(self, tmp_path):
        assert _read_uv_lock_packages(tmp_path) == []

    def test_dist_to_import_names_known_package(self):
        # pytest is definitely installed
        names = _dist_to_import_names("pytest")
        assert "pytest" in names or "_pytest" in names

    def test_dist_to_import_names_missing(self):
        assert _dist_to_import_names("definitely_not_a_real_package_xyz") == []


# ---------------------------------------------------------------------------
# ModuleExports properties
# ---------------------------------------------------------------------------
class TestModuleExportsProperties:
    def test_is_empty_when_no_exports(self):
        from scidb.discover import ModuleExports

        exports = ModuleExports(module_name="test")
        assert exports.is_empty
        assert exports.total_count == 0

    def test_is_empty_false_with_variable(self):
        from scidb.discover import ModuleExports

        exports = ModuleExports(module_name="test", variables=[object])
        assert not exports.is_empty
        assert exports.total_count == 1

    def test_is_empty_false_with_function(self):
        from scidb.discover import ModuleExports

        exports = ModuleExports(module_name="test", functions=[object])
        assert not exports.is_empty

    def test_is_empty_false_with_constant(self):
        from scidb.discover import ModuleExports
        from scidb import constant

        c = constant(42)
        exports = ModuleExports(module_name="test", constants=[("X", c)])
        assert not exports.is_empty
        assert exports.total_count == 1

    def test_total_count_mixed(self):
        from scidb.discover import ModuleExports
        from scidb import constant

        c = constant(42)
        exports = ModuleExports(
            module_name="test",
            variables=[object, object],
            functions=[object],
            constants=[("X", c), ("Y", c)],
        )
        assert exports.total_count == 5


# ---------------------------------------------------------------------------
# PackageResult properties
# ---------------------------------------------------------------------------
class TestPackageResultProperties:
    def test_counts_across_modules(self):
        from scidb.discover import ModuleExports, PackageResult
        from scidb import constant

        c = constant(1)
        m1 = ModuleExports(module_name="a", variables=[object, object])
        m2 = ModuleExports(module_name="b", functions=[object], constants=[("X", c)])
        result = PackageResult(name="test", modules=[m1, m2])
        assert result.variable_count == 2
        assert result.function_count == 1
        assert result.constant_count == 1

    def test_is_empty_all_empty_modules(self):
        from scidb.discover import ModuleExports, PackageResult

        m1 = ModuleExports(module_name="a")
        m2 = ModuleExports(module_name="b")
        result = PackageResult(name="test", modules=[m1, m2])
        assert result.is_empty

    def test_is_empty_no_modules(self):
        from scidb.discover import PackageResult

        result = PackageResult(name="test")
        assert result.is_empty

    def test_is_empty_false_if_any_module_has_exports(self):
        from scidb.discover import ModuleExports, PackageResult

        m1 = ModuleExports(module_name="a")
        m2 = ModuleExports(module_name="b", variables=[object])
        result = PackageResult(name="test", modules=[m1, m2])
        assert not result.is_empty


# ---------------------------------------------------------------------------
# DiscoveryResult.non_empty_libraries
# ---------------------------------------------------------------------------
class TestDiscoveryResultNonEmptyLibraries:
    def test_filters_empty_libraries(self):
        from scidb.discover import ModuleExports, PackageResult

        empty_pkg = PackageResult(name="empty_lib", modules=[ModuleExports(module_name="e")])
        nonempty_pkg = PackageResult(
            name="good_lib",
            modules=[ModuleExports(module_name="g", variables=[object])],
        )
        result = DiscoveryResult(
            project_code=PackageResult(name="proj"),
            libraries={"empty_lib": empty_pkg, "good_lib": nonempty_pkg},
        )
        non_empty = result.non_empty_libraries()
        assert "good_lib" in non_empty
        assert "empty_lib" not in non_empty

    def test_all_empty_returns_empty_dict(self):
        from scidb.discover import ModuleExports, PackageResult

        empty1 = PackageResult(name="a", modules=[ModuleExports(module_name="a")])
        empty2 = PackageResult(name="b", modules=[ModuleExports(module_name="b")])
        result = DiscoveryResult(
            project_code=PackageResult(name="proj"),
            libraries={"a": empty1, "b": empty2},
        )
        assert result.non_empty_libraries() == {}


# ---------------------------------------------------------------------------
# _PathInsert context manager
# ---------------------------------------------------------------------------
class TestPathInsert:
    def test_inserts_and_removes_path(self, tmp_path):
        from scidb.discover import _PathInsert

        target = str(tmp_path / "my_src")
        assert target not in sys.path
        with _PathInsert(target):
            assert target in sys.path
        assert target not in sys.path

    def test_does_not_double_insert(self, tmp_path):
        from scidb.discover import _PathInsert

        target = str(tmp_path / "already")
        sys.path.insert(0, target)
        try:
            initial_count = sys.path.count(target)
            with _PathInsert(target):
                assert sys.path.count(target) == initial_count
            # Should not have removed it since it didn't insert
            assert target in sys.path
        finally:
            sys.path.remove(target)

    def test_invalidates_caches_on_exit(self, tmp_path):
        from scidb.discover import _PathInsert
        import importlib

        target = str(tmp_path / "cache_test")
        # Just verify it doesn't raise
        with _PathInsert(target):
            pass


# ---------------------------------------------------------------------------
# _purge_module
# ---------------------------------------------------------------------------
class TestPurgeModule:
    def test_purge_removes_main_and_sub_modules(self):
        from scidb.discover import _purge_module

        # Inject fake modules
        sys.modules["_fake_purge_test"] = type(sys)("_fake_purge_test")
        sys.modules["_fake_purge_test.sub1"] = type(sys)("_fake_purge_test.sub1")
        sys.modules["_fake_purge_test.sub2.deep"] = type(sys)("_fake_purge_test.sub2.deep")

        _purge_module("_fake_purge_test")

        assert "_fake_purge_test" not in sys.modules
        assert "_fake_purge_test.sub1" not in sys.modules
        assert "_fake_purge_test.sub2.deep" not in sys.modules

    def test_purge_does_not_remove_unrelated(self):
        from scidb.discover import _purge_module

        # Inject fake modules — one unrelated
        sys.modules["_fake_purge_a"] = type(sys)("_fake_purge_a")
        sys.modules["_fake_purge_a_other"] = type(sys)("_fake_purge_a_other")

        _purge_module("_fake_purge_a")

        assert "_fake_purge_a" not in sys.modules
        # _fake_purge_a_other starts with "_fake_purge_a" but not "_fake_purge_a."
        assert "_fake_purge_a_other" in sys.modules
        del sys.modules["_fake_purge_a_other"]

    def test_purge_nonexistent_is_noop(self):
        from scidb.discover import _purge_module

        _purge_module("_definitely_not_in_sys_modules_xyz")
        # Should not raise


# ---------------------------------------------------------------------------
# scan_project: deep submodule hierarchy
# ---------------------------------------------------------------------------
class TestDeepSubmodules:
    def test_deep_nested_modules_scanned(self, project_factory):
        root = project_factory(
            package_name="fix_deep",
            files={
                "level1/__init__.py": "",
                "level1/level2/__init__.py": "",
                "level1/level2/constants.py": """
                    from scidb import constant
                    DEEP_CONST = constant(42, description="deeply nested")
                """,
            },
        )
        result = scan_project(root)
        all_constants = [
            (name, c) for m in result.project_code.modules for name, c in m.constants
        ]
        names = {name for name, _ in all_constants}
        assert "DEEP_CONST" in names

    def test_init_defines_exports(self, project_factory):
        """Exports defined in __init__.py should be discovered."""
        root = project_factory(
            package_name="fix_init_exports",
            files={
                "__init__.py": """
                    from scidb import constant
                    INIT_CONST = constant(99, description="from init")
                """,
            },
        )
        result = scan_project(root)
        all_constants = [
            (name, c) for m in result.project_code.modules for name, c in m.constants
        ]
        names = {name for name, _ in all_constants}
        assert "INIT_CONST" in names

    def test_empty_package_no_error(self, project_factory):
        """A package with only __init__.py and no modules should scan cleanly."""
        root = project_factory(
            package_name="fix_empty_pkg",
            files={},
        )
        result = scan_project(root)
        assert result.project_code.is_empty
        assert result.project_code.errors == []


# ---------------------------------------------------------------------------
# scan_project: multiple types in one module
# ---------------------------------------------------------------------------
class TestMixedModuleExports:
    def test_all_types_in_one_module(self, project_factory):
        root = project_factory(
            package_name="fix_mixed",
            files={
                "everything.py": """
                    from scidb import BaseVariable, constant
                    from scilineage import lineage_fcn

                    class MixedVar(BaseVariable):
                        schema_version = 1

                    @lineage_fcn
                    def mixed_fn(x):
                        return x

                    MIXED_CONST = constant(42)
                """,
            },
        )
        result = scan_project(root)
        by_module = {m.module_name: m for m in result.project_code.modules}
        assert "fix_mixed.everything" in by_module

        mod = by_module["fix_mixed.everything"]
        assert len(mod.variables) == 1
        assert mod.variables[0].__name__ == "MixedVar"
        assert len(mod.functions) == 1
        assert mod.functions[0].fcn.__name__ == "mixed_fn"
        assert len(mod.constants) == 1
        assert mod.constants[0][0] == "MIXED_CONST"


# ---------------------------------------------------------------------------
# scan_project: BaseVariable itself not collected
# ---------------------------------------------------------------------------
class TestBaseVariableNotCollected:
    def test_base_variable_not_in_results(self, project_factory):
        """BaseVariable itself must be excluded even if imported."""
        root = project_factory(
            package_name="fix_base",
            files={
                "variables.py": """
                    from scidb import BaseVariable
                    # Only re-imports BaseVariable, no subclass
                """,
            },
        )
        result = scan_project(root)
        all_vars = [v for m in result.project_code.modules for v in m.variables]
        assert len(all_vars) == 0
