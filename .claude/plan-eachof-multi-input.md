# #10: multiple nodes on one function input → EachOf

Status: **BUILT (2026-08-13)**.

## Scope, refined from the original to-do text

The original to-do ("if two path input, maybe constant and variable nodes
too, are attached to the same function input, treat as EachOf") turned
out to have very different answers per node type once investigated:

- **Variable nodes: already fully worked, no code needed.** Confirmed by
  direct read: `edge_resolver.resolve_function_edges` already collects
  multiple variable types wired to one input into a list, and
  `execution_service.build_run_inputs` already converts a multi-entry
  list into `EachOf(*variable_classes)`. The frontend already allows
  drawing multiple edges into one handle (`isValidConnection` only
  checks for cycles). Nothing to build.
- **Constant nodes: not a real "two nodes" scenario.** A single Constant
  node already holds multiple staged values (`values: ConstantValue[]`),
  which is the existing, correct fan-out mechanism. Two *separate*
  constant nodes wired to the same input is a latent last-write-wins
  bug, not a meaningful use case — out of scope here.
- **PathInput: the actual gap.** PathInput identity is a single global
  `{name, template, root_folder}` (see
  `.claude/plan-pathinput-fresh-run-fix.md` — PathInput isn't even
  edge-wired, it's matched to a function param purely by name). There
  was no way to give one parameter two alternative templates at all.

So the real work was: let one PathInput definition hold multiple
template alternatives, mirroring exactly how Constant nodes already hold
multiple values — not new edge-wiring semantics.

## Design (confirmed with user: list-of-rows UI, same pattern as
ConstantSettingsPanel)

**Storage** (`layout.py`): the primary `{template, root_folder}` fields
are unchanged (every existing reader/writer keeps working); a new
`alternate_templates: [{template, root_folder}, ...]` list rides
alongside. `read_all_path_input_names()` now always includes this key
(defaulted to `[]`) so no caller needs its own defensive `.get(...,
[])`. New functions `add_path_input_alternate(name, template,
root_folder)` / `remove_path_input_alternate(name, index)` — raises
`ValueError` if no primary definition exists yet (mirrors staging a
constant value on a constant node that doesn't exist).

**API** (3-places rule): `POST /api/path-inputs/{name}/alternates`,
`DELETE /api/path-inputs/{name}/alternates/{index}` in `api/layout.py`;
`add_path_input_alternate`/`remove_path_input_alternate` handlers in
`server.py`'s JSON-RPC table; matching routes in frontend `api.ts`.

**Execution** (`execution_service.build_run_inputs`): when a path-input
param has alternates, builds `EachOf(PathInput(primary), PathInput(alt1),
...)` instead of a bare `PathInput` — same construction site the
fresh-run fix already added, extended rather than duplicated.

**Display propagation**: `alternate_templates` threaded through
`graph_builder.overlay_saved_path_inputs` → `build_path_input_nodes`
(and the manual-node placeholder in `build_manual_node`) so the frontend
node data always carries it.

**Frontend**: `PathInputNode.tsx` shows a small "+N alt(s)" badge on the
canvas when alternates exist. `PathInputSettingsPanel.tsx` gained an
"Alternate Templates" section: a list of rows (template + root folder +
remove ×), an add-alternate form below — same shape as
`ConstantSettingsPanel`'s variant list, confirmed with the user before
building.

## Tests

`tests/test_pipeline_scopes.py`:
- `TestPathInputAlternates` (5 cases): add/list, index ordering across
  multiple adds, remove by index, 400 when no primary exists, new
  PathInputs default to an empty list.
- Two cases added to `TestPathInputExecutionResolution`: alternates
  resolve to `EachOf(PathInput, PathInput, ...)` with correct
  template/root_folder per alternative; the no-alternates case stays a
  bare `PathInput` (not EachOf-wrapped), confirming the common case is
  unaffected.

## To verify

```
cd /workspace
uv run pytest scistack-gui/tests/test_pipeline_scopes.py -k "PathInput" -v
cd scistack-gui/frontend && npm run build
```

Then in the GUI: select a PathInput node, add a second template via the
new "Alternate Templates" section, confirm the canvas badge shows "+1
alt", wire it to a function, and run — the log line from the fresh-run
fix should now say the input resolved via `EachOf(PathInput(...),
PathInput(...))`.
