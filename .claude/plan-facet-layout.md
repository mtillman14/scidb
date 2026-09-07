# Facet layout: N rows × N columns with per-slot ordering rules

## Context

The Plot Studio's "Layout" section today offers a single **"Wrap at"** box plus two
*variable-length* lists of match rules ("Rows", "Columns"). That surface has three
problems the user hit in practice:

1. **Panels are drawn on top of each other.** `reduce._assign_grid`
   (`scistackplot/src/scistackplot/reduce.py:583`) has no occupancy check when both
   axes carry rules: any two panels matching the same row rule *and* the same column
   rule land in the same `(grid_row, grid_col)`. In plotly that means two axis pairs
   with an identical `domain`; in matplotlib both draw onto the same `axes[row][col]`
   (`render/mpl.py:59` clamps rather than resolves).
2. **Tall grids render squashed/inverted.** `render/plotly_.py::_cell` uses a *fixed*
   `Y_GAP = 0.14`. Cell height is `(1 - 0.14*(n_rows-1))/n_rows`, which reaches ~0.002
   at 8 rows and goes **negative at 9+** — the y domain then runs backwards, so panels
   invert and overlap.
3. **Subplot content rotates.** Neither renderer states an orientation: plotly infers
   box/violin/bar orientation from which of `x`/`y` it sees, and auto-rotates category
   tick labels to vertical when a facet cell is narrow.

Separately, the rule lists don't express what the user actually wants to say: *"the
grid is 2 columns wide; column 1 is the L-names, column 2 the R-names; row 1 is the
HAM muscles"*. Rules should be **slots in a grid of a known size**, not an unbounded
list.

**Outcome:** Layout becomes `N rows` / `N columns` (either one auto-computes the
other from the facet count), with exactly that many per-row and per-column rule slots
that fix the facet order. Placement is guaranteed collision-free, the grid never
inverts, and panel content is always drawn horizontally (vertical marks, upright
labels).

Decisions already taken with the user:
- Overflow policy: **spill to the next free cell and warn** — never overlap, never drop.
- `FacetOptions.wrap` is **removed outright** (clean break, per the project's beta
  no-deprecation rule), replaced by `n_rows` / `n_cols`.

All layout semantics live in `scistackplot`, not in the GUI (CLAUDE.md NOTE 3); the
panel stays a renderer of what the backend returns.

---

## Stage 1 — `spec.py`: grid size on `FacetOptions`, inert blank matchers

`scistackplot/src/scistackplot/spec.py`

- `FacetOptions`: drop `wrap`; add `n_rows: int | None = None`, `n_cols: int | None = None`.
  Update `to_dict`/`_facet_from_dict` (both already enumerate facet fields by hand).
- `Matcher.matches`: a matcher with an **empty `value`** matches nothing, for every op.
  Today `MatchOp.CONTAINS` with `value=""` matches *everything* (`"" in text`), which
  would make every blank slot in the new fixed-length UI swallow the whole grid. Blank
  slot == "whatever is left over, in order" — that is the user's row-2 case.
  (`EQUALS`/`NOT_CONTAINS` against a literal empty string are not worth keeping; a
  blank box must mean "unset".)
- New pure helper, so the GUI and the library agree on the arithmetic:

  ```python
  def grid_shape_for(n_panels, n_rows=None, n_cols=None) -> tuple[int, int]
  ```
  - both given → returned as-is (Stage 2 may still grow them to avoid a collision);
  - one given → the other is `ceil(n_panels / given)`;
  - neither → the current `default_spec` heuristic moves here:
    `n_cols = min(4, ceil(sqrt(n)))` when `n > 3` else `n`, then `n_rows = ceil(n/n_cols)`
    — i.e. a small facet set stays a single horizontal row, which is the "always
    horizontal" default.

## Stage 2 — `reduce.py`: collision-free placement

`scistackplot/src/scistackplot/reduce.py` — rewrite `_assign_grid` (and fold
`_flow_grid` into it; the two modes become one algorithm).

Placement passes over an `occupied: set[tuple[int,int]]`, so **no cell is ever claimed
twice**:

1. Resolve rule indices per panel via the existing `_match_index` (first match wins);
   an unmatched panel on a *ruled* axis still goes to the trailing `"other"` slot as
   today, and a panel on an axis with only blank slots is simply "free" on that axis.
2. Grid size = `grid_shape_for(len(panels), facet.n_rows, facet.n_cols)`, raised to at
   least the number of non-blank rules (+1 for an `"other"` slot) on each axis.
3. Pass A — panels fixed on **both** axes claim their cell; a taken cell defers the
   panel to the spill list.
4. Pass B — panels fixed on **one** axis take the first *free* cell along the free
   axis (row-major within their column / left-to-right within their row). This is what
   makes the user's example fall out: `cols=[starts with "L", starts with "R"]`,
   `rows=["contains HAM", <blank>]` → `LHAM (0,0) RHAM (0,1) LQUAD (1,0) RQUAD (1,1)`.
5. Pass C — unconstrained panels fill the remaining free cells in row-major order
   (this reproduces today's plain wrapped flow when no rules are set).
6. Pass D — spilled panels take the next free cell row-major; if the grid is full it
   **grows by a row**, and a note is recorded.

Panel order within a pass stays the resolution order (level order), so the ordering the
user sees is stable.

Return an extra `notes: list[str]` alongside `(n_rows, n_cols, row_labels, col_labels)`:
one note per spill/overflow/grid-growth, each naming the panels involved. Keep the
existing `Log.warn`/`Log.debug` calls and add a debug line with the final placement map
(CLAUDE.md NOTE 2 — this is the diagnostic that makes a mis-placed facet observable).

## Stage 3 — carry the layout facts to the caller

- `resolved.py`: `ResolvedPlot` gains `layout_notes: list[str]`, serialized in `to_dict`
  under `"grid"` next to `row_labels`/`col_labels`.
- `render/plotly_.py`: extend the existing `layout["meta"]` (already `{rows, cols}`) with
  `panels: len(resolved.panels)` and `layout_notes`. `meta` is how the grid already
  reaches the GUI (`PlotStudio.tsx:373` reads `meta.rows` for sizing) — no new RPC.

## Stage 4 — renderers: no overlap, no rotation

`scistackplot/src/scistackplot/render/plotly_.py`
- `_cell`: clamp the gaps to the cell size —
  `y_gap = min(Y_GAP, 0.5 / n_rows)`, `x_gap = min(X_GAP, 0.5 / n_cols)` (0 when that
  axis has one slot). Cell height is then `≥ 0.5/n_rows > 0` for any grid, so domains
  can never invert or overlap. Figure *height* absorbs tall grids instead — the panel
  already scales by `gridRows * 240`.
- Box/violin/bar traces (`_panel_traces`, lines 161–196): set `"orientation": "v"`
  explicitly instead of letting plotly infer it from the arrays.
- `_add_axes`: `"tickangle": 0` and `"automargin": True` on the x axis, so narrow facet
  cells never flip category labels to vertical.

`scistackplot/src/scistackplot/render/mpl.py`
- `_apply_axes_cosmetics`: `ax.tick_params(axis="x", rotation=0)`.
- `render`: the `min(row, n_rows - 1)` clamp at lines 59–60 becomes a guard that logs a
  warning if it ever fires — after Stage 2 it must not.

## Stage 5 — `roles.py` + `codegen.py` follow the rename

- `roles.py::default_spec`: replace the local `wrap` computation with
  `FacetOptions(n_cols=..., n_rows=...)` from `grid_shape_for` (the heuristic moved in
  Stage 1; `math` import may become unused).
- `codegen.py:239`: `col_wrap=spec.facet.n_cols`.
- `codegen.py:117` docstring note: when the layout has rules on **one** axis only and
  there is a **single** FACET factor, emit seaborn's `col_order=[...]` (or `row_order`)
  taken from the resolved panel order, so the exported figure matches the preview.
  A two-axis rule grid over one factor still has no seaborn equivalent — keep the
  existing explanatory note for that case.

## Stage 6 — GUI Layout section

`scistack-gui/frontend/src/components/PlotStudio/PlotStudio.tsx`

- `FacetOptions` TS interface: `wrap` → `n_rows` / `n_cols`.
- Replace the "Wrap at" input with two number inputs, **N rows** and **N columns**.
  Each shows the *effective* value from the last render's `meta` as a muted
  placeholder when the user hasn't set it, so specifying one visibly computes the
  other. A cleared box returns that axis to auto.
- Replace `RuleList` (add/remove buttons) with `RuleSlots`: exactly `effRows` row slots
  and `effCols` column slots, each an op `<select>` + value `<input>` labelled
  "Row 1…N" / "Column 1…N", blank meaning "anything left over". `addRule`/`removeRule`
  are replaced by a single `setRuleAt(axis, index, patch)` that pads the array to the
  slot count. Slot count comes from the rendered grid, never re-derived in TS.
- Render `meta.layout_notes` as a warning line inside the Layout section (this is how
  the spill policy stays honest — the user is told which panel didn't land where the
  rule said).
- Keep the section gated on `faceted`.

## Stage 7 — tests

`scistackplot/tests/test_render.py` (extend the existing `_layout_spec` helper) and
`test_core.py`:

- `n_cols` set → `n_rows` computed to cover all facets, and vice versa.
- **No two panels share a cell** — asserted over the existing rule fixtures plus a
  deliberately colliding one (`rows=[contains "A"], cols=[contains "A"]`).
- The user's EMG case: `cols=[starts_with L, starts_with R]`, `rows=[contains HAM, blank]`
  → exact `(row, col)` for all four panels.
- A blank matcher matches nothing (regression guard for `"" in text`).
- Spill: 5 panels into a 2×2 → grid grows, every panel placed once, a note is emitted.
- plotly `_cell`: for 1…20 rows every domain is strictly increasing and non-overlapping.
- Box/violin/bar traces carry `orientation: "v"`; x axes carry `tickangle: 0`.
- Update the `wrap=`-based tests (`test_render.py:174`, `test_core.py:255-280`) to the
  new field names; update the round-trip test to cover `n_rows`/`n_cols`.

Also update `scistackplotdb/tests/test_fanout_parity.py` only if it names `wrap`.

## Verification

Python (hand off — I don't run pytest here), one package per invocation:

```
pytest scistackplot/tests
pytest scistackplotdb/tests
pytest scistack-gui/tests/test_plot_service.py
```

Frontend — both bundles, or the fix is dead on arrival:

```
cd scistack-gui/frontend
npm run build
VITE_BUILD_TARGET=webview npm run build
```

End-to-end in the Plot Studio, on a struct variable with L/R-named fields:
1. Set **N columns = 2** → N rows shows the computed count; the grid is 2 wide.
2. Column 1 `starts with "L"`, column 2 `starts with "R"` → sides split.
3. Row 1 `contains "HAM"` → row 1 reads `LHAM`, `RHAM`; the rest fill below in order.
4. Set N rows = 13, N columns = 1 → panels stay separate and upright (this is the case
   that used to invert).
5. "Save image" → the matplotlib figure has the same arrangement and no rotated labels.

## Housekeeping (CLAUDE.md)

- Copy this plan to `.claude/plan-facet-layout.md` as the first implementation step.
- Offer to write `docs/claude/facet-layout-grid.md` covering the placement algorithm and
  the plotly domain arithmetic once the code settles.
