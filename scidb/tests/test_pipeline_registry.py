"""Pipeline registry: deferred for_each registration and pull execution.

``db.pipeline(name)`` activates a Pipeline as the ambient registration
target: subsequent ``for_each`` calls register StepSpecs (returning Step
handles) instead of executing. ``pipeline=None`` forces an eager call;
``pipeline=other`` targets a non-ambient pipeline. Dependency edges are
inferred from variable types, so ``run_all``/``run_until`` execute in
topological order regardless of registration order, with
``skip_computed=True`` by default (memoized pull execution). ``plan()`` is
the non-executing dry run. Design: docs/claude/endpoint-first-pipelines.md.
"""

import numpy as np
import pytest

from scidb import (
    BaseVariable,
    NotFoundError,
    NotRegisteredError,
    Pipeline,
    PipelineCycleError,
    Step,
    active_pipeline,
    configure_database,
    for_each,
)

# A never-computed variable type raises NotFoundError if registered (e.g. by
# an earlier save of the same class) and NotRegisteredError otherwise.
NOT_STORED = (NotFoundError, NotRegisteredError)
from scidb.database import _local
from scidb.pipeline import _reset_pipeline_state, _unrun_pipelines


SCHEMA = ["subject", "trial"]
SUBJECTS = ["1", "2"]
TRIALS = ["1", "2"]


@pytest.fixture
def db(tmp_path):
    _reset_pipeline_state()
    db = configure_database(tmp_path / "registry.duckdb", SCHEMA)
    yield db
    db.close()
    if hasattr(_local, "database"):
        delattr(_local, "database")
    _reset_pipeline_state()


class RawSignal(BaseVariable):
    schema_version = 1


class Filtered(BaseVariable):
    schema_version = 1


class Speed(BaseVariable):
    schema_version = 1


class Unrelated(BaseVariable):
    schema_version = 1


class UnrelatedOut(BaseVariable):
    schema_version = 1


def _seed(db):
    for s in SUBJECTS:
        for t in TRIALS:
            RawSignal.save(np.array([2.0, 4.0, 6.0]), subject=s, trial=t)
            Unrelated.save(np.array([9.0]), subject=s, trial=t)


# Call-counting step functions. Counters are function attributes so each
# test can reset them; the functions themselves must be module-level and
# NAMED (stable identity for fn hashing / endpoint detection).

def halve(signal):
    halve.calls += 1
    return np.asarray(signal, dtype=float).ravel() / 2.0


def mean_of(filtered):
    mean_of.calls += 1
    return float(np.mean(np.asarray(filtered, dtype=float)))


def negate(unrelated):
    negate.calls += 1
    return -np.asarray(unrelated, dtype=float).ravel()


@pytest.fixture(autouse=True)
def _reset_counters():
    halve.calls = 0
    mean_of.calls = 0
    negate.calls = 0


def _register_chain(db):
    """Register the 3-step graph DELIBERATELY out of dependency order:
    consumer first, producer second, plus one unrelated branch."""
    for_each(mean_of, {"filtered": Filtered}, [Speed],
             subject=SUBJECTS, trial=TRIALS, db=db)
    for_each(halve, {"signal": RawSignal}, [Filtered],
             subject=SUBJECTS, trial=TRIALS, db=db)
    for_each(negate, {"unrelated": Unrelated}, [UnrelatedOut],
             subject=SUBJECTS, trial=TRIALS, db=db)


# ---------------------------------------------------------------------------
# Registration behavior
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_ambient_registration_defers_execution(self, db):
        _seed(db)
        pipe = db.pipeline("gait")
        assert active_pipeline() is pipe

        handle = for_each(halve, {"signal": RawSignal}, [Filtered],
                          subject=SUBJECTS, trial=TRIALS, db=db)

        assert isinstance(handle, Step)
        assert halve.calls == 0  # nothing executed
        assert len(pipe.steps) == 1
        with pytest.raises(NOT_STORED):
            Filtered.load(subject="1", trial="1")  # nothing saved

    def test_pipeline_none_forces_eager_while_active(self, db):
        _seed(db)
        db.pipeline("gait")

        result = for_each(halve, {"signal": RawSignal}, [Filtered],
                          subject=SUBJECTS, trial=TRIALS, db=db,
                          pipeline=None)

        assert not isinstance(result, Step)
        assert halve.calls == len(SUBJECTS) * len(TRIALS)
        assert Filtered.load(subject="1", trial="1") is not None

    def test_pipeline_kwarg_targets_non_ambient_pipeline(self, db):
        ambient = db.pipeline("ambient")
        other = Pipeline("other", db=db)  # created, NOT activated

        for_each(halve, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db, pipeline=other)

        assert len(other.steps) == 1
        assert len(ambient.steps) == 0
        assert halve.calls == 0

    def test_no_active_pipeline_is_eager_unchanged(self, db):
        _seed(db)
        result = for_each(halve, {"signal": RawSignal}, [Filtered],
                          subject=SUBJECTS, trial=TRIALS, db=db)
        assert not isinstance(result, Step)
        assert halve.calls == len(SUBJECTS) * len(TRIALS)

    def test_invalid_pipeline_kwarg_raises(self, db):
        with pytest.raises(TypeError, match="pipeline="):
            for_each(halve, {"signal": RawSignal}, [Filtered],
                     subject=SUBJECTS, trial=TRIALS, db=db,
                     pipeline="not-a-pipeline")

    def test_step_handle_fails_fast_on_data_use(self, db):
        db.pipeline("gait")
        handle = for_each(halve, {"signal": RawSignal}, [Filtered],
                          subject=SUBJECTS, trial=TRIALS, db=db)

        with pytest.raises(AttributeError, match="deferred pipeline step"):
            handle.head()
        with pytest.raises(TypeError, match="not.*iterable"):
            list(handle)


# ---------------------------------------------------------------------------
# Graph + execution
# ---------------------------------------------------------------------------


class TestExecution:
    def test_run_all_executes_in_dependency_order(self, db):
        _seed(db)
        pipe = db.pipeline("gait")
        _register_chain(db)  # consumer registered BEFORE its producer

        pipe.run_all()

        assert halve.calls == 4
        assert mean_of.calls == 4
        assert negate.calls == 4
        # mean_of consumed real Filtered data → the chain ran in order.
        rec = Speed.load(subject="1", trial="1")
        value = rec.data if hasattr(rec, "data") else rec
        assert float(np.asarray(value).ravel()[0]) \
            == pytest.approx(2.0)  # mean([1,2,3])

    def test_run_until_runs_only_ancestors_and_target(self, db):
        _seed(db)
        pipe = db.pipeline("gait")
        _register_chain(db)

        pipe.run_until(mean_of)

        assert halve.calls == 4      # ancestor ran
        assert mean_of.calls == 4    # target ran
        assert negate.calls == 0     # unrelated branch untouched
        with pytest.raises(NOT_STORED):
            UnrelatedOut.load(subject="1", trial="1")

    def test_second_run_skips_current_steps(self, db):
        _seed(db)
        pipe = db.pipeline("gait")
        _register_chain(db)
        pipe.run_until(mean_of)
        calls_after_first = (halve.calls, mean_of.calls)

        pipe.run_until(mean_of)  # default skip_computed=True → all current

        assert (halve.calls, mean_of.calls) == calls_after_first

    def test_pipeline_run_identity_matches_eager_run(self, db):
        """A step run via the pipeline must produce the same computation
        identity as the same call run eagerly: an eager re-run with
        skip_computed=True must skip every combo (zero fn calls)."""
        _seed(db)
        pipe = db.pipeline("gait")
        for_each(halve, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db)
        pipe.run_all()
        assert halve.calls == 4

        for_each(halve, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db,
                 pipeline=None, skip_computed=True)

        assert halve.calls == 4  # all combos skipped → identical identity

    def test_run_deactivates_pipeline(self, db):
        _seed(db)
        pipe = db.pipeline("gait")
        for_each(halve, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db)
        pipe.run_all()

        assert active_pipeline() is None
        # Post-run for_each calls are eager again.
        result = for_each(halve, {"signal": RawSignal}, [Filtered],
                          subject=SUBJECTS, trial=TRIALS, db=db,
                          skip_computed=True)
        assert not isinstance(result, Step)

    def test_run_until_unknown_target_raises(self, db):
        pipe = db.pipeline("gait")
        for_each(halve, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db)
        with pytest.raises(ValueError, match="no step matching"):
            pipe.run_until(mean_of)

    def test_cycle_raises(self, db):
        pipe = db.pipeline("gait")

        def refine(filtered):
            return filtered

        for_each(refine, {"filtered": Filtered}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db)
        with pytest.raises(PipelineCycleError, match="cycle"):
            pipe.run_all()

    def test_multiple_producers_all_precede_consumer(self, db):
        """Two variant branches producing Filtered are BOTH prerequisites
        of a Filtered consumer (fan-in, not ambiguity — graph level only)."""
        pipe = Pipeline("graph-only", db=db)

        def halve_a(signal):
            return signal

        def halve_b(signal):
            return signal

        for_each(mean_of, {"filtered": Filtered}, [Speed],
                 subject=SUBJECTS, trial=TRIALS, db=db, pipeline=pipe)
        for_each(halve_a, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db, pipeline=pipe)
        for_each(halve_b, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db, pipeline=pipe)

        pairs = pipe._composed_steps()
        order = pipe._topo_order(pairs)
        names = [pairs[i][1].name for i in order]
        assert names.index("mean_of") > names.index("halve_a")
        assert names.index("mean_of") > names.index("halve_b")


# ---------------------------------------------------------------------------
# plan() dry run
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_reports_red_then_green(self, db):
        _seed(db)
        pipe = db.pipeline("gait")
        _register_chain(db)

        before = pipe.plan()
        names = [e["step"] for e in before]
        assert names.index("halve") < names.index("mean_of")  # topo order
        assert all(e["state"] in ("red", "unknown") for e in before)
        assert halve.calls == 0  # plan never executes

        pipe.run_all()
        after = pipe.plan()
        assert all(e["state"] == "green" for e in after)

    def test_plan_with_target_excludes_unrelated_branch(self, db):
        _seed(db)
        pipe = db.pipeline("gait")
        _register_chain(db)

        entries = pipe.plan(target=mean_of)

        names = [e["step"] for e in entries]
        assert "negate" not in names
        assert set(names) == {"halve", "mean_of"}


# ---------------------------------------------------------------------------
# Footgun mitigations
# ---------------------------------------------------------------------------


class TestNeverRunWarning:
    def test_unrun_pipeline_is_flagged(self, db):
        pipe = db.pipeline("forgotten")
        for_each(halve, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db)

        assert pipe in _unrun_pipelines()

    def test_run_plan_or_deactivate_acknowledges(self, db):
        _seed(db)
        ran = db.pipeline("ran")
        for_each(halve, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db)
        ran.run_all()
        assert ran not in _unrun_pipelines()

        planned = db.pipeline("planned")
        for_each(mean_of, {"filtered": Filtered}, [Speed],
                 subject=SUBJECTS, trial=TRIALS, db=db)
        planned.plan()
        assert planned not in _unrun_pipelines()

        escaped = db.pipeline("escaped")
        for_each(negate, {"unrelated": Unrelated}, [UnrelatedOut],
                 subject=SUBJECTS, trial=TRIALS, db=db)
        escaped.deactivate()
        assert escaped not in _unrun_pipelines()

    def test_empty_pipeline_is_not_flagged(self, db):
        pipe = db.pipeline("empty")
        pipe.deactivate()
        assert pipe not in _unrun_pipelines()


# ---------------------------------------------------------------------------
# Endpoint interaction (finalized targeting)
# ---------------------------------------------------------------------------


class TestEndpointFinalized:
    def test_finalized_applies_to_target_endpoint_only(self, db, tmp_path):
        matplotlib = pytest.importorskip("matplotlib")
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from scidb import PathOutput

        class GaitFigure(BaseVariable):
            schema_version = 1

        def plot_filtered(filtered, filename):
            fig, ax = plt.subplots()
            ax.plot(np.asarray(filtered).ravel())
            return fig

        _seed(db)
        plots = tmp_path / "figs"
        plots.mkdir()
        pipe = db.pipeline("report")
        for_each(halve, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db)
        for_each(plot_filtered,
                 {"filtered": Filtered,
                  "filename": PathOutput(str(plots / "{subject}_{trial}.png"))},
                 [GaitFigure],
                 subject=SUBJECTS, trial=TRIALS, db=db)  # registered as DRAFT

        pipe.run_until("plot_filtered", finalized=True)

        # Upstream processing saved normally; endpoint recorded (not draft).
        assert Filtered.load(subject="1", trial="1") is not None
        assert GaitFigure.load(subject="1", trial="1") is not None
        assert (plots / "1_1.png").exists()


# ---------------------------------------------------------------------------
# Composition (uses=)
# ---------------------------------------------------------------------------


def double_unrelated(unrelated):
    return np.asarray(unrelated, dtype=float) * 2


class TestComposition:
    """Pipelines declare other pipelines as dependencies (uses=): graphs
    union, run_until/plan resolve producers across the boundary, run_all
    stays scoped to own steps + ancestors."""

    def _loading(self, db):
        """A 'loading' pipeline with one useful producer (halve -> Filtered)
        and one step unrelated to the analyses (negate -> UnrelatedOut)."""
        loading = Pipeline("loading", db=db)
        for_each(halve, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db, pipeline=loading)
        for_each(negate, {"unrelated": Unrelated}, [UnrelatedOut],
                 subject=SUBJECTS, trial=TRIALS, db=db, pipeline=loading)
        return loading

    def _analysis_using(self, db, loading):
        analysis = db.pipeline("analysis", uses=[loading])
        for_each(mean_of, {"filtered": Filtered}, [Speed],
                 subject=SUBJECTS, trial=TRIALS, db=db)
        return analysis

    def test_run_until_resolves_producer_in_used_pipeline(self, db):
        _seed(db)
        analysis = self._analysis_using(db, self._loading(db))

        analysis.run_until(mean_of)

        assert halve.calls == 4      # producer inside `loading` ran first
        assert mean_of.calls == 4
        assert negate.calls == 0     # unrelated used-pipeline step untouched
        rec = Speed.load(subject="1", trial="1")
        value = rec.data if hasattr(rec, "data") else rec
        assert float(np.asarray(value).ravel()[0]) == pytest.approx(2.0)

    def test_run_all_scope_is_own_steps_plus_ancestors(self, db):
        _seed(db)
        analysis = self._analysis_using(db, self._loading(db))

        analysis.run_all()

        assert halve.calls == 4      # ancestor of an own step
        assert mean_of.calls == 4    # own step
        assert negate.calls == 0     # in `loading` but not an ancestor

    def test_run_all_with_no_own_steps_runs_nothing(self, db):
        loading = self._loading(db)
        umbrella = db.pipeline("umbrella", uses=[loading])

        results = umbrella.run_all()

        assert results == []
        assert halve.calls == 0 and negate.calls == 0
        assert active_pipeline() is None  # early return still deactivates

    def test_target_inside_used_pipeline(self, db):
        _seed(db)
        analysis = self._analysis_using(db, self._loading(db))

        analysis.run_until(halve)

        assert halve.calls == 4
        assert mean_of.calls == 0

    def test_diamond_dedupes_shared_pipeline(self, db):
        base = Pipeline("base", db=db)
        for_each(halve, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, db=db, pipeline=base)
        left = Pipeline("left", db=db, uses=[base])
        right = Pipeline("right", db=db, uses=[base])
        top = Pipeline("top", db=db, uses=[left, right])

        pairs = top._composed_steps()

        base_specs = [s for (o, s) in pairs if o is base]
        assert len(base_specs) == 1  # same object everywhere -> appears once

    def test_pipeline_cycle_raises_at_declaration(self, db):
        a = Pipeline("a", db=db)
        b = Pipeline("b", db=db, uses=[a])
        with pytest.raises(PipelineCycleError, match="cycle between pipelines"):
            a.use(b)
        with pytest.raises(PipelineCycleError):
            a.use(a)

    def test_cross_database_uses_raises(self, db):
        other = Pipeline("other", db="a-different-db")
        with pytest.raises(ValueError, match="different database"):
            Pipeline("main", db=db, uses=[other])

    def test_db_none_used_pipeline_inherits(self, db):
        """A used pipeline bound to no db resolves to the user's db at run
        time (step option -> owner db -> running pipeline's db)."""
        _seed(db)
        loading = Pipeline("loading")  # no db bound anywhere
        for_each(halve, {"signal": RawSignal}, [Filtered],
                 subject=SUBJECTS, trial=TRIALS, pipeline=loading)
        analysis = db.pipeline("analysis", uses=[loading])
        for_each(mean_of, {"filtered": Filtered}, [Speed],
                 subject=SUBJECTS, trial=TRIALS, db=db)

        analysis.run_until(mean_of)

        assert halve.calls == 4
        assert Filtered.load(subject="1", trial="1") is not None

    def test_parent_run_acknowledges_executed_used_pipeline_only(self, db):
        _seed(db)
        loading = self._loading(db)
        spare = Pipeline("spare", db=db)  # used, but nothing consumes it
        for_each(double_unrelated, {"unrelated": Unrelated}, [UnrelatedOut],
                 subject=SUBJECTS, trial=TRIALS, db=db, pipeline=spare)

        analysis = db.pipeline("analysis", uses=[loading, spare])
        for_each(mean_of, {"filtered": Filtered}, [Speed],
                 subject=SUBJECTS, trial=TRIALS, db=db)
        assert loading in _unrun_pipelines()
        assert spare in _unrun_pipelines()

        analysis.run_until(mean_of)

        assert loading not in _unrun_pipelines()  # its step executed
        assert spare in _unrun_pipelines()        # used but never executed

    def test_plan_carries_owner_names(self, db):
        _seed(db)
        analysis = self._analysis_using(db, self._loading(db))

        entries = analysis.plan(target=mean_of)

        owners = {e["step"]: e["pipeline"] for e in entries}
        assert owners == {"halve": "loading", "mean_of": "analysis"}

    def test_second_composed_run_skips_across_boundary(self, db):
        _seed(db)
        analysis = self._analysis_using(db, self._loading(db))
        analysis.run_until(mean_of)
        snapshot = (halve.calls, mean_of.calls)

        analysis.run_until(mean_of)

        assert (halve.calls, mean_of.calls) == snapshot
