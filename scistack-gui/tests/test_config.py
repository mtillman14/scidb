"""Tests for scistack_gui.config — config loading edge cases."""

import sys
from pathlib import Path

import pytest

# Ensure the local package is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

from scistack_gui.config import (
    SciStackConfig,
    _extract_scistack_section,
    _normalize,
    add_path,
    clear_variable_file,
    load_config,
    remove_path,
    set_variable_file,
    tomllib,
)

# ---------------------------------------------------------------------------
# _extract_scistack_section
# ---------------------------------------------------------------------------


def test_empty_scistack_toml_returns_empty_dict():
    """An empty scistack.toml should return {} (valid all-defaults config)."""
    result = _extract_scistack_section({}, "scistack.toml")
    assert result == {}


def test_scistack_toml_with_content():
    """A scistack.toml with actual content returns that content."""
    data = {"modules": ["foo.py"], "auto_discover": False}
    result = _extract_scistack_section(data, "scistack.toml")
    assert result == data


def test_pyproject_with_scistack_section():
    """pyproject.toml with [tool.scistack] returns the section."""
    data = {"tool": {"scistack": {"modules": ["bar.py"]}}}
    result = _extract_scistack_section(data, "pyproject.toml")
    assert result == {"modules": ["bar.py"]}


def test_pyproject_without_scistack_section():
    """pyproject.toml without [tool.scistack] returns None."""
    data = {"tool": {"black": {"line-length": 88}}}
    result = _extract_scistack_section(data, "pyproject.toml")
    assert result is None


# ---------------------------------------------------------------------------
# load_config — integration tests using tmp_path
# ---------------------------------------------------------------------------


def test_empty_scistack_toml_loads_defaults(tmp_path):
    """An empty scistack.toml should produce a SciStackConfig with defaults."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text("")  # empty file → parsed as {}

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert isinstance(config, SciStackConfig)
    assert config.project_root == tmp_path
    assert config.modules == []
    assert config.packages == []
    assert config.auto_discover is True


def test_pyproject_without_scistack_section_loads_defaults(tmp_path):
    """A pyproject.toml lacking [tool.scistack] should use all defaults."""
    toml_file = tmp_path / "pyproject.toml"
    toml_file.write_text("[tool.black]\nline-length = 88\n")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert isinstance(config, SciStackConfig)
    assert config.project_root == tmp_path
    assert config.modules == []
    assert config.packages == []
    assert config.auto_discover is True


def test_packaged_project_auto_folds_own_name_into_packages(tmp_path):
    """A packaged project ([project].name + src/{name}/, no explicit
    [tool.scistack] packages entry) should have its own code auto-folded
    into config.packages -- otherwise registry.load_from_config never
    loads it, and a function shown in the "Discovered Code" panel would
    raise KeyError at actual run time (the packaged-mode execution gap)."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "my_pkg"\nversion = "0.1.0"\n[tool.scistack]\n'
    )
    (tmp_path / "src" / "my_pkg").mkdir(parents=True)
    (tmp_path / "src" / "my_pkg" / "__init__.py").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert config.packages == ["my_pkg"]


def test_packaged_project_already_listed_not_duplicated(tmp_path):
    """If the project's own name is already in [tool.scistack] packages,
    auto-fold must not add a second entry."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "my_pkg"\nversion = "0.1.0"\n'
        '[tool.scistack]\npackages = ["my_pkg"]\n'
    )
    (tmp_path / "src" / "my_pkg").mkdir(parents=True)
    (tmp_path / "src" / "my_pkg" / "__init__.py").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert config.packages == ["my_pkg"]


def test_packaged_project_without_src_layout_not_auto_folded(tmp_path):
    """No src/{name}/ directory -- matches scan_project's own precondition,
    so auto-fold must not add a name that isn't actually importable this way."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "my_pkg"\nversion = "0.1.0"\n[tool.scistack]\n'
    )

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert config.packages == []


def test_directory_without_any_toml_falls_back_to_folder_scan(tmp_path):
    """A directory with no toml files no longer raises — it falls back to
    scanning the directory directly for .py/.m files (zero-config mode for
    loose-script projects with no pyproject.toml/scistack.toml at all)."""
    (tmp_path / "pipeline.py").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert isinstance(config, SciStackConfig)
    assert [p.name for p in config.modules] == ["pipeline.py"]


def test_explicit_config_found_does_not_fall_back_to_folder_scan(tmp_path):
    """When a scistack.toml IS found, unlisted stray .py files must not
    leak in via folder-scan — only explicit config fields apply."""
    (tmp_path / "scistack.toml").write_text("")  # empty = all defaults
    (tmp_path / "stray.py").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert config.modules == []


def test_pyproject_with_scistack_section_loads_normally(tmp_path):
    """Happy path: pyproject.toml with [tool.scistack] works as before."""
    toml_file = tmp_path / "pyproject.toml"
    toml_file.write_text(
        '[tool.scistack]\nmodules = ["pipeline.py"]\nauto_discover = false\n'
    )
    # Create the module file so we don't get a warning
    (tmp_path / "pipeline.py").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert isinstance(config, SciStackConfig)
    assert len(config.modules) == 1
    assert config.auto_discover is False


# ---------------------------------------------------------------------------
# modules — directory and glob support
# ---------------------------------------------------------------------------


def test_modules_directory_recursively_discovers_py_files(tmp_path):
    """A directory entry in modules should recursively find all .py files."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('modules = ["lib"]')

    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "alpha.py").write_text("")
    (lib / "beta.py").write_text("")
    sub = lib / "sub"
    sub.mkdir()
    (sub / "gamma.py").write_text("")
    # Non-.py files should be ignored
    (lib / "readme.txt").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.modules)
    assert stems == ["alpha", "beta", "gamma"]


def test_modules_glob_pattern(tmp_path):
    """A glob pattern in modules should match only .py files."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('modules = ["src/**/*.py"]')

    src = tmp_path / "src"
    src.mkdir()
    (src / "one.py").write_text("")
    (src / "two.py").write_text("")
    (src / "data.csv").write_text("")
    nested = src / "nested"
    nested.mkdir()
    (nested / "three.py").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.modules)
    assert stems == ["one", "three", "two"]


def test_modules_mixed_files_dirs_and_globs(tmp_path):
    """modules list can mix individual files, directories, and globs."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('modules = ["single.py", "lib_dir", "extra/*.py"]')

    (tmp_path / "single.py").write_text("")

    lib_dir = tmp_path / "lib_dir"
    lib_dir.mkdir()
    (lib_dir / "a.py").write_text("")
    (lib_dir / "b.py").write_text("")

    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "c.py").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.modules)
    assert stems == ["a", "b", "c", "single"]


def test_modules_empty_directory_warns(tmp_path, caplog):
    """A directory with no .py files should log a warning."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('modules = ["empty_dir"]')

    (tmp_path / "empty_dir").mkdir()

    import logging

    with caplog.at_level(logging.WARNING):
        config = load_config(tmp_path, tmp_path / "dummy.duckdb")

    assert config.modules == []
    assert "no .py files" in caplog.text


def test_modules_directory_excludes_noise_directories(tmp_path):
    """A directory entry in modules should prune .venv/node_modules/etc.,
    the same way folder-scan mode already does -- otherwise transitioning
    a loose project from folder-scan to an explicit scistack.toml with
    modules = ["."] would newly sweep in noise dirs it never used to."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('modules = ["lib"]')

    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "real.py").write_text("")
    venv = lib / ".venv" / "site-packages"
    venv.mkdir(parents=True)
    (venv / "noise.py").write_text("")
    node_modules = lib / "node_modules" / "pkg"
    node_modules.mkdir(parents=True)
    (node_modules / "noise2.py").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.modules)
    assert stems == ["real"]


def test_modules_directory_excludes_test_files_and_dirs(tmp_path):
    """Anything under a tests/ dir, or named test_*.py/*_test.py, should be
    excluded from discovery -- these are found exclusively in a test and
    must not leak into functions/variables/constants/PathInputs/Sweeps."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('modules = ["lib"]')

    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "prod.py").write_text("")
    (lib / "test_helper.py").write_text("")
    (lib / "helper_test.py").write_text("")
    tests_dir = lib / "tests"
    tests_dir.mkdir()
    (tests_dir / "fixtures.py").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.modules)
    assert stems == ["prod"]


def test_explicit_single_test_file_module_entry_still_excluded(tmp_path):
    """Even an explicitly-listed single file is excluded if it's a test file
    -- there is no override for explicit config entries."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('modules = ["tests/test_x.py", "prod.py"]')

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_x.py").write_text("")
    (tmp_path / "prod.py").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.modules)
    assert stems == ["prod"]


def test_modules_glob_excludes_test_files(tmp_path):
    """A glob pattern in modules should not match test-named files."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('modules = ["src/**/*.py"]')

    src = tmp_path / "src"
    src.mkdir()
    (src / "one.py").write_text("")
    (src / "test_one.py").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.modules)
    assert stems == ["one"]


# ---------------------------------------------------------------------------
# matlab.functions / matlab.variables — directory and glob support
# ---------------------------------------------------------------------------


def test_matlab_functions_directory_recursively_discovers_m_files(tmp_path):
    """A directory entry in matlab.functions should recursively find .m files."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('[matlab]\nfunctions = ["matlab"]')

    matlab = tmp_path / "matlab"
    matlab.mkdir()
    (matlab / "foo.m").write_text("")
    (matlab / "bar.m").write_text("")
    sub = matlab / "sub"
    sub.mkdir()
    (sub / "baz.m").write_text("")
    # Non-.m files should not appear
    (matlab / "notes.txt").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.matlab_functions)
    assert stems == ["bar", "baz", "foo"]


def test_matlab_variables_directory(tmp_path):
    """A directory entry in matlab.variables should recursively find .m files."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('[matlab]\nvariables = ["types"]')

    types_dir = tmp_path / "types"
    types_dir.mkdir()
    (types_dir / "MyVar.m").write_text("")
    (types_dir / "OtherVar.m").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.matlab_variables)
    assert stems == ["MyVar", "OtherVar"]


def test_matlab_glob_filters_to_m_files_only(tmp_path):
    """A glob like 'matlab/*' should only return .m files."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('[matlab]\nfunctions = ["matlab/*"]')

    matlab = tmp_path / "matlab"
    matlab.mkdir()
    (matlab / "good.m").write_text("")
    (matlab / "readme.md").write_text("")
    (matlab / "data.csv").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = [p.stem for p in config.matlab_functions]
    assert stems == ["good"]


def test_matlab_empty_directory_warns(tmp_path, caplog):
    """A directory with no .m files should log a warning."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('[matlab]\nfunctions = ["empty"]')

    (tmp_path / "empty").mkdir()

    import logging

    with caplog.at_level(logging.WARNING):
        config = load_config(tmp_path, tmp_path / "dummy.duckdb")

    assert config.matlab_functions == []
    assert "no .m files" in caplog.text


def test_matlab_sources_key_populates_matlab_sources_unified(tmp_path):
    """[matlab] sources = [...] should populate matlab_sources unsplit --
    NOT matlab_functions/matlab_variables -- since each file is classified
    per-content at registry-load time (see matlab_registry.load_from_config),
    not pre-sorted by the config author. This is the key that lets a single
    GUI-added path (Paths popup) work for MATLAB without declaring
    function-vs-variable up front."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('[matlab]\nsources = ["mixed"]')

    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / "some_function.m").write_text("")
    (mixed / "SomeClass.m").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.matlab_sources)
    assert stems == ["SomeClass", "some_function"]
    assert config.matlab_functions == []
    assert config.matlab_variables == []


def test_matlab_sources_directory_excludes_noise_and_skip_dirs(tmp_path):
    """[matlab] sources directory entries should prune noise dirs and
    MATLAB private/@class/+package dirs, same as folder-scan mode."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('[matlab]\nsources = ["mixed"]')

    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / "keep.m").write_text("")
    private_dir = mixed / "private"
    private_dir.mkdir()
    (private_dir / "helper.m").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.matlab_sources)
    assert stems == ["keep"]


def test_matlab_sources_excludes_test_dir_and_pascal_test_files(tmp_path):
    """[matlab] sources should exclude anything under a tests/ dir, plus
    PascalCase Test*.m/*Test.m files even outside a tests/ dir -- these are
    found exclusively in a MATLAB test and must not leak into discovery."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('[matlab]\nsources = ["mixed"]')

    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / "good.m").write_text("")
    (mixed / "TestBar.m").write_text("")
    (mixed / "BazTest.m").write_text("")
    tests_dir = mixed / "tests"
    tests_dir.mkdir()
    (tests_dir / "Foo.m").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.matlab_sources)
    assert stems == ["good"]


def test_matlab_explicit_single_test_file_entry_still_excluded(tmp_path):
    """Even an explicitly-listed single .m file is excluded if it matches
    the test naming convention -- no override for explicit config entries."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('[matlab]\nfunctions = ["tests/TestForEach.m", "good.m"]')

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "TestForEach.m").write_text("")
    (tmp_path / "good.m").write_text("")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    stems = sorted(p.stem for p in config.matlab_functions)
    assert stems == ["good"]


# ---------------------------------------------------------------------------
# matlab_addpath auto-derivation
# ---------------------------------------------------------------------------


def test_matlab_addpath_auto_derived_from_functions_and_variables(tmp_path):
    """matlab_addpath should be auto-derived from parent dirs of functions, variables, and variable_dir."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text(
        "[matlab]\n"
        'functions = ["matlab/funcs/foo.m"]\n'
        'variables = ["matlab/types/MyVar.m"]\n'
        'variable_dir = "matlab/types"\n'
    )

    # Create directories and files.
    (tmp_path / "matlab" / "funcs").mkdir(parents=True)
    (tmp_path / "matlab" / "types").mkdir(parents=True)
    (tmp_path / "matlab" / "funcs" / "foo.m").write_text("function y = foo(x)\nend\n")
    (tmp_path / "matlab" / "types" / "MyVar.m").write_text(
        "classdef MyVar < scidb.BaseVariable\nend\n"
    )

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")

    # Compare against the non-canonicalized form since config no longer
    # calls .resolve() on stored paths (that would convert Windows mapped
    # drives to UNC, breaking VS Code's reveal_in_editor).
    addpath_set = set(config.matlab_addpath)
    assert (tmp_path / "matlab" / "funcs") in addpath_set
    assert (tmp_path / "matlab" / "types") in addpath_set
    assert len(config.matlab_addpath) == 2


def test_matlab_addpath_empty_when_no_matlab_files(tmp_path):
    """matlab_addpath should be empty when there are no MATLAB files."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text("modules = []")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert config.matlab_addpath == []


def test_matlab_variables_excluded_from_functions(tmp_path):
    """Files in matlab.variables must not also be parsed as matlab.functions.

    Regression test for the case where ``matlab.functions`` points at a
    parent directory that contains the ``matlab.variables`` subtree — the
    recursive walk would otherwise include variable .m files in the
    functions list, producing spurious parse warnings.
    """
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('[matlab]\nfunctions = ["src/"]\nvariables = ["src/vars/"]\n')

    src = tmp_path / "src"
    src.mkdir()
    (src / "func.m").write_text("function y = func(x)\ny = x;\nend\n")
    vars_dir = src / "vars"
    vars_dir.mkdir()
    (vars_dir / "var.m").write_text("classdef var < scidb.BaseVariable\nend\n")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert [p.name for p in config.matlab_functions] == ["func.m"]
    assert [p.name for p in config.matlab_variables] == ["var.m"]


# ---------------------------------------------------------------------------
# _normalize — preserves user's drive-letter form
# ---------------------------------------------------------------------------


def test_normalize_is_absolute_and_normpath(tmp_path):
    """_normalize should make the path absolute and collapse ``.``/``..``."""
    # Relative with .. segment
    rel = Path("a") / ".." / "b"
    result = _normalize(rel)
    assert result.is_absolute()
    # Normalized form has no .. segment.
    assert ".." not in result.parts

    # Already-absolute input passes through as-is (no following of symlinks).
    result2 = _normalize(tmp_path / "sub")
    assert result2 == tmp_path / "sub"


def test_normalize_does_not_follow_symlinks(tmp_path):
    """_normalize must NOT resolve symlinks (or Windows mapped drives) —
    that's what Path.resolve() does and what causes the UNC issue."""
    import os

    real = tmp_path / "real_dir"
    real.mkdir()
    (real / "file.m").write_text("")

    link = tmp_path / "link_dir"
    try:
        os.symlink(real, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not supported on this platform")

    normalized = _normalize(link / "file.m")
    # The symlinked path is preserved; only .resolve() would rewrite it.
    assert normalized == link / "file.m"
    # Sanity: .resolve() WOULD follow the symlink (this is the behavior we
    # deliberately avoid on Windows mapped drives).
    assert normalized.resolve() == real / "file.m"


def test_matlab_functions_not_canonicalized_through_symlink(tmp_path):
    """Regression test for the mapped-drive → UNC issue on Windows.

    If the MATLAB functions directory is referenced through a symlink
    (which simulates y:\\ → \\\\server\\share\\ on Windows), the stored
    paths in ``config.matlab_functions`` must retain the symlink form,
    not the resolved form. This ensures VS Code can open them using the
    same path the workspace was rooted at.
    """
    import os

    real_root = tmp_path / "real"
    real_root.mkdir()
    (real_root / "func.m").write_text("function y = func(x)\ny=x;\nend\n")
    (real_root / "scistack.toml").write_text('[matlab]\nfunctions = ["func.m"]\n')

    link_root = tmp_path / "link"
    try:
        os.symlink(real_root, link_root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not supported on this platform")

    config = load_config(link_root, link_root / "dummy.duckdb")
    assert len(config.matlab_functions) == 1
    # Crucial: stored path uses the link prefix, not the real prefix.
    assert config.matlab_functions[0] == link_root / "func.m"
    assert str(config.matlab_functions[0]).startswith(str(link_root))


def test_matlab_addpath_deduplicates(tmp_path):
    """matlab_addpath should deduplicate when functions and variables are in the same directory."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text(
        '[matlab]\nfunctions = ["matlab/foo.m"]\nvariables = ["matlab/MyVar.m"]\n'
    )

    (tmp_path / "matlab").mkdir()
    (tmp_path / "matlab" / "foo.m").write_text("function y = foo(x)\nend\n")
    (tmp_path / "matlab" / "MyVar.m").write_text(
        "classdef MyVar < scidb.BaseVariable\nend\n"
    )

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")

    # Both files are in the same directory — should produce exactly one entry.
    assert len(config.matlab_addpath) == 1
    assert config.matlab_addpath[0] == (tmp_path / "matlab")


# ---------------------------------------------------------------------------
# Folder-scan fallback (no pyproject.toml/scistack.toml anywhere)
# ---------------------------------------------------------------------------


def test_folder_scan_discovers_py_and_m_files_mixed(tmp_path):
    """Loose Python + MATLAB files with no config file at all: .py files
    become modules, .m files become the unified matlab_sources list."""
    (tmp_path / "loader.py").write_text("")
    (tmp_path / "analysis.py").write_text("")
    (tmp_path / "bandpass_filter.m").write_text("function y = bandpass_filter(x)\ny=x;\nend\n")
    (tmp_path / "RawSignal.m").write_text("classdef RawSignal < scidb.BaseVariable\nend\n")
    sub = tmp_path / "helpers"
    sub.mkdir()
    (sub / "util.py").write_text("")
    (sub / "util.m").write_text("function y = util(x)\ny=x;\nend\n")

    config = load_config(None, tmp_path / "dummy.duckdb")
    assert sorted(p.name for p in config.modules) == [
        "analysis.py",
        "loader.py",
        "util.py",
    ]
    assert sorted(p.name for p in config.matlab_sources) == [
        "RawSignal.m",
        "bandpass_filter.m",
        "util.m",
    ]
    # matlab_functions/matlab_variables stay empty — classification happens
    # per-file later, in matlab_registry.load_from_sources.
    assert config.matlab_functions == []
    assert config.matlab_variables == []


def test_folder_scan_project_path_directory_with_no_config(tmp_path):
    """An explicit --project pointing at a directory with no config file
    inside it also falls back to folder-scan, rooted at that directory."""
    (tmp_path / "pipeline.py").write_text("")

    config = load_config(tmp_path, tmp_path / "elsewhere" / "dummy.duckdb")
    assert config.project_root == tmp_path
    assert [p.name for p in config.modules] == ["pipeline.py"]


def test_folder_scan_no_project_path_roots_at_db_directory(tmp_path):
    """With no --project at all, folder-scan roots at the .duckdb's own
    directory (not an ancestor search — that's only for locating a config
    file, which doesn't exist here)."""
    project_dir = tmp_path / "my_study"
    project_dir.mkdir()
    (project_dir / "pipeline.py").write_text("")

    config = load_config(None, project_dir / "my_study.duckdb")
    assert config.project_root == project_dir
    assert [p.name for p in config.modules] == ["pipeline.py"]


def test_folder_scan_excludes_noise_directories(tmp_path):
    """Folder-scan must not walk into VCS/venv/build noise directories."""
    (tmp_path / "real.py").write_text("")
    for noise in (".git", "__pycache__", ".venv", "venv", "node_modules", "build", "dist"):
        d = tmp_path / noise
        d.mkdir()
        (d / "ignored.py").write_text("")
        (d / "ignored.m").write_text("function y = ignored(x)\ny=x;\nend\n")

    config = load_config(None, tmp_path / "dummy.duckdb")
    assert [p.name for p in config.modules] == ["real.py"]
    assert config.matlab_sources == []


def test_folder_scan_matlab_excludes_private_class_and_package_dirs(tmp_path):
    """private/, @ClassName/, and +package/ folders are skipped during
    folder-scan — sweeping them in would mis-register class methods or
    namespaced functions as standalone top-level functions."""
    (tmp_path / "public.m").write_text("function y = public(x)\ny=x;\nend\n")
    for skip_dir in ("private", "@MyClass", "+mypkg"):
        d = tmp_path / skip_dir
        d.mkdir()
        (d / "hidden.m").write_text("function y = hidden(x)\ny=x;\nend\n")

    config = load_config(None, tmp_path / "dummy.duckdb")
    assert [p.name for p in config.matlab_sources] == ["public.m"]


def test_folder_scan_excludes_test_dirs_and_test_named_files(tmp_path):
    """Folder-scan must not sweep in tests/ dirs or test-named files for
    either language -- these are found exclusively in a test."""
    (tmp_path / "real.py").write_text("")
    (tmp_path / "test_real.py").write_text("")
    (tmp_path / "real.m").write_text("function y = real_fn(x)\ny=x;\nend\n")
    (tmp_path / "TestReal.m").write_text("function y = t(x)\ny=x;\nend\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "helper.py").write_text("")
    (tests_dir / "helper.m").write_text("function y = helper(x)\ny=x;\nend\n")

    config = load_config(None, tmp_path / "dummy.duckdb")
    assert [p.name for p in config.modules] == ["real.py"]
    assert [p.name for p in config.matlab_sources] == ["real.m"]


def test_folder_scan_matlab_helpers_fixture_excludes_test_only_content(tmp_path):
    """Real regression test: scimatlab/tests/matlab/helpers/ contains plain
    functions (sum_all.m, col_max.m, ...) and BaseVariable classdefs
    (RawSignal.m, BaselineSignal.m, ...) that exist exclusively to support
    the MATLAB test suite. Copying that fixture under a tests/ dir and
    folder-scanning it must discover zero of its files."""
    import shutil

    real_helpers = (
        Path(__file__).parent.parent.parent
        / "scimatlab"
        / "tests"
        / "matlab"
        / "helpers"
    )
    assert real_helpers.is_dir(), "expected scimatlab/tests/matlab/helpers to exist"

    project_tests_dir = tmp_path / "tests" / "matlab" / "helpers"
    project_tests_dir.parent.mkdir(parents=True)
    shutil.copytree(real_helpers, project_tests_dir)
    (tmp_path / "real.py").write_text("")

    config = load_config(None, tmp_path / "dummy.duckdb")
    assert [p.name for p in config.modules] == ["real.py"]
    assert config.matlab_sources == []


def test_folder_scan_matlab_addpath_derived_from_sources(tmp_path):
    """matlab_addpath should be derived from matlab_sources' parent dirs
    too, not just the explicit matlab_functions/matlab_variables lists."""
    sub = tmp_path / "matlab"
    sub.mkdir()
    (sub / "foo.m").write_text("function y = foo(x)\ny=x;\nend\n")

    config = load_config(None, tmp_path / "dummy.duckdb")
    assert config.matlab_addpath == [sub]


# ---------------------------------------------------------------------------
# add_path / remove_path — GUI Paths popup write-back (loose-script only)
# ---------------------------------------------------------------------------


def _read_raw_section(toml_path: Path) -> dict:
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def test_add_path_creates_scistack_toml_when_none_exists(tmp_path):
    """First-ever '+' click on a pure folder-scan project: creates
    scistack.toml, seeding it with the project root (so code implicitly
    discovered under folder-scan mode isn't silently dropped) plus the
    newly added path -- in both modules and [matlab] sources."""
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    shared_repo = tmp_path / "shared_repo"
    shared_repo.mkdir()

    written = add_path(db_path, shared_repo)

    assert written == tmp_path / "scistack.toml"
    data = _read_raw_section(written)
    root_str = str(_normalize(tmp_path))
    repo_str = str(_normalize(shared_repo))
    assert set(data["modules"]) == {root_str, repo_str}
    assert set(data["matlab"]["sources"]) == {root_str, repo_str}


def test_add_path_appends_to_existing_scistack_toml_preserving_other_keys(tmp_path):
    """Adding a path to an already-configured project must not disturb
    unrelated hand-authored keys (packages, auto_discover, existing
    modules entries)."""
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    (tmp_path / "existing").mkdir()
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text(
        'modules = ["existing"]\n'
        'packages = ["foo"]\n'
        "auto_discover = false\n"
    )

    shared_repo = tmp_path / "shared_repo"
    shared_repo.mkdir()
    add_path(db_path, shared_repo)

    data = _read_raw_section(toml_file)
    assert "existing" in data["modules"]
    assert str(_normalize(shared_repo)) in data["modules"]
    assert data["packages"] == ["foo"]
    assert data["auto_discover"] is False


def test_add_path_is_idempotent_on_duplicate(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    shared_repo = tmp_path / "shared_repo"
    shared_repo.mkdir()

    add_path(db_path, shared_repo)
    written = add_path(db_path, shared_repo)

    data = _read_raw_section(written)
    repo_str = str(_normalize(shared_repo))
    assert data["modules"].count(repo_str) == 1
    assert data["matlab"]["sources"].count(repo_str) == 1


def test_add_path_rejects_relative_path(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    with pytest.raises(ValueError):
        add_path(db_path, Path("relative/dir"))


def test_add_path_rejects_nonexistent_path(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    with pytest.raises(FileNotFoundError):
        add_path(db_path, tmp_path / "does_not_exist")


def test_add_path_rejects_file_not_directory(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    a_file = tmp_path / "not_a_dir.py"
    a_file.write_text("")
    with pytest.raises(NotADirectoryError):
        add_path(db_path, a_file)


def test_add_path_rejects_packaged_project(tmp_path):
    """pyproject.toml projects are out of scope for this write path --
    the Paths popup keeps its old read-only view for those."""
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    (tmp_path / "pyproject.toml").write_text("[tool.scistack]\n")
    shared_repo = tmp_path / "shared_repo"
    shared_repo.mkdir()

    with pytest.raises(ValueError):
        add_path(db_path, shared_repo)


def test_remove_path_deletes_entry_from_both_lists(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    keep_dir = tmp_path / "keep"
    keep_dir.mkdir()
    drop_dir = tmp_path / "drop"
    drop_dir.mkdir()

    add_path(db_path, keep_dir)
    add_path(db_path, drop_dir)
    written = remove_path(db_path, drop_dir)

    data = _read_raw_section(written)
    keep_str = str(_normalize(keep_dir))
    drop_str = str(_normalize(drop_dir))
    assert keep_str in data["modules"]
    assert drop_str not in data["modules"]
    assert keep_str in data["matlab"]["sources"]
    assert drop_str not in data["matlab"]["sources"]


def test_remove_path_noop_when_no_config_file(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    with pytest.raises(FileNotFoundError):
        remove_path(db_path, tmp_path / "whatever")
    assert not (tmp_path / "scistack.toml").exists()


def test_remove_path_rejects_packaged_project(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    (tmp_path / "pyproject.toml").write_text("[tool.scistack]\nmodules = [\"x\"]\n")

    with pytest.raises(ValueError):
        remove_path(db_path, tmp_path / "x")


# ---------------------------------------------------------------------------
# set_variable_file / clear_variable_file
#
# Regression coverage for the "creating a PathInput/Sweep/Variable from the
# GUI silently failed with 'No module file was loaded at startup'" bug --
# see .claude/pathinput-sweep-variable-creation-fixes.md. Before this, there
# was no way to configure variable_file for a loose-script project at all.
# ---------------------------------------------------------------------------


def test_set_variable_file_auto_creates_default_when_none_exists(tmp_path):
    """First-ever auto-create on a pure folder-scan project (no scistack.toml/
    pyproject.toml yet): creates scistack.toml seeded with the project root
    (same reasoning as add_path), creates src/scistack_entities.py, and
    points variable_file at it."""
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")

    result = set_variable_file(db_path, None)

    expected = _normalize(tmp_path / "src" / "scistack_entities.py")
    assert result == expected
    assert expected.exists()
    content = expected.read_text()
    assert content  # non-empty scaffold, not a blank file
    assert "import scidb" in content  # immediately valid Python on creation

    toml_path = tmp_path / "scistack.toml"
    data = _read_raw_section(toml_path)
    assert data["variable_file"] == str(expected)
    assert str(_normalize(tmp_path)) in data["modules"]


def test_set_variable_file_accepts_relative_path(tmp_path):
    """A relative file_path (as the project-creation wizard now sends,
    e.g. 'src/scistack_entities.py') resolves against whatever project_root
    this function determines internally, instead of raising -- this is
    what lets the wizard pass a bare relative string without first having
    to know where the project root will end up."""
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")

    result = set_variable_file(db_path, "custom/relative_entities.py")

    expected = _normalize(tmp_path / "custom" / "relative_entities.py")
    assert result == expected
    assert expected.exists()

    toml_path = tmp_path / "scistack.toml"
    data = _read_raw_section(toml_path)
    assert data["variable_file"] == str(expected)


def test_set_variable_file_relative_path_resolves_against_existing_root(tmp_path):
    """When a scistack.toml already exists (not the first-write case), a
    relative file_path resolves against ITS project_root, not db_path's
    parent."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "scistack.toml").write_text("")
    db_path = project_root / "sub" / "proj.duckdb"
    db_path.parent.mkdir()
    db_path.write_text("")

    result = set_variable_file(db_path, "src/entities.py")

    assert result == _normalize(project_root / "src" / "entities.py")


def test_set_variable_file_explicit_path_registers_module(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    (tmp_path / "other").mkdir()
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text('modules = ["other"]\n')

    explicit = tmp_path / "vars" / "custom_variables.py"
    result = set_variable_file(db_path, explicit)

    assert result == _normalize(explicit)
    assert explicit.exists()
    data = _read_raw_section(toml_file)
    assert data["variable_file"] == str(_normalize(explicit))
    assert str(_normalize(explicit)) in data["modules"]
    assert "other" in data["modules"]  # untouched


def test_set_variable_file_does_not_overwrite_existing_file(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    existing = tmp_path / "my_variables.py"
    existing.write_text("from scidb import BaseVariable\n\nclass Foo(BaseVariable):\n    pass\n")

    set_variable_file(db_path, existing)

    assert existing.read_text() == (
        "from scidb import BaseVariable\n\nclass Foo(BaseVariable):\n    pass\n"
    )


def test_set_variable_file_skips_module_entry_when_already_covered(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    covering_dir = tmp_path / "src"
    covering_dir.mkdir()
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text(f'modules = [{str(covering_dir)!r}]\n')

    target = covering_dir / "variables.py"
    set_variable_file(db_path, target)

    data = _read_raw_section(toml_file)
    # Not appended again -- already discoverable via the directory entry.
    assert data["modules"] == [str(covering_dir)]


def test_set_variable_file_absolute_path_used_as_is(tmp_path):
    """An absolute file_path is used verbatim (unchanged behavior for
    existing callers like the Paths popup's 'Change' action)."""
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    absolute = tmp_path / "elsewhere" / "vars.py"

    result = set_variable_file(db_path, absolute)

    assert result == _normalize(absolute)


def test_set_variable_file_rejects_packaged_project(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    (tmp_path / "pyproject.toml").write_text("[tool.scistack]\n")

    with pytest.raises(ValueError):
        set_variable_file(db_path, None)


def test_clear_variable_file_removes_key_but_keeps_file(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    variable_file = set_variable_file(db_path, None)

    toml_path = tmp_path / "scistack.toml"
    written = clear_variable_file(db_path)

    assert written == toml_path
    data = _read_raw_section(toml_path)
    assert "variable_file" not in data
    assert variable_file.exists()  # never deletes the file itself


def test_clear_variable_file_noop_when_no_config_file(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    with pytest.raises(FileNotFoundError):
        clear_variable_file(db_path)


def test_clear_variable_file_rejects_packaged_project(tmp_path):
    db_path = tmp_path / "proj.duckdb"
    db_path.write_text("")
    (tmp_path / "pyproject.toml").write_text("[tool.scistack]\nvariable_file = \"x.py\"\n")

    with pytest.raises(ValueError):
        clear_variable_file(db_path)
