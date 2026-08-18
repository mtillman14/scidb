# Default plotting for scalar/1D variables (to-do #4)

Goal: a no-code way to visualize any scalar or 1D-numeric variable directly
from its node in the sidebar, aggregated at a user-chosen schema level
("every trial", "average over all trials", "average over all trials and
subjects", or any partial combination in between), with interactive
(hover-labeled) charts — as opposed to today's `plot_`/`stat_` mechanism
(`docs/claude/plotting-leaf-nodes.md`), which requires the user to author a
matplotlib function and only renders static PNGs.

## Eligibility: what counts as "scalar or 1D numeric"

Every variable's raw data lives in a physical DuckDB table named
`{VariableName}_data` with columns `record_id` + one-or-more data columns
(`scidb/database.py::_save_native`; the same table `api/variables.py`'s
existing `get_variable_records` already queries).

- Exactly ONE data column (excludes dict/DataFrame-shaped variables, which
  spread across multiple columns — out of scope, matches the to-do's
  "scalar or 1D" wording; `_infer_data_columns` in sciduckdb gives a dict
  one column PER KEY, so this check alone rules those out for free).
- **Classified from an actual fetched sample value's Python type**
  (`float`/`int` → scalar, `list` of numeric → 1D; `bool` explicitly
  excluded since it's an `int` subclass), NOT by parsing a DuckDB SQL
  type-name string. This was the original plan, but the exact
  `information_schema.columns.data_type` spelling for array/list columns
  (`"DOUBLE[]"` vs. something else across DuckDB versions) can't be
  verified in this environment (no `duckdb` Python package here) — sampling
  the duckdb client's own already-fetched Python value sidesteps that
  entirely and needs no DuckDB-version assumption. A column is uniformly
  typed, so one sample row classifies the whole column; the one edge case
  (a variable registered but with zero records) is handled as "no records
  yet", which is an accurate reason regardless of the underlying type.

## Backend

New `get_variable_plot_data(variable_name, db)` in `api/variables.py`
(alongside `get_variable_records`, same file/module — shares the
`_variables` existence check and the `{name}_data` JOIN-to-`_record`/
`_schema` query pattern, just also selecting the value column):

```
GET /api/variables/{variable_name}/plot-data
->
{
  "eligible": bool,
  "reason": str | null,           # why not, when eligible=false
  "kind": "scalar" | "1d" | null,
  "schema_keys": [...],
  "points": [
    {<schema_key>: <value-or-null>, ..., "value": number | number[]},
    ...
  ]
}
```

Ships every raw point to the frontend (no server-side aggregation) — this
is a local research tool, not a hosted multi-tenant service, and shipping
raw points lets the frontend recompute any schema-level aggregation
instantly with zero round trips as the user toggles checkboxes. Wired
through `services/variable_service.py`, `server.py`'s `_HANDLERS`, and
`api.ts` (three-places rule), mirroring `get_variable_records` exactly.

## Frontend

**New dependency**: `plotly.js-basic-dist-min` + `react-plotly.js`
(via its `/factory` entry point: `createPlotlyComponent(Plotly)` bound to
the lite bundle — scatter/bar/histogram only, ~1.1MB vs 3.5MB+ for the
full library, still real interactive hover/zoom/pan). This is the
standard way to get genuinely interactive charts in a React app without a
server-side rendering round trip; nothing else in this repo does
client-side charting yet.

**New `components/Sidebar/VariablePlot.tsx`**, rendered inside
`VariableSettingsPanel.tsx` below the existing Records section, only when
the fetched data is `eligible` (otherwise a one-line "not plottable"
note, not an error — matches the project's tolerant-by-default UX).

**Schema-level control**: one checkbox per schema key — checked = "keep
this dimension distinct" (an axis/grouping factor), unchecked = "average
over this dimension." Default: all checked (= "every trial", the to-do's
first example). This is a strict generalization of the to-do's named
examples rather than three hardcoded presets — "average over all trials"
is just the `trial` checkbox unchecked, "average over all trials and
subjects" is `trial` + `subject` unchecked, and any other partial
combination the user wants is already a first-class case for free.
Grouping/averaging happens **client-side** (fast, matches "ships every
raw point" above):
- **scalar**: group by the checked keys' values, mean the rest.
- **1d**: same grouping, then an elementwise mean across the group's
  arrays. Arrays of mismatched length within a group are NOT silently
  dropped or truncated — the group is flagged with a visible warning
  instead (fail loud, matches the hidden-ports precedent's "reversible,
  not restrictive" stance elsewhere in this app).

**Chart shape**:
- `kind: "scalar"` → one `scatter` trace (markers), x = a synthetic
  per-group index, hover text listing every checked schema key's value +
  the numeric value for that point/group.
- `kind: "1d"` → one `scatter` line trace PER remaining group, x = array
  index, hover text listing the group's schema-key values + index + value.

## Effort shape

Backend: one query function (mirrors an existing one almost exactly) + one
endpoint through the usual 3 layers. Small. Frontend: one new npm
dependency + one new chart component + a handful of checkboxes — the
aggregation and Plotly trace-building logic is the bulk of the real work.
Medium.

## Status: BUILT (2026-08-13)

Implemented as designed above, with the eligibility-check revision noted
above (sample-based, not SQL-type-string-based):

- **Backend** — `get_variable_plot_data` in `api/variables.py` (+
  `_numeric_plot_kind` helper), delegated through
  `services/variable_service.py`, `server.py`'s `_HANDLERS`, and `api.ts`'s
  route table. `GET /api/variables/{name}/plot-data`.
- **Frontend** — added `plotly.js-basic-dist-min` + `react-plotly.js`
  (factory pattern) as real npm dependencies (verified: `npm install`,
  `npx tsc --noEmit`, and `npm run build` all run and pass in this
  environment — Node/npm ARE available here, unlike Python). New ambient
  module declaration `src/plotly-basic-dist-min.d.ts` (the pre-bundled
  package ships no types; react-plotly.js's own factory typing already
  treats the Plotly instance as `unknown`). New
  `components/Sidebar/VariablePlot.tsx` — one checkbox per schema key
  (checked = kept as a distinct group, default all-checked = "every
  trial"), client-side grouping/averaging, mismatched-array-length groups
  flagged rather than silently dropped, Plotly scatter (scalar) or
  per-group line traces (1D). Wired into `VariableSettingsPanel.tsx` above
  the existing Records section.
- **Tests** — `tests/test_variable_plot_data.py`: scalar variable, 1D
  variable (reuses conftest's seeded `RawSignal`), unknown variable,
  string/2D-array/dict variables (each ineligible for a different reason),
  an all-records-excluded variable ("no records yet"), and the REST
  endpoint. Not yet run by the user (no Python access in this environment
  — handed over as usual).

Bundle size note: the production build (`npm run build`, which also
regenerated the previously-stale committed `scistack_gui/static/` bundle
to reflect ALL of today's session's frontend changes, not just this one)
grew to ~1.65MB main chunk (vite's 500KB chunk-size warning, not an
error) — the `-basic-dist-min` Plotly build was chosen specifically to
minimize this; further code-splitting wasn't done since it wasn't asked
for and adds complexity.
