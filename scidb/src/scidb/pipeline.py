"""Pipeline concepts: the ``@scistack`` marker and the ``Pipeline`` registry.

Two related pieces live here:

1. **The ``@scistack`` marker** — tags a plain Python function so scistack
   pays attention to it: :mod:`scidb.discover` collects tagged functions
   (GUI step-palette discovery), and :func:`scidb.for_each` reads the
   per-function ``generates_file`` option. The marker does **not** wrap the
   function or change its return value.

2. **The ``Pipeline`` registry** — deferred ``for_each`` registration for
   endpoint-first (pull) execution. Creating a pipeline via
   ``db.pipeline(name)`` activates it as the ambient registration target:
   subsequent ``for_each`` calls register a :class:`StepSpec` instead of
   executing (pass ``pipeline=None`` to force an eager call, or
   ``pipeline=other`` to target a non-ambient pipeline). Dependency edges
   are inferred from variable types — a step that consumes ``Filtered``
   depends on every registered step that produces ``Filtered`` — so
   :meth:`Pipeline.run_until` can walk backward from a target and run only
   its ancestors, and :meth:`Pipeline.plan` can report per-step green/red
   staleness before anything runs.

Design doc: ``docs/claude/endpoint-first-pipelines.md``;
plan: ``.claude/plan-pipeline-registry-stage1.md``.

Usage::

    @scistack
    def bandpass(signal, low_hz):
        return ...

    pipe = db.pipeline("gait_analysis")          # activates

    for_each(bandpass, {"signal": RawSignal, "low_hz": 20},
             [Filtered], subject=["1", "2"])     # registers (deferred)
    for_each(compute_speed, {"filtered": Filtered},
             [Speed], subject=["1", "2"])        # registers (deferred)

    pipe.plan()                                  # dry-run: green/red per step
    pipe.run_until(compute_speed)                # runs ancestors + target
"""

from __future__ import annotations

import atexit
from dataclasses import dataclass, field
from typing import Any, Callable

from .log import Log

# Attribute names stamped onto a tagged function.
SCISTACK_FLAG = "__scistack__"
GENERATES_FILE_ATTR = "__scistack_generates_file__"


def scistack(
    fn: Callable | None = None,
    *,
    generates_file: Any | None = None,
):
    """Mark a plain function so scistack pays attention to it.

    Works bare (``@scistack``) or called
    (``@scistack(generates_file="{subject}/out.csv")``). Returns the
    function unchanged except for marker attributes, so it stays an
    ordinary callable.
    """

    def deco(f: Callable) -> Callable:
        setattr(f, SCISTACK_FLAG, True)
        if generates_file is not None:
            setattr(f, GENERATES_FILE_ATTR, generates_file)
        return f

    return deco(fn) if callable(fn) else deco


def is_scistack_function(obj: Any) -> bool:
    """True if ``obj`` is a callable tagged by :func:`scistack`."""
    return callable(obj) and bool(getattr(obj, SCISTACK_FLAG, False))


# ---------------------------------------------------------------------------
# Deferred-step registry
# ---------------------------------------------------------------------------


def _loadable_classes(spec: Any) -> set[type]:
    """Variable classes a single input spec loads, unwrapping input markers.

    ``PathInput``, constants, and literal DataFrames contribute no producer
    edge (nothing in the pipeline produces them).
    """
    from .across_variants import AcrossVariants
    from .column_selection import ColumnSelection
    from .each_of import EachOf
    from .fixed import Fixed
    from .merge import Merge
    from .variant import Variant

    out: set[type] = set()
    if isinstance(spec, type):
        out.add(spec)
    elif isinstance(spec, (Fixed, Variant, AcrossVariants, ColumnSelection)):
        out |= _loadable_classes(spec.var_type)
    elif isinstance(spec, EachOf):
        for alt in spec.alternatives:
            out |= _loadable_classes(alt)
    elif isinstance(spec, Merge):
        for sub in spec.var_specs:
            out |= _loadable_classes(sub)
    return out


@dataclass
class StepSpec:
    """One deferred ``for_each`` call: the exact arguments, execution pending.

    ``options`` holds every ``for_each`` keyword argument other than
    ``fn``/``inputs``/``outputs``/``pipeline`` and is replayed verbatim, so
    a step run through the pipeline produces byte-identical version_keys to
    the same call run eagerly.
    """

    fn: Callable
    inputs: dict[str, Any]
    outputs: list
    metadata_iterables: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return getattr(self.fn, "__name__", repr(self.fn))

    def input_classes(self) -> set[type]:
        classes: set[type] = set()
        for spec in self.inputs.values():
            classes |= _loadable_classes(spec)
        return classes

    def output_classes(self) -> set[type]:
        return {o for o in self.outputs if isinstance(o, type)}

    def to_manifest(self) -> dict:
        """JSON-able projection for display / future GUI use (not replayable)."""
        from .foreach_config import ForEachConfig

        config = ForEachConfig(
            self.fn,
            self.inputs,
            where=self.options.get("where"),
            distribute=self.options.get("distribute", False),
            as_table=self.options.get("as_table"),
        )
        return {
            "fn": self.name,
            "module": getattr(self.fn, "__module__", None),
            "inputs": sorted(c.__name__ for c in self.input_classes()),
            "outputs": sorted(c.__name__ for c in self.output_classes()),
            "iterate": sorted(self.metadata_iterables),
            "version_keys": config.to_version_keys(),
            "call_id": config.to_call_id(),
        }


class Step:
    """Handle returned by a deferred ``for_each`` registration.

    Deliberately NOT data: any attempt to use it like a result DataFrame
    fails fast with a pointer to ``run_until``, so code written against
    eager ``for_each`` cannot silently operate on nothing.
    """

    __slots__ = ("spec", "pipeline_name")

    def __init__(self, spec: StepSpec, pipeline_name: str):
        object.__setattr__(self, "spec", spec)
        object.__setattr__(self, "pipeline_name", pipeline_name)

    def __repr__(self) -> str:
        return (
            f"<Step '{self.spec.name}' (deferred) in pipeline "
            f"'{self.pipeline_name}'>"
        )

    def __getattr__(self, item):
        raise AttributeError(
            f"'{self.spec.name}' is a deferred pipeline step, not a result — "
            f"nothing has executed. Call "
            f"pipeline.run_until({self.spec.name}) (or run_all()) first."
        )

    def __iter__(self):
        raise TypeError(
            f"'{self.spec.name}' is a deferred pipeline step and not "
            f"iterable — call pipeline.run_until(...) to execute it."
        )


# Module-level session state (pattern-matched to the current-db global):
# the activation stack ambient for_each registration targets, plus every
# pipeline created this session for the never-run atexit check.
_active_stack: "list[Pipeline]" = []
_all_pipelines: "list[Pipeline]" = []


def active_pipeline() -> "Pipeline | None":
    """The pipeline currently receiving deferred ``for_each`` registrations."""
    return _active_stack[-1] if _active_stack else None


def _reset_pipeline_state() -> None:
    """Clear all session pipeline state (test isolation helper)."""
    _active_stack.clear()
    _all_pipelines.clear()


def _unrun_pipelines() -> "list[Pipeline]":
    """Pipelines with registered steps that were never run/planned/deactivated."""
    return [p for p in _all_pipelines if p.steps and not p._acknowledged]


def _warn_unrun_pipelines() -> None:
    for p in _unrun_pipelines():
        Log.warn(
            f"pipeline_never_run: pipeline '{p.name}' registered "
            f"{len(p.steps)} step(s) but none of run_all/run_until/plan/"
            f"deactivate was called — nothing was executed"
        )


atexit.register(_warn_unrun_pipelines)


class Pipeline:
    """A named collection of deferred ``for_each`` steps with pull execution.

    Create via ``db.pipeline(name)`` (binds + activates) or directly
    (``Pipeline("name", db=db)``, activate explicitly). Registration order
    does not matter: execution order is topologically sorted from
    variable-type edges. Multiple producers of one variable type (variant
    branches) all become prerequisites of that type's consumers; variant
    disambiguation stays where it lives today — load-time branch_params.

    Pipelines COMPOSE: ``db.pipeline(name, uses=[other])`` (or
    ``pipe.use(other)``) unions the other pipeline's steps into this
    pipeline's graph, so ``run_until``/``plan`` resolve producers across
    the boundary. ``run_all`` runs own steps + their ancestors only.
    """

    def __init__(
        self,
        name: str,
        db: Any | None = None,
        uses: "tuple[Pipeline, ...] | list[Pipeline]" = (),
    ):
        self.name = name
        self.db = db
        self.steps: list[StepSpec] = []
        self.uses: list[Pipeline] = []
        # True once run_all/run_until/plan/deactivate acknowledged this
        # pipeline; guards the never-run atexit warning.
        self._acknowledged = False
        _all_pipelines.append(self)
        for other in uses:
            self.use(other)

    def __repr__(self) -> str:
        used = f", uses {len(self.uses)} pipeline(s)" if self.uses else ""
        return f"<Pipeline '{self.name}': {len(self.steps)} step(s){used}>"

    # -- composition -----------------------------------------------------------

    def use(self, other: "Pipeline") -> "Pipeline":
        """Declare ``other`` as a dependency: its steps join this pipeline's
        graph (union — nothing is copied), so ``run_until``/``plan`` resolve
        producers inside it. Never activates anything."""
        from .exceptions import PipelineCycleError

        if not isinstance(other, Pipeline):
            raise TypeError(
                f"uses= entries must be Pipeline instances; got "
                f"{type(other).__name__}"
            )
        if other is self or any(p is self for p in other._uses_closure()):
            raise PipelineCycleError(
                f"pipeline '{self.name}' cannot use '{other.name}': "
                f"dependency cycle between pipelines"
            )
        if (
            other.db is not None
            and self.db is not None
            and other.db is not self.db
        ):
            raise ValueError(
                f"pipeline '{other.name}' is bound to a different database "
                f"than '{self.name}' — cross-database composition is not "
                f"supported. Rebind one of them (a used pipeline with db=None "
                f"inherits the user's database)."
            )
        self.uses.append(other)
        Log.info(
            f"pipeline_uses: '{self.name}' uses '{other.name}' "
            f"({len(other.steps)} step(s) joined the graph)"
        )
        return self

    def _uses_closure(self) -> "list[Pipeline]":
        """Transitively used pipelines, dependencies-first, deduped by
        identity (a shared sub-pipeline is the same object everywhere —
        the diamond case collapses for free)."""
        ordered: list[Pipeline] = []
        seen: set[int] = set()

        def visit(p: "Pipeline") -> None:
            for u in p.uses:
                if id(u) not in seen:
                    seen.add(id(u))
                    visit(u)
                    ordered.append(u)

        visit(self)
        return ordered

    def _composed_steps(self) -> "list[tuple[Pipeline, StepSpec]]":
        """The full graph's steps as (owner pipeline, spec) pairs: used
        pipelines' steps first (closure order), then this pipeline's own."""
        pairs: list[tuple[Pipeline, StepSpec]] = []
        for p in self._uses_closure():
            pairs.extend((p, s) for s in p.steps)
        pairs.extend((self, s) for s in self.steps)
        return pairs

    # -- activation ---------------------------------------------------------

    def activate(self) -> "Pipeline":
        """Make this pipeline the ambient ``for_each`` registration target."""
        if active_pipeline() is not self:
            _active_stack.append(self)
        return self

    def deactivate(self) -> None:
        """Stop ambient registration without running (explicit escape)."""
        self._acknowledged = True
        while self in _active_stack:
            _active_stack.remove(self)

    # -- registration --------------------------------------------------------

    def register_call(
        self,
        *,
        fn: Callable,
        inputs: dict,
        outputs: list,
        metadata_iterables: dict,
        options: dict,
    ) -> Step:
        """Record one deferred ``for_each`` call. Zero side effects beyond the log."""
        spec = StepSpec(
            fn=fn,
            inputs=inputs,
            outputs=outputs,
            metadata_iterables=dict(metadata_iterables),
            options=dict(options),
        )
        self.steps.append(spec)
        Log.info(
            f"pipeline_step_registered: '{spec.name}' -> pipeline "
            f"'{self.name}' (deferred; {len(self.steps)} step(s) registered)"
        )
        return Step(spec, self.name)

    # -- graph ----------------------------------------------------------------

    @staticmethod
    def _step_label(owner: "Pipeline", spec: StepSpec, via: "Pipeline") -> str:
        """Display name for a step; owner-qualified when it lives in a used
        pipeline (``loading:bandpass``)."""
        return spec.name if owner is via else f"{owner.name}:{spec.name}"

    @staticmethod
    def _deps_for(pairs: "list[tuple[Pipeline, StepSpec]]") -> dict[int, set[int]]:
        """Pair index -> indices of prerequisite pairs (variable-type edges,
        crossing pipeline boundaries freely)."""
        producers: dict[type, set[int]] = {}
        for i, (_, s) in enumerate(pairs):
            for cls in s.output_classes():
                producers.setdefault(cls, set()).add(i)
        deps: dict[int, set[int]] = {}
        for i, (_, s) in enumerate(pairs):
            needed: set[int] = set()
            for cls in s.input_classes():
                needed |= producers.get(cls, set())
            deps[i] = needed
        return deps

    def _topo_order(
        self,
        pairs: "list[tuple[Pipeline, StepSpec]]",
        subset: "set[int] | None" = None,
    ) -> list[int]:
        """Kahn's algorithm over ``subset`` (default: all pairs).

        Deterministic: among ready steps, composed order (used pipelines
        first, then registration order) wins. Raises
        :class:`~scidb.exceptions.PipelineCycleError` if steps remain (a
        step consuming its own output type is the one-step case).
        """
        from .exceptions import PipelineCycleError

        indices = sorted(subset) if subset is not None else list(range(len(pairs)))
        index_set = set(indices)
        all_deps = self._deps_for(pairs)
        deps = {i: all_deps[i] & index_set for i in indices}
        order: list[int] = []
        done: set[int] = set()
        while len(order) < len(indices):
            ready = [i for i in indices if i not in done and deps[i] <= done]
            if not ready:
                stuck = [
                    self._step_label(pairs[i][0], pairs[i][1], self)
                    for i in indices if i not in done
                ]
                raise PipelineCycleError(
                    f"pipeline '{self.name}' has a dependency cycle among "
                    f"steps: {stuck}"
                )
            order.extend(ready)
            done.update(ready)
        return order

    def _resolve_target(
        self, pairs: "list[tuple[Pipeline, StepSpec]]", target: Any
    ) -> set[int]:
        """Pair indices matching ``target`` (Step handle, callable, or name)
        anywhere in the composed graph — own steps or used pipelines'.

        A function registered multiple times (variant branches) matches all
        of its registrations.
        """
        if isinstance(target, Step):
            matches = {i for i, (_, s) in enumerate(pairs) if s is target.spec}
        elif callable(target):
            matches = {i for i, (_, s) in enumerate(pairs) if s.fn is target}
        elif isinstance(target, str):
            matches = {i for i, (_, s) in enumerate(pairs) if s.name == target}
        else:
            raise TypeError(
                f"run_until target must be a Step, callable, or step name; "
                f"got {type(target).__name__}"
            )
        if not matches:
            registered = [self._step_label(o, s, self) for o, s in pairs]
            raise ValueError(
                f"no step matching {target!r} is registered in pipeline "
                f"'{self.name}' or its used pipelines; registered steps: "
                f"{registered}"
            )
        return matches

    def _ancestors(
        self, pairs: "list[tuple[Pipeline, StepSpec]]", targets: set[int]
    ) -> set[int]:
        deps = self._deps_for(pairs)
        seen: set[int] = set()
        frontier = list(targets)
        while frontier:
            i = frontier.pop()
            for dep in deps[i]:
                if dep not in seen:
                    seen.add(dep)
                    frontier.append(dep)
        return seen

    # -- dry run ----------------------------------------------------------------

    def plan(self, target: Any | None = None) -> list[dict]:
        """Topologically ordered dry-run report over the composed graph;
        nothing executes.

        Each entry: ``{"step", "pipeline", "state", "combos"}`` where
        ``pipeline`` names the step's owner and ``state`` is
        ``check_node_state``'s binary green (computed and current) / red
        (needs attention), or "unknown" when the check itself failed.
        """
        self._acknowledged = True
        pairs = self._composed_steps()
        if target is not None:
            targets = self._resolve_target(pairs, target)
            order = self._topo_order(pairs, targets | self._ancestors(pairs, targets))
        else:
            order = self._topo_order(pairs)

        entries: list[dict] = []
        for i in order:
            owner, spec = pairs[i]
            entry: dict[str, Any] = {"step": spec.name, "pipeline": owner.name}
            try:
                from .state import check_node_state

                manifest = spec.to_manifest()
                node = check_node_state(
                    spec.fn,
                    outputs=list(spec.output_classes()),
                    inputs=spec.inputs,
                    db=self._db_for(owner, spec),
                    call_id=manifest["call_id"],
                )
                entry["state"] = node.get("state", "unknown")
                entry["combos"] = node.get("combos", [])
            except Exception as exc:  # staleness check must never block planning
                Log.warn(
                    f"pipeline_plan: state check failed for step "
                    f"'{spec.name}': {exc}"
                )
                entry["state"] = "unknown"
                entry["combos"] = []
            entries.append(entry)
            Log.info(
                f"pipeline_plan: '{self.name}' step '{entry['step']}' state="
                f"{entry['state']} ({len(entry['combos'])} known combo(s))"
            )
        return entries

    # -- execution ----------------------------------------------------------------

    def run_all(self, skip_computed: bool = True) -> list:
        """Run this pipeline's OWN steps plus their ancestors (which may
        live in used pipelines) in dependency order.

        Deliberately NOT the full composed graph: a used pipeline may
        contain steps this pipeline never consumes, and running them here
        would be surprising. Target them with ``run_until`` or run the used
        pipeline directly.
        """
        pairs = self._composed_steps()
        own = {i for i, (owner, _) in enumerate(pairs) if owner is self}
        if not own:
            self.deactivate()
            if pairs:
                Log.warn(
                    f"pipeline_run_skipped: run_all on '{self.name}': no own "
                    f"steps registered — the {len(pairs)} step(s) from used "
                    f"pipelines were NOT run (target them with run_until, or "
                    f"run the used pipeline directly)"
                )
            return []
        order = self._topo_order(pairs, own | self._ancestors(pairs, own))
        return self._run(pairs, order, skip_computed=skip_computed)

    def run_until(
        self,
        target: Any,
        finalized: "bool | None" = None,
        skip_computed: bool = True,
    ) -> list:
        """Run ``target`` and its ancestors only — resolved over the
        composed graph, so both may live in used pipelines.

        ``finalized`` (endpoint draft/record mode) applies to the target
        step(s) only; other steps keep their registered flags.
        """
        pairs = self._composed_steps()
        targets = self._resolve_target(pairs, target)
        order = self._topo_order(pairs, targets | self._ancestors(pairs, targets))
        return self._run(
            pairs,
            order,
            skip_computed=skip_computed,
            finalized=finalized,
            finalized_for=targets,
        )

    def _db_for(self, owner: "Pipeline", spec: StepSpec):
        """Run-time db resolution: step option → owner pipeline → this
        pipeline (the C3 inheritance rule for db=None sub-pipelines)."""
        return spec.options.get("db") or owner.db or self.db

    def _run(
        self,
        pairs: "list[tuple[Pipeline, StepSpec]]",
        order: list[int],
        skip_computed: bool = True,
        finalized: "bool | None" = None,
        finalized_for: "set[int] | None" = None,
    ) -> list:
        from .foreach import for_each as _for_each

        self._acknowledged = True
        self.deactivate()
        names = [self._step_label(pairs[i][0], pairs[i][1], self) for i in order]
        Log.info(
            f"pipeline_run_started: '{self.name}' {len(order)} step(s) in "
            f"dependency order: {names}"
        )
        results = []
        for i in order:
            owner, spec = pairs[i]
            opts = dict(spec.options)
            opts["db"] = self._db_for(owner, spec)
            # Pull execution defaults to memoized runs; a step's explicitly
            # registered skip_computed=True always wins, and untracked steps
            # are left alone (skip_computed requires lineage).
            if opts.get("track_lineage", True):
                opts["skip_computed"] = opts.get("skip_computed") or skip_computed
            if finalized is not None and finalized_for and i in finalized_for:
                opts["finalized"] = finalized
            Log.info(
                f"pipeline_step_run: "
                f"'{self._step_label(owner, spec, self)}' (via pipeline "
                f"'{self.name}', skip_computed={opts.get('skip_computed', False)})"
            )
            results.append(
                _for_each(
                    spec.fn,
                    spec.inputs,
                    spec.outputs,
                    pipeline=None,  # replay is always eager
                    **opts,
                    **spec.metadata_iterables,
                )
            )
            # An executed step acknowledges its owner: a pipeline that only
            # exists as a dependency should not warn at session end.
            owner._acknowledged = True
        Log.info(f"pipeline_run_finished: '{self.name}' ({len(order)} step(s))")
        return results
