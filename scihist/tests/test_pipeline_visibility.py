"""Regression tests: scihist outputs must be visible to list_pipeline_variants().

After scihist.for_each saves a LineageFcnResult, the record's version_keys
must include __fn and __fn_hash so that db.list_pipeline_variants() can
discover them — exactly as scidb.for_each already does for plain functions.

Without this, the GUI shows scihist output variables as green (up-to-date)
even when some combos are missing, because the pipeline graph never learns
about the function that produced them.
"""

import numpy as np
import pytest

from scidb import BaseVariable, Fixed
from scilineage import lineage_fcn
from scihist import for_each

from conftest import DEFAULT_TEST_SCHEMA_KEYS


# ---------------------------------------------------------------------------
# Variable types
# ---------------------------------------------------------------------------

class RawData(BaseVariable):
    schema_version = 1

class ProcessedData(BaseVariable):
    schema_version = 1

class AuxData(BaseVariable):
    schema_version = 1

class Figure(BaseVariable):
    schema_version = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skip_lines(text: str) -> list[str]:
    return [l for l in text.splitlines() if l.startswith("[skip]")]

def _recompute_lines(text: str) -> list[str]:
    return [l for l in text.splitlines() if l.startswith("[recompute]")]


# ===========================================================================
# list_pipeline_variants visibility
# ===========================================================================

class TestListPipelineVariantsVisibility:
    """Scihist outputs must appear in db.list_pipeline_variants()."""

    def test_single_output_visible(self, db):
        """After scihist.for_each, list_pipeline_variants finds the function."""
        @lineage_fcn
        def double(x):
            return x * 2

        RawData.save(np.array([1, 2, 3]), subject=1, trial=1)
        for_each(double, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1], trial=[1])

        variants = db.list_pipeline_variants()
        fn_names = {v["function_name"] for v in variants}
        assert "double" in fn_names

    def test_output_type_correct(self, db):
        """The variant's output_type matches the output variable class."""
        @lineage_fcn
        def double(x):
            return x * 2

        RawData.save(np.array([1, 2, 3]), subject=1, trial=1)
        for_each(double, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1], trial=[1])

        variants = db.list_pipeline_variants(output_type="ProcessedData")
        assert len(variants) >= 1
        assert variants[0]["function_name"] == "double"

    def test_record_count_matches(self, db):
        """Variant record_count should match the number of saved combos."""
        @lineage_fcn
        def double(x):
            return x * 2

        for s in [1, 2, 3]:
            RawData.save(np.array([s * 10]), subject=s, trial=1)

        for_each(double, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1, 2, 3], trial=[1])

        variants = db.list_pipeline_variants(output_type="ProcessedData")
        total = sum(v["record_count"] for v in variants)
        assert total == 3

    def test_multiple_functions_both_visible(self, db):
        """Two different lineage_fcns produce two separate variants."""
        @lineage_fcn
        def step1(x):
            return x + 1

        @lineage_fcn
        def step2(y):
            return y * 2

        RawData.save(np.array([1, 2, 3]), subject=1, trial=1)
        for_each(step1, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1], trial=[1])
        for_each(step2, inputs={"y": ProcessedData}, outputs=[AuxData],
                 subject=[1], trial=[1])

        variants = db.list_pipeline_variants()
        fn_names = {v["function_name"] for v in variants}
        assert "step1" in fn_names
        assert "step2" in fn_names

    def test_constant_variants_visible(self, db):
        """Different constant values produce distinct variants."""
        @lineage_fcn
        def scale(x, factor):
            return x * factor

        RawData.save(np.array([1, 2, 3]), subject=1, trial=1)
        for_each(scale, inputs={"x": RawData, "factor": 2},
                 outputs=[ProcessedData], subject=[1], trial=[1])
        for_each(scale, inputs={"x": RawData, "factor": 3},
                 outputs=[ProcessedData], subject=[1], trial=[1])

        variants = db.list_pipeline_variants(output_type="ProcessedData")
        assert len(variants) >= 2
        all_fn = {v["function_name"] for v in variants}
        assert all_fn == {"scale"}

    def test_generates_file_visible(self, db):
        """generates_file=True functions should also be visible."""
        @lineage_fcn(generates_file=True)
        def make_plot(data, subject, trial):
            return None

        RawData.save(np.array([1, 2, 3]), subject=1, trial=1)
        for_each(make_plot, inputs={"data": RawData}, outputs=[Figure],
                 subject=[1], trial=[1])

        variants = db.list_pipeline_variants(output_type="Figure")
        fn_names = {v["function_name"] for v in variants}
        assert "make_plot" in fn_names


# ===========================================================================
# skip_computed with __fn in version_keys
# ===========================================================================

class TestSkipComputedWithFnVersionKeys:
    """skip_computed must still work after __fn/__fn_hash are in version_keys."""

    def test_skip_works_after_fn_version_keys_added(self, db, capsys):
        """Records with __fn in version_keys are found by skip_computed lookup."""
        @lineage_fcn
        def double(x):
            return x * 2

        RawData.save(np.array([1, 2, 3]), subject=1, trial=1)
        for_each(double, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1], trial=[1])
        capsys.readouterr()

        # Second run — must skip
        for_each(double, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1], trial=[1])
        out = capsys.readouterr().out
        assert len(_skip_lines(out)) == 1
        assert not _recompute_lines(out)

    def test_skip_works_with_constants(self, db, capsys):
        """skip_computed correctly finds records when constants + __fn are in version_keys."""
        @lineage_fcn
        def scale(x, factor):
            return x * factor

        RawData.save(np.array([1, 2, 3]), subject=1, trial=1)
        for_each(scale, inputs={"x": RawData, "factor": 2},
                 outputs=[ProcessedData], subject=[1], trial=[1])
        capsys.readouterr()

        for_each(scale, inputs={"x": RawData, "factor": 2},
                 outputs=[ProcessedData], subject=[1], trial=[1])
        out = capsys.readouterr().out
        assert len(_skip_lines(out)) == 1
        assert not _recompute_lines(out)

    def test_input_change_still_recomputes(self, db, capsys):
        """Changing upstream data still triggers recompute (not broken by __fn in lookup)."""
        call_count = [0]

        @lineage_fcn
        def double(x):
            call_count[0] += 1
            return x * 2

        RawData.save(np.array([1, 2, 3]), subject=1, trial=1)
        for_each(double, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1], trial=[1])
        assert call_count[0] == 1

        # Change input
        RawData.save(np.array([10, 20, 30]), subject=1, trial=1)
        capsys.readouterr()

        for_each(double, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1], trial=[1])
        out = capsys.readouterr().out
        assert _recompute_lines(out)
        assert call_count[0] == 2

    def test_function_change_still_computes(self, db, capsys):
        """Changing the function name means no existing record matches __fn,
        so the combo is treated as missing (computed, not skipped)."""
        call_count = [0]

        @lineage_fcn
        def process_v1(x):
            return x * 2

        @lineage_fcn
        def process_v2(x):
            call_count[0] += 1
            return x * 3

        RawData.save(np.array([1, 2, 3]), subject=1, trial=1)
        for_each(process_v1, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1], trial=[1])
        capsys.readouterr()

        for_each(process_v2, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1], trial=[1])
        # process_v2 has a different __fn, so no existing record matches →
        # skip_computed sees "output missing" and lets it run
        assert call_count[0] == 1
        assert not _skip_lines(capsys.readouterr().out)

    def test_load_still_works_with_schema_keys_only(self, db):
        """BaseVariable.load(subject=1, trial=1) returns correct data despite __fn in version_keys."""
        @lineage_fcn
        def double(x):
            return x * 2

        RawData.save(np.array([1, 2, 3]), subject=1, trial=1)
        for_each(double, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1], trial=[1])

        loaded = ProcessedData.load(subject=1, trial=1)
        np.testing.assert_array_equal(loaded.data, np.array([2, 4, 6]))

    def test_multiple_subjects_skip_and_recompute_mixed(self, db, capsys):
        """With 3 subjects, changing one still correctly skips the other two."""
        call_count = [0]

        @lineage_fcn
        def double(x):
            call_count[0] += 1
            return x * 2

        for s in [1, 2, 3]:
            RawData.save(np.array([s * 10]), subject=s, trial=1)

        for_each(double, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1, 2, 3], trial=[1])
        assert call_count[0] == 3

        # Change only subject=2
        RawData.save(np.array([999]), subject=2, trial=1)
        capsys.readouterr()

        for_each(double, inputs={"x": RawData}, outputs=[ProcessedData],
                 subject=[1, 2, 3], trial=[1])
        out = capsys.readouterr().out

        assert len(_skip_lines(out)) == 2
        assert len(_recompute_lines(out)) == 1
        assert any("subject=2" in l for l in _recompute_lines(out))
        assert call_count[0] == 4  # 3 original + 1 recompute
