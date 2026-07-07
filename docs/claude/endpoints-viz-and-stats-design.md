# Endpoints: Data Visualization and Statistics — Design

Status: **design settled** (2026-07-05). All major decisions made (marked
**DECIDED**); only implementation-time details remain open (bottom). Next
step: `.claude/plan-*.md` for stage 1 (D1) when implementation begins.

## Motivation

Data analysis = processing + visualization + summary statistics, repeated in
arbitrary order. Processing is mature; the observability CLI just shipped. Viz
and stats are the remaining two legs. They follow the same philosophy as
processing — orchestrating *users' custom functions* — but they sit at the
**leaf nodes** of the pipeline graph.

## The key reframe: the axis is not "viz vs. stats," it is "artifact vs. data"

- **Figures are artifacts.** Opaque files whose *path* is the DB record. They
  need rendering, file management, and artifact provenance — and they are
  terminal by definition.
- **Stats results are just data.** A test result is a small row — exactly what
  `BaseVariable` already stores. And stats results are *not fully terminal*:
  p-values feed multiple-comparison corrections, and stats annotate figures.
  Storing them as opaque "reports" would cut off those downstream uses.

Consequence: stats needs integration + ergonomics on top of what exists, while
viz owns the genuinely new surface (draft mode, artifact provenance).

## What already exists (do not rebuild)

1. **`plot_` leaf nodes — v1 shipped.** See
   [plotting-leaf-nodes.md](plotting-leaf-nodes.md). Name-prefix detection in
   `scidb/foreach.py`, `PathOutput` for the figure path, framework saves+closes
   the Figure, stores the *path* as a queryable VARCHAR record with full
   lineage and `skip_computed`, `share_limits` for grouped axis ranges. Tests
   in `scidb/tests/test_plotting.py`.
2. **Fan-in (aggregation mode).** Iterating a strict subset of schema keys
   delivers a multi-row DataFrame per combo; zero iterated keys = grand
   aggregation (all rows, one call — the paired-t-test-across-subjects shape).
   See [scidb-for-each-internals.md](scidb-for-each-internals.md) Step 12.
   *Fan-in data delivery is done; endpoints need no new loading machinery.*
3. **Non-contiguous schema keys.** Save/load with any subset of schema keys —
   built for cross-cutting analyses. See
   [schema-hierarchy-contiguity.md](schema-hierarchy-contiguity.md).
4. **Per-variant runs.** `Variant(X, low_hz=20)` pins an input;
   `EachOf(Variant(...), Variant(...))` runs once per variant. See
   [variant-branch-param-pinning.md](variant-branch-param-pinning.md).
5. **A Step 12 warning** logs whenever multiple record_ids feed one aggregated
   table, so variant pooling is not silent.

## Decisions

### D1. Variants auto-split by default in aggregation mode — **IMPLEMENTED** (2026-07, pending user test run)

Aggregation mode will split by branch-param signature by default, one call per
signature — as if the user had written `EachOf(Variant(...), Variant(...))`.
Rationale: no use case exists for the current identity-stripped pooling. The
only legitimate cross-variant analysis is **multiverse / specification-curve
robustness** ("does the effect survive regardless of filter cutoff?"), and
even that requires variant identity per row — which pooling destroys. So:

- **Default: auto-split.** One aggregate call per branch-param signature,
  distinct output records per signature (identity via the same mechanism as
  `EachOf(Variant)` — `Variant.to_key()` → `__inputs` version key + propagated
  upstream branch_params).
- **Explicit opt-in for multiverse:** an `AcrossVariants(X)` input wrapper
  that pools rows *and includes branch_params as columns* so the function can
  group by specification.
- This applies to **all** aggregations, not just endpoints — processing
  aggregations (e.g. mean across trials) are equally wrong when pooled.

Implementation cautions:

- Implement inside foreach Step 12 by grouping rid expansion on branch-param
  signature (via `rid_to_bp`), **not** by literal `EachOf` recursion — `EachOf`
  re-runs the full recursive `for_each` (including loads) per alternative,
  an N+1 pattern to keep off hot paths.
- **Ragged variant sets → WARN** (decided 2026-07-05). If trial 1 has variants
  `{low_hz=20, 50}` but trial 2 only `{20}`, the `50` group is missing trial 2:
  the aggregation proceeds on the partial group with a clear warning naming the
  group's branch-param signature and the schema locations it is missing.
- This supersedes the pooling default described in the aggregation section of
  [scidb-for-each-internals.md](scidb-for-each-internals.md) and implements
  the "auto-grouping" future work named in
  [variant-branch-param-pinning.md](variant-branch-param-pinning.md).

### D2. No framework faceting — delegate to plotting libraries — **DECIDED**

The framework will NOT implement facet/subplot/channel mapping. The aggregated
DataFrame already contains schema keys as ordinary columns, which is exactly
the input contract of faceting libraries:

```python
def plot_gait(df, filename):
    g = sns.relplot(data=df, col="session", hue="trial", ...)
    return g.figure
```

The framework's role is only what it already does: **iterated keys → separate
figure files; non-iterated keys → columns in the DataFrame** for the plotting
library to facet. This keeps users' facet customization fully transparent
(their own seaborn/ggplot/tiledlayout code) and avoids reimplementing a hard,
solved problem. `share_limits` remains the one cross-figure coordination
affordance (shared axis ranges across separately-iterated figures) and may
later grow siblings (shared color scales) — coordination *across* files is the
one thing a plotting library working on a single figure cannot do.

### D3. Draft vs. record mode; draft default; record requires a re-run — **IMPLEMENTED** (2026-07-06, pending user test run)

- **Draft mode (default):** render the figure to its path (so the user can
  look at it), write **nothing** to the DB — no record, no lineage. Styling
  churn produces zero DB clutter.
- **Record mode:** the normal shipped v1 behavior — path stored as a record
  with full lineage, `skip_computed` honored.
- **Switching to record re-runs the endpoint.** No draft-promotion lifecycle.
  Rationale: promotion-without-rerun would require drafts to write provisional
  records (draft flags, stale-draft cleanup, CLI filtering, MATLAB parity) and
  a promoted draft is an unverified claim that code+data haven't changed since
  it rendered — verifying that claim means recomputing the hashes, at which
  point it is just `skip_computed` deciding rerun-vs-skip. Endpoints are cheap
  to re-run *by construction* (inputs already computed; rendering is seconds).
  Note: a draft leaves no record, so the first record-mode run always renders.
- **Uniform for `plot_` and `stat_`:** a draft `stat_` prints its formatted
  result without saving — matching how scientists explore stats interactively.
- Mode is the `for_each` parameter **`finalized`** (decided 2026-07-05):
  `finalized=False` (default) = draft, `finalized=True` = record. Passed
  through the MATLAB bridge as a plain flag.

### D4. Artifact-embedded provenance: figure record_id + redundancy — **IMPLEMENTED** (2026-07-06, pending user test run)

Embed a small JSON blob in the artifact file — **both** endpoint kinds:
`plot_` figures AND `stat_` PDF reports (the `report_path` artifact):

- `record_id` of the artifact's own DB record — the primary key; via the
  bipartite provenance graph it reaches the producing invocation, function
  hash, input record_ids, and branch_params. Embedding derived hashes as
  primary keys would be redundant indirection.
- Human-readable redundancy (survives DB loss/detachment): producing function
  name, **input record_ids** (the data in the figure), the schema combo,
  database filename, timestamp.
- Draft renders have no record → the **FULL blob** with `draft: true` in
  place of the record_id (decided 2026-07-06; supersedes the earlier
  minimal-draft idea) — a draft figure is fully traceable to its exact input
  records. `stat_` drafts resolve PathOutput to None → no artifact to stamp.

**Implementation locus: the scidb save path (Python), not the renderer.**
It is the correct scistack layer (CLAUDE.md NOTE 3); the record_id only
exists after the save; and it works identically for MATLAB-rendered figures,
whose path crosses the bridge anyway (`exportgraphics` cannot write custom
metadata). As built (`scidb/artifact_stamp.py`, all stdlib): PNG `tEXt`
chunk, SVG `<metadata>` element, PDF incremental update (original bytes
untouched; classic-xref producers = reportlab + matplotlib), sidecar
`<artifact>.provenance.json` fallback otherwise. Record-mode stamp in
`_save_results` (record_id + meta + artifact path coexist there); draft-mode
stamp in `_for_each_save_resolved`. `read_artifact_stamp`/`stamp_artifact`
exported. Known limitation: PathOutput templates can't reference
branch_params, so multiple variant groups at one location share an artifact
path — last group's stamp wins (future: a vsig placeholder). Tests:
`scidb/tests/test_artifact_stamp.py`.

### D5. Stats vocabulary: integrate csv-stats, no universal key convention — **IMPLEMENTED** (2026-07-06, pending user test run)

No lowest-common-denominator key convention (`statistic`/`p`/`df`/...) — there
are too many test types for one schema. Instead integrate the user's
**csv-stats** package (PyPI; formatted output per statistical test type):

- `stat_` functions return csv-stats result objects (or plain dicts/DataFrames
  for tests it doesn't cover); the formatted per-test output is what gets
  stored.
- Each test type naturally maps to its own variable type with a well-defined
  view; cross-test summary tables project whatever common fields exist rather
  than mandating them.
- **Result shape** (decided 2026-07-05): a **JSON-formatted string** whose
  fields vary by test type — store the string as the record's data. Fitted
  model objects are **not** stored (summary-only) until a concrete need
  appears.
- **csv-stats API (captured 2026-07-06 from v0.1.10, installed in
  `/workspace/.venv/lib/python3.11/site-packages/csvstats/`):**
  - Import path is **`csvstats`** (the README's `csv_stats` is a docs bug).
  - Functions: `ttest_ind(data, group_column, data_column, filename=...,
    render_plot=False, popmean=0)`, `ttest_dep(..., repeated_measures_column,
    ...)`, `anova1way/2way/3way(...)`. All return a plain **dict** with
    test-specific keys (`test`, `t_statistic`/`F`, `p`/`p_value` (rounded 4),
    `df_between`/`df_within`, nested `summary_statistics` {grouped, overall},
    assumption tests (normality / homogeneity / sphericity), `post_hoc`,
    `date`).
  - **`data` accepts a DataFrame directly** — the aggregated long-format
    DataFrame from for_each (schema keys as columns) is exactly its input
    contract: schema keys serve as `group_column` /
    `repeated_measures_column`. D1's auto-split keeps variants out of the
    test. Near-zero glue needed.
  - **Side effect: `filename` defaults to a PDF name, NOT None** — by default
    it writes a rendered-JSON PDF report to CWD (`.json` filename writes JSON;
    `filename=None` disables). The `stat_` wrapper must pass `filename=None`
    in draft mode and route the PDF through `PathOutput` in record mode (the
    PDF is an artifact exactly like a `plot_` figure; the dict is the data
    record). `convert_types` handles numpy → JSON.
  - `data_column="_"` loops over all columns (natural `for_columns` analog).
  - **`result["date"]` is a wall-clock timestamp inside the result dict** —
    nondeterministic across identical reruns; the `stat_` save path should
    strip or segregate it so stored results are reproducible.
  - Upstream bugs found while reading (fix in csv-stats, not scistack):
    `utils/save_stats.py::dict_to_json` calls `json.dump(f, result)` with
    swapped arguments (crashes for `.json` filenames); README import path.

Family-wise operations remain inherently two-stage: run tests per combo →
correct across the family. Because results are ordinary data, this is
expressible today (`correct_pvalues` consuming `TTestResult.load(as_df=True)`);
document the pattern rather than building machinery.

### D6. API: `plot_`/`stat_` name-prefix detection stays — **DECIDED**

Good enough for now; an explicit marker (decorator / `for_each` flag) can be
added later without breaking the prefix convention.

### D7. MATLAB parity strategy — **DECIDED**

Principle: **figure handles never cross the bridge; only the path string
does** (same split as PathInput resolution — MATLAB touches the local
environment, Python owns correctness).

- MATLAB-side `for_each` detects the `plot_` prefix and wraps the user fn:
  a returned **figure handle** → `exportgraphics(fig, resolved_path)` then
  `close(fig)` (memory-bounded across combos, mirroring `plt.close`); a
  returned **char/string path** → passthrough (fn saved it itself). Same
  contract as the Python wrapper.
- The path string flows through the existing MATLAB→bridge save path; storage,
  lineage, `skip_computed`, and D4 metadata stamping all happen Python-side —
  correctness lives in one place.
- `stat_` results cross the bridge as data like any other save (existing
  type round-trip machinery).
- `share_limits` prepass lives in scifor → needs a MATLAB-scifor port when viz
  work lands there (same pattern as the `for_columns` port).
- Draft/record flag passes through the bridge as a plain parameter.

## Reporting surface (the payoff — build last)

Endpoints exist because of a paper/report. Once figures and stats are
lineage-tracked records, a `scidb report` CLI command (extending the
observability CLI) can dump all figures + stats tables for an analysis into a
folder or HTML page.

## Staging

Design together (done above), implement staged:

1. **D1** — variant auto-split in aggregation (scidb Step 12; benefits
   processing too; the deepest semantic change, do it first while everything
   else layers on top). Includes the ragged-group policy + logging + tests.
   **DONE** (2026-07, pending user test run): `__vsig_*` signature split,
   `AcrossVariants` wrapper, ragged warning, group-bound skip_computed gate.
   Plan: `.claude/plan-endpoint-variant-autosplit.md`; tests:
   `scidb/tests/test_aggregation_with_variants.py`.
2. **`stat_` leaves** — detection, draft-print/record behavior, csv-stats
   integration (after capturing its API), tests. Small delta; stress-tests
   endpoint semantics with a second consumer immediately.
   **DONE** (2026-07-06, pending user test run): Step 1.56 detection,
   `_make_stat_wrapper` (JSON normalization, date-stripping, report_path),
   `finalized` flag implemented for BOTH `stat_` and `plot_` (D3 pulled
   forward from stage 3 since the flag is shared), `as_table` defaulted on
   for `stat_`. Plan: `.claude/plan-stat-leaves.md`; tests:
   `scidb/tests/test_stat_leaves.py` + updated `test_plotting.py`; docs:
   [plotting-leaf-nodes.md](plotting-leaf-nodes.md) (now covers both kinds).
3. **Viz enhancements** — artifact metadata stamping (D4). No faceting work
   (D2). (`finalized` for `plot_` landed with stage 2.)
   **DONE** (2026-07-06, pending user test run): `artifact_stamp.py`
   (PNG/SVG/PDF + sidecar), record- and draft-mode stamping passes, full-blob
   drafts. Plan: `.claude/plan-artifact-provenance-stamp.md`; tests:
   `scidb/tests/test_artifact_stamp.py`.
4. **MATLAB parity** (D7) — plot wrapper in MATLAB for_each, bridge flag,
   share_limits port as needed.
5. **Report/CLI surface.**

## Remaining open questions

1. csv-stats result-object API details (D5 TODO) — user will provide when the
   stats phase starts.
2. Zero-iterated-keys grand aggregation: **confirmed as intended behavior**
   (2026-07-05); still needs an end-to-end regression test (combo formation
   with no iteration kwargs) when D1 work touches Step 12.
3. Final name for the `AcrossVariants(...)` opt-in wrapper (working name
   stands unless something better appears at implementation time).

## Related docs

- [plotting-leaf-nodes.md](plotting-leaf-nodes.md) — shipped `plot_` v1
- [variant-branch-param-pinning.md](variant-branch-param-pinning.md) —
  `Variant`/`EachOf`; D1 implements its named future work
- [scidb-for-each-internals.md](scidb-for-each-internals.md) — aggregation
  mode (Step 12); D1 supersedes its pooling default
- [schema-hierarchy-contiguity.md](schema-hierarchy-contiguity.md) —
  non-contiguous key support
- [observability-api-design.md](observability-api-design.md) — the CLI the
  report surface extends
