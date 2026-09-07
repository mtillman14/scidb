# Parameter refresh-from-file + open-source-file (right-click)

## Context

Parameters with complex values (dicts/structs) are awkward to build through
`ParameterSettingsPanel`'s add-value form. The user wants to hand-edit
`src/scistack_entities.toml` directly for those, then pull the change into
the GUI without paying for a full "🔄 Refresh Code" rescan (~16.5s on a real
project — re-imports every Python module, re-parses every MATLAB file). They
also want a quick way to jump to a Parameter's declaration from the canvas.

Both asks turn out to be nearly free, because the primitives already exist
and just aren't reachable from a Parameter's UI yet:

- `registry.reload_entities_file()` (`scistack_gui/registry.py:716`) is
  already a narrow, single-TOML-parse reload — today it only fires
  internally after the GUI's own writes
  (`target_file_service.py:701`). There is no standalone route for a user
  to trigger it after an *external* edit.
- Every `Parameter` already carries `source_file`/`source_line`
  (`scidb/src/scidb/entities.py:338-339` for TOML-declared,
  `scidb/src/scidb/parameter.py:78-79` for legacy `.py`-declared) — no new
  location tracking needed.
- The VS Code open-in-editor bridge (`reveal_in_editor`, intercepted in
  `extension/src/dagPanel.ts:68-80/189+`) and its non-VS-Code fallback
  (`SourceLocationDialog`) already exist and are already used this way by
  `FunctionNode.tsx:234-254`'s double-click "open source".

Confirmed with the user: "open source" generalizes to wherever a Parameter
is actually declared (dynamic `file:line` label), not restricted to
`scistack_entities.toml` — covers legacy read-only `.py`/`.m` Parameters for
free. Per this repo's CLAUDE.md NOTE 3, this is entirely GUI-layer work
(`scistack-gui/`) — no `scidb` changes needed.

## Backend

1. **`scistack_gui/domain/graph_builder.py`** — add a pure helper:
   ```python
   def is_declared_in_entities_file(source_file, entities_file) -> bool:
       return source_file is not None and entities_file is not None and source_file == entities_file
   ```
   Extend `build_parameter_nodes(...)` (line 1237) with a new optional
   trailing kwarg `entities_file: "str | None" = None`. In the per-name
   loop, pull `param.source_file`/`param.source_line` (guard `param is
   None` for DB-only/no-longer-declared values) and add `source_file`,
   `source_line`, `declared_in_entities_file` to each node's `data`.

2. **`scistack_gui/api/pipeline.py:693`** — pass the entities file at the
   one call site:
   `str(registry._config.entities_file) if registry._config and registry._config.entities_file else None`.

3. **`scistack_gui/services/layout_service.py`**
   - Extend `get_parameters()` (line 291) with the same three fields,
     reusing `is_declared_in_entities_file` — keeps one comparison instead
     of a second copy for the sidebar.
   - Add `refresh_parameter_source(name: "str | None" = None) -> dict`,
     next to `hide_parameter_value`/`unhide_parameter_value` (line 551) for
     the `_notify_dag_updated()` precedent (dispatches to WS broadcast or
     stdout JSON-RPC correctly either way). Body: call
     `registry.reload_entities_file()`; `{"ok": False, "error": ...}` on
     failure, else `_notify_dag_updated()` + `{"ok": True}`. `name` is
     logged only — the reload is whole-file, so every entities-file
     Parameter refreshes as a side effect, not just the one clicked.

4. **`scistack_gui/api/layout.py`** — new route beside the existing
   `/parameters/{name}` CRUD (~line 123-169):
   ```python
   @router.post("/parameters/{name}/refresh-source")
   def refresh_parameter_source(name: str):
       from scistack_gui.services.layout_service import refresh_parameter_source as _refresh
       return _refresh(name)
   ```

5. **`scistack_gui/server.py`** — RPC handler mirroring
   `_h_create_parameter`/`_h_update_parameter` (lines 542-562), registered
   in `_HANDLERS` (~line 936) as `"refresh_parameter_source": _h_refresh_parameter_source`.
   Does **not** call `notify()` itself — `layout_service` already does.

6. **`frontend/src/api.ts`** — route table entry:
   `refresh_parameter_source: { path: (p) => \`/api/parameters/${encodeURIComponent(p.name as string)}/refresh-source\`, method: 'POST' }`.

## Frontend

7. **`ParameterNode.tsx`** — extend `ParameterNodeData` (lines 70-73) with
   `source_file?: string | null`, `source_line?: number | null`,
   `declared_in_entities_file?: boolean`. No render changes here —
   `PipelineDAG.tsx` reads `node.data` directly for its context menu, same
   as it already does for `functionNode`/`variableNode`.

8. **`PipelineDAG.tsx`** — canvas context menu:
   - Widen `ContextMenuState`'s `nodeType` to include `'parameterNode'`
     plus `paramLabel`, `paramSourceFile`, `paramSourceLine`,
     `paramDeclaredInEntitiesFile`.
   - Widen `onNodeContextMenu`'s guard (line 370) to allow
     `parameterNode`; bail if `!data.source_file` (mirrors the existing
     "isolated node, nothing to offer" bail for `variableNode`, line 388).
   - New render block (pattern-matched against the two at 786-806): "🔄
     Refresh from file" gated on `paramDeclaredInEntitiesFile`; "📝 Open
     source (`file:line`)" shown whenever a location is known — reuse
     `formatLocation` from `Sidebar/useSourceEdit.ts`.
   - Two handlers: `handleRefreshParameterSource` (calls
     `refresh_parameter_source`, no optimistic update — relies on the
     backend's `dag_updated` broadcast, same as hide/unhide);
     `handleOpenParameterSource` (mirrors `FunctionNode.tsx`'s
     `isVSCodeMode ? reveal_in_editor(...) : setSourceLoc(...)`, but skips
     the RPC round-trip since file/line are already on the node data).
   - Render `<SourceLocationDialog>` once, driven by new `sourceLoc` state.

9. **`Sidebar/EditTab.tsx`** — sidebar row context menu:
   - `parameters` state: `string[]` → `{name, source_file, source_line,
     declared_in_entities_file}[]`; update `fetchParameters()` (~204-211)
     accordingly; update the render map (678-687) to `c.name` + a new
     `onContextMenu` prop on `DragItem`, wired only when `c.source_file`
     is present.
   - `DragItem`: add optional `onContextMenu?` prop on the root `<div>` —
     additive, every other caller is unaffected.
   - New local state + the same two handlers as step 8 (viewport-`fixed`
     positioning + a transparent backdrop `<div>` to close on click-away,
     since EditTab has no canvas-relative bounding box to work with).

**No shared `ContextMenu` component.** This matches the codebase's existing
convention — `PipelineDAG.tsx` already hand-rolls two separate inline menu
blocks rather than one generic one, and the two new call sites differ
enough in positioning model (canvas-relative vs. viewport-fixed) and state
plumbing (`useReactFlow().setNodes` vs. plain `useState`) that a shared
component would need a nontrivial prop surface for what it saves. The real,
sufficient reuse is `formatLocation` (already extracted) and the
`refresh_parameter_source` RPC name.

## Verification

**Backend — hand off to the user, never run via Bash here:**
- Extend `tests/test_graph_builder.py`'s `TestBuildParameterNodes`:
  `source_file`/`source_line`/`declared_in_entities_file` threaded
  correctly (match, mismatch → `False`, and the DB-only/no-current-source
  case → all `None`/`False`).
- New `tests/test_parameter_refresh.py`: `refresh_parameter_source()`
  success (hand-edit the TOML text directly, call the function, assert
  `{"ok": True}` and the registry reflects the new value) and failure (no
  entities file configured); assert `_notify_dag_updated` fires on success
  only — `test_narrow_reload.py` already asserts absence of the expensive
  full-reload path and is the pattern to match. Also extend
  `get_parameters()` coverage for the three new keys (entities-file case
  and legacy-`.py` case).
- `tests/test_entity_update_endpoints.py`: add REST coverage for `POST
  /api/parameters/{name}/refresh-source` using this file's existing
  `_project(tmp_path, body)` + `client` fixtures.

Copy-paste for the user:
```
cd /workspace/scistack-gui
python -m pytest tests/test_graph_builder.py tests/test_parameter_refresh.py tests/test_entity_update_endpoints.py -v
python -m pytest tests -q
```

**Frontend — run directly (Node/npm available in this environment):**
```
cd /workspace/scistack-gui/frontend
npx tsc --noEmit
npm run build
VITE_BUILD_TARGET=webview npx vite build
```
Both builds matter — a committed `.tsx` fix is dead until **both** vite
targets rebuild; `dev-install.sh` does not build them. Check LSP
diagnostics on every edited file before calling the frontend work done.

**Manual pass (needs the user, not the test suite):**
- Browser: hand-edit `scistack_entities.toml`, right-click the Parameter
  node → "Refresh from file" updates values without the full-rescan wait;
  "Open source" shows the in-app dialog (browsers can't open local files).
- VS Code webview (after rebuild): "Open source" actually opens/reveals
  the file at the right line.
- Legacy `.py`/`.m`-declared Parameter: only "Open source" appears on
  canvas and in the sidebar, no "Refresh from file" — confirms the
  `declared_in_entities_file` gate.
- Sidebar row for a DB-only value with no current declaration: no context
  menu appears at all (gated on `source_file` truthiness).

## Critical files
- `scistack-gui/scistack_gui/domain/graph_builder.py`
- `scistack-gui/scistack_gui/services/layout_service.py`
- `scistack-gui/scistack_gui/api/layout.py`
- `scistack-gui/scistack_gui/api/pipeline.py`
- `scistack-gui/scistack_gui/server.py`
- `scistack-gui/frontend/src/api.ts`
- `scistack-gui/frontend/src/components/DAG/PipelineDAG.tsx`
- `scistack-gui/frontend/src/components/DAG/ParameterNode.tsx`
- `scistack-gui/frontend/src/components/Sidebar/EditTab.tsx`
