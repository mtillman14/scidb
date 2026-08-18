# #8: Sweep node

Status: **BUILT (2026-08-13)**.

## Design

Confirmed with user: backend is sugar over the same `EachOf` mechanism
#10 built (PathInput alternates); the real work is the frontend UI for
building the value list.

**Identity model**: Sweep builds on Constant's established pattern —
shared-by-name, wired via the same `in__{param}`/edge convention, palette
"+" creates an empty `{name, values: []}` definition, then the settings
panel configures it. Unlike Constant, a Sweep's values are never staged
one at a time through `_pipeline_pending_constants` — the whole point is
a *generated* list, computed once and stored as the final flat array
(mirrors the PathInput-alternates precedent: range generation is a pure
frontend concern, the backend only ever stores and wraps plain numbers).

**Resolution**: exactly parallels PathInput's "resolve missing params by
name, last, in `build_run_inputs`" pattern (see
`.claude/plan-pathinput-fresh-run-fix.md`) — a Sweep is never a citizen
of `input_types`/`constants`/DB history either, for the same reason
PathInput isn't: it's meant to become `EachOf(...)` fresh at execution
time, not a staged scalar. `build_run_inputs` now checks the PathInput
registry first, then the Sweep registry, per missing param — confirmed
independent (a function can have both a PathInput param and a Sweep
param resolved correctly in one call).

## What was built

**Backend** — `layout.py`: `sweeps: []` in storage (new default key +
migration `setdefault`), `read_all_sweep_names()` / `write_sweep(name,
values)` / `delete_sweep(name)`. `graph_builder.py`: `"sweep__"` added to
`_DB_DERIVED_PREFIXES` (multi-scope placement support, same reason
`pathInput__`/`const__` are there — same-named node placed independently
in more than one scope needs placement-qualification); `build_sweep_nodes()`
(no DB-aggregation counterpart to overlay onto, unlike PathInput — reads
`layout.json` directly); `build_manual_node`'s type dispatch gained a
`sweepNode` branch. `api/pipeline.py`: `build_sweep_nodes` wired into the
node-building sequence. `execution_service.build_run_inputs`: Sweep
resolution branch — `EachOf(*values)` for >1 value, plain scalar for
exactly 1, left unresolved (logged) for an empty/unconfigured Sweep.
`edge_resolver.py`: **no changes needed** — confirmed a sweepNode source
already falls through both the constant and variable branches untouched,
identically to how PathInput sources already do.

REST (`api/layout.py`) + JSON-RPC (`server.py`) + frontend routes
(`api.ts`): `GET/POST /api/sweeps`, `PUT/DELETE /api/sweeps/{name}`.

**Frontend**:
- `SweepNode.tsx` — canvas node, distinct color (`#65a30d`, unused by any
  other node type), shows a value preview + "N values — EachOf" badge
  when >1.
- `SweepSettingsPanel.tsx` — the core ask. Two modes:
  - **List**: comma/space-separated direct entry.
  - **Range**: start + end + a toggle between "step size" and "number of
    steps" (both explicitly requested in the original to-do text) — one
    numeric field whose meaning switches with the toggle, live-generates
    the value list in JS (`generateRange`, float-noise-cleaned via
    rounding to 10 decimals).
  - Both modes show a live preview before saving, and an "EachOf(N
    values)" hint once there's more than one.
  - Save sends the final computed array to `update_sweep`.
- Wired into `PipelineDAG.tsx` (nodeTypes registry, click-selection,
  drag-create prefix/optimistic data), `EditTab.tsx` (new "Sweeps"
  palette section, same "+" create-then-configure flow as Path Inputs),
  `Sidebar.tsx` (type guard + dispatch).

## Tests

`tests/test_pipeline_scopes.py`:
- `TestSweeps` (4 cases): create/list, update replaces (not appends),
  delete, canvas placement + edge wiring (mirrors how a Constant node is
  placed and wired).
- `TestSweepExecutionResolution` (4 cases): multi-value → `EachOf`;
  single-value → plain scalar (not EachOf-wrapped); empty/unconfigured →
  left unresolved (fail-safe, not a crash); a function with BOTH a
  PathInput param and a Sweep param resolves both correctly in one call.

## To verify

```
cd /workspace
uv run pytest scistack-gui/tests/test_pipeline_scopes.py -k "Sweep" -v
cd scistack-gui/frontend && npm run build
```

Then in the GUI: drag a Sweep from the palette, name it, select it, try
both List and Range modes (check the live preview and the step-size ↔
count toggle), save, wire it into a function's input, and run — the
`[execution] ... resolved via Sweep(N value(s))` log line should appear,
followed by N separate `for_each` iterations (one per value).
