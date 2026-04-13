"""
Tests for MATLAB support: parser, registry, and command generation.
"""

import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# matlab_parser tests
# ---------------------------------------------------------------------------


class TestParseMatlabFunction:
    def test_basic_function(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "bandpass_filter.m"
        f.write_text(textwrap.dedent("""\
            function [filtered] = bandpass_filter(signal, low_hz, high_hz)
            % BANDPASS_FILTER  Apply a bandpass filter.
                filtered = signal * low_hz;
            end
        """))

        info = parse_matlab_function(f)
        assert info is not None
        assert info.name == "bandpass_filter"
        assert info.params == ["signal", "low_hz", "high_hz"]
        assert info.language == "matlab"
        assert len(info.source_hash) == 64  # SHA-256 hex

    def test_single_output(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "compute_vo2.m"
        f.write_text("function result = compute_vo2(breath_data)\n  result = 0;\nend\n")

        info = parse_matlab_function(f)
        assert info is not None
        assert info.name == "compute_vo2"
        assert info.params == ["breath_data"]

    def test_no_output(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "plot_results.m"
        f.write_text("function plot_results(data, title_str)\n  plot(data);\nend\n")

        info = parse_matlab_function(f)
        assert info is not None
        assert info.name == "plot_results"
        assert info.params == ["data", "title_str"]

    def test_no_params(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "setup.m"
        f.write_text("function setup()\n  disp('hi');\nend\n")

        info = parse_matlab_function(f)
        assert info is not None
        assert info.name == "setup"
        assert info.params == []

    def test_not_a_function(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "script.m"
        f.write_text("% Just a script\nx = 5;\n")

        info = parse_matlab_function(f)
        assert info is None

    def test_missing_file(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        info = parse_matlab_function(tmp_path / "nonexistent.m")
        assert info is None

    def test_multiple_outputs(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "decompose.m"
        f.write_text("function [amp, phase, freq] = decompose(signal, fs)\nend\n")

        info = parse_matlab_function(f)
        assert info is not None
        assert info.name == "decompose"
        assert info.params == ["signal", "fs"]

    def test_source_hash_changes(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "foo.m"
        f.write_text("function y = foo(x)\n  y = x;\nend\n")
        info1 = parse_matlab_function(f)

        f.write_text("function y = foo(x)\n  y = x * 2;\nend\n")
        info2 = parse_matlab_function(f)

        assert info1.source_hash != info2.source_hash


class TestParseMatlabVariable:
    def test_basic_classdef(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_variable

        f = tmp_path / "RawSignal.m"
        f.write_text(textwrap.dedent("""\
            classdef RawSignal < scidb.BaseVariable
                % Raw EMG signal data
            end
        """))

        name = parse_matlab_variable(f)
        assert name == "RawSignal"

    def test_not_base_variable(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_variable

        f = tmp_path / "MyClass.m"
        f.write_text("classdef MyClass < handle\nend\n")

        name = parse_matlab_variable(f)
        assert name is None

    def test_custom_base(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_variable

        f = tmp_path / "Foo.m"
        f.write_text("classdef Foo < mylib.BaseVariable\nend\n")

        name = parse_matlab_variable(f)
        assert name == "Foo"

    def test_missing_file(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_variable

        name = parse_matlab_variable(tmp_path / "nonexistent.m")
        assert name is None

    def test_no_classdef(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_variable

        f = tmp_path / "script.m"
        f.write_text("% Just a script\n")

        name = parse_matlab_variable(f)
        assert name is None


# ---------------------------------------------------------------------------
# matlab_command tests
# ---------------------------------------------------------------------------


class TestGenerateMatlabCommand:
    def test_template_no_variants(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="bandpass_filter",
            db_path="/data/experiment.duckdb",
            schema_keys=["subject", "session"],
        )

        assert "bandpass_filter" in cmd
        assert "/data/experiment.duckdb" in cmd
        assert "scihist.configure_database" in cmd
        assert "scihist.for_each" in cmd

    def test_with_variants(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        variants = [
            {
                "input_types": {"signal": "RawSignal"},
                "output_type": "FilteredSignal",
                "constants": {"low_hz": 20},
                "record_count": 4,
            }
        ]

        cmd = generate_matlab_command(
            function_name="bandpass_filter",
            db_path="/data/experiment.duckdb",
            schema_keys=["subject", "session"],
            variants=variants,
        )

        assert "scidb.register_variable('FilteredSignal')" in cmd
        assert "scidb.register_variable('RawSignal')" in cmd
        assert "@bandpass_filter" in cmd
        assert "RawSignal()" in cmd
        assert "{FilteredSignal()}" in cmd
        assert "20" in cmd

    def test_addpath(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="foo",
            db_path="/data/db.duckdb",
            schema_keys=["subject"],
            addpath_dirs=["/home/user/matlab/lib", "/home/user/shared"],
        )

        assert "addpath('/home/user/matlab/lib')" in cmd
        assert "addpath('/home/user/shared')" in cmd

    def test_schema_filter(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        variants = [
            {
                "input_types": {"x": "X"},
                "output_type": "Y",
                "constants": {},
                "record_count": 2,
            }
        ]

        cmd = generate_matlab_command(
            function_name="process",
            db_path="/data/db.duckdb",
            schema_keys=["subject", "session"],
            variants=variants,
            schema_filter={"subject": [1, 2, 3]},
        )

        assert "'subject'" in cmd
        assert "[1 2 3]" in cmd

    def test_string_schema_filter(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        variants = [
            {
                "input_types": {},
                "output_type": "Y",
                "constants": {},
                "record_count": 1,
            }
        ]

        cmd = generate_matlab_command(
            function_name="process",
            db_path="/db.duckdb",
            schema_keys=["session"],
            variants=variants,
            schema_filter={"session": ["pre", "post"]},
        )

        assert '"pre"' in cmd
        assert '"post"' in cmd

    def test_deduplicates_variants(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        # Same constants, different output types → should deduplicate.
        variants = [
            {
                "input_types": {"x": "X"},
                "output_type": "Y1",
                "constants": {"k": 5},
                "record_count": 1,
            },
            {
                "input_types": {"x": "X"},
                "output_type": "Y2",
                "constants": {"k": 5},
                "record_count": 1,
            },
        ]

        cmd = generate_matlab_command(
            function_name="f",
            db_path="/db.duckdb",
            schema_keys=["s"],
            variants=variants,
        )

        # Should only have one for_each call.
        assert cmd.count("scihist.for_each") == 1

    def test_escape_single_quotes(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="f",
            db_path="/path/with'quote/db.duckdb",
            schema_keys=["s"],
        )

        assert "/path/with''quote/db.duckdb" in cmd


# ---------------------------------------------------------------------------
# config MATLAB parsing tests
# ---------------------------------------------------------------------------


class TestConfigMatlabParsing:
    def test_pyproject_with_matlab(self, tmp_path):
        from scistack_gui.config import load_config

        # Create a pyproject.toml with MATLAB section.
        (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""\
            [tool.scistack]
            modules = []

            [tool.scistack.matlab]
            functions = ["matlab/bandpass_filter.m"]
            variables = ["matlab/types/*.m"]
            addpath = ["matlab/lib"]
            variable_dir = "matlab/types"
        """))

        # Create the referenced files.
        (tmp_path / "matlab").mkdir()
        (tmp_path / "matlab" / "lib").mkdir()
        (tmp_path / "matlab" / "types").mkdir()

        (tmp_path / "matlab" / "bandpass_filter.m").write_text(
            "function y = bandpass_filter(x)\ny = x;\nend\n"
        )
        (tmp_path / "matlab" / "types" / "RawSignal.m").write_text(
            "classdef RawSignal < scidb.BaseVariable\nend\n"
        )

        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        config = load_config(tmp_path, db_path)
        assert len(config.matlab_functions) == 1
        assert config.matlab_functions[0].name == "bandpass_filter.m"
        assert len(config.matlab_variables) == 1
        assert config.matlab_variables[0].name == "RawSignal.m"
        assert len(config.matlab_addpath) == 1
        assert config.matlab_variable_dir == (tmp_path / "matlab" / "types").resolve()

    def test_scistack_toml(self, tmp_path):
        from scistack_gui.config import load_config

        # Create a scistack.toml (standalone, no pyproject.toml).
        (tmp_path / "scistack.toml").write_text(textwrap.dedent("""\
            modules = []

            [matlab]
            functions = ["process.m"]
        """))

        (tmp_path / "process.m").write_text(
            "function y = process(x)\ny = x;\nend\n"
        )

        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        config = load_config(tmp_path, db_path)
        assert len(config.matlab_functions) == 1

    def test_no_matlab_section(self, tmp_path):
        from scistack_gui.config import load_config

        (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""\
            [tool.scistack]
            modules = []
        """))

        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        config = load_config(tmp_path, db_path)
        assert config.matlab_functions == []
        assert config.matlab_variables == []
        assert config.matlab_addpath == []
        assert config.matlab_variable_dir is None
