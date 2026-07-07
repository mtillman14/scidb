# Endpoint leaf nodes: `plot_` and `stat_` functions, and `finalized`

Plots and statistics are the **leaf nodes** of a processing pipeline: they
consume saved variables and emit a figure or a statistical result rather than
data to process further. scidb gives both first-class support so they
participate in the same `for_each` iteration, aggregation auto-split, lineage,
and `skip_computed` machinery as any other step. Design decisions: D2–D5 in
[endpoints-viz-and-stats-design.md](endpoints-viz-and-stats-design.md).

Detection is by name prefix (`foreach.py` Steps 1.55/1.56): `plot_*` is a
plotting leaf, `stat_*` a statistics leaf.

## `finalized` — draft vs. record (D3)

Both endpoint kinds honor `for_each(..., finalized: bool)`:

- **`finalized=False` (DEFAULT — draft):** nothing is written to the database
  (no records, no lineage, no graph; the save phase is suppressed wholesale).
  The in-memory result table is still returned. A `plot_` figure IS still
  rendered to its path — looking at it is the point of a draft — while a
  `stat_` result is pretty-printed to the console and any `PathOutput`
  resolves to `None` (so e.g. csv-stats' `filename=None` contract disables
  its PDF report). Style-tweak and explore freely: zero DB clutter.
- **`finalized=True` (record):** outputs saved as queryable records with full
  provenance; `skip_computed` works. Switching a draft to a record **requires
  a re-run** — drafts leave no record to promote, endpoints are cheap to
  re-run by construction, and the re-run guarantees the record reflects
  exactly the code+data that produced it.
- Drafts never skip (`skip_computed` has no record to gate against).
- Passing `finalized=True` with a non-endpoint function warns and is ignored
  (processing functions always record).

## Plotting leaves (`plot_`)

A `plot_` function must be given a `PathOutput` input naming where the figure
goes (required — raises without it), and returns a matplotlib `Figure`:

```python
def plot_timeseries(signal, filename, subject=None, signal_limits=None):
    fig, ax = plt.subplots()
    ax.plot(signal)
    return fig            # framework saves + closes it

for_each(
    plot_timeseries,
    inputs={"signal": RawSignal,
            "filename": PathOutput("plots/{subject}_{trial}.png")},
    outputs=[PlotFigure],
    share_limits={"signal": ["subject"]},
    finalized=True,                       # record; omit while iterating on style
    subject=["1", "2"], trial=["1", "2", "3"],
)

PlotFigure.load(subject="1", trial="2")   # -> "plots/1_2.png"
```

- **Figure wrapper** (`_make_plot_wrapper`): saves the returned Figure to the
  resolved `PathOutput` path (`fig.savefig`), **closes** it (bounds memory
  across combos), and returns the path **string** — which in record mode flows
  through the normal lineage + save path as a queryable `VARCHAR` record. A
  `str`/`Path` return passes through (fn saved it itself).
- **`share_limits={"input": [keys_to_hold_fixed]}`** — scifor prepass giving
  every combo in a group a shared `{input}_limits=(min, max)` kwarg (only
  injected if the signature accepts it). General, not plot-specific.
- Faceting is deliberately NOT framework work (D2): non-iterated schema keys
  arrive as DataFrame columns, which is exactly seaborn's faceting contract.

## Statistics leaves (`stat_`)

A `stat_` function returns a **dict** (e.g. a csv-stats result) or a ready
JSON **string**; anything else raises `TypeError`. The wrapper
(`_make_stat_wrapper`) normalizes numpy values, **strips the top-level
`"date"` key** (csv-stats stamps a wall-clock timestamp; identical reruns
must store identical bytes — the DB save timestamp is the time authority),
and stores a canonical JSON string as the record data.

```python
class StepLengthTTest(BaseVariable):
    pass

def stat_step_length(df, filename):
    from csvstats.ttest import ttest_dep
    return ttest_dep(df, "session", "StepLength",
                     repeated_measures_column="subject", filename=filename)

for_each(stat_step_length,
         inputs={"df": StepLength,
                 "filename": PathOutput("reports/step_length_ttest.pdf")},
         outputs=[StepLengthTTest],
         finalized=True)      # no iteration kwargs: grand aggregation fans in
```

- **`as_table` defaults ON for `stat_`**: statistics need the long-format
  table — schema keys (subject, session, …) as ordinary columns, which is
  exactly csv-stats' `group_column`/`repeated_measures_column` contract.
  An explicit user `as_table` (including `False`) is respected.
- **`PathOutput` is OPTIONAL for `stat_`** (unlike `plot_`): the record is
  the deliverable; the PDF report is a sidecar. In record mode the resolved
  path passes through to the fn (hand it to csv-stats' `filename=`) and is
  embedded as `"report_path"` in the stored JSON so the artifact is
  discoverable from the record. In draft mode it resolves to `None`.
- **No csv-stats dependency in scidb**: the integration is convention-level —
  any dict works. csv-stats (import path `csvstats`) is the recommended
  companion; its results are exercised in an `importorskip` test.
- **Variant auto-split composes** (D1): a `stat_` over an input with multiple
  upstream branch_param variants runs **one test per variant group**, each
  record carrying its group's branch_params — multiverse comparison in one
  call. Family-wise p-value correction remains a second-stage step consuming
  `TTestResult.load(as_df=True)` (results are ordinary data).

## Artifact provenance stamping (D4)

Every endpoint artifact gets an embedded JSON provenance blob
(`scidb/artifact_stamp.py`; `read_artifact_stamp` / `stamp_artifact` exported):
the artifact's own `record_id`, producing `function`, consumed input
record_ids per param (`inputs`), the row's `schema` combo, `database` name,
and `timestamp`. **Drafts embed the full blob with `draft: true` in place of
the record_id** — a draft figure on disk is fully traceable to its exact
input records. `stat_` PDF reports (the `report_path` artifact) are stamped
identically; `stat_` drafts resolve PathOutput to None, so they have no
artifact.

- Formats (all stdlib-only): PNG `tEXt` chunk, SVG `<metadata>` element,
  PDF **incremental update** (original bytes untouched; classic-xref
  producers — reportlab and matplotlib both qualify). Anything else, or a
  parse failure, falls back to a `<artifact>.provenance.json` **sidecar**
  (embedded metadata travels with the file; a sidecar can be left behind by
  a copy — it is strictly the fallback).
- Stamping lives in the scidb save phase (record mode: inside
  `_save_results`, where the record_id exists; draft mode: in
  `_for_each_save_resolved`), never in the renderer — so MATLAB-rendered
  figures (stage 4) inherit it for free. Failures warn and continue.

## PathOutput branch_param placeholders (per-group artifact paths)

`PathOutput` templates may reference branch_params with the same `{}` syntax
as schema keys, so each variant group writes its OWN file:

```python
PathOutput("plots/{subject}_{low_hz}.png")            # bare name, suffix-matched
PathOutput("plots/{subject}_{bandpass.low_hz}.png")   # namespaced
PathOutput("plots/{subject}_{variant}.png")           # 8-char group digest
```

- Bare names follow the `Variant()`/`branch_param()` matching contract
  (suffix match; ambiguity across two namespaced keys → hard error; a key
  with conflicting values across this call's inputs → hard error).
  `{variant}` digests the group's canonical signature — stable across runs,
  defined even with zero variants.
- Mechanics (NOTE 3, zero scifor changes): `PathOutput.resolve` is a literal
  `str.replace` per combo key, so scidb injects per-group values into the
  expanded combos at Step 12 / rid expansion, and strips those keys before
  save/introspect (they never become branch_params or result columns). An
  unmatched placeholder warns and leaves the literal `{name}` in the path.
- **Collision guard**: when one resolved path is shared by combos that agree
  on schema identity but differ in variant identity, for_each raises BEFORE
  anything renders, naming the differing branch_param and the one-line fix.
  Schema-key-omission collisions (e.g. a template without `{trial}`) are
  deliberately not errors — pre-existing overwrite behavior. `{ColName}`
  templates are covered (the for_columns axis is concrete before prepare).
  Editing a template changes the call's `__inputs` identity → endpoints
  re-render once. Tests: `scidb/tests/test_pathoutput_variants.py`.

## Deliberately out of scope

- Auto-creating `PathOutput` parent directories (must exist).
- Framework faceting (D2 — delegated to plotting libraries).
- MATLAB endpoint parity (D7 — stage 4).
- csv-stats' `data_column="_"` all-columns loop (a `for_columns` analog;
  future).

## Tests

`scidb/tests/test_plotting.py` — files written + path records queryable
(finalized), draft renders-without-recording, `share_limits`, skip_computed.
`scidb/tests/test_stat_leaves.py` — JSON record + date-stripping + numpy
normalization, draft print/no-write, PathOutput None/report_path, return
contract, one-stat-per-variant-group, skip_computed, non-endpoint warning,
csv-stats end-to-end (importorskip).
