# Plan: `scistackplot` / `scistackplotdb` — interactive plotting layer

**Status:** ALL 6 STAGES IMPLEMENTED, TESTS PASSING 2026-09-06 (uncommitted).
128 passed / 1 skipped (`test_spec_toml_round_trip`, needs `tomli-w`) across
`scistackplot/tests`, `scistackplotdb/tests`, and
`scistack-gui/tests/test_plot_service.py`. Frontend typechecks; both vite
bundles rebuilt. Run commands are at the bottom of this file.

Five failures were fixed on the first run — see "First-run fixes" below.
**Prior art:** `/workspace/csv-data-visualizer-code` (R/Shiny proof of concept),
`docs/claude/plotting-leaf-nodes.md` (existing `plot_` endpoints),
`docs/claude/endpoints-viz-and-stats-design.md` (D2: no framework faceting),
`csvstats` (the standalone-companion precedent).

---

## 1. Decisions taken

| Question | Decision | Rationale |
|---|---|---|
| Packaging | **Two new sibling packages in this monorepo**, not folded into scifor/scidb | `scifor`'s selling point is zero dependencies; `scidb` must not gain matplotlib. Repo already holds 9 separately-installable packages. |
| Names | `scistackplot` (≈scifor), `scistackplotdb` (≈scidb) | Follows the `scistacklog` namespacing precedent (`sciplot`/`sciviz` are taken). |
| Export target | **Generated literal seaborn/matplotlib code** | Matches the existing `plot_` contract (returns a `Figure`), keeps figure code transparent, honors the "minimize lock-in" goal, and follows `gui-export-to-plain-python.md`. |
| GUI host, v1 | **VS Code webview panel only** | Reuses the existing JSON-RPC Python process. A standalone `serve` mode is added later against the same `DataSource` protocol. |
| MATLAB | **Not in v1** | Existing MATLAB `plot_` functions are unaffected. `ResolvedPlot` leaves the door open for a MATLAB renderer with no redesign. |
| Interactive renderer | plotly.js in the webview | No image round-trip; CSP-safe self-contained bundle. matplotlib runs server-side only for export/pipeline. |

## 2. Core insight

The Shiny app is a **spec builder**, not a plotting app. Every widget in `ui.R`
sets one field of a small serializable object; `runPlotButton` compiles it into
a ggplot. That is what makes an inherently-visual tool pipeline-compatible: the
GUI's product is a `PlotSpec`, and a `PlotSpec` is exactly what the body of a
`plot_` endpoint needs. Explore → freeze the spec → it becomes a
lineage-tracked `plot_` node in the DAG.

## 3. Architecture

```
DataSource (protocol)  ──►  LongTable  ──►  PlotSpec
                                              │
                                    resolve(spec, table)   pure, testable
                                              ▼
                                        ResolvedPlot          per-panel tidy
                                       ╱      │      ╲        frames + encodings
                              mpl.py    plotly.py   codegen.py
                            (export)  (interactive)  (source text)
```

`ResolvedPlot` earns its place three ways: it stops the interactive plotly view
and the exported matplotlib figure from silently diverging, it is what a future
MATLAB renderer targets, and it is what the code generator reads.

### One protocol, two implementations

`DataSource` (`list_factors()`, `list_measures()`, `get_table(measure, filters)`)
is defined in `scistackplot`. The CSV/DataFrame implementation ships there; the
scidb implementation ships in `scistackplotdb`. The GUI talks only to the
protocol, so the same app serves a lone CSV and a full scidb project. This is
the entire "standalone yet compatible" mechanism.

## 4. The role model

`server.R` spends most of its length hand-maintaining consistency between four
widgets (`dataReductionFactorsCheckboxGroup`, `tickFactorsselectInput`,
`colorFactorSelectInput`, `facetFactorCheckboxGroup`) via repeated `setdiff`
calls. Those four widgets encode one invariant: **every factor has exactly one
role.** Model it directly.

| Role | Meaning |
|---|---|
| `ITERATE` | separate figure per level (fan-out; = scidb's iterated keys) |
| `X` | x-axis position |
| `COLOR` | one series/hue per level |
| `FACET_ROW` / `FACET_COL` | subplot grid |
| `AGGREGATE` | collapse — mean ± error across its levels |
| `FREE` | left as a column; contributes replicate points |

### Capability function

```python
available_plots(measure_shape: Shape, roles: dict[str, Role]) -> list[PlotKind]
default_plot(measure_shape, roles) -> PlotKind
```

Pure, in `scistackplot`, shared by GUI and API (CLAUDE.md NOTE 3 — the GUI only
renders what this returns). The "more summative options become available"
requirement falls straight out: a boxplot needs a distribution, which exists
only when some factor is `AGGREGATE` or `FREE` under the x grouping.

| Measure shape | no aggregation | with aggregation |
|---|---|---|
| scalar | scatter (one point per schema ID) | box / violin / bar+CI |
| 1D array | one line per schema ID | mean line + shaded error region |
| 2D | heatmap / image | mean heatmap |
| two measures | x–y scatter | ellipse / regression |

## 5. `PlotSpec` (sketch)

```python
@dataclass
class PlotSpec:
    measures: list[str]              # y, and optionally x for xy scatter
    roles: dict[str, Role]           # factor column -> role (exactly one each)
    kind: PlotKind
    aggregate: Aggregation           # statistic (mean/median) + error (sd/sem/ci95/iqr)
    index_column: str | None         # within-observation axis for 1D shapes
    facet: FacetOptions              # wrap, shared axes
    style: StyleOptions              # palette, size, labels, log scales
    filters: list[Filter]            # factor level include/exclude, numeric range
    variant_policy: Literal["facet", "pin", "pool"]
```

Serializes to TOML/JSON. Round-trip (`spec -> toml -> spec`) is a test.

## 6. What `scistackplotdb` actually has to solve

`load(as_df=True)` already yields schema keys as columns, so long format is
free. The genuinely new work is the four things a single CSV never had:

1. **Shape classification** — scalar vs 1D vs 2D per variable, and for 1D
   whether to explode the array into rows with an implicit index column
   (`sample`/`percent`) or keep it nested. Determines which plots are offered;
   cached.
2. **Cross-variable joins across schema depths** — plotting trial-level `Speed`
   against subject-level `Mass` means broadcasting the shallower variable down
   the hierarchy. scidb knows the hierarchy; the plot layer must not guess.
   Also gates *which* variables may share a plot at all.
3. **Variants are factors** — a variable with two `low_hz` branch-param variants
   returns *two rows per schema combo* from `as_df`. Treating branch_params as
   ordinary columns silently overplots two pipelines' results as replicates.
   Variants surface as first-class factors (assignable to COLOR/FACET/ITERATE),
   with `variant_policy="pool"` required to be explicit — mirroring the
   `AcrossVariants` decision already made for stats.
4. **Payload budget** — 1D data over hundreds of trials is megabytes.
   Aggregation and downsampling happen server-side before anything crosses to
   the webview.

**Known trap:** zero-padded schema keys (`"01"` stays a string — see the
existing project rule) must survive into factor levels *and* into categorical
sort order. Lexicographic sorting of `"1","10","2"` is a visible bug on an axis.
Order factor levels using scidb's declared key type, not pandas' default.

## 7. Integration with existing `plot_` endpoints

No new recording machinery — `finalized`, artifact stamping, and `scidb report`
already work. `scistackplot` only supplies the body:

```python
def plot_step_length(df, filename):
    g = sns.catplot(data=df, x="session", y="StepLength",
                    hue="limb", col="group", kind="box")
    return g.figure
```

"Save to pipeline" emits that function plus a `for_each(...)` call in which the
spec's `ITERATE` roles become the iterated schema keys and every other factor
stays a DataFrame column — which is exactly decision D2.

**Consistency requirement (test this):** the same spec must produce the same set
of figures whether rendered interactively (internal `groupby` fan-out, many
small panels in the studio) or through the exported `for_each` call (iterated
keys + `PathOutput`). One test asserts panel-set equality across the two paths.

`scifor` is deliberately *not* a dependency of `scistackplot`; interactive
fan-out is a pandas `groupby`. The mapping ITERATE-role → `for_each` kwarg lives
in `scistackplotdb`'s codegen, which may import scifor freely.

## 8. Module layout

```
scistackplot/                        # dist: scistackplot; deps pandas, matplotlib, seaborn, plotly
  src/scistackplot/
    spec.py          PlotSpec, Role, PlotKind, Aggregation — serializable
    table.py         LongTable: factor / measure / index column roles
    shape.py         Shape classification from a DataFrame column
    roles.py         role assignment + invariant validation (exactly one role per factor)
    capability.py    available_plots(), default_plot()
    reduce.py        resolve(spec, table) -> ResolvedPlot  (aggregation, error bands, faceting)
    resolved.py      ResolvedPlot: panels[], series[], encodings, shared limits
    render/
      base.py        Renderer protocol
      mpl.py         ResolvedPlot -> matplotlib Figure     (export / pipeline)
      plotly_.py     ResolvedPlot -> plotly figure dict    (interactive)
    codegen.py       ResolvedPlot + PlotSpec -> literal seaborn/matplotlib source
    sources/
      base.py        DataSource protocol
      frame.py       DataFrameSource
      csv.py         CsvSource

scistackplotdb/                      # dist: scistackplotdb; deps scistackplot + scidb
  src/scistackplotdb/
    source.py        ScidbSource(DataSource)
    load.py          BaseVariable(s) -> long df; multi-variable join
    hierarchy.py     schema-depth broadcast; join eligibility
    variants.py      branch_params as factors; refuse silent pooling
    shape.py         shape classification informed by scidb column types
    endpoint.py      spec -> generated plot_ function + for_each call
```

## 9. VS Code integration

- Right-click a `VariableNode` in the DAG webview → **Plot** → opens a "Plot
  Studio" webview beside the DAG.
- Backed by the **same** Python process over the existing JSON-RPC transport.
  New methods: `plot.describe`, `plot.capabilities`, `plot.resolve`,
  `plot.export`. Reusing the one process is required, not just convenient — a
  second DuckDB connection reintroduces the lock contention the MATLAB
  run-ownership work already fixed.
- Additional entry points: sidebar variable list, `SciStack: Plot…` command,
  and right-click on a `.csv` in the Explorer (routes to `CsvSource`, needs no
  project at all — proves the standalone path stays live).
- Empty state: plotting a variable whose pipeline has never run must say so
  explicitly rather than render an empty axes.

## 10. Staging — all complete 2026-09-05

1. ✅ **`scistackplot` core** — `spec/shape/table/roles/capability/reduce/
   resolved/render.mpl`, `sources/{base,frame,csv}`.
2. ✅ **plotly renderer + codegen** — `render/plotly_.py` emits a plain
   plotly.js dict (no plotly dependency); `codegen.py` emits literal seaborn.
3. ✅ **`scistackplotdb`** — `load/hierarchy/source/endpoint`.
4. ✅ **GUI backend** — `services/plot_service.py`, `api/plot.py` (HTTP), six
   `_h_plot_*` JSON-RPC handlers + METHODS entries, router registered.
5. ✅ **Plot Studio webview** — `components/PlotStudio/PlotStudio.tsx`,
   DAG right-click ▸ Plot, sidebar "Open Plot Studio", `plotly.js-cartesian-
   dist-min` added (the basic bundle has no box/violin/heatmap).
6. ✅ **"Add to pipeline"** — `plot_service.add_to_pipeline` declares the output
   variable through the normal entity path and appends the function to
   `scistack_plots.py` beside the entities file, then reloads the registry.

### First-run fixes (2026-09-06)

1. **`classify_value(True)` returned UNKNOWN.** `bool` is an `int` subclass, so
   the numeric guard rejected it and nothing downstream caught it.
   `classify_column` had the check; the value path didn't. Explicit bool branch
   added ahead of the numeric check.
2. **Two-measure joins dropped the first measure** (`KeyError`). Both
   variables' data columns are named `value` by default; renaming *after* the
   merge used a dict with two identical keys, so one silently shadowed the
   other. Each frame is now renamed to its measure name BEFORE the merge. This
   affected every two-measure plot, not just the failing tests.
3. **Unknown variable raised `ValueError` ("no data column")**, conflating "you
   named something nonexistent" with "this exists but has nothing to plot".
   `ScidbSource.get_table` now validates against the registered variables and
   raises `KeyError` listing what's available, matching the CSV source.
4. **Bad test assertion** (not a bug): generated code legitimately contains the
   `scistackplot-spec:` docstring marker the GUI reads back. The test now
   asserts no `import scistackplot` / `scistackplot.render` instead of a blunt
   substring check.
5. **`describe()` loaded every variable's full data** just to learn its schema
   depth — reading every 1-D array in the database to open the panel, against
   the "stays cheap" claim in its own docstring. Added `load.variable_levels()`
   (one COUNT query per variable; COUNT ignores NULLs) plus a `_levels` cache.

### Follow-on: dict/struct variables (2026-09-06)

Reported after the first real use: a dict-valued variable (`RawEMG`, 13 muscle
fields) plotted only its first field, with a "plotting the first" warning the
user never saw. scidb's `multi_column` storage puts one DuckDB column per key,
and `_value_column` was taking `columns[0]`.

Fixed by melting fields into a **field factor** (`ColName`, matching
`scidb.ColName()` / `PathOutput("{ColName}")`) rather than special-casing
structs in the renderer:

- `FactorInfo.is_field`; `LongTable.from_frame(field_factors=...)`.
- `default_roles` gives a field factor `FACET_COL` — one subplot per field.
- New `default_spec(table, measure)` bundles roles + kind + facet wrap, so a
  13-field struct opens as a wrapped 4-wide grid rather than a 13-wide strip.
  `plot_service.describe` now calls it instead of assembling a spec by hand.
- `codegen` emits the matching `df.melt(...)` — the endpoint receives one
  column per field, so reshaping on the interactive path only would break the
  preview/export equality the parity test exists to protect.
- Two-measure plots with a struct on either side are refused with a message
  (the join has no single value to pair), and structs are excluded from
  `joinable_with`.
- Because the fields are an ordinary factor, moving them to COLOR / ITERATE /
  AGGREGATE all work with no further code.

### Follow-on: facet layout rules, one Facet role (2026-09-06)

1. **`FACET_ROW`/`FACET_COL` collapsed into one `Role.FACET`.** They were
   indistinguishable in use, and forcing the grid decision into the role could
   not express "left/right x muscle group" from a single field factor. FACET is
   NOT single-assignment: several factors may be faceted at once.
2. **Layout is now a rule set**, `FacetOptions.rows`/`cols`: a list of
   `Matcher(op, value)` with ops `starts_with`/`ends_with`/`contains`/
   `not_contains`/`equals`/`regex`. Each panel is placed by matching its label.
   Describing a layout instead of hand-arranging one is what makes it reusable
   across variables — and it is already serialized inside `PlotSpec`, so saving
   these as presets later needs no new format.
   - A panel matching no rule lands in a trailing "other" row/column, never
     dropped; an invalid regex (still being typed) matches nothing rather than
     raising.
   - With rules on one axis only, panels flow along the other.
3. **`reduce` owns the grid.** `Panel.grid_row`/`grid_col` are assigned once;
   `render/base` just reads them. Renderers no longer derive layout, which is
   what let the two axis rules drift.
4. **One rule for tick labels and axis titles** (`base.shows_x_labels`). The
   matplotlib bug behind the report: the title followed "nothing below", but
   the categorical block re-applied `set_xticklabels` to every panel, so tick
   labels came back everywhere. Visibility is now applied last, after every
   `set_xticklabels` call.
5. **UI**: the Controls toggle moved to the left of the header, over the rail it
   collapses; the Full screen button and its `toggle_zen` host handlers are
   gone (the studio is its own tab now).

### Follow-on: the studio is its own editor tab (2026-09-06)

It began as a modal overlay inside the DAG webview, which made the pipeline
canvas unreachable while a figure was open. It is now a separate
`WebviewPanel` (`extension/src/plotPanel.ts`) opened at
`ViewColumn.Beside`, so the two are ordinary tabs that can be split, moved, or
dragged to another window.

- **Same editor group, not a split.** It first opened at
  `ViewColumn.Beside`, which forces a permanent 50/50 split. It now opens in
  the pipeline's own column — read from `DagPanel.viewColumn` rather than
  assumed to be `ViewColumn.One`, so it follows the pipeline tab if the user
  moves it — making the plot a full-width sibling tab next to "SciStack
  Pipeline". Splitting stays available through VS Code's own drag/Split Editor,
  which is the user's layout decision to make, not this panel's.
- **One bundle, two roots.** The plot webview loads the same React bundle and
  is switched into plot mode by an injected `window.__SCISTACK_VIEW__`
  (`main.tsx` → `PlotRoot.tsx`). A second vite target would double the build
  for one component, and the two views share the whole transport layer.
- **The tab is reused.** Plotting a second variable retargets and reveals the
  open panel via an `open_plot_studio` notification rather than piling up tabs;
  `PlotRoot` remounts `PlotStudio` on a key change so no stale spec shows.
- **One entry point.** The DAG right-click, the sidebar button, and both
  commands all funnel through the `scistack.openPlotPanel` command, so there is
  exactly one place deciding how a plot tab opens. `dagPanel.ts` forwards
  `open_plot_panel` to it.
- `PlotStudio` gained an `embedded` prop: no backdrop, no card, no ✕ (the tab's
  own chrome does that). Browser (non-extension) mode keeps the modal, since a
  plain page has no tabs — both callers fall back to it if the RPC fails.
- `retainContextWhenHidden` is on: a spec and its role assignments are
  expensive to rebuild and have no persistence of their own.

### Follow-on: making the figure bigger (2026-09-06)

The panel is a webview inside an editor tab, so `position: fixed` is bounded by
the iframe — a plot can never escape the SciStack tab from inside the webview.
Three layers, smallest hammer first:

1. **Collapse the controls rail** (`Controls ❯` in the header) — width 0 rather
   than unmounted, so control state survives the toggle.
2. **Measured figure height.** Plotly needs a definite pixel height, and the
   hardcoded 460/300 wasted every pixel a bigger panel gained. A ResizeObserver
   on the canvas feeds the real height: one figure fills it, several split it.
   The panel itself grew 90vw/86vh → 96vw/94vh.
3. **`⛶ Full screen`** → host-side `toggle_zen` in `dagPanel.ts`, running
   `workbench.action.toggleZenMode`. Zen Mode hides the activity bar, sidebar,
   panel and status bar, and (default `zenMode.fullScreen`) takes the window
   fullscreen. Deliberately a TOGGLE with a neutral label so the webview keeps
   no state that could desync when the user leaves zen with Esc Esc. In browser
   (non-extension) mode the same button uses the Fullscreen API instead.

Also: backdrop click no longer closes the panel — a stray click while dragging
a plotly selection threw away the exploration.

### Deviations from the original plan

- **Where generated code lands.** The plan said "write into the pipeline
  module". The GUI builds pipelines from the DAG, not from a script, and the
  entities file is the only writable declaration surface — so the function goes
  into `scistack_plots.py` at the project root (inside discovery scope) and the
  `for_each` snippet is *returned* for the user to wire up on the canvas or
  paste into a script. No new write surface was invented.
- **CSV entry point landed early.** Planned as a v1 nicety; implemented because
  it is the cheapest proof that the `DataSource` seam is real
  (`plot_service.get_source(csv_path=...)`, extension `scistack.plotCsv`).
- **Numeric-ID inference limit (new, documented).** A CSV column of bare
  numeric IDs classifies as a measure, not a factor — values alone cannot
  distinguish them. Documented in `sources/csv.py` with the two workarounds.
  scidb sources never hit it.

## 10b. How to run the tests

```bash
pip install -e scistackplot -e scistackplotdb   # or ./dev-install.sh
pytest scistackplot/tests -q
pytest scistackplotdb/tests -q
pytest scistack-gui/tests/test_plot_service.py -q
```

The frontend is already built (`frontend/npm run build` +
`extension/npm run build:all`); rerun both if you edit the .tsx.

## 11. Logging & diagnostics (CLAUDE.md NOTE 2)

- Log through `scistacklog` with `layer="scistackplot"` / `"scistackplotdb"`.
- INFO: spec resolved (measure, kind, panel count, row count); export written.
- DEBUG: role assignment, chosen aggregation, per-panel row counts, and
  `[timing]` for load → resolve → render, since "the plot is slow" will
  otherwise be unattributable between DB load, reduction, and rendering.
- WARN on the traps: variants pooled, factor levels sorted lexicographically
  because no key type was declared, downsampling applied.

## 12. Tests

- `capability.py` truth table across shape × role combinations.
- `PlotSpec` TOML round-trip.
- `resolve()` golden `ResolvedPlot` fixtures (renderer-independent).
- Interactive fan-out vs exported `for_each` panel-set equality (§7).
- Zero-padded key ordering on a categorical axis.
- Variant-bearing variable: refuses to pool silently; facets correctly.
- Generated code executes and returns a `matplotlib.figure.Figure`.
- Schema-depth broadcast join (subject-level × trial-level).

## 13. Open items

- Standalone `serve` mode (FastAPI + the same React app) — deferred past v1;
  the `DataSource` seam is what keeps it cheap.
- MATLAB renderer against `ResolvedPlot` — deferred.
- Shared color scales across separately-iterated figures (the sibling to
  `share_limits` named as future work in the endpoints design doc).
- `for_columns` analog: plotting every column of a multi-column variable.
