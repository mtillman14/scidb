"""Unit tests for scifor.discovery -- the generic package-walking harness."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest
from scifor.discovery import (
    PathInsert,
    is_test_modname,
    is_test_path,
    purge_module,
    read_project_name,
    walk_package,
)


@pytest.fixture
def package_factory(tmp_path: Path):
    """Scaffold a throwaway importable package under tmp_path, add it to
    sys.path, and clean up sys.modules/sys.path after the test."""
    created: list[str] = []

    def _make(package_name: str, files: dict[str, str]) -> None:
        pkg_dir = tmp_path / package_name
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "__init__.py").write_text("")
        for rel, content in files.items():
            full = pkg_dir / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(textwrap.dedent(content))
        created.append(package_name)

    sys.path.insert(0, str(tmp_path))
    yield _make

    sys.path.remove(str(tmp_path))
    for name in created:
        prefix = name + "."
        for mod_name in list(sys.modules):
            if mod_name == name or mod_name.startswith(prefix):
                sys.modules.pop(mod_name, None)


class TestWalkPackage:
    def test_top_level_import_failure_captured(self):
        wr = walk_package("definitely_not_a_real_package_xyz", lambda m: None)
        assert wr.per_module == []
        assert len(wr.errors) == 1
        assert wr.errors[0].module_name == "definitely_not_a_real_package_xyz"

    def test_calls_on_module_for_top_level_and_submodules(self, package_factory):
        package_factory(
            "fix_walk_basic",
            files={"a.py": "X = 1\n", "b.py": "Y = 2\n"},
        )
        seen = []
        wr = walk_package("fix_walk_basic", lambda m: seen.append(m.__name__))
        names = {n for n, _ in wr.per_module}
        assert names == {"fix_walk_basic", "fix_walk_basic.a", "fix_walk_basic.b"}
        assert set(seen) == names
        assert wr.errors == []

    def test_submodule_import_failure_does_not_abort_walk(self, package_factory):
        package_factory(
            "fix_walk_broken",
            files={
                "good.py": "X = 1\n",
                "broken.py": "raise RuntimeError('boom')\n",
            },
        )
        wr = walk_package("fix_walk_broken", lambda m: m.__name__)
        names = {n for n, _ in wr.per_module}
        assert "fix_walk_broken.good" in names
        assert "fix_walk_broken.broken" not in names
        broken_errors = [e for e in wr.errors if "broken" in e.module_name]
        assert len(broken_errors) == 1
        assert "boom" in broken_errors[0].traceback

    def test_on_module_exception_captured_not_raised(self, package_factory):
        package_factory("fix_walk_callback_error", files={"a.py": "X = 1\n"})

        def on_module(mod):
            if mod.__name__.endswith(".a"):
                raise ValueError("callback exploded")
            return None

        wr = walk_package("fix_walk_callback_error", on_module)
        errors = [e for e in wr.errors if e.module_name.endswith(".a")]
        assert len(errors) == 1
        assert "callback exploded" in errors[0].traceback

    def test_test_modules_skipped(self, package_factory):
        package_factory(
            "fix_walk_test_skip",
            files={
                "prod.py": "X = 1\n",
                "tests/__init__.py": "",
                "tests/helpers.py": "Y = 2\n",
                "test_helper.py": "Z = 3\n",
            },
        )
        wr = walk_package("fix_walk_test_skip", lambda m: m.__name__)
        names = {n for n, _ in wr.per_module}
        assert "fix_walk_test_skip.prod" in names
        assert not any("tests" in n for n in names)
        assert "fix_walk_test_skip.test_helper" not in names

    def test_non_package_module_no_submodule_walk(self, package_factory):
        """A module (not a package) has no __path__ -- walk_package should
        just call on_module once and return, not raise."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            Path(d, "fix_bare_module.py").write_text("X = 1\n")
            sys.path.insert(0, d)
            try:
                wr = walk_package("fix_bare_module", lambda m: m.__name__)
                assert [n for n, _ in wr.per_module] == ["fix_bare_module"]
                assert wr.errors == []
            finally:
                sys.path.remove(d)
                sys.modules.pop("fix_bare_module", None)


class TestIsTestPathAndModname:
    def test_file_inside_tests_dir(self):
        assert is_test_path("pkg/tests/helper.py")

    def test_test_prefixed_filename(self):
        assert is_test_path("pkg/test_foo.py")

    def test_test_suffixed_filename(self):
        assert is_test_path("pkg/foo_test.py")

    def test_normal_file_not_excluded(self):
        assert not is_test_path("pkg/helper.py")

    def test_false_positive_guard_latest(self):
        assert not is_test_path("pkg/latest.py")

    def test_modname_with_tests_component(self):
        assert is_test_modname("mypackage.tests.helpers")

    def test_modname_bare_tests_leaf(self):
        assert is_test_modname("mypackage.tests")

    def test_modname_normal_not_excluded(self):
        assert not is_test_modname("mypackage.helpers")

    def test_modname_false_positive_guard(self):
        assert not is_test_modname("mypackage.latest")


class TestReadProjectName:
    def test_reads_project_name(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "my_study"\nversion = "0.1.0"\n'
        )
        assert read_project_name(tmp_path) == "my_study"

    def test_missing_file(self, tmp_path):
        assert read_project_name(tmp_path) is None

    def test_missing_section(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires = []\n")
        assert read_project_name(tmp_path) is None


class TestPathInsert:
    def test_inserts_and_removes_path(self, tmp_path):
        target = str(tmp_path / "my_src")
        assert target not in sys.path
        with PathInsert(target):
            assert target in sys.path
        assert target not in sys.path

    def test_does_not_double_insert(self, tmp_path):
        target = str(tmp_path / "already")
        sys.path.insert(0, target)
        try:
            initial_count = sys.path.count(target)
            with PathInsert(target):
                assert sys.path.count(target) == initial_count
            assert target in sys.path
        finally:
            sys.path.remove(target)


class TestPurgeModule:
    def test_purge_removes_main_and_sub_modules(self):
        sys.modules["_fake_purge_test"] = type(sys)("_fake_purge_test")
        sys.modules["_fake_purge_test.sub1"] = type(sys)("_fake_purge_test.sub1")

        purge_module("_fake_purge_test")

        assert "_fake_purge_test" not in sys.modules
        assert "_fake_purge_test.sub1" not in sys.modules

    def test_purge_nonexistent_is_noop(self):
        purge_module("_definitely_not_in_sys_modules_xyz")
