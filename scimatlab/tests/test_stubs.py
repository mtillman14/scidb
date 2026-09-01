"""Materializing MATLAB classdefs for TOML-declared variables.

Regression cover for the failure in
``.claude/plan-matlab-variable-classdef-materialization.md``: a variable
declared in the entities file but never given a classdef made the run die
with ``Unrecognized function or variable 'RawEMG'`` from inside a
``for_each`` call, because materialization was gated on a
``[matlab] variable_dir`` the project never configured.
"""

from pathlib import Path

import pytest

from scimatlab.stubs import (
    DEFAULT_STUB_DIRNAME,
    classdef_text,
    variable_stub_dir,
    write_variable_classdefs,
)


@pytest.fixture(autouse=True)
def _clear_entities_cache():
    """``entities_path`` reads through ``scidb.entities``' mtime cache."""
    from scidb import entities

    entities.clear_cache()
    yield
    entities.clear_cache()


class TestVariableStubDir:
    def test_configured_variable_dir_wins(self, tmp_path):
        (tmp_path / "scistack.toml").write_text(
            'entities_file = "src/scistack_entities.toml"\n'
            "[matlab]\n"
            'variable_dir = "matlab/vars"\n',
            encoding="utf-8",
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "scistack_entities.toml").write_text(
            'variables = ["RawEMG"]\n', encoding="utf-8"
        )

        assert variable_stub_dir(tmp_path) == tmp_path / "matlab" / "vars"

    def test_defaults_beside_the_entities_file(self, tmp_path):
        """The case that produced the bug: entities declared, no
        variable_dir anywhere."""
        (tmp_path / "scistack.toml").write_text(
            'entities_file = "src/scistack_entities.toml"\n', encoding="utf-8"
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "scistack_entities.toml").write_text(
            'variables = ["RawEMG"]\n', encoding="utf-8"
        )

        assert (
            variable_stub_dir(tmp_path)
            == tmp_path / "src" / DEFAULT_STUB_DIRNAME
        )

    def test_none_without_an_entities_file(self, tmp_path):
        """Nothing to materialize from, so no directory is invented."""
        (tmp_path / "scistack.toml").write_text("modules = []\n", encoding="utf-8")

        assert variable_stub_dir(tmp_path) is None

    def test_none_without_a_project(self, tmp_path):
        assert variable_stub_dir(tmp_path) is None

    def test_configured_dir_wins_even_with_no_entities_file(self, tmp_path):
        (tmp_path / "scistack.toml").write_text(
            "[matlab]\nvariable_dir = \"m\"\n", encoding="utf-8"
        )

        assert variable_stub_dir(tmp_path) == tmp_path / "m"


class TestWriteVariableClassdefs:
    def test_writes_a_classdef_per_missing_name(self, tmp_path):
        result = write_variable_classdefs(["RawEMG", "Filtered"], target_dir=tmp_path)

        assert sorted(result["created"]) == ["Filtered", "RawEMG"]
        assert result["dir"] == str(tmp_path)
        text = (tmp_path / "RawEMG.m").read_text(encoding="utf-8")
        assert text.startswith("classdef RawEMG < scidb.BaseVariable")
        assert text == classdef_text("RawEMG")

    def test_never_overwrites_an_existing_file(self, tmp_path):
        hand_written = tmp_path / "RawEMG.m"
        hand_written.write_text("classdef RawEMG < scidb.BaseVariable\nend\n")

        result = write_variable_classdefs(["RawEMG"], target_dir=tmp_path)

        assert result["created"] == []
        assert result["skipped"] == ["RawEMG"]
        assert hand_written.read_text() == (
            "classdef RawEMG < scidb.BaseVariable\nend\n"
        )

    def test_directory_created_only_when_there_is_something_to_write(self, tmp_path):
        target = tmp_path / "scistack_variables"

        assert write_variable_classdefs([], target_dir=target)["created"] == []
        assert not target.exists()

        write_variable_classdefs(["RawEMG"], target_dir=target)
        assert (target / "RawEMG.m").exists()

    def test_resolves_the_target_from_the_project_when_not_given(self, tmp_path):
        (tmp_path / "scistack.toml").write_text(
            'entities_file = "src/scistack_entities.toml"\n', encoding="utf-8"
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "scistack_entities.toml").write_text(
            'variables = ["RawEMG"]\n', encoding="utf-8"
        )

        result = write_variable_classdefs(["RawEMG"], project_start=tmp_path)

        assert (
            Path(result["dir"]) == tmp_path / "src" / DEFAULT_STUB_DIRNAME
        )
        assert (Path(result["dir"]) / "RawEMG.m").exists()

    def test_nowhere_to_write_is_reported_not_raised(self, tmp_path):
        """A project with no entities file and no variable_dir: the names
        are named in ``errors`` so the caller can say which types will
        fail, instead of silently doing nothing."""
        result = write_variable_classdefs(["RawEMG"], project_start=tmp_path)

        assert result["dir"] == ""
        assert result["created"] == []
        assert any("RawEMG" in e for e in result["errors"])

    def test_write_failure_is_collected_per_name(self, tmp_path):
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")

        result = write_variable_classdefs(["RawEMG"], target_dir=blocker / "vars")

        assert result["created"] == []
        assert any("RawEMG" in e for e in result["errors"])
