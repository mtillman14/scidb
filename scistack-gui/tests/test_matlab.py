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
        f.write_text(
            textwrap.dedent("""\
            function [filtered] = bandpass_filter(signal, low_hz, high_hz)
            % BANDPASS_FILTER  Apply a bandpass filter.
                filtered = signal * low_hz;
            end
        """)
        )

        info = parse_matlab_function(f)
        assert info is not None
        assert info.name == "bandpass_filter"
        assert info.params == ["signal", "low_hz", "high_hz"]
        assert info.language == "matlab"
        assert len(info.source_hash) == 64  # SHA-256 hex
        assert info.n_outputs == 1  # [filtered]

    def test_single_output(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "compute_vo2.m"
        f.write_text("function result = compute_vo2(breath_data)\n  result = 0;\nend\n")

        info = parse_matlab_function(f)
        assert info is not None
        assert info.name == "compute_vo2"
        assert info.params == ["breath_data"]
        assert info.n_outputs == 1

    def test_no_output(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "plot_results.m"
        f.write_text("function plot_results(data, title_str)\n  plot(data);\nend\n")

        info = parse_matlab_function(f)
        assert info is not None
        assert info.name == "plot_results"
        assert info.params == ["data", "title_str"]
        assert info.n_outputs == 0

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
        assert info.n_outputs == 3  # [amp, phase, freq]

    def test_source_hash_changes(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "foo.m"
        f.write_text("function y = foo(x)\n  y = x;\nend\n")
        info1 = parse_matlab_function(f)

        f.write_text("function y = foo(x)\n  y = x * 2;\nend\n")
        info2 = parse_matlab_function(f)

        assert info1.source_hash != info2.source_hash

    def test_method_inside_non_basevariable_classdef_not_registered(self, tmp_path):
        """A `function` inside a methods block of a non-BaseVariable classdef
        (e.g. a matlab.unittest.TestCase's setup helper) must not be
        extracted as a standalone pipeline function — regression test for
        the 'shadows previous definition' bug where every unittest test
        class's identically-named setup method (e.g. resetSchema/addPaths)
        overwrote the last one registered."""
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "TestSomething.m"
        f.write_text(
            textwrap.dedent("""\
            classdef TestSomething < matlab.unittest.TestCase
                methods (TestMethodSetup)
                    function resetSchema(~)
                        scifor.set_schema(string.empty(1, 0));
                    end
                end
            end
        """)
        )

        info = parse_matlab_function(f)
        assert info is None

    def test_method_inside_basevariable_classdef_not_registered(self, tmp_path):
        """Same rule applies to a BaseVariable classdef's own methods (e.g.
        a constructor) -- parse_matlab_function must defer to
        parse_matlab_variable/classify_matlab_file for these, not extract
        the constructor as a standalone function."""
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "RawSignal.m"
        f.write_text(
            textwrap.dedent("""\
            classdef RawSignal < scidb.BaseVariable
                methods
                    function obj = RawSignal()
                    end
                end
            end
        """)
        )

        info = parse_matlab_function(f)
        assert info is None


class TestExtractDocstring:
    """Docstring extraction: the contiguous %-comment block immediately
    following the function declaration (MATLAB's own help/H1 convention).
    """

    def test_single_line(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "bandpass_filter.m"
        f.write_text(
            textwrap.dedent("""\
            function [filtered] = bandpass_filter(signal, low_hz, high_hz)
            % BANDPASS_FILTER  Apply a bandpass filter.
                filtered = signal * low_hz;
            end
        """)
        )

        info = parse_matlab_function(f)
        assert info.docstring == "BANDPASS_FILTER  Apply a bandpass filter."

    def test_multi_line(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "compute_vo2.m"
        f.write_text(
            textwrap.dedent("""\
            function result = compute_vo2(breath_data)
            %COMPUTE_VO2 Estimate VO2 from breath-by-breath data.
            %   result = COMPUTE_VO2(breath_data) returns the estimated VO2.
            %
            %   See also COMPUTE_VCO2.
              result = 0;
            end
        """)
        )

        info = parse_matlab_function(f)
        assert info.docstring == (
            "COMPUTE_VO2 Estimate VO2 from breath-by-breath data.\n"
            "  result = COMPUTE_VO2(breath_data) returns the estimated VO2.\n"
            "\n"
            "  See also COMPUTE_VCO2."
        )

    def test_none_when_blank_line_follows(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "setup.m"
        f.write_text("function setup()\n\n  disp('hi');\nend\n")

        info = parse_matlab_function(f)
        assert info.docstring is None

    def test_none_when_code_follows_immediately(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "plot_results.m"
        f.write_text("function plot_results(data)\n  plot(data);\nend\n")

        info = parse_matlab_function(f)
        assert info.docstring is None

    def test_stops_at_first_non_comment_line(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "decompose.m"
        f.write_text(
            textwrap.dedent("""\
            function [amp, phase] = decompose(signal)
            % DECOMPOSE  Split a signal into amplitude and phase.
            amp = abs(signal);
            % this trailing comment is not part of the docstring
            phase = angle(signal);
            end
        """)
        )

        info = parse_matlab_function(f)
        assert info.docstring == "DECOMPOSE  Split a signal into amplitude and phase."


class TestParseMatlabVariable:
    def test_basic_classdef(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_variable

        f = tmp_path / "RawSignal.m"
        f.write_text(
            textwrap.dedent("""\
            classdef RawSignal < scidb.BaseVariable
                % Raw EMG signal data
            end
        """)
        )

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


class TestBlockCommentStripping:
    """A %{ %} block comment must not false-positive as a real
    function/classdef declaration — a common way scientists leave
    "here's how to call this" example code in their scripts."""

    def test_function_example_inside_block_comment_ignored(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "real_fn.m"
        f.write_text(
            textwrap.dedent("""\
            %{
            Example usage:
            function y = fake_example(x)
                y = x * 2;
            end
            %}
            function y = real_fn(x)
                y = x;
            end
        """)
        )

        info = parse_matlab_function(f)
        assert info is not None
        assert info.name == "real_fn"

    def test_classdef_example_inside_block_comment_ignored(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_variable

        f = tmp_path / "RealVar.m"
        f.write_text(
            textwrap.dedent("""\
            %{
            classdef FakeVar < scidb.BaseVariable
            end
            %}
            classdef RealVar < scidb.BaseVariable
            end
        """)
        )

        name = parse_matlab_variable(f)
        assert name == "RealVar"

    def test_entirely_commented_out_function_not_registered(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "commented.m"
        f.write_text(
            textwrap.dedent("""\
            %{
            function y = commented(x)
                y = x;
            end
            %}
        """)
        )

        info = parse_matlab_function(f)
        assert info is None


class TestLineContinuation:
    """A `...`-continued multi-line function signature must not leak the
    continuation marker or the next line's leading whitespace into a
    captured parameter name."""

    def test_multiline_signature_params_are_clean(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "many_args.m"
        f.write_text(
            "function y = many_args(alpha, beta, ...\n"
            "    gamma, delta)\n"
            "y = alpha;\n"
            "end\n"
        )

        info = parse_matlab_function(f)
        assert info is not None
        assert info.name == "many_args"
        assert info.params == ["alpha", "beta", "gamma", "delta"]
        assert not any("..." in p for p in info.params)
        assert not any("\n" in p for p in info.params)

    def test_multiline_signature_with_trailing_comment(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_function

        f = tmp_path / "commented_continuation.m"
        f.write_text(
            "function y = commented_continuation(a, ... this is a note\n"
            "    b)\n"
            "y = a;\n"
            "end\n"
        )

        info = parse_matlab_function(f)
        assert info is not None
        assert info.params == ["a", "b"]

    def test_source_hash_unaffected_by_preprocessing(self, tmp_path):
        """The source_hash must still be over the raw, unmodified file
        bytes — preprocessing is only applied to the text used for
        regex matching, never to what gets hashed."""
        from hashlib import sha256

        from scistack_gui.matlab_parser import parse_matlab_function

        raw = b"function y = foo(a, ...\n    b)\ny=a;\nend\n"
        f = tmp_path / "foo.m"
        f.write_bytes(raw)

        info = parse_matlab_function(f)
        assert info.source_hash == sha256(raw).hexdigest()


class TestPreprocessingIsLengthPreserving:
    """``_preprocess_for_parsing`` masks block comments and line
    continuations with spaces rather than deleting them, so an offset into
    the parsed text is also a valid offset into the original file. Without
    this, a span computed during parsing would land at the wrong place on
    write-back and corrupt the file (plan Stage 2)."""

    @pytest.mark.parametrize(
        "text",
        [
            "function y = f(a)\ny = a;\nend\n",
            "%{\nblock comment\n%}\nfunction y = f(a)\ny = a;\nend\n",
            "function y = f(a, ...\n    b)\ny = a;\nend\n",
            "%{\nblock\n%}\nfunction y = f(a, ... note\n    b)\ny = a;\nend\n",
            "%{\n%}\n",
            "",
        ],
    )
    def test_length_is_preserved(self, text):
        from scistack_gui.matlab_parser import _preprocess_for_parsing

        assert len(_preprocess_for_parsing(text)) == len(text)

    def test_block_comment_keeps_line_count(self):
        """Block comments become blank lines, so line numbers reported to
        the user still match the real file."""
        from scistack_gui.matlab_parser import _preprocess_for_parsing

        text = "%{\na\nb\n%}\nfunction y = f()\n"
        out = _preprocess_for_parsing(text)
        assert out.count("\n") == text.count("\n")
        assert "block" not in out
        assert out.index("function") == text.index("function")

    def test_masked_regions_carry_no_keywords(self):
        from scistack_gui.matlab_parser import _preprocess_for_parsing

        text = "%{\nfunction y = fake(x)\nclassdef Fake < scidb.BaseVariable\n%}\n"
        out = _preprocess_for_parsing(text)
        assert "function" not in out
        assert "classdef" not in out


class TestParseMatlabEntitiesScript:
    """The MATLAB entities script — a plain .m of top-level bindings, the
    analogue of src/scistack_entities.py (plan D1)."""

    def _write(self, tmp_path, body):
        f = tmp_path / "scistack_entities.m"
        f.write_text(textwrap.dedent(body))
        return f

    def test_parses_each_kind(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_entities_script

        f = self._write(
            tmp_path,
            """\
            raw_emg = scidb.PathInput('{subject}/{trial}.mat');
            window = scidb.Parameter(10, 20, 30);
            thresh = scidb.Parameter(2);
            """,
        )

        bindings = {b.name: b for b in parse_matlab_entities_script(f)}
        assert set(bindings) == {"raw_emg", "window", "thresh"}
        assert bindings["raw_emg"].kind == "path_input"
        assert bindings["window"].kind == "parameter"
        assert bindings["thresh"].kind == "parameter"

    def test_spans_locate_expression_and_arguments(self, tmp_path):
        from scistack_gui.matlab_parser import (
            parse_matlab_entities_script,
            read_source_text,
        )

        f = self._write(tmp_path, "window = scidb.Parameter(10, 20);\n")
        text = read_source_text(f)
        b = parse_matlab_entities_script(f)[0]

        assert b.expr_span.extract(text) == "scidb.Parameter(10, 20)"
        assert b.args_span.extract(text) == "10, 20"

    def test_expression_span_enables_a_form_change(self, tmp_path):
        """The RHS span covers the constructor too, so Constant -> Sweep is
        the same splice as a value edit (D4)."""
        from scidb.source_edit import splice

        from scistack_gui.matlab_parser import (
            parse_matlab_entities_script,
            read_source_text,
        )

        f = self._write(tmp_path, "thresh = scidb.Parameter(2);\nx = 1;\n")
        text = read_source_text(f)
        b = parse_matlab_entities_script(f)[0]

        assert (
            splice(text, b.expr_span, "scidb.Parameter(2, 5)")
            == "thresh = scidb.Parameter(2, 5);\nx = 1;\n"
        )

    def test_scifor_namespace_accepted(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_entities_script

        f = self._write(tmp_path, "window = scidb.Parameter(1);\n")
        assert parse_matlab_entities_script(f)[0].kind == "parameter"

    def test_bare_constructor_accepted(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_entities_script

        f = self._write(tmp_path, "window = Parameter(1);\n")
        assert parse_matlab_entities_script(f)[0].kind == "parameter"

    def test_non_entity_lines_are_skipped(self, tmp_path):
        """An entities script may contain ordinary MATLAB."""
        from scistack_gui.matlab_parser import parse_matlab_entities_script

        f = self._write(
            tmp_path,
            """\
            n = 5;
            label = 'hello';
            window = scidb.Parameter(1);
            """,
        )
        assert [b.name for b in parse_matlab_entities_script(f)] == ["window"]

    def test_comparison_is_not_a_binding(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_entities_script

        f = self._write(tmp_path, "if a == scidb.Parameter(1)\nend\n")
        assert parse_matlab_entities_script(f) == []

    def test_paren_inside_a_template_does_not_break_the_span(self, tmp_path):
        from scistack_gui.matlab_parser import (
            parse_matlab_entities_script,
            read_source_text,
        )

        f = self._write(tmp_path, "p = scidb.PathInput('{s}/a(1).mat');\n")
        text = read_source_text(f)
        b = parse_matlab_entities_script(f)[0]
        assert b.args_span.extract(text) == "'{s}/a(1).mat'"

    def test_semicolon_is_optional(self, tmp_path):
        from scistack_gui.matlab_parser import (
            parse_matlab_entities_script,
            read_source_text,
        )

        f = self._write(tmp_path, "window = scidb.Parameter(1)\nother = 2\n")
        text = read_source_text(f)
        b = parse_matlab_entities_script(f)[0]
        assert b.expr_span.extract(text) == "scidb.Parameter(1)"

    def test_continued_argument_list(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_entities_script

        f = self._write(tmp_path, "window = scidb.Parameter(1, ...\n    2);\n")
        b = parse_matlab_entities_script(f)[0]
        assert b.kind == "parameter"

    def test_constant_literal_extracted(self, tmp_path):
        from scistack_gui.matlab_parser import (
            binding_parameter_literal,
            parse_matlab_entities_script,
            read_source_text,
        )

        f = self._write(
            tmp_path, "w = scidb.Parameter(30, description='Analysis window');\n"
        )
        text = read_source_text(f)
        b = parse_matlab_entities_script(f)[0]
        assert binding_parameter_literal(b, text) == ([30], "Analysis window")

    def test_literals_extracted(self, tmp_path):
        from scistack_gui.matlab_parser import (
            binding_path_input_literal,
            binding_parameter_literal,
            parse_matlab_entities_script,
            read_source_text,
        )

        f = self._write(
            tmp_path,
            """\
            raw = scidb.PathInput('{s}/a.mat', root_folder='/data');
            window = scidb.Parameter(10, 20.5, 'x');
            """,
        )
        text = read_source_text(f)
        bindings = {b.name: b for b in parse_matlab_entities_script(f)}

        assert binding_path_input_literal(bindings["raw"], text) == (
            "{s}/a.mat",
            "/data",
        )
        assert binding_parameter_literal(bindings["window"], text) == ([10, 20.5, "x"], "")

    def test_root_folder_accepted_in_both_matlab_syntaxes(self, tmp_path):
        """+scifor/PathInput.m's `arguments` block accepts name=value
        (R2021b+) and name-value pairs alike, so extraction must too."""
        from scistack_gui.matlab_parser import (
            binding_path_input_literal,
            parse_matlab_entities_script,
            read_source_text,
        )

        f = self._write(
            tmp_path,
            """\
            a = scidb.PathInput('x.mat', root_folder='/data');
            b = scidb.PathInput('x.mat', 'root_folder', '/data');
            """,
        )
        text = read_source_text(f)
        bindings = {b.name: b for b in parse_matlab_entities_script(f)}

        assert binding_path_input_literal(bindings["a"], text) == ("x.mat", "/data")
        assert binding_path_input_literal(bindings["b"], text) == ("x.mat", "/data")

    def test_equals_inside_a_template_is_not_a_named_argument(self, tmp_path):
        from scistack_gui.matlab_parser import (
            binding_path_input_literal,
            parse_matlab_entities_script,
            read_source_text,
        )

        f = self._write(tmp_path, "a = scidb.PathInput('{s}/a=b.mat');\n")
        text = read_source_text(f)
        b = parse_matlab_entities_script(f)[0]
        assert binding_path_input_literal(b, text) == ("{s}/a=b.mat", None)

    def test_non_literal_value_invalidates_extraction(self, tmp_path):
        from scistack_gui.matlab_parser import (
            binding_parameter_literal,
            parse_matlab_entities_script,
            read_source_text,
        )

        f = self._write(tmp_path, "window = scidb.Parameter(1, some_var);\n")
        text = read_source_text(f)
        b = parse_matlab_entities_script(f)[0]
        assert binding_parameter_literal(b, text) is None

    def test_missing_file_returns_empty(self, tmp_path):
        from scistack_gui.matlab_parser import parse_matlab_entities_script

        assert parse_matlab_entities_script(tmp_path / "nope.m") == []

    def test_is_entities_script_rejects_functions_and_classdefs(self, tmp_path):
        from scistack_gui.matlab_parser import is_matlab_entities_script

        script = self._write(tmp_path, "window = scidb.Parameter(1);\n")
        assert is_matlab_entities_script(script)

        fn = tmp_path / "window_fn.m"
        fn.write_text("function s = window_fn()\ns = scidb.Parameter(1);\nend\n")
        assert not is_matlab_entities_script(fn)

        cls = tmp_path / "RawSignal.m"
        cls.write_text("classdef RawSignal < scidb.BaseVariable\nend\n")
        assert not is_matlab_entities_script(cls)

        plain = tmp_path / "plain.m"
        plain.write_text("x = 1;\n")
        assert not is_matlab_entities_script(plain)

    def test_classify_returns_entities_script(self, tmp_path):
        from scistack_gui.matlab_parser import classify_matlab_file

        f = self._write(tmp_path, "window = scidb.Parameter(1);\n")
        kind, _ = classify_matlab_file(f)
        assert kind == "entities_script"

    def test_classify_still_prefers_function_over_entities_script(self, tmp_path):
        """Regression guard: the entities check runs last, so it can never
        steal a file from an existing category. A function that happens to
        construct a Sweep is just a function — the value-getter convention
        no longer exists."""
        from scistack_gui.matlab_parser import classify_matlab_file

        f = tmp_path / "window.m"
        f.write_text("function s = window()\ns = scidb.Parameter(1);\nend\n")
        kind, payload = classify_matlab_file(f)
        assert kind == "function"
        assert payload.name == "window"


class TestLoadEntitiesScript:
    """Entities declared in a script must register into the SAME shared
    registry the getter path uses, so nothing downstream can tell which
    form declared them."""

    def test_registers_path_input_and_sweep(self, tmp_path):
        from scistack_gui import matlab_registry, registry

        f = tmp_path / "scistack_entities.m"
        f.write_text(
            "raw = scidb.PathInput('{s}/a.mat');\nwindow = scidb.Parameter(1, 2);\n"
        )

        matlab_registry.load_entities_script(f)

        pi = registry.get_path_inputs_registry()["raw"]
        assert pi.path_template == "{s}/a.mat"
        sw = registry.get_parameters_registry()["window"]
        assert list(sw.alternatives) == [1, 2]

    def test_registered_sweep_is_a_real_eachof(self, tmp_path):
        from scifor import EachOf

        from scistack_gui import matlab_registry, registry

        f = tmp_path / "scistack_entities.m"
        f.write_text("window = scidb.Parameter(1, 2);\n")
        matlab_registry.load_entities_script(f)

        assert isinstance(registry.get_parameters_registry()["window"], EachOf)

    def test_last_binding_of_a_name_wins(self, tmp_path):
        from scistack_gui import matlab_registry, registry

        f = tmp_path / "scistack_entities.m"
        f.write_text("window = scidb.Parameter(1);\nwindow = scidb.Parameter(9);\n")
        matlab_registry.load_entities_script(f)

        assert list(registry.get_parameters_registry()["window"].alternatives) == [9]

    def test_registers_constant_with_source_declared_identity(self, tmp_path):
        """Before +scidb/Constant.m, a MATLAB constant was an anonymous value
        in a for_each struct with no discoverable name (the old "MATLAB has
        no equivalent" note in code-discovery-categories.md §3)."""
        from scistack_gui import matlab_registry, registry

        f = tmp_path / "scistack_entities.m"
        f.write_text(
            "window = scidb.Parameter(30, description='Analysis window');\n"
        )

        matlab_registry.load_entities_script(f)

        const = registry.get_parameters_registry()["window"]
        assert const.value == 30
        assert const.description == "Analysis window"
        assert "window" in matlab_registry.get_all_parameter_names()

    def test_constant_registers_as_a_real_scidb_constant(self, tmp_path):
        """It must be the same type Python discovery produces, so
        build_parameter_nodes and every other consumer stay language-agnostic."""
        from scidb import Parameter

        from scistack_gui import matlab_registry, registry

        f = tmp_path / "scistack_entities.m"
        f.write_text("window = scidb.Parameter(30);\n")
        matlab_registry.load_entities_script(f)

        assert isinstance(registry.get_parameters_registry()["window"], Parameter)

    def test_constant_description_optional_and_both_syntaxes(self, tmp_path):
        from scistack_gui import matlab_registry, registry

        f = tmp_path / "scistack_entities.m"
        f.write_text(
            "a = scidb.Parameter(1);\n"
            "b = scidb.Parameter(2, description='named');\n"
            "c = scidb.Parameter(3, 'description', 'paired');\n"
        )
        matlab_registry.load_entities_script(f)

        consts = registry.get_parameters_registry()
        assert consts["a"].value == 1 and consts["a"].description == ""
        assert consts["b"].description == "named"
        assert consts["c"].description == "paired"

    def test_constant_string_value(self, tmp_path):
        from scistack_gui import matlab_registry, registry

        f = tmp_path / "scistack_entities.m"
        f.write_text("label = scidb.Parameter('baseline');\n")
        matlab_registry.load_entities_script(f)

        assert registry.get_parameters_registry()["label"].value == "baseline"

    def test_non_literal_constant_stays_unregistered(self, tmp_path):
        from scistack_gui import matlab_registry, registry

        f = tmp_path / "scistack_entities.m"
        f.write_text("window = scidb.Parameter(some_var);\n")
        registry._parameters.pop("window", None)
        matlab_registry.load_entities_script(f)

        assert "window" not in registry.get_parameters_registry()
        assert any(
            "window" in e.get("error", "") for e in matlab_registry.get_load_errors()
        )

    def test_missing_file_is_not_an_error(self, tmp_path):
        from scistack_gui import matlab_registry

        matlab_registry.load_entities_script(tmp_path / "nope.m")
        assert not any(
            "nope.m" in e.get("source", "") for e in matlab_registry.get_load_errors()
        )

    def test_non_literal_declaration_records_a_load_error(self, tmp_path):
        from scistack_gui import matlab_registry

        f = tmp_path / "scistack_entities.m"
        f.write_text("window = scidb.Parameter(some_var);\n")
        matlab_registry.load_entities_script(f)

        assert any(
            "window" in e.get("error", "") for e in matlab_registry.get_load_errors()
        )


class TestClassifyMatlabFile:
    def test_classifies_function(self, tmp_path):
        from scistack_gui.matlab_parser import classify_matlab_file

        f = tmp_path / "foo.m"
        f.write_text("function y = foo(x)\ny=x;\nend\n")

        kind, payload = classify_matlab_file(f)
        assert kind == "function"
        assert payload.name == "foo"

    def test_classifies_variable(self, tmp_path):
        from scistack_gui.matlab_parser import classify_matlab_file

        f = tmp_path / "RawSignal.m"
        f.write_text("classdef RawSignal < scidb.BaseVariable\nend\n")

        kind, payload = classify_matlab_file(f)
        assert kind == "variable"
        assert payload == "RawSignal"

    def test_classdef_with_method_is_variable_not_function(self, tmp_path):
        """A BaseVariable classdef containing a method (which itself has a
        `function` declaration) must be classified as a variable, not a
        function — classdef parsing is tried first specifically for this
        reason."""
        from scistack_gui.matlab_parser import classify_matlab_file

        f = tmp_path / "RawSignal.m"
        f.write_text(
            textwrap.dedent("""\
            classdef RawSignal < scidb.BaseVariable
                methods
                    function obj = RawSignal()
                    end
                end
            end
        """)
        )

        kind, payload = classify_matlab_file(f)
        assert kind == "variable"
        assert payload == "RawSignal"

    def test_neither_returns_none(self, tmp_path):
        from scistack_gui.matlab_parser import classify_matlab_file

        f = tmp_path / "script.m"
        f.write_text("% just a script\nx = 5;\n")

        assert classify_matlab_file(f) is None


class TestMatlabRegistryLoadFromSources:
    def test_mixed_sources_classified_and_registered(self, tmp_path):
        from scistack_gui import matlab_registry

        fn_file = tmp_path / "foo.m"
        fn_file.write_text("function y = foo(x)\ny=x;\nend\n")
        var_file = tmp_path / "RawSignal.m"
        var_file.write_text("classdef RawSignal < scidb.BaseVariable\nend\n")

        matlab_registry._matlab_functions.clear()
        matlab_registry._matlab_variables.clear()
        matlab_registry.load_from_sources([fn_file, var_file])

        assert matlab_registry.is_matlab_function("foo")
        assert "RawSignal" in matlab_registry.get_all_variable_names()

    def test_refresh_deregisters_stale_entry_from_shared_registry(self, tmp_path):
        """Removing a PathInput declaration and refreshing must not leave
        its OLD registered object lingering forever in
        scistack_gui.registry -- matlab_registry.clear() only ever touched
        its own dicts before this fix."""
        from scistack_gui import config, matlab_registry, registry

        entities = tmp_path / "scistack_entities.m"
        entities.write_text("raw_emg = scidb.PathInput('{subject}.mat');\n")
        cfg = config.SciStackConfig(
            project_root=tmp_path, matlab_entities_file=entities
        )

        registry._path_inputs.clear()
        matlab_registry.load_from_config(cfg)
        assert registry.get_path_input("raw_emg") is not None

        # The declaration is deleted from the entities script -- simulate by
        # loading an EMPTY config.
        empty_cfg = config.SciStackConfig(project_root=tmp_path)
        matlab_registry.load_from_config(empty_cfg)

        assert registry.get_path_input("raw_emg") is None

    def test_unclassifiable_file_skipped_without_warning(self, tmp_path, caplog):
        """A folder-scanned .m file that classifies as neither a function
        nor a variable (e.g. an ordinary script) is expected, not a
        misconfiguration — most real MATLAB projects have plenty of these.
        load_from_sources logs it at DEBUG (not WARNING) and does NOT
        record it as a load error; only files explicitly listed in
        matlab.functions/matlab.variables that fail to parse are load
        errors (see load_from_config)."""
        import logging

        from scistack_gui import matlab_registry

        script_file = tmp_path / "script.m"
        script_file.write_text("% just a script\n")

        matlab_registry._matlab_functions.clear()
        matlab_registry._matlab_variables.clear()
        matlab_registry._load_errors.clear()
        with caplog.at_level(logging.DEBUG):
            matlab_registry.load_from_sources([script_file])

        assert matlab_registry.get_all_function_names() == []
        assert "Skipping non-function/non-variable" in caplog.text
        assert "Could not classify" not in caplog.text
        assert matlab_registry.get_load_errors() == []

    def test_same_named_setup_methods_across_test_classes_do_not_shadow(
        self, tmp_path, caplog
    ):
        """Regression test for the 'shadows previous definition' warning
        seen scanning a real MATLAB unittest suite: many test classes each
        define their own local setup method under the same name (e.g.
        resetSchema/addPaths). Folder-scan discovery must not register
        these as standalone functions at all -- so two files reusing the
        same setup-method name must NOT collide in the registry."""
        import logging

        from scistack_gui import matlab_registry

        test_a = tmp_path / "TestA.m"
        test_a.write_text(
            textwrap.dedent("""\
            classdef TestA < matlab.unittest.TestCase
                methods (TestMethodSetup)
                    function resetSchema(~)
                        scifor.set_schema(string.empty(1, 0));
                    end
                end
            end
        """)
        )
        test_b = tmp_path / "TestB.m"
        test_b.write_text(
            textwrap.dedent("""\
            classdef TestB < matlab.unittest.TestCase
                methods (TestMethodSetup)
                    function resetSchema(~)
                        scifor.set_schema(string.empty(1, 0));
                    end
                end
            end
        """)
        )

        matlab_registry._matlab_functions.clear()
        matlab_registry._matlab_variables.clear()
        matlab_registry._load_errors.clear()
        with caplog.at_level(logging.DEBUG):
            matlab_registry.load_from_sources([test_a, test_b])

        assert "resetSchema" not in matlab_registry.get_all_function_names()
        assert "shadows previous definition" not in caplog.text


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

        assert "scidb.register_variable(FilteredSignal())" in cmd
        assert "scidb.register_variable(RawSignal())" in cmd
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

    def test_pyenv_preamble_present(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="f",
            db_path="/db.duckdb",
            schema_keys=["s"],
            python_executable="/usr/bin/python3",
        )

        # Stage 1: bind
        assert "pyenv('Version', scistack_pyenv_target__)" in cmd
        assert "scistack_pyenv_target__ = '/usr/bin/python3';" in cmd
        assert 'if scistack_pyenv__.Status == "NotLoaded"' in cmd
        assert "SciStack:PyenvMismatch" in cmd
        # Stage 2: force-load (smoke test)
        assert "py.sys.version" in cmd
        # Stage 3: diagnostic dump on smoke-test failure
        assert "OutOfProcess" in cmd
        # Stage 4: pre-import scidb so py.scidb.* is warm
        assert "py.importlib.import_module('scidb')" in cmd
        # Teardown: clear all temporaries
        assert "clear scistack_pyenv__ scistack_pyenv_target__" in cmd
        # clear functions is NOT emitted — it breaks py.list inside package
        # functions (MATLAB resolves py.X as a module lookup post-cache-clear,
        # which fails for builtins like list).
        assert "clear functions" not in cmd

    def test_pyenv_preamble_omitted_when_none(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="f",
            db_path="/db.duckdb",
            schema_keys=["s"],
            python_executable=None,
        )

        assert "pyenv" not in cmd

    def test_pyenv_preamble_escapes_single_quotes(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="f",
            db_path="/db.duckdb",
            schema_keys=["s"],
            python_executable="/tmp/O'Neil/python",
        )

        # Single quote in path must be doubled inside the MATLAB literal.
        assert "scistack_pyenv_target__ = '/tmp/O''Neil/python';" in cmd

    def test_pyenv_preamble_windows_path(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="f",
            db_path="/db.duckdb",
            schema_keys=["s"],
            python_executable=r"C:\Users\mtillman\venvs\stim-device-comparison\Scripts\python.exe",
        )

        # Backslashes converted to forward slashes for the MATLAB literal.
        assert (
            "scistack_pyenv_target__ = "
            "'C:/Users/mtillman/venvs/stim-device-comparison/Scripts/python.exe';"
        ) in cmd
        assert "\\" not in cmd.split("scistack_pyenv_target__ =")[1].splitlines()[0]

    def test_pyenv_preamble_mismatch_uses_normalized_compare(self):
        """The mismatch check must tolerate backslash/forward-slash differences
        between what MATLAB's pyenv returns and our target literal.
        Regression: previously ``string(Executable) ~= string(target)`` fired
        erroneously when Status=Loaded and the paths differed only in separators.
        """
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="f",
            db_path="/db.duckdb",
            schema_keys=["s"],
            python_executable=r"C:\Users\mtillman\venvs\scistack-gui\.venv\Scripts\python.exe",
        )

        # The comparison MUST use a path normalizer (strrep + strcmpi), not a
        # raw string equality.
        assert "scistack_norm_path__" in cmd
        # MATLAB literal: strrep(char(p), '\', '/')  (single backslash in MATLAB).
        assert "strrep(char(p), '\\', '/')" in cmd
        assert "strcmpi(" in cmd
        # And the raw mismatching pattern must NOT be present.
        assert (
            "string(scistack_pyenv__.Executable) ~= string(scistack_pyenv_target__)"
            not in cmd
        )

    def test_pyenv_preamble_ordered_before_addpath(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="f",
            db_path="/db.duckdb",
            schema_keys=["s"],
            addpath_dirs=["/home/user/matlab/lib"],
            python_executable="/usr/bin/python3",
        )

        pyenv_idx = cmd.index("scistack_pyenv_target__")
        addpath_idx = cmd.index("addpath(")
        assert pyenv_idx < addpath_idx


# ---------------------------------------------------------------------------
# _format_path_input tests
# ---------------------------------------------------------------------------


class TestFormatPathInput:
    def test_explicit_root_folder_used_as_is(self):
        from scistack_gui.api.matlab_command import _format_path_input

        pi = {"template": "{subject}/data.mat", "root_folder": "/my/data"}
        result = _format_path_input(pi)
        assert (
            result == 'scifor.PathInput("{subject}/data.mat", root_folder="/my/data")'
        )

    def test_no_root_folder_no_project_root(self):
        from scistack_gui.api.matlab_command import _format_path_input

        pi = {"template": "{subject}/data.mat", "root_folder": None}
        result = _format_path_input(pi)
        assert result == 'scifor.PathInput("{subject}/data.mat")'

    def test_relative_template_uses_project_root_when_no_root_folder(self):
        from scistack_gui.api.matlab_command import _format_path_input

        pi = {"template": "{subject}/data.mat", "root_folder": None}
        result = _format_path_input(pi, project_root="/projects/myexp")
        assert (
            result
            == 'scifor.PathInput("{subject}/data.mat", root_folder="/projects/myexp")'
        )

    def test_explicit_root_folder_takes_priority_over_project_root(self):
        from scistack_gui.api.matlab_command import _format_path_input

        pi = {"template": "{subject}/data.mat", "root_folder": "/explicit/root"}
        result = _format_path_input(pi, project_root="/projects/myexp")
        assert (
            result
            == 'scifor.PathInput("{subject}/data.mat", root_folder="/explicit/root")'
        )

    def test_absolute_template_ignores_project_root(self):
        from scistack_gui.api.matlab_command import _format_path_input

        pi = {"template": "/absolute/path/{subject}.mat", "root_folder": None}
        result = _format_path_input(pi, project_root="/projects/myexp")
        assert result == 'scifor.PathInput("/absolute/path/{subject}.mat")'

    def test_generate_matlab_command_injects_project_root_for_path_inputs(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="load_file",
            db_path="/data/exp.duckdb",
            schema_keys=["subject"],
            path_inputs={
                "filepath": {"template": "{subject}/data.mat", "root_folder": None}
            },
            project_root="/projects/myexp",
        )
        assert 'root_folder="/projects/myexp"' in cmd

    def test_generate_matlab_command_injects_sweep_as_scifor_sweep(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="bandpass_filter",
            db_path="/data/exp.duckdb",
            schema_keys=["subject"],
            sweeps={"low_hz": [10, 20, 30]},
        )
        assert "scidb.Parameter(10, 20, 30)" in cmd

    def test_generate_matlab_command_sweep_and_path_input_together(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="bandpass_filter",
            db_path="/data/exp.duckdb",
            schema_keys=["subject"],
            path_inputs={
                "filepath": {"template": "{subject}/data.mat", "root_folder": None}
            },
            sweeps={"low_hz": [10, 20]},
            project_root="/projects/myexp",
        )
        assert "scidb.Parameter(10, 20)" in cmd
        assert "scifor.PathInput" in cmd


# ---------------------------------------------------------------------------
# _format_sweep tests
# ---------------------------------------------------------------------------


class TestFormatSweep:
    def test_numeric_values(self):
        from scistack_gui.api.matlab_command import _format_sweep

        assert _format_sweep([10, 20, 30]) == "scidb.Parameter(10, 20, 30)"

    def test_string_values(self):
        from scistack_gui.api.matlab_command import _format_sweep

        assert _format_sweep(["low", "high"]) == "scidb.Parameter('low', 'high')"

    def test_single_value(self):
        from scistack_gui.api.matlab_command import _format_sweep

        assert _format_sweep([42]) == "scidb.Parameter(42)"


# ---------------------------------------------------------------------------
# config MATLAB parsing tests
# ---------------------------------------------------------------------------


class TestConfigMatlabParsing:
    def test_pyproject_with_matlab(self, tmp_path):
        from scistack_gui.config import load_config

        # Create a pyproject.toml with MATLAB section.
        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent("""\
            [tool.scistack]
            modules = []

            [tool.scistack.matlab]
            functions = ["matlab/bandpass_filter.m"]
            variables = ["matlab/types/*.m"]
            variable_dir = "matlab/types"
        """)
        )

        # Create the referenced files.
        (tmp_path / "matlab").mkdir()
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
        # addpath is auto-derived from parent dirs of functions, variables, and variable_dir
        assert len(config.matlab_addpath) == 2
        # Paths are stored in absolute-but-not-UNC-canonicalized form (see
        # config._normalize); compare against that form, not .resolve().
        addpath_set = set(config.matlab_addpath)
        assert (tmp_path / "matlab") in addpath_set
        assert (tmp_path / "matlab" / "types") in addpath_set
        assert config.matlab_variable_dir == (tmp_path / "matlab" / "types")

    def test_scistack_toml(self, tmp_path):
        from scistack_gui.config import load_config

        # Create a scistack.toml (standalone, no pyproject.toml).
        (tmp_path / "scistack.toml").write_text(
            textwrap.dedent("""\
            modules = []

            [matlab]
            functions = ["process.m"]
        """)
        )

        (tmp_path / "process.m").write_text("function y = process(x)\ny = x;\nend\n")

        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        config = load_config(tmp_path, db_path)
        assert len(config.matlab_functions) == 1

    def test_no_matlab_section(self, tmp_path):
        from scistack_gui.config import load_config

        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent("""\
            [tool.scistack]
            modules = []
        """)
        )

        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        config = load_config(tmp_path, db_path)
        assert config.matlab_functions == []
        assert config.matlab_variables == []
        assert config.matlab_addpath == []
        assert config.matlab_variable_dir is None
        assert config.matlab_entities_file is None

    def test_explicit_entities_file(self, tmp_path):
        from scistack_gui.config import load_config

        (tmp_path / "pyproject.toml").write_text(
            textwrap.dedent("""\
            [tool.scistack]
            modules = []

            [tool.scistack.matlab]
            functions = ["process.m"]
            entities_file = "scistack_entities.m"
        """)
        )
        (tmp_path / "process.m").write_text("function y = process(x)\ny = x;\nend\n")
        (tmp_path / "scistack_entities.m").write_text(
            "raw_emg = scidb.PathInput('{subject}.mat');\n"
        )

        db_path = tmp_path / "test.duckdb"
        db_path.touch()

        config = load_config(tmp_path, db_path)
        assert len(config.matlab_functions) == 1
        assert config.matlab_entities_file.name == "scistack_entities.m"
        # The entities script's directory joins addpath, so a generated
        # MATLAB command can `run` it.
        assert config.matlab_entities_file.parent in config.matlab_addpath


# ---------------------------------------------------------------------------
# scimatlab MATLAB directory discovery
# ---------------------------------------------------------------------------


class TestGenerateMatlabCommandOutputTypes:
    """Regression: MATLAB function output param names must not leak into the
    generated MATLAB command as BaseVariable class names.

    A function declared as ``function [time, force_left, force_right] = load_csv(f)``
    has output *parameter names* ``time`` / ``force_left`` / ``force_right``.  The
    actual BaseVariable class names are ``Time`` / ``Force_Left`` / ``Force_Right``
    (whatever is wired to the function node's output handles in the GUI).
    The generated MATLAB command must use the class names, not the param names.
    """

    def test_output_types_from_variants_use_class_names(self):
        """When DB variants exist, output_type (class name) must appear in
        the outputs cell array, not the function's output parameter names."""
        from scistack_gui.api.matlab_command import generate_matlab_command

        variants = [
            {
                "input_types": {},
                "output_type": "Time",
                "constants": {},
                "record_count": 1,
            },
            {
                "input_types": {},
                "output_type": "Force_Left",
                "constants": {},
                "record_count": 1,
            },
            {
                "input_types": {},
                "output_type": "Force_Right",
                "constants": {},
                "record_count": 1,
            },
        ]

        cmd = generate_matlab_command(
            function_name="load_csv",
            db_path="/data/exp.duckdb",
            schema_keys=["subject"],
            variants=variants,
        )

        assert "Time()" in cmd
        assert "Force_Left()" in cmd
        assert "Force_Right()" in cmd
        # Lowercase param names must NOT appear as class instantiations
        assert "time()" not in cmd
        assert "force_left()" not in cmd
        assert "force_right()" not in cmd

    def test_output_types_with_no_variants_uses_provided_output_types(self):
        """When no DB variants exist and output_types are provided, the class
        names should appear (not lowercase function param names)."""
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="load_csv",
            db_path="/data/exp.duckdb",
            schema_keys=["subject"],
            variants=None,
            output_types=["Time", "Force_Left", "Force_Right"],
        )

        assert "Time()" in cmd
        assert "Force_Left()" in cmd
        assert "Force_Right()" in cmd
        assert "time()" not in cmd
        assert "force_left()" not in cmd
        assert "force_right()" not in cmd


class TestSortInferredByParamsOrder:
    def test_reorders_to_match_params(self):
        from scistack_gui.services.matlab_command_service import (
            _sort_inferred_by_params_order,
        )

        inferred = ["Force_Right", "Force_Left", "Time"]
        params = ["time", "force_left", "force_right"]
        result = _sort_inferred_by_params_order(inferred, params)
        assert result == ["Time", "Force_Left", "Force_Right"]

    def test_passthrough_when_already_ordered(self):
        from scistack_gui.services.matlab_command_service import (
            _sort_inferred_by_params_order,
        )

        inferred = ["Time", "Force_Left", "Force_Right"]
        params = ["time", "force_left", "force_right"]
        result = _sort_inferred_by_params_order(inferred, params)
        assert result == ["Time", "Force_Left", "Force_Right"]

    def test_unmatched_appended_at_end(self):
        from scistack_gui.services.matlab_command_service import (
            _sort_inferred_by_params_order,
        )

        inferred = ["Extra", "Time", "Force_Left"]
        params = ["time", "force_left"]
        result = _sort_inferred_by_params_order(inferred, params)
        assert result == ["Time", "Force_Left", "Extra"]

    def test_empty_params_preserves_inferred_order(self):
        from scistack_gui.services.matlab_command_service import (
            _sort_inferred_by_params_order,
        )

        inferred = ["Force_Right", "Time"]
        result = _sort_inferred_by_params_order(inferred, [])
        assert result == ["Force_Right", "Time"]


class TestNormalizeInputTypes:
    """derive_target_for_node's never-run fallback (resolve_function_edges)
    returns each input param as a LIST of candidate types — even a single
    candidate is ["RawSignal"], not "RawSignal" — unlike real DB-history
    variants, which are already flat. generate_matlab_pipeline_command
    must flatten this before handing targets to api.matlab_command's
    generator, or a single-candidate list ends up nested inside a dict
    key's tuple and raises `TypeError: unhashable type: 'list'` in
    _group_variants (regression: found via a never-run MATLAB node in
    test_matlab_pipeline_execution.py)."""

    def test_flat_values_pass_through(self):
        from scistack_gui.services.matlab_command_service import (
            _normalize_input_types,
        )

        flat, unresolved = _normalize_input_types({"signal": "RawSignal"})
        assert flat == {"signal": "RawSignal"}
        assert unresolved == []

    def test_single_item_list_collapses_to_scalar(self):
        from scistack_gui.services.matlab_command_service import (
            _normalize_input_types,
        )

        flat, unresolved = _normalize_input_types({"signal": ["RawSignal"]})
        assert flat == {"signal": "RawSignal"}
        assert unresolved == []

    def test_multi_item_list_reported_unresolved(self):
        from scistack_gui.services.matlab_command_service import (
            _normalize_input_types,
        )

        flat, unresolved = _normalize_input_types(
            {"signal": ["RawSignal", "OtherSignal"]}
        )
        assert "signal" not in flat
        assert unresolved == ["signal"]

    def test_mixed_params(self):
        from scistack_gui.services.matlab_command_service import (
            _normalize_input_types,
        )

        flat, unresolved = _normalize_input_types(
            {"a": "Flat", "b": ["OneCandidate"], "c": ["X", "Y"]}
        )
        assert flat == {"a": "Flat", "b": "OneCandidate"}
        assert unresolved == ["c"]


class TestCollectSweepParams:
    """_collect_sweep_params mirrors PathInput's edge collection
    (matlab_command_service's "Source 2"), but a Parameter has no DB-history
    source at all — the registry + edges are the ONLY source.

    Both now route through the shared edge_resolver rather than hand-rolling
    the scan, so the MATLAB generators and the Python execution path agree on
    what a given canvas means."""

    def _edge(self, source, target, target_handle):
        return {"source": source, "target": target, "targetHandle": target_handle}

    def test_wires_parameter_to_the_param_its_handle_names(self):
        from scistack_gui.services.matlab_command_service import (
            _collect_sweep_params,
        )

        edges = [self._edge("param__low_hz", "fn__bandpass_filter", "in__low_hz")]
        result = _collect_sweep_params(
            "bandpass_filter", {"low_hz": [10, 20, 30]}, edges, {}
        )
        assert result == {"low_hz": [10, 20, 30]}

    def test_declared_name_may_differ_from_the_param(self):
        """Keyed by the PARAM the edge names, looked up by the DECLARED name
        — the distinction the old hand-rolled scan collapsed."""
        from scistack_gui.services.matlab_command_service import (
            _collect_sweep_params,
        )

        edges = [self._edge("param__test", "fn__bandpass_filter", "in__low_hz")]
        result = _collect_sweep_params(
            "bandpass_filter", {"test": [10, 20]}, edges, {}
        )
        assert result == {"low_hz": [10, 20]}

    def test_ignores_edges_for_other_functions(self):
        from scistack_gui.services.matlab_command_service import (
            _collect_sweep_params,
        )

        edges = [self._edge("param__low_hz", "fn__other_fn", "in__low_hz")]
        result = _collect_sweep_params(
            "bandpass_filter", {"low_hz": [10, 20, 30]}, edges, {}
        )
        assert result == {}

    def test_ignores_non_parameter_source_edges(self):
        from scistack_gui.services.matlab_command_service import (
            _collect_sweep_params,
        )

        edges = [self._edge("var__low_hz", "fn__bandpass_filter", "in__low_hz")]
        result = _collect_sweep_params(
            "bandpass_filter", {"low_hz": [10, 20, 30]}, edges, {}
        )
        assert result == {}

    def test_parameter_name_not_in_saved_sweeps_is_skipped(self):
        from scistack_gui.services.matlab_command_service import (
            _collect_sweep_params,
        )

        edges = [self._edge("param__unknown", "fn__bandpass_filter", "in__low_hz")]
        result = _collect_sweep_params(
            "bandpass_filter", {"low_hz": [10, 20, 30]}, edges, {}
        )
        assert result == {}

    def test_placement_qualified_fn_endpoint_is_recognised(self):
        """A graduated node's edge carries fn__{name}__{wiring}::{scope};
        the shared _fn_node_ids adopts it, where the old prefix-only scan
        matched on a bare split and could miss it."""
        from scistack_gui.services.matlab_command_service import (
            _collect_sweep_params,
        )

        edges = [
            self._edge(
                "param__low_hz",
                "fn__bandpass_filter__0123456789abcdef::main",
                "in__low_hz",
            )
        ]
        result = _collect_sweep_params(
            "bandpass_filter", {"low_hz": [10]}, edges, {}
        )
        assert result == {"low_hz": [10]}


class TestCollectEdgePathInputs:
    """The PathInput half of the same shared resolution."""

    def _edge(self, source, target, target_handle):
        return {"source": source, "target": target, "targetHandle": target_handle}

    def test_declared_name_may_differ_from_the_param(self):
        from scistack_gui.services.matlab_command_service import (
            _collect_edge_path_inputs,
        )

        edges = [
            self._edge("pathInput__test_pi", "fn__load_raw", "in__filepath")
        ]
        result = _collect_edge_path_inputs(
            "load_raw",
            {"test_pi": {"template": "{subject}.csv", "root_folder": "/data"}},
            edges,
            {},
        )
        assert result == {
            "filepath": {"template": "{subject}.csv", "root_folder": "/data"}
        }

    def test_unknown_declared_name_is_skipped(self):
        from scistack_gui.services.matlab_command_service import (
            _collect_edge_path_inputs,
        )

        edges = [self._edge("pathInput__gone", "fn__load_raw", "in__filepath")]
        result = _collect_edge_path_inputs("load_raw", {}, edges, {})
        assert result == {}

    def test_ignores_edges_for_other_functions(self):
        from scistack_gui.services.matlab_command_service import (
            _collect_edge_path_inputs,
        )

        edges = [self._edge("pathInput__test_pi", "fn__other", "in__filepath")]
        result = _collect_edge_path_inputs(
            "load_raw", {"test_pi": {"template": "x.csv"}}, edges, {}
        )
        assert result == {}


class TestMatlabFnProxyHash:
    """Fix A — the proxy hash must match what MATLAB's scidb.LineageFcn(fn)
    (unpack_output=false default) produces, so scihist.check_node_state does
    not report every combo as "stale: function hash changed"."""

    def test_proxy_uses_unpack_false(self, monkeypatch):
        from hashlib import sha256

        from scistack_gui import matlab_registry as _mr
        from scistack_gui.api.pipeline import _build_matlab_fn_proxy

        class FakeInfo:
            source_hash = "a" * 64
            n_outputs = 3
            params = ("x",)
            output_names = ("a", "b", "c")

        monkeypatch.setattr(_mr, "get_matlab_function", lambda _name: FakeInfo())

        proxy = _build_matlab_fn_proxy("load_csv")
        expected = sha256(f"{FakeInfo.source_hash}-False".encode()).hexdigest()
        assert proxy.hash == expected
        assert proxy.unpack_output is False

    def test_single_output_hash_also_unpack_false(self, monkeypatch):
        from hashlib import sha256

        from scistack_gui import matlab_registry as _mr
        from scistack_gui.api.pipeline import _build_matlab_fn_proxy

        class FakeInfo:
            source_hash = "b" * 64
            n_outputs = 1
            params = ()
            output_names = ("only",)

        monkeypatch.setattr(_mr, "get_matlab_function", lambda _name: FakeInfo())
        proxy = _build_matlab_fn_proxy("fn")
        expected = sha256(f"{FakeInfo.source_hash}-False".encode()).hexdigest()
        assert proxy.hash == expected


class TestGenerateMatlabPipelineCommand:
    """generate_matlab_pipeline_command (whole-pipeline MATLAB execution,
    plan-matlab-pipeline-execution.md Stage 1)."""

    def _two_step_pipeline(self):
        return [
            {
                "function_name": "load_csv",
                "variants": [
                    {
                        "input_types": {},
                        "output_type": "RawSignal",
                        "constants": {},
                    }
                ],
            },
            {
                "function_name": "bandpass_filter",
                "variants": [
                    {
                        "input_types": {"signal": "RawSignal"},
                        "output_type": "FilteredSignal",
                        "constants": {"low_hz": 20},
                    }
                ],
            },
        ]

    def test_wraps_steps_in_scidb_pipeline(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        cmd = generate_matlab_pipeline_command(
            pipeline_id="gait_analysis",
            steps=self._two_step_pipeline(),
            db_path="/data/exp.duckdb",
            schema_keys=["subject"],
        )

        assert "pipe = scidb.Pipeline('gait_analysis');" in cmd
        assert cmd.count("scidb.for_each") == 2
        assert "@load_csv" in cmd
        assert "@bandpass_filter" in cmd
        assert "pipe.run_all(" in cmd

    def test_registration_order_independent(self):
        """Pipeline.m's execution_order() topo-sorts server-side — the
        script may register steps in any order."""
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        steps = self._two_step_pipeline()
        cmd_forward = generate_matlab_pipeline_command(
            pipeline_id="p", steps=steps, db_path="/db.duckdb", schema_keys=["s"]
        )
        cmd_reversed = generate_matlab_pipeline_command(
            pipeline_id="p",
            steps=list(reversed(steps)),
            db_path="/db.duckdb",
            schema_keys=["s"],
        )
        assert cmd_forward.count("scidb.for_each") == cmd_reversed.count(
            "scidb.for_each"
        )
        assert "@load_csv" in cmd_reversed
        assert "@bandpass_filter" in cmd_reversed

    def test_mode_until_calls_run_until_with_target(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        cmd = generate_matlab_pipeline_command(
            pipeline_id="p",
            steps=self._two_step_pipeline(),
            db_path="/db.duckdb",
            schema_keys=["s"],
            mode="until",
            target="bandpass_filter",
        )
        assert "pipe.run_until('bandpass_filter'" in cmd
        assert "pipe.run_all(" not in cmd

    def test_mode_until_requires_target(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        with pytest.raises(ValueError):
            generate_matlab_pipeline_command(
                pipeline_id="p",
                steps=self._two_step_pipeline(),
                db_path="/db.duckdb",
                schema_keys=["s"],
                mode="until",
                target="",
            )

    def test_mode_endpoints_calls_run_endpoints(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        cmd = generate_matlab_pipeline_command(
            pipeline_id="p",
            steps=self._two_step_pipeline(),
            db_path="/db.duckdb",
            schema_keys=["s"],
            mode="endpoints",
            finalized=True,
        )
        assert "pipe.run_endpoints(" in cmd
        assert "'include_used', true" in cmd
        assert "'finalized', true" in cmd

    def test_show_mode_rejected(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        with pytest.raises(ValueError):
            generate_matlab_pipeline_command(
                pipeline_id="p",
                steps=self._two_step_pipeline(),
                db_path="/db.duckdb",
                schema_keys=["s"],
                mode="show",
                target="bandpass_filter",
            )

    def test_step_with_no_variants_skipped_with_comment(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        steps = self._two_step_pipeline()
        steps.append({"function_name": "never_run_fn", "variants": []})
        cmd = generate_matlab_pipeline_command(
            pipeline_id="p", steps=steps, db_path="/db.duckdb", schema_keys=["s"]
        )
        assert "SKIPPED: 'never_run_fn'" in cmd
        assert "@never_run_fn" not in cmd
        # The two runnable steps still registered.
        assert cmd.count("scidb.for_each") == 2

    def test_no_runnable_steps_raises(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        with pytest.raises(ValueError):
            generate_matlab_pipeline_command(
                pipeline_id="p",
                steps=[{"function_name": "never_run_fn", "variants": []}],
                db_path="/db.duckdb",
                schema_keys=["s"],
            )

    def test_variable_registration_union_across_steps(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        cmd = generate_matlab_pipeline_command(
            pipeline_id="p",
            steps=self._two_step_pipeline(),
            db_path="/db.duckdb",
            schema_keys=["s"],
        )
        assert cmd.count("scidb.register_variable(RawSignal())") == 1
        assert cmd.count("scidb.register_variable(FilteredSignal())") == 1

    def test_step_sweep_rendered_as_scifor_sweep(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        steps = self._two_step_pipeline()
        # window_seconds is NOT among this step's fixture "constants" —
        # picking a param already in "constants" would collide, since
        # _for_each_call_lines applies constants after sweeps and would
        # silently overwrite the sweep-formatted value for that key.
        steps[1]["sweeps"] = {"window_seconds": [10, 20, 30]}
        cmd = generate_matlab_pipeline_command(
            pipeline_id="p", steps=steps, db_path="/db.duckdb", schema_keys=["s"]
        )
        assert "scidb.Parameter(10, 20, 30)" in cmd

    def test_pyenv_preamble_present(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        cmd = generate_matlab_pipeline_command(
            pipeline_id="p",
            steps=self._two_step_pipeline(),
            db_path="/db.duckdb",
            schema_keys=["s"],
            python_executable="/usr/bin/python3",
        )
        assert "pyenv('Version', scistack_pyenv_target__)" in cmd
        pyenv_idx = cmd.index("scistack_pyenv_target__")
        pipe_idx = cmd.index("pipe = scidb.Pipeline(")
        assert pyenv_idx < pipe_idx

    def test_addpath_and_configure_database_emitted_once(self):
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        cmd = generate_matlab_pipeline_command(
            pipeline_id="p",
            steps=self._two_step_pipeline(),
            db_path="/data/exp.duckdb",
            schema_keys=["subject"],
            addpath_dirs=["/home/user/matlab/lib"],
        )
        assert cmd.count("addpath('/home/user/matlab/lib')") == 1
        assert cmd.count("scihist.configure_database(") == 1
        assert cmd.count("scidb.close_database(db)") == 2  # success path + catch

    def test_multi_output_function_collapses_to_one_call(self):
        """Same grouping behavior as generate_matlab_command: multiple
        variant rows sharing (input_types, constants) but different
        output_type collapse into one for_each with a multi-item outputs
        cell."""
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        steps = [
            {
                "function_name": "load_csv",
                "variants": [
                    {"input_types": {}, "output_type": "Time", "constants": {}},
                    {"input_types": {}, "output_type": "Force_Left", "constants": {}},
                ],
            }
        ]
        cmd = generate_matlab_pipeline_command(
            pipeline_id="p", steps=steps, db_path="/db.duckdb", schema_keys=["s"]
        )
        assert cmd.count("scidb.for_each") == 1
        assert "{Time(), Force_Left()}" in cmd

    def test_mixed_language_pipeline_only_registers_matlab_steps(self):
        """Regression guard for the mixed-pipeline scope decision: the
        MATLAB script generator only ever sees the steps its caller
        (matlab_command_service.generate_matlab_pipeline_command) already
        filtered to MATLAB functions — passing a step list that mirrors
        'a Python node was excluded upstream' (i.e. simply absent here)
        must still produce a clean script for the remaining MATLAB steps."""
        from scistack_gui.api.matlab_command import generate_matlab_pipeline_command

        # Only the MATLAB step is passed — as the service layer would do
        # after filtering out a co-scoped Python function node.
        steps = [self._two_step_pipeline()[1]]  # bandpass_filter only
        cmd = generate_matlab_pipeline_command(
            pipeline_id="p", steps=steps, db_path="/db.duckdb", schema_keys=["s"]
        )
        assert cmd.count("scidb.for_each") == 1
        assert "@bandpass_filter" in cmd
        assert "@load_csv" not in cmd


class TestFindSciMatlabMatlabDir:
    def test_finds_matlab_dir(self):
        """scimatlab is installed in this environment; its matlab/ dir must be found."""
        from scistack_gui.server import _find_scimatlab_matlab_dir

        result = _find_scimatlab_matlab_dir()
        assert result is not None, (
            "scimatlab is installed but _find_scimatlab_matlab_dir returned None"
        )
        d = Path(result)
        assert d.is_dir(), f"Expected a directory at {result}"
        # The directory must contain the +scihist, +scidb, +scifor MATLAB packages.
        assert (d / "+scihist").is_dir(), f"+scihist not found under {result}"
        assert (d / "+scidb").is_dir(), f"+scidb not found under {result}"
        assert (d / "+scifor").is_dir(), f"+scifor not found under {result}"

    def test_close_database_helper_present(self):
        """Regression: +scidb/close_database.m must exist so matlab_command.py
        can call scidb.close_database(db) for post-close lock-release logging.
        """
        from scistack_gui.server import _find_scimatlab_matlab_dir

        result = _find_scimatlab_matlab_dir()
        assert result is not None
        close_db = Path(result) / "+scidb" / "close_database.m"
        assert close_db.exists(), f"scidb.close_database not found at {close_db}"
        contents = close_db.read_text()
        # The RELEASED log MUST fire after close returns, not before.
        # Use rfind so docstring mentions of these strings (which appear
        # before the code) don't mask the real code-order check.
        release_idx = contents.rfind("DuckDB lock RELEASED")
        close_idx = contents.rfind("db.close()")
        assert 0 < close_idx < release_idx, (
            "RELEASED log must appear after db.close() in close_database.m"
        )
        # A close error must be logged and rethrown (not silently swallowed).
        assert "db.close FAILED" in contents
        assert "rethrow(close_err__)" in contents

    def test_scihist_configure_database_present(self):
        """Regression: +scihist/configure_database.m must exist so MATLAB can call it."""
        from scistack_gui.server import _find_scimatlab_matlab_dir

        result = _find_scimatlab_matlab_dir()
        assert result is not None
        cfg_db = Path(result) / "+scihist" / "configure_database.m"
        assert cfg_db.exists(), f"scihist.configure_database not found at {cfg_db}"
