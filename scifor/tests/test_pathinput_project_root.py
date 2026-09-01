"""The pinned project root for rootless PathInputs.

A ``PathInput`` with no ``root_folder`` resolves relative templates against
``_find_project_root()``, which walks up from the **cwd**. That is right for a
script run inside the project and wrong for an embedded interpreter: MATLAB's
cwd is wherever MATLAB is sitting (for a generated command, a temp script
directory), so the walk finds the wrong project or none at all.

``set_project_root`` lets the caller that knows the project say so. The point
of these tests is the invariant that makes it safe: it changes *resolution*
only and never ``to_key()``, so the identity a run is recorded under is the
same wherever it ran. Rewriting ``root_folder`` instead is what grew
``__unresolved__`` ghost nodes on the GUI canvas — see
``.claude/plan-pathinput-unresolved-after-run.md``.
"""

import os

import pytest
from scifor.pathinput import (
    PathInput,
    _find_project_root,
    clear_project_root,
    get_project_root,
    set_project_root,
)


@pytest.fixture(autouse=True)
def _no_leaked_override():
    """The override is process-global; never let one test set it for the next."""
    clear_project_root()
    yield
    clear_project_root()


@pytest.fixture
def project(tmp_path):
    """A project root with data, and an unrelated 'elsewhere' cwd."""
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    (root / "scistack.toml").write_text("[scistack]\n")
    (root / "data" / "s01.mat").touch()
    (tmp_path / "elsewhere").mkdir()
    return root


class TestOverride:
    def test_unset_by_default(self):
        assert get_project_root() is None

    def test_set_and_get_round_trip(self, project):
        set_project_root(project)
        assert get_project_root() == project.resolve()

    def test_clear_restores_walk_up(self, project, monkeypatch):
        set_project_root(project)
        clear_project_root()
        assert get_project_root() is None
        monkeypatch.chdir(project / "data")
        assert _find_project_root() == project.resolve()

    def test_none_clears(self, project):
        set_project_root(project)
        set_project_root(None)
        assert get_project_root() is None

    def test_accepts_a_string(self, project):
        set_project_root(str(project))
        assert get_project_root() == project.resolve()


class TestResolution:
    def test_override_beats_cwd(self, project, tmp_path, monkeypatch):
        """The whole point: cwd is outside the project, resolution still lands
        inside it."""
        monkeypatch.chdir(tmp_path / "elsewhere")
        set_project_root(project)
        pi = PathInput("data/{subject}.mat")
        assert pi.load(subject="s01") == (project / "data" / "s01.mat").resolve()

    def test_without_override_cwd_decides(self, project, tmp_path, monkeypatch):
        """Baseline for the test above: with nothing pinned, a cwd outside the
        project resolves somewhere else entirely (``load`` returns the
        non-existent path rather than raising)."""
        monkeypatch.chdir(tmp_path / "elsewhere")
        resolved = PathInput("data/{subject}.mat").load(subject="s01")
        assert resolved != (project / "data" / "s01.mat").resolve()
        assert not resolved.exists()

    def test_explicit_root_folder_still_wins(self, project, tmp_path):
        """An override is a fallback for *rootless* inputs, never an override
        of a declared root."""
        other = tmp_path / "other"
        (other / "data").mkdir(parents=True)
        (other / "data" / "s01.mat").touch()
        set_project_root(project)
        pi = PathInput("data/{subject}.mat", root_folder=str(other))
        assert pi.load(subject="s01") == (other / "data" / "s01.mat").resolve()

    def test_explicit_start_still_walks_up(self, project):
        """``_find_project_root(start)`` answers about *start*, not the pin."""
        set_project_root(project.parent)
        assert _find_project_root(project / "data") == project.resolve()

    def test_discover_uses_the_override(self, project, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path / "elsewhere")
        (project / "data" / "s02.mat").touch()
        set_project_root(project)
        found = PathInput("data/{subject}.mat").discover()
        assert sorted(c["subject"] for c in found) == ["s01", "s02"]


class TestIdentityUnaffected:
    def test_to_key_does_not_record_the_override(self, project, tmp_path, monkeypatch):
        """The regression this whole change exists for: the recorded key of a
        rootless PathInput must be identical whether or not a root is pinned,
        or GUI-launched and terminal-launched runs of the same input land under
        different keys and the canvas shows two nodes for one input."""
        monkeypatch.chdir(tmp_path / "elsewhere")
        unpinned = PathInput("data/{subject}.mat").to_key()
        set_project_root(project)
        assert PathInput("data/{subject}.mat").to_key() == unpinned
        assert "proj" not in unpinned

    def test_root_folder_attribute_stays_none(self, project):
        set_project_root(project)
        assert PathInput("data/{subject}.mat").root_folder is None

    def test_pinning_is_not_the_same_as_declaring(self, project):
        """A pinned root and a declared root are different identities even
        when they name the same directory — which is why the GUI's
        graph_builder has to normalize the two when reading old history."""
        set_project_root(project)
        assert PathInput("data/{s}.mat").to_key() != PathInput(
            "data/{s}.mat", root_folder=str(project)
        ).to_key()


class TestEnvironmentIndependence:
    def test_override_survives_a_cwd_change(self, project, tmp_path, monkeypatch):
        set_project_root(project)
        monkeypatch.chdir(tmp_path / "elsewhere")
        assert _find_project_root() == project.resolve()
        monkeypatch.chdir(os.fspath(tmp_path))
        assert _find_project_root() == project.resolve()
