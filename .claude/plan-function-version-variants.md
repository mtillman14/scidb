# Plan: function-body edits as first-class variants

Diagnosis + fix plan for the three symptoms reported 2026-09-06 after editing
`loadDelsysEMGOneFile`'s body and re-running from the GUI.

Evidence base: `/workspace/scidb.log`, lines 7060–7238 (session 2026-09-06 15:39 → 16:38).

---

## 0. What the log actually shows

| time | line | meaning |
|---|---|---|
| 16:37:29 | `get_variable_records -> schema_keys[2], records[1], variants[1]` | before the run: 1 record |
| 16:37:59 | `start_run … loadDelsysEMGOneFile` | the run |
| 16:38:10 | `[batch_save] no _invocation_input edges — expected, the inputs are files (PathInput)` | the node is an **inputless** loader |
| 16:38:11 | `[save] pass=1: RawEMG -> record_id=4b59d66ae6fb (dict, 12 keys)` | new record has **12** keys, as expected |
| 16:38:15 | `propagate_run_states complete: 2 total nodes (2 green, 0 pending, 0 red)` | never red — before OR after |
| 16:38:31 | `get_variable_records -> … records[2], variants[1]` | **2 records, 1 variant** |
| 16:38:48 | `melted 'RawEMG': 13 field(s) -> 13 row(s)` | melt emits `len(frame) × len(fields)`, so the frame held **1** record — the old 13-field one |
| 16:38:49 | `downsampled 715000 row(s) to 20429` | byte-identical to the pre-run render at 16:32:48 |

Across all 7238 log lines: **zero** occurrences of a non-`0 red` run-state count,
and **zero** occurrences of `[plot] source cache invalidated`.

---

## A. The node never turns red — two independent defects

### A1. Inputless loaders are exempt from function-version staleness by construction

`check_node_state` (`scidb/src/scidb/state.py:432`) builds its expected set from
`provenance_query.expected_invocations_for_function`. That function has two sources:

- **(b) live prediction** — `_predict_config_invocations`
  (`scidb/src/scidb/provenance_query.py:1043`) folds `fn_hash` into
  `compute_invocation_id`, so a body edit shifts the expected id → not present →
  `missing` → **red**. This is the working mechanism.
  But line 1052: `if not input_types: return` — it bails immediately for a
  config with no DB-variable inputs.
- **(a) realized inputless invocations** — `realized_inputless_invocations`
  (`provenance_query.py:1145`) is a *pure structural read* of what already exists,
  with **no reference to `fn_hash` at all**.

`loadDelsysEMGOneFile` takes only a `PathInput`, so only (a) contributes:
expected ≡ present, unconditionally. The node reads green forever once run,
whatever the body says. `provenance_query.py:1240-1244` documents this as
intentional; it is the gap to close.

Note: `check_pathinput_node_state` (`state.py:484`) exists for exactly this node
shape and reconstructs a live should-run set from `PathInput.discover()` ∩ grid.
The GUI's batched path (`api/pipeline.py:_compute_run_states`) **never calls it**
— only `scidb/inspect/api.py:802` does. And it too ignores `fn_hash`.

### A2. For MATLAB functions the read-side hash is not the MATLAB source hash

- **Save side**: `_invocation.function_hash` ← `__fn_hash` ←
  `scidb.internal.hash_function` → `compute_matlab_function_hash(fileread(...))`
  = `sha256(source.encode("utf-8"))` (`scimatlab/bridge.py:1466`).
- **Read side**: `check_node_state` does
  `_compute_fn_hash(fn.fcn if hasattr(fn, "fcn") else fn)` (`state.py:431`).
  For a `MatlabLineageFcn`, `fn.fcn` is a `_FunctionProxy` holding only
  `__name__` (`scimatlab/bridge.py:41`). `compute_function_hash` fails
  `inspect.getsource` and falls to `_hash_bytecode_only` on a non-function
  (`scilineage/hashing.py:124-129`) — a constant with no relationship to the
  `.m` file.
- `MatlabLineageFcn.hash` — which *does* encode the source hash — is computed in
  `__init__` and then **never read** by the state path.

Consequence today: masked by A1. But **any MATLAB function with variable inputs
is permanently red**, because the predicted invocation_id can never match a
stored one. Fixing A1 alone exposes A2 immediately.

The registry side is fine: `matlab_parser.py:171` computes
`sha256(path.read_bytes())`, which agrees with MATLAB's recipe on ASCII/LF files
(user-verified 2026-04-19), and `matlab_registry.refresh_all` re-scans behind an
`(mtime_ns, size)` cache, so an edited file yields a fresh hash on the next
`get_registry`.

### Is this the deferred content-staleness check?

**No.** The 2026-04 decision was "don't reinstate `stored_hash != fn.hash →
stale`" on the old `_lineage` equality path, because it false-reddened valid
re-runs. The architecture has since changed: `fn_hash` is already folded into
`compute_invocation_id`, and functions with variable inputs already redden on a
body edit *by design*. Closing A1/A2 makes inputless loaders and MATLAB
functions behave like everything else, rather than resurrecting the old check.

---

## B. Two records collapse into one `(raw)` variant

`scistack-gui/scistack_gui/api/variables.py`:

- `_format_variant_label` (line 22) returns `"(raw)"` whenever `branch_params` is empty.
- The variant grouping key (line 118) is `json.dumps(branch_params, sort_keys=True)`.

`branch_params` comes from `provenance_query.branch_params_batch`
(`provenance_query.py:243`), which accumulates **only constants** along the
upstream chain. The producing function's version is not part of variant identity
anywhere in the stack. Two records differing solely by function body are
therefore indistinguishable *by construction* → `records[2], variants[1]`.

---

## C. The plotted variant was the pre-run one — stale cache

`plot_service._sources` (`services/plot_service.py:29`) caches the `ScidbSource`,
which caches `VariableFrame`s in `ScidbSource._frames`
(`scistackplotdb/source.py:165`). `invalidate()` exists (line 74), is registered
as the `plot_invalidate` RPC (`server.py:1148`) and as a REST route
(`api/plot.py:130`), and is declared in `frontend/src/api.ts:245` —
**and is called by nothing.** The hook was never wired.

Proof it served pre-run data: `_melt_fields` emits `len(frame) × len(usable)`
rows, and the post-run melt logged `13 field(s) -> 13 row(s)` → the frame held
exactly one record, the old 13-field one. The new 12-key record was never in it.

Secondary: the cache key is `("db", id(db))`. CPython reuses `id()` after GC;
the db path is the correct key.

## D. Behind C, a worse latent bug

Once the cache is fixed, `load_variable` loads **both** records. `attach_variants`
(`scistackplotdb/load.py:176`) finds no branch params → adds no variant column →
`roles.validate`'s pooling guard (`scistackplot/roles.py:141-156`), which exists
for precisely this, never fires → the two runs are silently overplotted as if
they were replicates. Its own docstring calls this "a figure that is wrong in a
way that looks like data."

**B and D are one root cause and take one fix.**

---

## Fix plan

Layering per CLAUDE.md NOTE 3: the variant-identity notion belongs in **scidb**;
the GUI and plotdb only render it.

### Stage 1 — scidb: producing function version as variant identity — **BUILT 2026-09-06, tests unrun**

Implemented in `scidb/src/scidb/provenance_query.py`; tests in
`scidb/tests/test_variant_identity.py`. Not exported from `scidb/__init__.py` —
`branch_params_batch` isn't either, and both display consumers import from
`scidb.provenance_query` directly, so this keeps the existing convention.

Decisions made while building, worth knowing before Stages 2–4 consume it:

- **`is_latest` is a property of the VERSION, not the record.** Two records of
  the same version (a plain re-save) are both `True`. That is what pinning
  wants — pin a version, keep all of its rows.
- **"Latest" means most recently written, not last-by-ordinal.** Re-running an
  older body makes *it* latest again while keeping its original `v1` label.
  Ordinals order by each version's earliest save (stable — a third version
  appends `v3`); latest orders by most recent save.
- **`saved_at` is populated for raw records too**, from its own
  `saved_at_batch` lookup rather than from the version map, since the UI sorts
  on it.
- **Ordinals are numbered per TYPE; `is_latest` is resolved per LOCATION.**
  Corrected 2026-09-06 while starting Stage 2 — the original per-location
  ordinal was wrong. Plot Studio turns `fn_version` into one factor column
  spanning every location, so per-location numbering could make one hash `v1`
  at `subject=1` and `v2` at `subject=2` (incoherent column, wrong figure).
  `is_latest` stays per-location, because a type-wide "latest" would silently
  drop every location never re-run under the newest code.
- **Both span every non-excluded record of the type**, not just the requested
  ids, so a caller asking about a subset gets the same labels as one asking
  about everything. Excluded records don't create versions.
- **`__save__`-anchored records are not a version** — that synthetic invocation
  carries `function_hash = ""` and must read as raw.
- Logging is **one aggregated INFO line per call** (count of ambiguous
  locations + up to 3 spelled out), not one per location: this runs on every
  panel open and a variable with 500 locations would emit 500 lines.

`scidb/src/scidb/provenance_query.py`

- `producing_function_versions_batch(duck, record_ids)` →
  `{record_id: {"fn_name", "fn_hash", "saved_at"}}` — one batched join over
  `_invocation_output` / `_invocation` / `_record_save`. No per-record queries
  (the N+1 trap).
- `variant_identity_batch(duck, record_ids)` →
  `{record_id: {"branch_params": {...}, "fn_name", "fn_hash", "fn_version",
  "is_latest", "saved_at"}}`. `fn_version` is an ordinal (`v1`, `v2`, …) over the
  distinct `function_hash` values seen for that record's `(type, schema_id)`,
  ordered by earliest `_record_save.timestamp` so labels stay stable as new
  versions appear. **Populated only when that location has >1 distinct version**
  — the single-version case keeps today's clean labels and nothing existing changes.
- INFO log when >1 version is found at a location, naming the type, schema_id,
  version count and which is latest.

Note on the existing model: `_producing_variant_key` (`provenance_query.py:941`)
is constants-only, so scidb already treats a body re-run as **supersession** —
`_current_records_by_schema` keeps only the newest, which is why downstream
consumers already see the 12-key record. Stage 1 does not change that; it makes
the superseded history *visible and labelled*, consistent with the
never-delete-mark-hidden ethos.

Tests (`scidb/tests/`): two runs of one function under different `fn_hash` at the
same schema_id → 2 records, 2 distinct `fn_version`s, exactly one `is_latest`;
plus the single-version case asserting no discriminator is emitted.

### Stage 2 — scistack-gui variables API — **BUILT 2026-09-06, tests unrun**

`api/variables.py` now calls `variant_identity_batch`; records and variant rows
carry `fn_name`/`fn_hash`/`fn_version`/`is_latest`/`saved_at`; the grouping key
is `(branch_params, fn_hash)`. Label format: `low_hz=20 · bandpass_filter v2
(latest)`, falling back to today's exact output when no version is in play.
Frontend `VariableSettingsPanel.tsx` gains a "Code" column and a banner, shown
only when versions exist. **Both vite bundles rebuilt** (standalone + webview).
Tests added to `scistack-gui/tests/test_api.py`.

Caught while building:

- The summary label must be computed **after** aggregating the group, not taken
  from its first record: `is_latest` can flip to True partway through, leaving
  a row whose label omits "(latest)" while its field says True.
- The latest-first sort is gated on a version actually existing. Sorting
  unconditionally would also reshuffle a variable holding both raw and
  function-produced records (`is_latest` None vs True), which is unrelated.
- `test_api.py:796`'s existing `all(... == "(raw)")` assertion still passes
  unchanged — raw records have no producing invocation, so they keep the
  clean label. No edit was needed there after all.

`scistack-gui/scistack_gui/api/variables.py`

- `_format_variant_label` takes the version discriminator: `(raw)` when
  unambiguous, `loadDelsysEMGOneFile v2 (latest)` / `… v1` when not.
- Variant grouping key becomes `(branch_params, fn_hash)`.
- Per-record and per-variant response gains `fn_name` / `fn_hash` / `fn_version`
  / `is_latest` / `saved_at` so the sidebar can render and sort it.
- Update `scistack-gui/tests/test_api.py:796` (currently asserts every record is
  `"(raw)"`) and add a two-version case.

### Stage 3 — scistackplotdb — **BUILT 2026-09-06, tests unrun**

`load.attach_variants` now calls `variant_identity_batch` and appends a
`CodeVersion` column (constant `VERSION_FACTOR`, exported) to the **variant**
column list, which is what arms `roles.validate`'s pooling guard. Attached only
when scidb reports a version, so the single-version case is byte-identical to
before. Raw records in a versioned type get the level `(raw)` rather than NaN,
which would drop them silently out of every facet. Tests appended to
`scistackplotdb/tests/test_source.py`.

**One fix outside scistackplotdb was required.** `scistackplot.roles.default_roles`
gave the first multi-level variant `COLOR` and every *extra* one `Role.FREE` —
but `validate` refuses a pooled variant outright, so a table with two variant
factors produced an error instead of a figure. That was reachable before (two
multi-level branch params) but rare; adding `CodeVersion` makes it common, e.g.
a constant sweep on a function whose body was later edited. Extras now default
to `FACET`, which keeps them separated the way `COLOR` does for the first.

`scistackplotdb/src/scistackplotdb/load.py`

- `attach_variants` switches to `variant_identity_batch` and attaches the
  function-version column **as a variant column**, so
  `roles.validate` refuses to pool it and D can no longer happen silently.
- Column name follows the stack's existing vocabulary (a `FIELD_FACTOR`-style
  module constant, e.g. `VERSION_FACTOR = "fn_version"`), with the same
  never-shadow-a-schema-key guard.

### Stage 4 — default plot behaviour when >1 version exists — **BUILT 2026-09-06, tests unrun**

Implemented as a generic seam rather than a scidb special case: `LongTable`
gains `default_pin` ("a `pinned_variant` the SOURCE recommends"), `default_spec`
opens on it with `VariantPolicy.PIN`, and `ScidbSource` populates it. `CsvSource`
leaves it None and is untouched.

**The pin is on a per-row flag, not on a version level, and that is the whole
correctness argument.** `CodeVersion` is numbered per type, so pinning
`CodeVersion == "v2"` would delete every schema location never re-run under the
newest code — silently losing subjects from the figure, the same class of bug
this whole plan exists to fix. `attach_variants` therefore also writes
`CodeIsLatest` (constant `LATEST_COLUMN`), resolved per location, and the pin is
`{"CodeIsLatest": True}`. Each location contributes its own newest record and
nothing is lost. There is a test for exactly this (one subject re-run, the rest
not).

`CodeIsLatest` is deliberately **not** a variant column, which also keeps it out
of `hierarchy.join_frames` (that selects only levels, values and variant
columns) — so a two-measure join drops it and falls back to showing every
version, which `default_roles` keeps visibly separated anyway.

Test-surface gotcha, hit while writing these: a `ResolvedFigure`'s panels carry
`reduce`'s **canonical** frame (`__x`/`__y`/`__color`), not the original factor
columns — those are projected away. Assertions must go through
`resolved.encoding.x` / `.color` / `.y` to name a column, never `frame["subject"]`
or `frame["CodeVersion"]`.

`attach_variants` now returns a 3-tuple `(frame, variant_columns,
latest_column)`. Clean break, no shim, per the beta-no-deprecation rule; it has
exactly one caller.

Frontend: the Variants dropdown previously offered only facet/pool, so a `pin`
policy would have rendered as a **blank select**. It now offers "Show only the
current code version" (only when something was handed to us to pin — `validate`
refuses PIN with an empty `pinned_variant`), and shows a note saying what is
being left out and how to get it back. Both bundles rebuilt.

**Decided (user, 2026-09-06): pin the latest.** The default Plot Studio spec
sets `variant_policy="pin"` with `pinned_variant` naming the **latest**
function version; older versions remain selectable in the panel. This is the
user's stated expectation ("the variant plotted should be the latest") and keeps
the default figure readable — faceting a 13-field EMG struct across two versions
would produce 26 panels by default.

Requirements this puts on the earlier stages:

- Stage 1's `is_latest` must be authoritative — `default_spec` needs to name the
  pinned level without re-deriving recency itself.
- The panel must **say** it is pinned, not silently drop the other version. The
  version selector shows both levels with the latest marked; the log line from
  `reduce.py`'s PIN branch (`variant pin %s kept %d of %d row(s)`) already
  records it backend-side.
- Pinning is a *default*, not a lock: switching the version factor to
  `color`/`facet` must still work, which it does — `variant_policy` is per-spec.

### Stage 5 — plot cache invalidation — **BUILT 2026-09-06, tests unrun**

`api/run.py` gains `_notify_records_changed()`, and all four
`push_message({"type": "dag_updated"})` sites now call it. It drops the plot
source cache and then pushes `dag_updated`, so the two can no longer travel
separately (only one ever did).

- **Takes no db handle**, deliberately. `_drive_matlab_in_thread` has none —
  the MATLAB threads have released the connection to the sidecar by the time
  they finish — so the helper invalidates by `get_db_path()`. This is only
  possible because of the rekey below; it was the argument for doing it.
- `_sources` is rekeyed from `("db", id(db))` to `("db", <file path>)`.
  CPython reuses ids after GC, so a freshly-opened manager could land on a
  dead entry's key and inherit another database's frames.
- `invalidate()` accepts a `DatabaseManager` **or** a plain path, and logs how
  many sources it dropped.
- Invalidation failure is caught and logged, never raised: a cache we failed
  to drop is a stale figure, not a failed run, and must not bury the result.

**Pre-existing bug found and fixed:** `ScidbSource.__init__` read
`getattr(db, "db_path", ...)` for its display name, but `DatabaseManager` has
`dataset_db_path` — the attribute has never existed, so every project's source
name silently fell back to the literal `"scidb"`.

Frontend untouched: `plot_invalidate` stays available as an RPC/manual escape
hatch, it simply no longer needs a caller. No rebuild required.

`scistack-gui/scistack_gui/api/run.py` has four `push_message({"type":
"dag_updated"})` sites (lines 742, 1127, 1251, 1379) — these *are* the
"records may have changed" choke points the `plot_service` comment says don't
exist. Introduce `_notify_records_changed(db)` that calls
`plot_service.invalidate(db)`, logs at INFO, then pushes `dag_updated`, and route
all four sites through it. Backend-side, so the web GUI and the VS Code
extension cannot drift (CLAUDE.md NOTE 3).

Also: rekey `_sources` from `("db", id(db))` to the db path.

Test: a fake source registered in `_sources`, a simulated run completion, assert
the entry is gone.

### Stage 6 — node state: red on a body edit

**Decided (user, 2026-09-06): both defects together.** 6a and 6b ship as one
unit — fixing 6b alone would turn every MATLAB function with variable inputs
permanently red, because the read side would finally start comparing a hash it
computes wrongly (A2).

- **6a (MATLAB hash parity).** Make the read side use the same hash the save side
  stored. `check_node_state` should prefer an explicitly-supplied source hash
  over AST-hashing `fn.fcn`. Save stores the *bare* source hash, so that is the
  one to converge on — `MatlabLineageFcn.hash` (sha256 of `source_hash + delim +
  unpack`) must not be used as-is. Add an assertion-style test that a MATLAB
  function's read-side hash equals what `record_run` wrote.
- **6b (inputless loaders).** Route PathInput-only call sites in
  `_compute_run_states` through `check_pathinput_node_state`, and add `fn_hash`
  to the realized-set match in `realized_inputless_schema_ids`
  (`provenance_query.py:1182`) alongside the existing constants match. Then an
  edited body empties the realized set → every should-run combo reads `missing`
  → **red**; re-running refills it → **green**. Because the should-run set is
  reconstructed live from `PathInput.discover()`, this cannot get stuck red.
- Regression test with **≥2 historical hashes for the same combo** (explicitly
  requested by the 2026-04 memory note on `find_record_id` selection).
- Diagnostics: log at INFO in `check_node_state` when a node is red *because of*
  a function-version change specifically, naming stored vs current hash — today
  there is no way to tell that reason from the others.

#### As built — 2026-09-06, tests unrun

**6a shipped as planned.** `MatlabLineageFcn` now exposes `source_hash` (the .m
digest, verbatim as the save path stored it), and a new
`foreach_config.function_hash_for(fn)` is the single read-side recipe: an
explicit `source_hash` wins, else the AST hash with the existing `.fcn` unwrap.
Duck-typed, so scidb still does not import scimatlab. Wired into
`state.check_node_state`, `state._check_via_graph`, and
`inspect/graph._node_states` — every read-side hash site. `to_version_keys` is
deliberately untouched: changing the *write* recipe would invalidate the hashes
in existing databases.

**6b took a different route than planned, and the planned one was wrong.** The
fix is `fn_hash` on `realized_inputless_invocations`, threaded through
`expected_invocations_for_function` — the path `check_node_state` actually uses.
An edited body empties the realized set → node red; re-running refills it under
the new hash → green.

The two planned items were both rejected on inspection:

- *Adding `fn_hash` to `realized_inputless_schema_ids`* would break its only
  caller. `check_pathinput_node_state` is invoked from `inspect/api.py` with a
  bare `_stub()` that has no source and no meaningful hash, so a hash filter
  there matches nothing and reddens every node permanently. It keeps the
  any-version default (`fn_hash=None`), which is right: it asks "where has this
  loader produced output", not "under which code".
- *Routing `_compute_run_states` through `check_pathinput_node_state`* is
  unnecessary for this bug and solves a **different** one — detecting new files
  that appeared but were never run. `check_pathinput_node_state` ignores
  `fn_hash` entirely, so it would not have fixed the body edit at all. Left
  alone; it is a separate feature, not part of this.

Also added `provenance_query.function_versions_recorded` (diagnostic) and an
INFO line in `check_node_state` naming *why* a node is red — edited source vs
never-run vs partially-run, which were previously indistinguishable.

Tests: `scihist/tests/test_state_pathinput.py` (green→edit→red→re-run→green,
≥2 historical hashes, revert-restores-green, call_id-scoped) and
`scimatlab/tests/test_bridge.py` (hash parity, the 6a defect pinned directly).

---

## Sequencing

1. **Stage 5** (plot cache invalidation) — a few lines, no dependencies, and on
   its own it makes the Plot Studio stop showing pre-run data. Land first.
   Caveat: alone, it exposes D (silent overplotting of both records), so it
   should not sit unaccompanied for long.
2. **Stage 1** (scidb `variant_identity_batch`) — the shared foundation.
3. **Stages 2, 3, 4** (GUI labels, plotdb variant column, pin-latest default) —
   all consume Stage 1 and can go in one pass; together they close B and D.
4. **Stage 6** (6a + 6b together) — independent of 1–4, deeper, and the one that
   closes A. Ships second.

Verification is the user's to run (never invoke pytest here): each stage lists
its own tests, and the end-to-end check is the reported scenario — edit the
`.m` body → node goes red → Run → node goes green → the variable panel shows two
distinctly-labelled variants → the plot renders the 12-field latest one.

## Docs

Candidate `docs/claude/` note afterwards: **"function-version variants"** —
what makes two records at one schema location distinct, which layer owns that
answer, and why supersession is visible rather than destructive.
