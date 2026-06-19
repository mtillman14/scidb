"""Integration test: MATLAB PathInput-only function with partial failure → grey.

Drives the **real MATLAB bridge flow** — ``scimatlab.bridge.for_each_prepare``
(which persists the expected combo set and resolves PathInput filesystem
discovery) followed by ``for_each_save`` (which routes through scidb's
``_save_results``, the same batch save path Python uses). This is how real MATLAB
``scidb.for_each`` saves; it excludes the resolved PathInput filepath from graph
constants at the source, so node-state needs no special handling.

Scenario (mirrors ``scidb.log`` / load_csv.m):
- ``load_csv`` takes one ``PathInput`` (``sub{subject}/trial{trial}.csv``) and
  declares 3 outputs: ``Time``, ``Force_Left``, ``Force_Right``.
- A full subject × trial grid is the expected set (an explicit
  ``metadata_iterables`` grid is persisted in full — a combo whose run fails
  shows as *missing*, exactly like ``test_state_realworld``).
- One combo's run fails (saves nothing) → node is grey.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from scidb import BaseVariable
from scimatlab.bridge import (
    MatlabLineageFcn,
    for_each_prepare,
    for_each_save,
    register_matlab_variable,
)
from scihist.state import check_node_state


FN_NAME = "load_csv"
FN_SOURCE_HASH = sha256(b"function [time,force_left,force_right]=load_csv(filepath)").hexdigest()

SUBJECTS = ["01", "02"]
TRIALS = ["01", "02", "03"]
FAILED_COMBO = ("02", "03")   # run fails → saves nothing → missing → grey
OUTPUTS = ["Time", "Force_Left", "Force_Right"]
N_EXPECTED = len(SUBJECTS) * len(TRIALS)        # 6
N_SUCCESS = N_EXPECTED - 1                       # 5


def _all_combos() -> list[tuple]:
    return [(s, t) for s in SUBJECTS for t in TRIALS]


def _successful_combos() -> list[tuple]:
    return [c for c in _all_combos() if c != FAILED_COMBO]


def _write_files(root, combos) -> None:
    """Create (dummy) CSV files so PathInput discovery finds these combos.

    Content is irrelevant — the bridge does not run the function (MATLAB would);
    we supply the output values in the result tables. Only file existence matters.
    """
    for subj, trial in combos:
        d = Path(root) / f"sub{subj}"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"trial{trial}.csv").write_text("time,force_left,force_right\n0,0,0\n")


def _path_spec(root) -> dict:
    return {
        "kind": "pathinput",
        "template": "sub{subject}/trial{trial}.csv",
        "root_folder": str(root),
    }


def _bridge_run(db, root, combos_to_save):
    """Run one MATLAB-style for_each over the full grid, saving the given combos.

    Mirrors the GUI/MATLAB sequence: ``for_each_prepare`` (persists the expected
    combo set + discovers files) → MATLAB builds per-output result tables →
    ``for_each_save`` (→ ``_save_results``).
    """
    prep = for_each_prepare(
        FN_NAME,
        FN_SOURCE_HASH,
        {"filepath": _path_spec(root)},
        OUTPUTS,
        {"subject": SUBJECTS, "trial": TRIALS},
        db=db,
    )
    handle = prep["handle"]
    full_combos = prep["full_combos"]
    output_names = prep["output_names"]

    save_set = set(combos_to_save)
    dfs = []
    for idx, oname in enumerate(output_names):
        rows = []
        for combo in full_combos:
            key = (combo["subject"], combo["trial"])
            if key not in save_set:
                continue
            # Distinct value per combo so content hashes differ.
            seed = SUBJECTS.index(combo["subject"]) * 10 + TRIALS.index(combo["trial"])
            rows.append({"subject": combo["subject"], "trial": combo["trial"],
                         oname: float(seed * 3 + idx + 1)})
        dfs.append(pd.DataFrame(rows))

    for_each_save(handle, dfs, save=True)


class TestMatlabPathInputPartialRunGoesGrey:
    """Function + all 3 output variables should turn grey after 15/16 success."""

    @pytest.fixture
    def matlab_run(self, db, tmp_path):
        for n in OUTPUTS:
            register_matlab_variable(n)
        outputs = [BaseVariable._all_subclasses[n] for n in OUTPUTS]

        _write_files(tmp_path, _all_combos())
        _bridge_run(db, tmp_path, _successful_combos())

        fn_proxy = MatlabLineageFcn(FN_SOURCE_HASH, FN_NAME, unpack_output=False)
        fn_proxy.__name__ = FN_NAME
        return {"fn": fn_proxy, "outputs": outputs, "root": str(tmp_path)}

    def test_function_state_is_grey(self, db, matlab_run):
        """Aggregate state across all 3 outputs: N-1 up_to_date, 1 missing → grey."""
        result = check_node_state(matlab_run["fn"], matlab_run["outputs"], db=db)
        assert result["state"] == "grey", (
            f"Expected grey ({N_SUCCESS}/{N_EXPECTED}), got {result['state']}. "
            f"Counts: {result['counts']}"
        )
        assert result["counts"]["up_to_date"] == N_SUCCESS
        assert result["counts"]["missing"] == 1
        assert result["counts"]["stale"] == 0

    @pytest.mark.parametrize("output_name", OUTPUTS)
    def test_each_output_variable_is_grey(self, db, matlab_run, output_name):
        """Each individual output variable also reports grey."""
        cls = BaseVariable._all_subclasses[output_name]
        result = check_node_state(matlab_run["fn"], [cls], db=db)
        assert result["state"] == "grey", (
            f"Expected {output_name} grey, got {result['state']}. "
            f"Counts: {result['counts']}"
        )
        assert result["counts"]["up_to_date"] == N_SUCCESS
        assert result["counts"]["missing"] == 1

    def test_grey_persists_across_db_close_reopen(self, db, matlab_run, tmp_path):
        """Partial-run grey must survive a full DB close/reopen cycle (GUI restart)."""
        from scidb import configure_database
        from scidb.database import _local

        before = check_node_state(matlab_run["fn"], matlab_run["outputs"], db=db)
        assert before["state"] == "grey"
        assert before["counts"]["up_to_date"] == N_SUCCESS
        assert before["counts"]["missing"] == 1

        db_path = db.dataset_db_path
        schema_keys = list(db.dataset_schema_keys)
        db.close()
        if hasattr(_local, "database"):
            delattr(_local, "database")

        reopened = configure_database(db_path, schema_keys)
        fresh_fn = MatlabLineageFcn(FN_SOURCE_HASH, FN_NAME, unpack_output=False)
        fresh_fn.__name__ = FN_NAME
        fresh_outputs = [BaseVariable._all_subclasses[n] for n in OUTPUTS]
        try:
            after = check_node_state(fresh_fn, fresh_outputs, db=reopened)
            assert after["state"] == "grey", (
                f"Expected grey to persist after reopen, got {after['state']}. "
                f"Counts: {after['counts']}"
            )
            assert after["counts"]["up_to_date"] == N_SUCCESS
            assert after["counts"]["missing"] == 1
            assert after["counts"]["stale"] == 0
        finally:
            reopened.close()

    def test_grey_goes_green_after_fix_and_rerun(self, db, matlab_run):
        """grey → re-run the previously-failing combo → green."""
        before = check_node_state(matlab_run["fn"], matlab_run["outputs"], db=db)
        assert before["state"] == "grey"
        assert before["counts"]["missing"] == 1

        # The fix lets the previously-failing combo run and save this time.
        _bridge_run(db, matlab_run["root"], _successful_combos() + [FAILED_COMBO])

        after = check_node_state(matlab_run["fn"], matlab_run["outputs"], db=db)
        assert after["state"] == "green", (
            f"Expected green after fix, got {after['state']}. Counts: {after['counts']}"
        )
        assert after["counts"]["up_to_date"] == N_EXPECTED
        assert after["counts"]["missing"] == 0
