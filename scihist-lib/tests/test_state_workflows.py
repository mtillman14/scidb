"""End-to-end workflow tests for scihist.state.

Complements test_state.py / test_state_realworld.py / test_state_pathinput.py
by covering user workflows that previously had no explicit test:

1. Multi-step propagation (3+ node chains) — data-change staleness walks
   through the full lineage graph.
2. Fork / Join DAG shapes.
3. Mixed input types (PathInput + Variable + Constant in a single function).
4. True multi-output functions (single @lineage_fcn returning a tuple).

Design decisions codified here (see .claude/node-state-deep-propagation.md):

- **Data-change propagation is deep**. If any ancestor record_id in the
  provenance chain has been superseded, the descendant combo is stale.
  scihist walks the full `_lineage` graph, not just one hop.

- **Function-code-change propagation is shallow**. `check_node_state(fn, ...)`
  can only detect a fn-hash mismatch for `fn` itself, because it has no
  handle on other functions. Propagation of "ancestor fn code changed but
  not yet re-run" to descendants is a GUI-layer DAG-walk concern.

  Workaround: once the ancestor is re-run, it produces a new record_id,
  which then cascades as a data change through the deep walk.
"""

import shutil
import numpy as np
import pandas as pd
from pathlib import Path

from scidb import BaseVariable
from scifor import PathInput
from scilineage import lineage_fcn
from scihist import for_each
from scihist.state import check_node_state

DATA_DIR = Path(__file__).parent.parent.parent / "examples" / "aim2" / "data"


# ---------------------------------------------------------------------------
# Variable types (module-level so BaseVariable registry picks them up)
# ---------------------------------------------------------------------------

class WfRaw(BaseVariable):
    schema_version = 1

class WfStep1(BaseVariable):
    schema_version = 1

class WfStep2(BaseVariable):
    schema_version = 1

class WfStep3(BaseVariable):
    schema_version = 1

class WfForkLeft(BaseVariable):
    schema_version = 1

class WfForkRight(BaseVariable):
    schema_version = 1

class WfJoined(BaseVariable):
    schema_version = 1

class WfBaseline(BaseVariable):
    schema_version = 1

class WfMixedOut(BaseVariable):
    schema_version = 1

class WfMultiA(BaseVariable):
    schema_version = 1

class WfMultiB(BaseVariable):
    schema_version = 1

class WfMultiC(BaseVariable):
    schema_version = 1


# ---------------------------------------------------------------------------
# Pipeline functions
# ---------------------------------------------------------------------------

@lineage_fcn
def step1(raw):
    return np.asarray(raw, dtype=float) * 2.0

@lineage_fcn
def step2(s1):
    return np.asarray(s1, dtype=float) + 1.0

@lineage_fcn
def step3(s2):
    return np.asarray(s2, dtype=float) - 0.5

@lineage_fcn
def fork_left(raw):
    return np.asarray(raw, dtype=float) * 10.0

@lineage_fcn
def fork_right(raw):
    return np.asarray(raw, dtype=float) * 100.0

@lineage_fcn
def join_sides(left, right):
    return float(np.sum(np.asarray(left) + np.asarray(right)))

@lineage_fcn
def mixed_inputs(filepath, baseline, scale):
    """PathInput + Variable + Constant, all in one function."""
    df = pd.read_csv(filepath)
    return float(np.mean(df["force_left"].values) - np.mean(np.asarray(baseline))) * float(scale)

@lineage_fcn(unpack_output=True)
def multi_output(raw):
    """Single function, three outputs — the canonical load_csv.m shape.
    Uses unpack_output=True so each tuple element becomes its own
    LineageFcnResult, which scifor then routes to the corresponding
    output class.
    """
    arr = np.asarray(raw, dtype=float)
    return arr * 1.0, arr * 2.0, arr * 3.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_raw(db, subjects=(1, 2), trials=("A", "B")):
    for subj in subjects:
        for trial in trials:
            WfRaw.save(np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
                       subject=subj, trial=trial, db=db)


# ---------------------------------------------------------------------------
# 1. Multi-step propagation
# ---------------------------------------------------------------------------

class TestMultiStepPropagation:
    """WfRaw → step1 → step2 → step3. A re-save of WfRaw must cascade to
    every downstream node via the deep lineage walk.
    """

    def _run_full_chain(self, db):
        _seed_raw(db)
        for_each(step1, inputs={"raw": WfRaw}, outputs=[WfStep1],
                 subject=[1, 2], trial=["A", "B"], db=db)
        for_each(step2, inputs={"s1": WfStep1}, outputs=[WfStep2],
                 subject=[1, 2], trial=["A", "B"], db=db)
        for_each(step3, inputs={"s2": WfStep2}, outputs=[WfStep3],
                 subject=[1, 2], trial=["A", "B"], db=db)

    def test_stale_propagates_through_three_hops(self, db):
        """Re-save WfRaw[1,A] → step1, step2, step3 all red for that combo."""
        self._run_full_chain(db)
        assert check_node_state(step1, [WfStep1], db=db)["state"] == "green"
        assert check_node_state(step2, [WfStep2], db=db)["state"] == "green"
        assert check_node_state(step3, [WfStep3], db=db)["state"] == "green"

        WfRaw.save(np.array([99.0] * 5), subject=1, trial="A", db=db)

        r1 = check_node_state(step1, [WfStep1], db=db)
        r2 = check_node_state(step2, [WfStep2], db=db)
        r3 = check_node_state(step3, [WfStep3], db=db)

        assert r1["state"] == "red"
        assert r2["state"] == "red", (
            f"step2 should be red — deep walk detects superseded WfRaw. "
            f"Got {r2['state']}."
        )
        assert r3["state"] == "red", (
            f"step3 should be red — 2-hop cascade from WfRaw. "
            f"Got {r3['state']}."
        )

        for r in (r1, r2, r3):
            assert r["counts"]["stale"] == 1
            assert r["counts"]["up_to_date"] == 3

    def test_midchain_fn_change_affects_only_checked_node(self, db):
        """Changing step2's code is detected only by check_node_state(step2).

        scihist cannot cascade ancestor-fn-code changes to descendants
        without a registry of current function objects. The GUI layer's
        DAG walk is responsible for propagating step2's 'red' to step3.
        Once step2 is re-run, the new record_id cascades as a data change.
        """
        self._run_full_chain(db)

        @lineage_fcn
        def step2_v2(s1):
            return np.asarray(s1, dtype=float) + 42.0
        step2_v2.__name__ = "step2"

        r1 = check_node_state(step1, [WfStep1], db=db)
        r2 = check_node_state(step2_v2, [WfStep2], db=db)
        r3 = check_node_state(step3, [WfStep3], db=db)

        assert r1["state"] == "green"
        assert r2["state"] == "red", "step2 fn hash mismatch"
        assert r3["state"] == "green", (
            "step3's own state stays green — scihist cannot see step2_v2. "
            "GUI layer must propagate step2's red to step3."
        )

    def test_new_upstream_combo_only_greys_direct_consumer(self, db):
        """New WfRaw combo → step1 grey; step2/step3 own-state stays green
        until step1 is re-run (which would add new WfStep1 records that
        step2 then sees as missing).
        """
        self._run_full_chain(db)
        WfRaw.save(np.array([7.0] * 5), subject=3, trial="A", db=db)

        r1 = check_node_state(step1, [WfStep1], db=db)
        r2 = check_node_state(step2, [WfStep2], db=db)
        r3 = check_node_state(step3, [WfStep3], db=db)

        assert r1["state"] == "grey"
        assert r1["counts"]["missing"] == 1
        assert r1["counts"]["up_to_date"] == 4
        assert r2["state"] == "green"
        assert r3["state"] == "green"


# ---------------------------------------------------------------------------
# 2. Fork / Join DAG shapes
# ---------------------------------------------------------------------------

class TestForkJoinPropagation:
    """WfRaw feeds fork_left and fork_right; join_sides consumes both."""

    def _run_fork_join(self, db):
        _seed_raw(db)
        for_each(fork_left, inputs={"raw": WfRaw}, outputs=[WfForkLeft],
                 subject=[1, 2], trial=["A", "B"], db=db)
        for_each(fork_right, inputs={"raw": WfRaw}, outputs=[WfForkRight],
                 subject=[1, 2], trial=["A", "B"], db=db)
        for_each(join_sides,
                 inputs={"left": WfForkLeft, "right": WfForkRight},
                 outputs=[WfJoined],
                 subject=[1, 2], trial=["A", "B"], db=db)

    def test_fork_one_upstream_taints_both_branches(self, db):
        """Re-save WfRaw[1,A] → both fork_left and fork_right go red for that combo."""
        self._run_fork_join(db)
        assert check_node_state(fork_left, [WfForkLeft], db=db)["state"] == "green"
        assert check_node_state(fork_right, [WfForkRight], db=db)["state"] == "green"

        WfRaw.save(np.array([42.0] * 5), subject=1, trial="A", db=db)

        rl = check_node_state(fork_left, [WfForkLeft], db=db)
        rr = check_node_state(fork_right, [WfForkRight], db=db)
        assert rl["state"] == "red"
        assert rr["state"] == "red"
        assert rl["counts"]["stale"] == 1
        assert rr["counts"]["stale"] == 1

    def test_join_cascades_from_root(self, db):
        """Re-save WfRaw[1,A] → join_sides red (deep 2-hop cascade).

        The join's immediate inputs (WfForkLeft/Right) haven't themselves
        been re-run, but WfRaw has been superseded. The deep lineage walk
        reaches WfRaw through the join's ancestors.
        """
        self._run_fork_join(db)
        assert check_node_state(join_sides, [WfJoined], db=db)["state"] == "green"

        WfRaw.save(np.array([42.0] * 5), subject=1, trial="A", db=db)

        rj = check_node_state(join_sides, [WfJoined], db=db)
        assert rj["state"] == "red", (
            f"join_sides should cascade from WfRaw through fork outputs. "
            f"Got {rj['state']} counts={rj['counts']}"
        )
        assert rj["counts"]["stale"] == 1

    def test_join_red_when_direct_input_resaved(self, db):
        """Re-save WfForkLeft directly → join_sides red for that combo."""
        self._run_fork_join(db)
        WfForkLeft.save(np.array([1e6] * 5), subject=1, trial="A", db=db)

        rj = check_node_state(join_sides, [WfJoined], db=db)
        assert rj["state"] == "red"
        assert rj["counts"]["stale"] == 1


# ---------------------------------------------------------------------------
# 3. Mixed input types
# ---------------------------------------------------------------------------

class TestMixedInputTypes:
    """Single function with PathInput + Variable + Constant inputs.

    PathInput and Variable share the (subject, trial) schema — seed one
    WfBaseline record per combo. Constant: scale=2.0.
    """

    SUBJECTS = ["01", "02"]
    TRIALS = ["01", "02"]

    def _seed_baselines(self, db):
        for subj in self.SUBJECTS:
            for trial in self.TRIALS:
                WfBaseline.save(np.array([0.1] * 5),
                                subject=subj, trial=trial, db=db)

    def _run_mixed(self, db, root=str(DATA_DIR)):
        self._seed_baselines(db)
        for_each(
            mixed_inputs,
            inputs={
                "filepath": PathInput(
                    "sub{subject}/trial{trial}.csv",
                    root_folder=root,
                ),
                "baseline": WfBaseline,
                "scale": 2.0,
            },
            outputs=[WfMixedOut],
            subject=self.SUBJECTS,
            trial=self.TRIALS,
            db=db,
        )

    def test_green_after_full_run_with_all_three_input_types(self, db):
        self._run_mixed(db)
        r = check_node_state(mixed_inputs, [WfMixedOut], db=db)
        assert r["state"] == "green", (
            f"Got {r['state']} counts={r['counts']}"
        )
        assert r["counts"]["up_to_date"] == 4
        assert r["counts"]["missing"] == 0

    def test_grey_when_pathinput_file_missing(self, db, tmp_path):
        for subj in self.SUBJECTS:
            (tmp_path / f"sub{subj}").mkdir()
            for trial in self.TRIALS:
                if (subj, trial) == ("02", "02"):
                    continue
                shutil.copy(
                    DATA_DIR / f"sub{subj}" / f"trial{trial}.csv",
                    tmp_path / f"sub{subj}" / f"trial{trial}.csv",
                )

        self._run_mixed(db, root=str(tmp_path))
        r = check_node_state(mixed_inputs, [WfMixedOut], db=db)
        assert r["state"] == "grey", f"Got {r['state']} counts={r['counts']}"
        assert r["counts"]["up_to_date"] == 3
        assert r["counts"]["missing"] == 1

    def test_red_when_variable_input_resaved(self, db):
        """Re-saving a Variable input → mixed fn red for affected combos."""
        self._run_mixed(db)
        assert check_node_state(mixed_inputs, [WfMixedOut], db=db)["state"] == "green"

        WfBaseline.save(np.array([9.9] * 5), subject="01", trial="01", db=db)

        r = check_node_state(mixed_inputs, [WfMixedOut], db=db)
        assert r["state"] == "red"
        assert r["counts"]["stale"] >= 1


# ---------------------------------------------------------------------------
# 4. True multi-output (single @lineage_fcn → tuple)
# ---------------------------------------------------------------------------

class TestMultiOutputSingleFunction:
    """One @lineage_fcn(unpack_output=True) returns a tuple; for_each saves
    each tuple element to a separate output type. check_node_state(fn, [A,B,C])
    aggregates across all three output classes.
    """

    def _run_multi(self, db):
        _seed_raw(db)
        for_each(
            multi_output,
            inputs={"raw": WfRaw},
            outputs=[WfMultiA, WfMultiB, WfMultiC],
            subject=[1, 2], trial=["A", "B"], db=db,
        )

    def test_green_when_all_three_outputs_present(self, db):
        self._run_multi(db)
        r = check_node_state(
            multi_output, [WfMultiA, WfMultiB, WfMultiC], db=db,
        )
        assert r["state"] == "green", (
            f"Got {r['state']} counts={r['counts']}"
        )
        assert r["counts"]["up_to_date"] == 4

    def test_missing_when_one_output_class_lacks_a_combo(self, db):
        """If WfMultiB's (1,A) record is excluded, that combo reports missing
        even though A and C have it (check_combo_state treats missing-any as
        missing-all for this combo)."""
        self._run_multi(db)

        db._duck._execute(
            "UPDATE _record_metadata SET excluded = TRUE "
            "WHERE variable_name = ? AND schema_id IN ("
            "  SELECT schema_id FROM _schema WHERE subject = ? AND trial = ?"
            ")",
            [WfMultiB.__name__, "1", "A"],
        )

        r = check_node_state(
            multi_output, [WfMultiA, WfMultiB, WfMultiC], db=db,
        )
        assert r["state"] == "grey", (
            f"Got {r['state']} counts={r['counts']}"
        )
        assert r["counts"]["missing"] == 1
        assert r["counts"]["up_to_date"] == 3

    def test_all_outputs_go_stale_together_on_input_resave(self, db):
        """A single upstream input serves all 3 outputs — re-saving WfRaw
        taints every output class for that combo via the shared lineage."""
        self._run_multi(db)
        assert check_node_state(
            multi_output, [WfMultiA, WfMultiB, WfMultiC], db=db,
        )["state"] == "green"

        WfRaw.save(np.array([123.0] * 5), subject=1, trial="A", db=db)

        r = check_node_state(
            multi_output, [WfMultiA, WfMultiB, WfMultiC], db=db,
        )
        assert r["state"] == "red"
        assert r["counts"]["stale"] == 1
        assert r["counts"]["up_to_date"] == 3
