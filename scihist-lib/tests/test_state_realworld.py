"""Real-world scenario tests: scihist.state with CSV data.

Mirrors the aim2 pipeline: a function reading CSV files iterated across
3 subjects × 5 trials (15 combos total). Key scenarios not covered by
the existing contrived tests:

- Realistic dataset scale (3×5 vs 2×2)
- Function errors mid-run for some combos → grey (not omitting combos
  from the iteration range, but failing during execution)
- All combos fail → red
- Multi-output functions (3 outputs like load_csv.m returning
  time, force_left, force_right)
"""

import shutil
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from scidb import BaseVariable
from scilineage import lineage_fcn
from scifor import PathInput
from scihist import for_each
from scihist.state import check_node_state

DATA_DIR = Path(__file__).parent.parent.parent / "examples" / "aim2" / "data"
SUBJECTS = ["01", "02", "03"]
TRIALS = ["01", "02", "03", "04", "05"]


# ---------------------------------------------------------------------------
# Variable types — module-level for BaseVariable registry
# ---------------------------------------------------------------------------

class RwTime(BaseVariable):
    schema_version = 1

class RwForceLeft(BaseVariable):
    schema_version = 1

class RwForceRight(BaseVariable):
    schema_version = 1

class RwPeakForce(BaseVariable):
    schema_version = 1


# ---------------------------------------------------------------------------
# Pipeline functions
# ---------------------------------------------------------------------------

@lineage_fcn
def load_time(filepath):
    """Python equivalent of load_csv.m — returns time column."""
    df = pd.read_csv(filepath)
    return df["time"].values


@lineage_fcn
def load_force_left(filepath):
    df = pd.read_csv(filepath)
    return df["force_left"].values


@lineage_fcn
def load_force_right(filepath):
    df = pd.read_csv(filepath)
    return df["force_right"].values


@lineage_fcn
def compute_peak(force_left, force_right):
    """Downstream function: peak combined force."""
    return float(np.max(np.abs(np.asarray(force_left) + np.asarray(force_right))))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_forces(db, subjects=SUBJECTS, trials=TRIALS):
    """Seed ForceLeft and ForceRight records from real CSV data."""
    for subj in subjects:
        for trial in trials:
            path = DATA_DIR / f"sub{subj}" / f"trial{trial}.csv"
            df = pd.read_csv(path)
            RwForceLeft.save(df["force_left"].values, subject=subj, trial=trial, db=db)
            RwForceRight.save(df["force_right"].values, subject=subj, trial=trial, db=db)


def _path_input():
    return PathInput(
        "sub{subject}/trial{trial}.csv",
        root_folder=str(DATA_DIR),
    )


# ---------------------------------------------------------------------------
# Tests: PathInput + real CSV data, single output
# ---------------------------------------------------------------------------

class TestCsvLoadNodeState:
    """check_node_state with PathInput over real 3-subject × 5-trial CSV data."""

    def test_green_after_full_run(self, db):
        for_each(
            load_time,
            inputs={"filepath": _path_input()},
            outputs=[RwTime],
            subject=SUBJECTS,
            trial=TRIALS,
            db=db,
        )
        result = check_node_state(load_time, [RwTime], db=db)
        assert result["state"] == "green"
        assert result["counts"]["up_to_date"] == 15
        assert result["counts"]["missing"] == 0
        assert result["counts"]["stale"] == 0

    def test_grey_when_one_combo_errors(self, db, tmp_path):
        """Grey when one trial file is missing (function raises FileNotFoundError).

        Copies all files except sub03/trial05 to tmp_path, so that combo
        raises during execution while the other 14 succeed.  Mirrors the
        real scenario where subject=01, trial=06 raised 'Assertion failed'
        during MATLAB execution.
        """
        for subj in SUBJECTS:
            (tmp_path / f"sub{subj}").mkdir()
            for trial in TRIALS:
                src = DATA_DIR / f"sub{subj}" / f"trial{trial}.csv"
                dst = tmp_path / f"sub{subj}" / f"trial{trial}.csv"
                if subj == "03" and trial == "05":
                    continue  # leave this one missing → FileNotFoundError
                shutil.copy(src, dst)

        pi = PathInput("sub{subject}/trial{trial}.csv", root_folder=str(tmp_path))
        for_each(
            load_time,
            inputs={"filepath": pi},
            outputs=[RwTime],
            subject=SUBJECTS,
            trial=TRIALS,
            db=db,
        )

        result = check_node_state(load_time, [RwTime], db=db)
        assert result["state"] == "grey", (
            f"Expected grey (14/15 combos ran), got {result['state']}. "
            f"Counts: {result['counts']}"
        )
        assert result["counts"]["up_to_date"] == 14
        assert result["counts"]["missing"] == 1

    def test_grey_when_multiple_combos_error(self, db, tmp_path):
        """Grey when several trial files are missing — partial completion."""
        missing = {("01", "03"), ("02", "04"), ("03", "01")}
        for subj in SUBJECTS:
            (tmp_path / f"sub{subj}").mkdir()
            for trial in TRIALS:
                if (subj, trial) not in missing:
                    shutil.copy(
                        DATA_DIR / f"sub{subj}" / f"trial{trial}.csv",
                        tmp_path / f"sub{subj}" / f"trial{trial}.csv",
                    )

        pi = PathInput("sub{subject}/trial{trial}.csv", root_folder=str(tmp_path))
        for_each(
            load_time,
            inputs={"filepath": pi},
            outputs=[RwTime],
            subject=SUBJECTS,
            trial=TRIALS,
            db=db,
        )

        result = check_node_state(load_time, [RwTime], db=db)
        assert result["state"] == "grey"
        assert result["counts"]["up_to_date"] == 12
        assert result["counts"]["missing"] == 3

    def test_red_when_all_combos_error(self, db, tmp_path):
        """Red when no files exist — every combo raises FileNotFoundError."""
        # tmp_path is empty — all 15 combos will fail
        for subj in SUBJECTS:
            (tmp_path / f"sub{subj}").mkdir()

        pi = PathInput("sub{subject}/trial{trial}.csv", root_folder=str(tmp_path))
        for_each(
            load_time,
            inputs={"filepath": pi},
            outputs=[RwTime],
            subject=SUBJECTS,
            trial=TRIALS,
            db=db,
        )

        result = check_node_state(load_time, [RwTime], db=db)
        assert result["state"] == "red"
        assert result["counts"]["up_to_date"] == 0
        assert result["counts"]["missing"] == 15


# ---------------------------------------------------------------------------
# Tests: multi-output (3 outputs, like load_csv.m)
# ---------------------------------------------------------------------------

class TestMultiOutputNodeState:
    """check_node_state with separate functions for each of load_csv.m's 3 outputs.

    load_csv.m returns [time, force_left, force_right].  In Python we model
    this as three separate @lineage_fcn functions, one per output.  The state
    of each output type is independent — if one function's combo fails, only
    that output goes grey.
    """

    def test_green_all_three_outputs_after_full_run(self, db):
        for_each(
            load_force_left,
            inputs={"filepath": _path_input()},
            outputs=[RwForceLeft],
            subject=SUBJECTS,
            trial=TRIALS,
            db=db,
        )
        for_each(
            load_force_right,
            inputs={"filepath": _path_input()},
            outputs=[RwForceRight],
            subject=SUBJECTS,
            trial=TRIALS,
            db=db,
        )

        left_result = check_node_state(load_force_left, [RwForceLeft], db=db)
        right_result = check_node_state(load_force_right, [RwForceRight], db=db)

        assert left_result["state"] == "green"
        assert right_result["state"] == "green"
        assert left_result["counts"]["up_to_date"] == 15
        assert right_result["counts"]["up_to_date"] == 15

    def test_grey_one_output_when_partial_failure(self, db, tmp_path):
        """When one file is missing, its output is grey while others are green."""
        missing = {("02", "03")}
        for subj in SUBJECTS:
            (tmp_path / f"sub{subj}").mkdir()
            for trial in TRIALS:
                if (subj, trial) not in missing:
                    shutil.copy(
                        DATA_DIR / f"sub{subj}" / f"trial{trial}.csv",
                        tmp_path / f"sub{subj}" / f"trial{trial}.csv",
                    )

        pi = PathInput("sub{subject}/trial{trial}.csv", root_folder=str(tmp_path))
        for_each(
            load_force_left,
            inputs={"filepath": pi},
            outputs=[RwForceLeft],
            subject=SUBJECTS,
            trial=TRIALS,
            db=db,
        )
        for_each(
            load_force_right,
            inputs={"filepath": pi},
            outputs=[RwForceRight],
            subject=SUBJECTS,
            trial=TRIALS,
            db=db,
        )

        left_result = check_node_state(load_force_left, [RwForceLeft], db=db)
        right_result = check_node_state(load_force_right, [RwForceRight], db=db)

        assert left_result["state"] == "grey"
        assert right_result["state"] == "grey"
        assert left_result["counts"]["up_to_date"] == 14
        assert left_result["counts"]["missing"] == 1


# ---------------------------------------------------------------------------
# Tests: downstream function after partial upstream run
# ---------------------------------------------------------------------------

class TestDownstreamStateAfterPartialUpstream:
    """check_node_state for a downstream function when upstream has missing combos.

    compute_peak(force_left, force_right) depends on RwForceLeft and
    RwForceRight.  If those are only partially populated, compute_peak
    can only run for the combos that exist — its own state is green for
    what it ran, but the GUI propagates upstream grey down to it.
    """

    def test_downstream_green_for_available_combos(self, db):
        """compute_peak runs successfully for all seeded combos."""
        _seed_forces(db)
        for_each(
            compute_peak,
            inputs={"force_left": RwForceLeft, "force_right": RwForceRight},
            outputs=[RwPeakForce],
            subject=SUBJECTS,
            trial=TRIALS,
            db=db,
        )
        result = check_node_state(compute_peak, [RwPeakForce], db=db)
        assert result["state"] == "green"
        assert result["counts"]["up_to_date"] == 15

    def test_downstream_grey_when_upstream_partially_seeded(self, db):
        """compute_peak is grey when upstream only covers 2 of 3 subjects.

        Only sub01 and sub02 have force data seeded; sub03 data is absent.
        compute_peak ran for what was available (10 combos).  Expected
        combos are inferred from available RwForceLeft records, so 5
        sub03 combos are missing.
        """
        _seed_forces(db, subjects=["01", "02"])  # sub03 intentionally absent
        for_each(
            compute_peak,
            inputs={"force_left": RwForceLeft, "force_right": RwForceRight},
            outputs=[RwPeakForce],
            subject=["01", "02"],
            trial=TRIALS,
            db=db,
        )

        # Now seed sub03 data (simulates new data arriving after first run)
        _seed_forces(db, subjects=["03"])

        result = check_node_state(compute_peak, [RwPeakForce], db=db)
        assert result["state"] == "grey", (
            f"Expected grey (sub03 force data added after run), "
            f"got {result['state']}. Counts: {result['counts']}"
        )
        assert result["counts"]["up_to_date"] == 10
        assert result["counts"]["missing"] == 5

    def test_downstream_red_when_stale_after_upstream_update(self, db):
        """compute_peak goes red when an upstream force record is re-saved."""
        _seed_forces(db)
        for_each(
            compute_peak,
            inputs={"force_left": RwForceLeft, "force_right": RwForceRight},
            outputs=[RwPeakForce],
            subject=SUBJECTS,
            trial=TRIALS,
            db=db,
        )
        # Re-save one upstream record → makes its output stale
        path = DATA_DIR / "sub01" / "trial01.csv"
        df = pd.read_csv(path)
        RwForceLeft.save(df["force_left"].values * 2.0, subject="01", trial="01", db=db)

        result = check_node_state(compute_peak, [RwPeakForce], db=db)
        assert result["state"] == "red"
        assert result["counts"]["stale"] >= 1
