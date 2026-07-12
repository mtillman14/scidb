"""Numeric-equivalence fallback for zero-padded filenames in PathInput.load().

Covers the native handling of the common zero-padded case: the literal path
is tried first; when it is missing and a metadata value is numeric-like, the
template is re-matched against disk with digit placeholders compared by
integer value (trial=1 finds 6MWT-001.mat).
"""

import pytest

from scifor.pathinput import PathInput


@pytest.fixture
def padded_tree(tmp_path):
    """
    tmp_path/
        1/
            6MWT-001.mat
            6MWT-010.mat
        sub-002/
            trial_1.mat
        exact/
            6MWT-5.mat
    """
    (tmp_path / "1").mkdir()
    (tmp_path / "1" / "6MWT-001.mat").touch()
    (tmp_path / "1" / "6MWT-010.mat").touch()
    (tmp_path / "sub-002").mkdir()
    (tmp_path / "sub-002" / "trial_1.mat").touch()
    (tmp_path / "exact").mkdir()
    (tmp_path / "exact" / "6MWT-5.mat").touch()
    return tmp_path


class TestLiteralFirst:
    def test_exact_path_short_circuits(self, padded_tree):
        # Unpadded file + unpadded value: literal hit, no fallback involved.
        pi = PathInput("exact/6MWT-{trial}.mat", root_folder=str(padded_tree))
        assert pi.load(trial=5) == (padded_tree / "exact" / "6MWT-5.mat").resolve()

    def test_padded_string_value_is_literal_hit(self, padded_tree):
        pi = PathInput("{subject}/6MWT-{trial}.mat", root_folder=str(padded_tree))
        assert pi.load(subject=1, trial="001") == (
            padded_tree / "1" / "6MWT-001.mat"
        ).resolve()


class TestNumericFallback:
    def test_int_value_finds_padded_file(self, padded_tree):
        pi = PathInput("{subject}/6MWT-{trial}.mat", root_folder=str(padded_tree))
        assert pi.load(subject=1, trial=1) == (
            padded_tree / "1" / "6MWT-001.mat"
        ).resolve()

    def test_digit_string_value_finds_padded_file(self, padded_tree):
        # MATLAB's num2str marshaling sends "1"; must match 001 too.
        pi = PathInput("{subject}/6MWT-{trial}.mat", root_folder=str(padded_tree))
        assert pi.load(subject="1", trial="1") == (
            padded_tree / "1" / "6MWT-001.mat"
        ).resolve()

    def test_integral_float_finds_padded_file(self, padded_tree):
        # MATLAB doubles cross the bridge as 1.0.
        pi = PathInput("{subject}/6MWT-{trial}.mat", root_folder=str(padded_tree))
        assert pi.load(subject=1.0, trial=1.0) == (
            padded_tree / "1" / "6MWT-001.mat"
        ).resolve()

    def test_multi_digit_padded(self, padded_tree):
        pi = PathInput("{subject}/6MWT-{trial}.mat", root_folder=str(padded_tree))
        assert pi.load(subject=1, trial=10) == (
            padded_tree / "1" / "6MWT-010.mat"
        ).resolve()

    def test_padded_directory_segment(self, padded_tree):
        # Padding in an intermediate directory name, not just the filename.
        pi = PathInput("sub-{subject}/trial_{trial}.mat", root_folder=str(padded_tree))
        assert pi.load(subject=2, trial=1) == (
            padded_tree / "sub-002" / "trial_1.mat"
        ).resolve()

    def test_pad_width_cache_second_load(self, padded_tree):
        # Second load reuses the learned width via a direct stat (no scan);
        # verify only the observable result — both loads resolve correctly.
        pi = PathInput("{subject}/6MWT-{trial}.mat", root_folder=str(padded_tree))
        assert pi.load(subject=1, trial=1).name == "6MWT-001.mat"
        assert pi._pad_width["trial"] == 3
        assert pi.load(subject=1, trial=10).name == "6MWT-010.mat"


class TestFallbackBoundaries:
    def test_ambiguous_matches_raise(self, tmp_path):
        (tmp_path / "6MWT-1.mat").touch()
        (tmp_path / "6MWT-001.mat").touch()
        pi = PathInput("6MWT-{trial}.mat", root_folder=str(tmp_path))
        with pytest.raises(RuntimeError, match="matched 2 files"):
            pi.load(trial="01")  # literal 6MWT-01.mat missing; 1 and 001 tie

    def test_zero_matches_returns_literal_path(self, padded_tree):
        # Historical behavior: load() never raised on missing files.
        pi = PathInput("{subject}/6MWT-{trial}.mat", root_folder=str(padded_tree))
        assert pi.load(subject=1, trial=99) == (
            padded_tree / "1" / "6MWT-99.mat"
        ).resolve()

    def test_non_numeric_values_never_scan(self, padded_tree):
        pi = PathInput("{group}/results.csv", root_folder=str(padded_tree))
        assert pi.load(group="control") == (
            padded_tree / "control" / "results.csv"
        ).resolve()

    def test_bool_is_not_numeric(self, padded_tree):
        (padded_tree / "flag-True.csv").touch()
        pi = PathInput("flag-{flag}.csv", root_folder=str(padded_tree))
        assert pi.load(flag=True) == (padded_tree / "flag-True.csv").resolve()

    def test_numeric_value_equal_but_different_number_no_match(self, padded_tree):
        # 6MWT-001 exists but trial=2 must not match it.
        pi = PathInput("{subject}/6MWT-{trial}.mat", root_folder=str(padded_tree))
        assert pi.load(subject=1, trial=2).name == "6MWT-2.mat"

    def test_regex_mode_unaffected(self, padded_tree):
        pi = PathInput(
            r"{subject}/6MWT-0{0,2}1\.mat", root_folder=str(padded_tree), regex=True
        )
        assert pi.load(subject=1) == (padded_tree / "1" / "6MWT-001.mat").resolve()
