"""Tests for scistack_gui.config — config loading edge cases."""

import sys
from pathlib import Path

import pytest

# Ensure the local package is importable.
sys.path.insert(0, str(Path(__file__).parent.parent))

from scistack_gui.config import SciStackConfig, _extract_scistack_section, load_config


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
    toml_file.write_text('[tool.black]\nline-length = 88\n')

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert isinstance(config, SciStackConfig)
    assert config.project_root == tmp_path
    assert config.modules == []
    assert config.packages == []
    assert config.auto_discover is True


def test_directory_without_any_toml_raises(tmp_path):
    """A directory with no toml files should still raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="No pyproject.toml or scistack.toml"):
        load_config(tmp_path, tmp_path / "dummy.duckdb")


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
    toml_file.write_text(
        'modules = ["single.py", "lib_dir", "extra/*.py"]'
    )

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


# ---------------------------------------------------------------------------
# matlab_addpath auto-derivation
# ---------------------------------------------------------------------------

def test_matlab_addpath_auto_derived_from_functions_and_variables(tmp_path):
    """matlab_addpath should be auto-derived from parent dirs of functions, variables, and variable_dir."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text(
        '[matlab]\n'
        'functions = ["matlab/funcs/foo.m"]\n'
        'variables = ["matlab/types/MyVar.m"]\n'
        'variable_dir = "matlab/types"\n'
    )

    # Create directories and files.
    (tmp_path / "matlab" / "funcs").mkdir(parents=True)
    (tmp_path / "matlab" / "types").mkdir(parents=True)
    (tmp_path / "matlab" / "funcs" / "foo.m").write_text("function y = foo(x)\nend\n")
    (tmp_path / "matlab" / "types" / "MyVar.m").write_text("classdef MyVar < scidb.BaseVariable\nend\n")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")

    addpath_set = set(config.matlab_addpath)
    assert (tmp_path / "matlab" / "funcs").resolve() in addpath_set
    assert (tmp_path / "matlab" / "types").resolve() in addpath_set
    assert len(config.matlab_addpath) == 2


def test_matlab_addpath_empty_when_no_matlab_files(tmp_path):
    """matlab_addpath should be empty when there are no MATLAB files."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text("modules = []")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")
    assert config.matlab_addpath == []


def test_matlab_addpath_deduplicates(tmp_path):
    """matlab_addpath should deduplicate when functions and variables are in the same directory."""
    toml_file = tmp_path / "scistack.toml"
    toml_file.write_text(
        '[matlab]\n'
        'functions = ["matlab/foo.m"]\n'
        'variables = ["matlab/MyVar.m"]\n'
    )

    (tmp_path / "matlab").mkdir()
    (tmp_path / "matlab" / "foo.m").write_text("function y = foo(x)\nend\n")
    (tmp_path / "matlab" / "MyVar.m").write_text("classdef MyVar < scidb.BaseVariable\nend\n")

    config = load_config(tmp_path, tmp_path / "dummy.duckdb")

    # Both files are in the same directory — should produce exactly one entry.
    assert len(config.matlab_addpath) == 1
    assert config.matlab_addpath[0] == (tmp_path / "matlab").resolve()
