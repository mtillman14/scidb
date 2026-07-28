"""Tests for PathInput.discover() — filesystem-driven metadata discovery."""

from pathlib import Path

import pytest
from scifor.pathinput import PathInput


@pytest.fixture
def tmp_tree(tmp_path):
    """Create a temp directory tree:

    tmp_path/
        1/
            XSENS/
                A/
                    1_XSENS_A_fast-001.xlsx
                    1_XSENS_A_slow-001.xlsx
                B/
                    1_XSENS_B_fast-001.xlsx
        2/
            XSENS/
                A/
                    2_XSENS_A_fast-001.xlsx
    """
    for subject in ["1", "2"]:
        sessions = ["A", "B"] if subject == "1" else ["A"]
        for session in sessions:
            speeds = (
                ["fast", "slow"] if (subject == "1" and session == "A") else ["fast"]
            )
            for speed in speeds:
                d = tmp_path / subject / "XSENS" / session
                d.mkdir(parents=True, exist_ok=True)
                fname = f"{subject}_XSENS_{session}_{speed}-001.xlsx"
                (d / fname).touch()
    return tmp_path


class TestPlaceholderKeys:
    def test_simple(self):
        pi = PathInput("{subject}/data.mat")
        assert pi.placeholder_keys() == ["subject"]

    def test_multiple(self):
        pi = PathInput("{subject}/{session}/data.mat")
        assert pi.placeholder_keys() == ["subject", "session"]

    def test_mixed_segment(self):
        pi = PathInput("{subject}_XSENS_{session}_{speed}-001.xlsx")
        assert pi.placeholder_keys() == ["subject", "session", "speed"]

    def test_no_placeholders(self):
        pi = PathInput("data/raw/file.mat")
        assert pi.placeholder_keys() == []

    def test_duplicate_keys(self):
        pi = PathInput("{subject}/{subject}_data.mat")
        assert pi.placeholder_keys() == ["subject"]


class TestDiscover:
    def test_basic_discovery(self, tmp_tree):
        pi = PathInput(
            "{subject}/XSENS/{session}/{subject}_XSENS_{session}_{speed}-001.xlsx",
            root_folder=tmp_tree,
        )
        combos = pi.discover()
        assert len(combos) == 4
        # Check specific combos exist
        assert {"subject": "1", "session": "A", "speed": "fast"} in combos
        assert {"subject": "1", "session": "A", "speed": "slow"} in combos
        assert {"subject": "1", "session": "B", "speed": "fast"} in combos
        assert {"subject": "2", "session": "A", "speed": "fast"} in combos

    def test_values_are_strings(self, tmp_tree):
        pi = PathInput(
            "{subject}/XSENS/{session}/{subject}_XSENS_{session}_{speed}-001.xlsx",
            root_folder=tmp_tree,
        )
        combos = pi.discover()
        for combo in combos:
            for v in combo.values():
                assert isinstance(v, str)

    def test_literal_segment_filtering(self, tmp_tree):
        """Literal 'XSENS' segment filters out non-matching dirs."""
        # Create a distractor directory
        (tmp_tree / "1" / "OTHER").mkdir()
        (tmp_tree / "1" / "OTHER" / "A").mkdir()
        (tmp_tree / "1" / "OTHER" / "A" / "1_OTHER_A_fast-001.xlsx").touch()

        pi = PathInput(
            "{subject}/XSENS/{session}/{subject}_XSENS_{session}_{speed}-001.xlsx",
            root_folder=tmp_tree,
        )
        combos = pi.discover()
        # Should not include the OTHER directory
        for combo in combos:
            assert combo.get("session") in ("A", "B")

    def test_empty_filesystem(self, tmp_path):
        pi = PathInput(
            "{subject}/data/{file}.csv",
            root_folder=tmp_path,
        )
        combos = pi.discover()
        assert combos == []

    def test_no_placeholders(self, tmp_path):
        """Template with no placeholders — returns one combo (empty dict) if file exists."""
        (tmp_path / "data.mat").touch()
        pi = PathInput("data.mat", root_folder=tmp_path)
        combos = pi.discover()
        assert combos == [{}]

    def test_no_placeholders_missing_file(self, tmp_path):
        pi = PathInput("data.mat", root_folder=tmp_path)
        combos = pi.discover()
        assert combos == []

    def test_repeated_placeholder_consistency(self, tmp_tree):
        """When {subject} appears in both dir and filename, values must be consistent."""
        pi = PathInput(
            "{subject}/XSENS/{session}/{subject}_XSENS_{session}_{speed}-001.xlsx",
            root_folder=tmp_tree,
        )
        combos = pi.discover()
        for combo in combos:
            # subject should be self-consistent (dir segment = filename segment)
            assert combo["subject"] in ("1", "2")

    def test_repeated_placeholder_rejects_inconsistent(self, tmp_path):
        """If {x} in dir doesn't match {x} in filename, path is excluded."""
        d = tmp_path / "A"
        d.mkdir()
        # File says B but dir is A — should not match
        (d / "B_data.csv").touch()
        # File says A and dir is A — should match
        (d / "A_data.csv").touch()

        pi = PathInput("{x}/{x}_data.csv", root_folder=tmp_path)
        combos = pi.discover()
        assert len(combos) == 1
        assert combos[0] == {"x": "A"}

    def test_pure_placeholder_directories(self, tmp_path):
        """Pure {key} segments match any directory."""
        for name in ["alpha", "beta"]:
            d = tmp_path / name
            d.mkdir()
            (d / "result.csv").touch()
        # Distractor: directory without the file
        (tmp_path / "gamma").mkdir()

        pi = PathInput("{group}/result.csv", root_folder=tmp_path)
        combos = pi.discover()
        assert len(combos) == 2
        groups = {c["group"] for c in combos}
        assert groups == {"alpha", "beta"}

    def test_no_root_folder_uses_cwd(self, tmp_path, monkeypatch):
        """Fallback: when no pyproject.toml/scistack.toml ancestor exists, cwd is used."""
        (tmp_path / "file_A.txt").touch()
        (tmp_path / "file_B.txt").touch()
        monkeypatch.chdir(tmp_path)

        pi = PathInput("file_{x}.txt")
        combos = pi.discover()
        assert len(combos) == 2
        xs = {c["x"] for c in combos}
        assert xs == {"A", "B"}

    def test_no_root_folder_uses_pyproject_root_for_discover(
        self, tmp_path, monkeypatch
    ):
        """discover() with no root_folder roots at the pyproject.toml ancestor."""
        (tmp_path / "pyproject.toml").touch()
        sub = tmp_path / "subdir"
        sub.mkdir()
        (tmp_path / "file_A.txt").touch()
        (tmp_path / "file_B.txt").touch()
        monkeypatch.chdir(sub)  # cwd is a subdirectory, not the project root

        pi = PathInput("file_{x}.txt")
        combos = pi.discover()
        assert len(combos) == 2
        xs = {c["x"] for c in combos}
        assert xs == {"A", "B"}

    def test_no_root_folder_uses_scistack_toml_root_for_discover(
        self, tmp_path, monkeypatch
    ):
        """discover() finds the root via scistack.toml when pyproject.toml is absent."""
        (tmp_path / "scistack.toml").touch()
        sub = tmp_path / "subdir"
        sub.mkdir()
        (tmp_path / "data_X.csv").touch()
        monkeypatch.chdir(sub)

        pi = PathInput("data_{x}.csv")
        combos = pi.discover()
        assert combos == [{"x": "X"}]


class TestApplyDiscovery:
    """The discovery-orchestration decision shared by scidb and scifor."""

    def _pi(self, tmp_tree):
        return PathInput(
            "{subject}/XSENS/{session}/{subject}_XSENS_{session}_{speed}-001.xlsx",
            root_folder=tmp_tree,
        )

    def test_case_a_no_iterables_adopts_all_keys(self, tmp_tree):
        """No metadata iterables -> adopt every discovered key + use combos directly."""
        pi = self._pi(tmp_tree)
        iterables, combos = pi.apply_discovery({}, set())
        assert set(iterables) == {"subject", "session", "speed"}
        assert sorted(iterables["subject"]) == ["1", "2"]
        # Combos drive iteration directly (no Cartesian invention).
        assert combos is not None
        assert len(combos) == 4

    def test_case_b_all_empty_uses_discovered_combos(self, tmp_tree):
        """All template keys passed as [] -> fill from disk, use combos directly."""
        pi = self._pi(tmp_tree)
        iterables, combos = pi.apply_discovery(
            {"subject": [], "session": [], "speed": []}, set()
        )
        assert sorted(iterables["subject"]) == ["1", "2"]
        assert sorted(iterables["session"]) == ["A", "B"]
        assert combos is not None
        assert len(combos) == 4
        # Crucially NOT the Cartesian product (2x2x2=8) — only real files (4).
        assert {"subject": "2", "session": "B", "speed": "slow"} not in combos

    def test_case_b_explicit_key_falls_back_to_cartesian(self, tmp_tree):
        """An explicit (non-empty) template key asserts intent -> no direct combos."""
        pi = self._pi(tmp_tree)
        iterables, combos = pi.apply_discovery(
            {"subject": ["1"], "session": [], "speed": []},
            user_explicit_keys={"subject"},
        )
        # Empty keys still filled from disk...
        assert sorted(iterables["session"]) == ["A", "B"]
        # ...but discovered combos do NOT drive iteration (Cartesian does).
        assert combos is None
        # Explicit key left untouched.
        assert iterables["subject"] == ["1"]

    def test_empty_discovery_returns_unchanged(self, tmp_path):
        pi = PathInput("{subject}/missing/{x}.csv", root_folder=tmp_path)
        iterables, combos = pi.apply_discovery({"subject": []}, set())
        assert combos is None
        assert iterables["subject"] == []

    def test_log_callback_invoked(self, tmp_tree):
        pi = self._pi(tmp_tree)
        msgs = []
        pi.apply_discovery(
            {"subject": [], "session": [], "speed": []}, set(), log=msgs.append
        )
        assert any("matching_files=4" in m for m in msgs)
        assert any("disk combos" in m for m in msgs)


class TestApplyDiscoveryCondenseNumeric:
    """condense_numeric=True (standalone-scifor-only opt-in): digit-only
    discovered values collapse to int, stripping leading zeros. Off by
    default so scidb's declared-only schema_key_types contract is
    unaffected -- see docs/claude/schema-key-types.md."""

    @pytest.fixture
    def padded_tree(self, tmp_path):
        """tmp_path/data-001.mat, tmp_path/data-002.mat"""
        (tmp_path / "data-001.mat").touch()
        (tmp_path / "data-002.mat").touch()
        return tmp_path

    def test_condenses_zero_padded_digits(self, padded_tree):
        pi = PathInput("data-{subject}.mat", root_folder=padded_tree)
        iterables, combos = pi.apply_discovery({}, set(), condense_numeric=True)
        assert sorted(iterables["subject"]) == [1, 2]
        assert all(isinstance(v, int) for v in iterables["subject"])
        assert {"subject": 1} in combos
        assert {"subject": 2} in combos

    def test_default_off_stays_verbatim_strings(self, padded_tree):
        pi = PathInput("data-{subject}.mat", root_folder=padded_tree)
        iterables, combos = pi.apply_discovery({}, set())
        assert sorted(iterables["subject"]) == ["001", "002"]
        assert {"subject": "001"} in combos

    def test_non_digit_values_untouched(self, tmp_tree):
        """tmp_tree's session/speed values ('A', 'B', 'fast', 'slow') are not
        digit-only and must pass through unchanged even with the flag on."""
        pi = PathInput(
            "{subject}/XSENS/{session}/{subject}_XSENS_{session}_{speed}-001.xlsx",
            root_folder=tmp_tree,
        )
        iterables, combos = pi.apply_discovery({}, set(), condense_numeric=True)
        assert sorted(iterables["session"]) == ["A", "B"]
        assert all(isinstance(v, str) for v in iterables["session"])
        assert all(isinstance(v, str) for v in iterables["speed"])
        # subject folders ("1", "2") ARE digit-only -> condensed.
        assert sorted(iterables["subject"]) == [1, 2]

    def test_explicit_values_never_condensed(self, padded_tree):
        """A key with an explicit (non-empty) value asserts user intent and
        is left completely alone -- condensation only ever touches values
        scifor itself discovered from disk."""
        pi = PathInput("data-{subject}.mat", root_folder=padded_tree)
        iterables, combos = pi.apply_discovery(
            {"subject": ["001", "002"]},
            user_explicit_keys={"subject"},
            condense_numeric=True,
        )
        assert iterables["subject"] == ["001", "002"]


class TestLoad:
    def test_load_with_root_folder(self, tmp_path):
        pi = PathInput("{subject}/data.mat", root_folder=tmp_path)
        result = pi.load(subject="01")
        assert result == (tmp_path / "01" / "data.mat").resolve()

    def test_load_no_root_folder_uses_project_root(self, tmp_path, monkeypatch):
        """load() with no root_folder resolves relative to pyproject.toml ancestor."""
        (tmp_path / "pyproject.toml").touch()
        sub = tmp_path / "scripts"
        sub.mkdir()
        monkeypatch.chdir(sub)

        pi = PathInput("{subject}/data.mat")
        result = pi.load(subject="01")
        assert result == (tmp_path / "01" / "data.mat").resolve()

    def test_load_no_root_folder_fallback_to_cwd(self, tmp_path, monkeypatch):
        """load() falls back to cwd when no pyproject.toml ancestor exists."""
        monkeypatch.chdir(tmp_path)
        pi = PathInput("{subject}/data.mat")
        result = pi.load(subject="01")
        assert result == (tmp_path / "01" / "data.mat").resolve()

    def test_load_absolute_template_ignores_project_root(self, tmp_path, monkeypatch):
        """load() does not prepend the project root when template resolves to absolute."""
        monkeypatch.chdir(tmp_path)
        pi = PathInput("/absolute/path/{subject}.mat")
        result = pi.load(subject="01")
        assert result == Path("/absolute/path/01.mat")

    def test_mixed_filename_segment(self, tmp_path):
        """Template with literal+placeholder in filename segment."""
        d = tmp_path / "data"
        d.mkdir()
        (d / "report_2024_final.csv").touch()
        (d / "report_2023_draft.csv").touch()
        (d / "other.csv").touch()  # should not match

        pi = PathInput("data/report_{year}_{status}.csv", root_folder=tmp_path)
        combos = pi.discover()
        assert len(combos) == 2
        years = {c["year"] for c in combos}
        assert years == {"2024", "2023"}

    def test_deeply_nested_template(self, tmp_path):
        """Template with many segments."""
        d = tmp_path / "a" / "b" / "c"
        d.mkdir(parents=True)
        (d / "file.txt").touch()

        pi = PathInput("{x}/b/{y}/file.txt", root_folder=tmp_path)
        combos = pi.discover()
        assert combos == [{"x": "a", "y": "c"}]


class TestDiscoverAbsoluteTemplates:
    """Absolute templates anchor discovery at their own root (the MATLAB
    ``fullfile(...)`` pattern produces absolute templates with no
    root_folder — discovery must match load()'s anchoring, not walk from
    the project root)."""

    def test_absolute_posix_template(self, tmp_path):
        d = tmp_path / "EMG"
        d.mkdir()
        (d / "6MWT-001.mat").touch()
        (d / "6MWT-004.mat").touch()
        (d / "6MWT-001.adicht").touch()  # different extension: no match
        (d / "Bike-1.mat").touch()  # different stem: no match

        pi = PathInput(f"{tmp_path}/EMG/6MWT-{{pass}}.mat")
        combos = pi.discover()
        assert sorted(c["pass"] for c in combos) == ["001", "004"]

    def test_absolute_template_load_roundtrip(self, tmp_path):
        d = tmp_path / "EMG"
        d.mkdir()
        (d / "6MWT-001.mat").touch()

        pi = PathInput(f"{tmp_path}/EMG/6MWT-{{pass}}.mat")
        combos = pi.discover()
        assert len(combos) == 1
        # The discovered combo literal-resolves back to the real file.
        assert pi.load(**combos[0]) == (d / "6MWT-001.mat").resolve()

    def test_windows_drive_template_parsing(self):
        pi = PathInput(r"Y:\data\EMG\6MWT-{pass}.mat")
        root, segments = pi._root_and_segments()
        assert str(root).rstrip("/\\") == "Y:"
        assert segments == ["data", "EMG", "6MWT-{pass}.mat"]

    def test_unc_template_parsing(self):
        pi = PathInput(r"\\fs2.smpp.local\RTO\GitRepos\{subject}\data.mat")
        root, segments = pi._root_and_segments()
        assert str(root).replace("\\", "/") == "//fs2.smpp.local/RTO"
        assert segments == ["GitRepos", "{subject}", "data.mat"]

    def test_relative_template_still_uses_root_folder(self, tmp_path):
        d = tmp_path / "EMG"
        d.mkdir()
        (d / "6MWT-001.mat").touch()

        pi = PathInput("EMG/6MWT-{pass}.mat", root_folder=str(tmp_path))
        combos = pi.discover()
        assert [c["pass"] for c in combos] == ["001"]
