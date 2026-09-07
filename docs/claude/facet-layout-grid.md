# Facet Layout: the Grid, the Slots, and the Placement Passes

> Status: **implemented 2026-09-07, all tests passing, uncommitted.** Stage
> detail: `.claude/plan-facet-layout.md`. Companion to
> `docs/claude/plotting-library-design.md`, which covers roles and the
> spec→resolve→render pipeline; this file covers only the arrangement of
> subplots inside one figure.
>
> The short version a future session needs: **the facet grid has a SIZE that the
> user sets and the library completes, a fixed number of ordering SLOTS derived
> from that size, and a placement algorithm whose central invariant is that no
> two panels ever occupy the same cell.** The rendering bugs at the end of this
> file are all consequences of a grid that used to be allowed to lie about its
> own shape.

## 1. The question the controls answer

A `multi_column` EMG variable melts into a field factor (`ColName`) with levels
like `LHAM RHAM LQUAD RQUAD`. Those names carry **two independent facts** — a
side and a muscle group — but the data has only **one** factor. seaborn's model
(`col=` one column, `row=` another) cannot express "left column = the L names",
because there is no L/R column to point at.

So the arrangement is described by **rules over panel names**, not by a second
factor. That is what makes a layout reusable: "left column = names starting with
L" holds for any muscle set, any subject, any variable.

The pre-2026-09-07 surface got this half right. It had rules, but they lived in
two **unbounded** lists ("Rows", "Columns") with +/- buttons, plus a "Wrap at"
box that was ignored whenever any rule existed. The user could not say *"the grid
is 2 columns wide"*; they could only add rules and discover the width
afterwards. Worse, the placement had no occupancy check, so two rules matching
one panel produced two subplots in the same cell.

## 2. The size: `spec.grid_shape_for`

```python
grid_shape_for(n_panels, n_rows=None, n_cols=None) -> (n_rows, n_cols)
```

| pinned        | result                                                     |
|---------------|------------------------------------------------------------|
| `n_cols` only | `n_rows = ceil(n_panels / n_cols)`                         |
| `n_rows` only | `n_cols = ceil(n_panels / n_rows)`                         |
| both          | returned as given                                          |
| neither       | `n_cols = min(4, ceil(sqrt(n)))` if `n > 3` else `n`, then rows follow |

**This is the only copy of that arithmetic.** `roles.default_spec` calls it (a
13-field struct opens 4 wide, 3 fields stay in one horizontal row);
`reduce.plan_layout` calls it; the GUI does **not** — it reads the effective grid
back off the rendered figure (§5). A second implementation in TypeScript is
precisely the thing that would drift.

`FacetOptions.wrap` no longer exists. It was removed outright rather than
aliased, per the project's beta no-deprecation rule.

## 3. The slots

`FacetOptions.rows` and `.cols` are **grid slots, not a list**. `rows[1]` is row
2 whether or not row 1 was filled in, so blanks must stay in the list and
positions must never be compacted.

That makes `Matcher.is_blank` load-bearing:

```python
@property
def is_blank(self) -> bool:
    return not self.value

def matches(self, text):
    if self.is_blank:
        return False          # <- without this, CONTAINS "" matches EVERYTHING
    ...
```

`"" in text` is true of every string, so before this guard the first blank slot
claimed every panel. With fixed-length slots most slots are blank most of the
time, so this went from a curiosity to the default case. A blank slot means
**"whatever is left over, in order"** — which is exactly what makes the worked
example below need only one row rule.

`Matcher.display` returns `""` for a blank slot rather than the op's name, so
blank slots contribute empty headers instead of a column labelled "contains".

Two more slot rules, both about not surprising the user:

* A dimension the user **pinned** truncates the slot list (`row_slots[:n_rows]`).
  Shrinking a 4-row grid to 2 must not be undone by the rules already written
  into rows 3 and 4 — those stay in the spec, so re-widening restores them, but
  they are not rows.
* A dimension left **auto** widens to hold every slot that was written, and then
  shrinks at the end to the cells actually used, so a rule-defined layout never
  leaves a trailing empty column.

## 4. Placement: `reduce.plan_layout`

```python
plan_layout(labels: list[str], facet) -> GridPlan
```

Pure, label-only, no data. That signature is deliberate: `_assign_grid` applies
the result to `Panel` objects, `codegen` **replays** it to emit a matching
`col_order`, and tests assert placement without building a single frame.

Every placement goes through one `occupied: dict[(row, col), label]`. Four
passes, in this order:

| pass | panels | rule |
|------|--------|------|
| **A** | ruled on *both* axes | claim the exact cell; if taken → spill list |
| **B** | ruled on *one* axis | first **free** cell along the other axis |
| **C** | ruled on neither | remaining free cells, row-major, in resolution order |
| **D** | everything spilled | next free cell row-major; **grow a row** if the grid is full |

Pass B searching for a *free* cell (rather than keeping a per-column counter) is
what makes partially-specified grids work, and pass D is what makes the
"never overlap" promise unconditional: a grid too small for its panels gets
taller, it does not stack them.

Panels keep resolution order (the factor's declared level order — zero-padded
keys included) within every pass, so the reading order is stable.

### The worked example

```
cols = [starts_with "L", starts_with "R"]
rows = [contains "HAM",  <blank>]
```

* Pass A: `LHAM → (0,0)`, `RHAM → (0,1)` (both axes ruled).
* Pass B: `LQUAD` has column 0 and no row → first free row in column 0 → `(1,0)`.
  `RQUAD` → `(1,1)`.

Result: `LHAM RHAM / LQUAD RQUAD`, from **one** row rule. Nothing was said about
QUAD anywhere.

### Nothing is dropped, nothing is silent

A panel matching no rule on a ruled axis is simply *free* on that axis and takes
a remaining cell; if that pushes the grid past the declared slots, the extra
rows/columns are labelled `"other"`. Losing a muscle to a typo in a pattern is
the worst possible failure here, so it cannot happen — the muscle appears in an
"other" column instead.

Every deviation from what the rules literally said is appended to
`GridPlan.notes`:

```
GridPlan.notes → ResolvedPlot.layout_notes → to_dict()["grid"]["layout_notes"]
              → plotly layout.meta.layout_notes → the GUI's Layout section
```

plus a `Log.warn` per note and one `Log.debug` carrying the whole placement map
(`RHAM@(0,0), RTA@(0,1), LMG@(1,2)`) — the diagnostic to reach for when a panel
is somewhere unexpected.

## 5. How the GUI stays thin

The panel renders `effRows`/`effCols` slot editors, where those numbers come
from **`figure.layout.meta`**:

```json
{"rows": 2, "cols": 2, "panels": 4, "layout_notes": []}
```

`meta` already existed (the panel sizes the figure from `meta.rows`), so echoing
the effective grid back needed no new RPC. This is what makes "I set 2 columns"
visibly answer "so, 3 rows": the unpinned box shows the computed value as its
placeholder, in italic muted text, and typing into it pins it. Clearing it
returns that axis to auto.

`setRuleAt(axis, index, patch)` pads the array out to the edited index. There is
no add/remove, because the number of rows and columns is the thing the user set
— a rule is a property **of** row 2, not an extra row.

## 6. Three rendering bugs the grid rework depended on

These were all reported as "facets overlap / change orientation / should stay
horizontal", and all three are in the renderers rather than in the layout.

### 6a. Negative cell height inverted tall grids

`render/plotly_.py::_cell` spent a **fixed** fraction of the figure on gaps:

```python
Y_GAP = 0.14
cell_height = (1.0 - Y_GAP * (n_rows - 1)) / n_rows
```

At 8 rows that is ~0.002; at **9 rows it is negative**, so the y domain
`[y0, y0 + h]` runs backwards. Plotly draws those panels inverted and on top of
each other — which reads as corrupt data, not as a layout bug.

Gaps are now clamped to half the figure, in `_gaps(n_rows, n_cols)`:

```python
y_gap = min(Y_GAP, 0.5 / (n_rows - 1)) if n_rows > 1 else 0.0
```

Every cell is then at least `0.5 / n` tall for any grid. Height is absorbed in
**pixels** instead — the panel already sizes the figure by `gridRows * 240`.
`_panel_title` calls the same `_gaps`, because a title offset by the nominal gap
while the cells used a smaller one lands inside the panel above it.

### 6b. Inferred trace orientation

plotly picks box/violin/bar orientation from which of `x`/`y` it recognises, so
a panel whose x came out numeric could draw sideways. All three trace types now
state `"orientation": "v"`.

### 6c. Auto-rotated tick labels

plotly rotates category tick labels towards vertical once a facet cell is too
narrow, so the same figure reads differently at two facet counts. x axes now
carry `"tickangle": 0` with `"automargin": true`; matplotlib gets the matching
`ax.tick_params(axis="x", rotation=0)`.

The mpl renderer's old `row = min(row, n_rows - 1)` clamp silently drew two
panels onto one axes. It is now a guard that logs a warning if it ever fires —
after §4 it must not.

## 7. Export fidelity

seaborn *can* express a rule layout more often than the old code assumed. A
single faceted factor is a strip of panels wrapped at `col_wrap` in `col_order`
order, so any arrangement that **fills the grid without holes** is reproducible —
including two-axis rule grids.

`codegen._facet_layout_args` replays `plan_layout` over the factor's levels and
emits `col_wrap=` plus `col_order=[...]` when `GridPlan.fills_row_major`.
`_seaborn_can_express_layout` asks the same question for the docstring, so the
"seaborn cannot express this" note now fires only for layouts with actual holes
(e.g. `rows=[R, L] x cols=[HAM, TA, MG]` over three panels leaves `(1,0)` empty).

Replaying the plan rather than re-deriving an order is the point: an order
computed twice is an order that can differ, and a preview/export mismatch is
invisible until someone compares two figures by eye.

## 8. Where the tests are

`scistackplot/tests/test_render.py`:

* `test_grid_shape_for_is_the_one_place_the_arithmetic_lives` — the size table.
* `test_no_two_panels_ever_share_a_cell` — parametrized over no rules, pinned
  grids, one-axis rules, a deliberately colliding rule pair, and a 1×1 grid.
  **This is the invariant of the whole rewrite.**
* `test_columns_by_side_then_a_row_by_group` — the worked example, exact cells.
* `test_a_blank_slot_claims_nothing`, `test_shrinking_the_grid_ignores_leftover_slots`.
* `test_plotly_cells_never_invert_or_overlap` / `..._columns_...` — 1 through 20.
* `test_plotly_distributions_are_drawn_vertically`, `..._tick_labels_stay_upright`.

`scistackplot/tests/test_codegen.py` covers both export branches
(`col_order` emitted / "cannot express" note). The `bilateral_table` fixture in
`conftest.py` is the four-muscle L/R × HAM/QUAD table these cases need.
