# Plan: Tabbed sidebar palette + item-info panel

## Goal
Rework the GUI's left-hand entity palette (`EditTab.tsx`, rendered inside
`Sidebar.tsx`) so that:

1. The six categories — Submodules, Functions, Variables, Constants, Path
   Inputs, Sweeps — are shown as an icon tab strip instead of six stacked
   always-visible sections. Each tab shows its icon with a small always-
   visible text label underneath (mobile-tab-bar style), so no hover is
   needed.
2. Clicking an item in the active tab's list selects it and reveals an info
   panel docked to the bottom ~20% of the sidebar:
   - **Functions**: read-only signature + docstring (Python via
     `inspect.signature`/`__doc__`; MATLAB via a new docstring extraction in
     `matlab_parser.py`, since MATLAB has no runtime object to introspect).
   - **Everything else** (submodules, variables, constants, path inputs,
     sweeps): a free-text, user-editable textarea, autosaved on blur,
     persisted in `<db>.layout.json` under a new `"notes"` key.
3. Clicking the canvas (`onPaneClick` in `PipelineDAG.tsx`) clears the
   selection and the info panel disappears.

## Icons (reusing existing conventions already in the app)
- Submodules: `⧉` (already used for pipeline nodes/uses elsewhere)
- Functions: `f(x)`
- Variables: `x`
- Constants: `C`
- Path Inputs: `📁` (already used for the header's Paths popup)
- Sweeps: `🧹`

## Backend changes

### `scistack_gui/layout.py`
- `_load()`: add `raw.setdefault("notes", {})` (flat dict, additive — no
  migration flag needed).
- `read_notes() -> dict[str, str]`
- `write_note(key: str, text: str) -> None` (delete the key when `text`
  is empty, to keep the file tidy).

Note key scheme: `f"{kind}:{name}"`, where `kind` is one of
`submodule|variable|constant|pathInput|sweep` and `name` is the entity's
stable identifier (`pipeline_id` for submodules, the registered name for
everything else).

### `scistack_gui/matlab_parser.py`
- Add `docstring: str | None` field to `MatlabFunctionInfo`.
- After the `function ... (...)` line, collect contiguous `%`-prefixed
  comment lines (MATLAB's H1-line convention) until a non-comment/blank
  line, strip the leading `%`/whitespace, join with `\n`.

### `scistack_gui/services/pipeline_service.py`
- `get_function_doc(fn_name: str) -> dict`:
  - MATLAB: build `"name(p1, p2) -> out1, out2"` from
    `matlab_registry.get_matlab_function`, return its `docstring`.
  - Python: `inspect.signature(registry._functions[fn_name])` for the
    signature string, `fn.__doc__` for the docstring.
  - Same not-registered error shape as `get_function_source`.

### `scistack_gui/services/layout_service.py`
- `get_notes() -> dict[str, str]`, `set_note(key: str, text: str) -> dict`
  thin wrappers over `layout.py`, mirroring `get_constants`/`create_constant`.

### `scistack_gui/api/pipeline.py`
- `GET /function/{fn_name}/doc` → `get_function_doc`.

### `scistack_gui/api/layout.py`
- `GET /notes` → `get_notes`.
- `PUT /notes/{key:path}` (body `{text: str}`) → `set_note`. (`:path`
  converter since keys contain `:`.)

### `scistack_gui/server.py`
- New JSON-RPC handlers `get_function_doc`, `get_notes`, `set_note`,
  registered in the method dispatch table (VS Code transport).

### Tests
- `tests/test_matlab.py`: extend `TestParseMatlabFunction` with docstring
  extraction cases (H1-only, multi-line, none, block-comment interaction).
- `tests/test_layout.py`: `read_notes`/`write_note` round-trip, delete-on-empty.
- A service-level test for `get_function_doc` (Python + MATLAB + unregistered).
- Logging: mirror the existing `logger.debug`/`info` calls already used
  throughout `layout.py`/`pipeline_service.py` for the new functions (per
  project convention of instrumenting new code paths).

## Frontend changes

### `frontend/src/api.ts`
- Add `get_function_doc`, `get_notes`, `set_note` entries to the
  standalone-mode `routes` map (paths as above).

### New: `frontend/src/context/SidebarSelectionContext.tsx`
- `{ selectedItem: {kind, name, pipelineId?} | null, setSelectedItem }`,
  same shape as `SelectedNodeContext`. Needed so `PipelineDAG.tsx`'s
  `onPaneClick` can clear it (EditTab's own local state can't be reached
  from the canvas).
- Wire the provider into `App.tsx` alongside `SelectedNodeProvider`.

### `frontend/src/components/DAG/PipelineDAG.tsx`
- `onPaneClick`: also call `setSidebarSelectedItem(null)`.

### `frontend/src/components/Sidebar/EditTab.tsx`
- Replace the six stacked `<Section>` renders with:
  - A tab strip (icons + tooltip `title`) driving `activeTab` local state.
  - Only the active tab's `<Section>` renders below the strip.
  - Each list row becomes clickable (not just draggable) → sets
    `selectedItem` in the new context; switching tabs clears selection.
- New bottom panel (`~20%` height, `flex-shrink: 0`, scrollable), rendered
  when `selectedItem` is set:
  - `kind === 'function'`: fetch `get_function_doc`, render signature
    (monospace) + docstring (or "No docstring" placeholder).
  - otherwise: fetch `get_notes`, render a `<textarea>` bound to
    `notes[selectedItem key]`, `onBlur` → `set_note`.
- Root layout becomes `flex-direction: column`, list area `flex: 1;
  overflow-y: auto`, info panel `height: 20%` (or `flex: 0 0 20%`).

## Out of scope / open questions
- Submodule notes are keyed by `pipeline_id` (stable across renames), not
  by the display name.
- No markdown rendering for notes — plain textarea, plain text.
- I'm treating "Submodules" as belonging to the "editable text notes"
  bucket (not the function-doc bucket) since a submodule has no single
  code signature.

After this lands, I'll ask whether to write a `docs/claude/*.md` note
summarizing the notes-persistence key scheme and the MATLAB docstring
convention, since neither is discoverable from README's alone.
