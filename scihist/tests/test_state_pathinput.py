"""Tests for check_node_state with PathInput-only functions.

PathInput-only functions have no DB-variable inputs, so node completeness is
driven by the persisted expected-invocation set (``_for_each_expected``, written
at for_each time) tested via the real for_each + PathInput path. See
.claude/phase5-node-state-rewrite.md.
"""

import numpy as np
import pytest

from scidb import BaseVariable
from scilineage import lineage_fcn
from scihist import for_each
from scihist.state import check_node_state


# ---------------------------------------------------------------------------
# Variable types
# ---------------------------------------------------------------------------

class PathInputOutput(BaseVariable):
    schema_version = 1


class RawForFallback(BaseVariable):
    schema_version = 1


class ProcessedForFallback(BaseVariable):
    schema_version = 1


# ---------------------------------------------------------------------------
# Pipeline functions
# ---------------------------------------------------------------------------

@lineage_fcn
def import_from_file(filepath):
    """PathInput-only function: reads a single number from a file."""
    with open(filepath) as fh:
        return float(fh.read().strip())


@lineage_fcn
def process_raw(raw):
    return np.asarray(raw, dtype=float) * 2.0


# PathInput template + file helpers (real for_each path — mirrors
# test_state_realworld.py). Using the real path means the resolved filepath is
# excluded from graph constants at the source, so node-state needs no special
# handling. (The earlier per-combo ``scihist_save`` simulation made the raw
# array/path a CONSTANT, polluting derived branch_params — see
# .claude/phase5-node-state-rewrite.md.)
_GRID = [("1", "A"), ("1", "B"), ("2", "A"), ("2", "B")]


def _write_combo_files(root, combos):
    """Create ``sub{subject}/trial{trial}.txt`` files under ``root``."""
    from pathlib import Path
    for i, (subj, trial) in enumerate(combos):
        d = Path(root) / f"sub{subj}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"trial{trial}.txt").write_text(str(float(i + 1)))


def _path_input(root):
    from scifor import PathInput
    return PathInput("sub{subject}/trial{trial}.txt", root_folder=str(root))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCheckNodeStatePathInput:
    """Integration tests: check_node_state with a real PathInput-only function.

    Drives the actual for_each + PathInput path (not a per-combo save
    simulation), so the resolved filepath is excluded from graph constants at
    the source and node-state works without special-casing.
    """

    def _run(self, db, tmp_path, files):
        """Write files for ``files`` combos, then run import_from_file over the
        full 2×2 grid via the real for_each + PathInput path."""
        _write_combo_files(tmp_path, files)
        for_each(
            import_from_file,
            inputs={"filepath": _path_input(tmp_path)},
            outputs=[PathInputOutput],
            subject=["1", "2"],
            trial=["A", "B"],
            db=db,
        )

    def test_grey_when_partial_success(self, db, tmp_path):
        """3/4 combos have files, 1 missing → grey."""
        self._run(db, tmp_path, [("1", "A"), ("1", "B"), ("2", "B")])

        result = check_node_state(import_from_file, [PathInputOutput], db=db)
        assert result["state"] == "grey"
        assert result["counts"]["up_to_date"] == 3
        assert result["counts"]["missing"] == 1

    def test_green_when_all_succeed(self, db, tmp_path):
        """All 4 combos have files → green."""
        self._run(db, tmp_path, _GRID)

        result = check_node_state(import_from_file, [PathInputOutput], db=db)
        assert result["state"] == "green"
        assert result["counts"]["up_to_date"] == 4
        assert result["counts"]["missing"] == 0

    def test_red_when_none_succeed(self, db, tmp_path):
        """No files → no combos run → red."""
        # Create the root dir but no files, so PathInput discovers nothing.
        from pathlib import Path
        Path(tmp_path).mkdir(parents=True, exist_ok=True)
        for_each(
            import_from_file,
            inputs={"filepath": _path_input(tmp_path)},
            outputs=[PathInputOutput],
            subject=["1", "2"],
            trial=["A", "B"],
            db=db,
        )

        result = check_node_state(import_from_file, [PathInputOutput], db=db)
        assert result["state"] == "red"
        assert result["counts"]["up_to_date"] == 0

    def test_expected_replaced_on_rerun(self, db, tmp_path):
        """Re-run over a smaller grid; prior records remain → green.

        Same call site (inputs/where/flags unchanged) → same call_id, so the
        second run replaces the expected set with the smaller grid. The 4 records
        from the first run still exist, so every (now-2) expected combo is
        up_to_date → green.
        """
        self._run(db, tmp_path, _GRID)

        # Re-run over a 2-combo subset (same PathInput call site).
        for_each(
            import_from_file,
            inputs={"filepath": _path_input(tmp_path)},
            outputs=[PathInputOutput],
            subject=["1"],
            trial=["A", "B"],
            db=db,
        )

        result = check_node_state(import_from_file, [PathInputOutput], db=db)
        assert result["state"] == "green"
        assert result["counts"]["missing"] == 0
