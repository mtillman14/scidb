# Plan: layout-file write race + duplicate seed roots

Two independent defects found in the GUI session logged in `test_logs.md`
(11:00:29 – 11:02:11). Both are GUI-layer problems (canvas positions and the
GUI's own `scistack.toml` writer), so both fixes belong in `scistack-gui` —
neither touches scifor/scidb/sciduckdb.

---

## Defect A — manually added nodes vanish (concurrent layout-file write)

### Evidence

Three identical occurrences in `test_logs.md` (11:00:52, 11:01:53, 11:02:02).
Trimmed from the 11:00:52 one:

```
2829: RPC >> put_layout(node_id=var__Raw_EMG__ssh5rr, x=605.5, y=125.8, node_type=variableNode, label=Raw_EMG)
2833: RPC >> put_layout(node_id=var__Raw_EMG__ssh5rr, x=511.5, y=97.8)      # position only, ~1ms later
2851: [layout] Loading layout file from ...test_afl.layout.json             # thread A reads
2852: [layout] Loading layout file from ...test_afl.layout.json             # thread B reads the same bytes
2856: [layout] Saving layout file to ...                                    # both write
2858: ERROR: RPC << put_layout FAILED (125.0ms): [Errno 13] Permission denied
2877: [layout] Layout file saved successfully                               # the other writer won
```

Traceback: `layout_service.py:81 → layout.py:276 write_manual_node →
layout.py:142 _save → p.open("w")`.

After 11:00:52 the id `var__Raw_EMG__ssh5rr` never appears again — no read
returns it, and no delete was ever issued. Same for `__abqvvj` (11:01:53).
The user re-added the same Raw_EMG node three times, each with a fresh random
id, each hitting the same error.

### Root cause chain

1. **The frontend sends two `put_layout` RPCs per drop.**
   `PipelineDAG.tsx:514` persists the new node (`node_type` + `label`) at the
   raw drop position. Then the re-center effect at `PipelineDAG.tsx:213-225`
   fires as soon as React Flow measures the node's rendered size and sends a
   *second*, position-only `put_layout` for the same id. Nothing orders them.

2. **Every RPC gets its own thread.** `server.py:1403` —
   `threading.Thread(target=_handle_request, args=(req,), daemon=True).start()`.
   No serialization.

3. **`layout.py` does an unguarded read-modify-write.** Both
   `write_node_position` (`layout.py:248-251`) and `write_manual_node`
   (`layout.py:274-276`) do `_load()` → mutate → `_save()` with no lock, and
   `_save` (`layout.py:142`) truncates in place via `p.open("w")`. On
   Windows/SMB the second opener gets a sharing violation; on any platform the
   later writer silently discards the earlier writer's changes (lost update).

   **Corrected after the pre-fix test run (2026-09-01):** the raising is not
   Windows-specific either. Because `"w"` truncates on open, a concurrent
   *reader* on POSIX loads an empty/partial document —
   `JSONDecodeError("Expecting value: line 1 column 1")` out of `_load`, seen
   on macOS. Every platform was exposed and any `GET /layout` overlapping a
   drag could hit it; only the symptom differed. This is what justifies
   `_load` taking the lock, which the original plan did not call for.

4. **The failure aborts before the DB write, so the node never exists.**
   `write_manual_node` writes the position to JSON *first* (`layout.py:274-276`)
   and only then writes the structural row and unhides
   (`layout.py:277-317`). `_save` raised, so
   `pipeline_store.write_manual_node(db, ...)` never ran — the node is absent
   from `_pipeline_nodes` and disappears on the next DAG refresh. The
   cosmetic write killed the structural one.

### Fix

**`layout_write_lock`** — module-level `threading.RLock` in `layout.py`
guarding each read-modify-write as one critical section. Applies to every
mutator that calls `_save`: `drop_scope_positions`, `drop_node_positions`,
`move_node_position`, `write_node_position`, `write_manual_node`,
`delete_node`, `write_constant`, `delete_parameter_from_palette`,
`write_note`, `graduate_manual_node`. Reentrant because `delete_node` and
`write_manual_node` call into helpers that also load.

The lock is process-local, and that is a deliberate scope decision rather
than an assumption that only one process exists. `scistack_gui/layout.py` is
the only module that reads or writes the file — MATLAB writes to the DB, the
`scidb` CLI doesn't touch it, and `db.py:371` only hands the path to the
one-time `migrate_from_json` reader — but nothing stops a *second GUI
backend* from running. DuckDB's lock would not prevent that: the GUI drops
its file lock between requests on purpose (`db.py:40-46`, visible as the
per-RPC `DuckDB lock ACQUIRED`/`RELEASED` pairs in the log) so MATLAB can
take it, so two instances interleave freely — and since the layout file has
no lock at all, a second instance would produce a silent lost update rather
than an error. That becomes reachable with two VS Code windows on one
project (there is no single-instance guard in `scistack_gui` or
`extension/src`), or a colleague opening the same project off the share.

Not designing around that now, by decision (2026-09-01): the observed bug is
two threads inside one process, which the in-process lock fixes completely.
Recorded here so the limit is a known edge rather than a surprise. Note the
real fix for it would not be a cross-process file lock — it would be
finishing the migration `layout.py`'s docstring already describes ("all
structural pipeline data lives in DuckDB"; positions are the last thing left
in the JSON), at which point the DB lock governs positions too. A
server-based DB backend does not change any of this on its own; it matters
only because multi-user access multiplies GUI processes.

Note `atomic_layout_save` below is independent of all this: sync clients, AV
scanners and `git checkout` can hold the file briefly without being logical
writers, and no lock helps there.

**`atomic_layout_save`** — `_save` writes to a sibling temp file and
`os.replace()`s it over the target, so a crash or a denied write can never
leave a truncated/partial `*.layout.json`. Wrap the replace in a short
bounded retry (a few attempts, ~50ms backoff) for transient Windows/SMB
denials from AV scanners and SMB oplock breaks, logging each retry. Re-raise
with the path and attempt count if the retries are exhausted.

**`manual_node_db_write_first`** — reorder `write_manual_node` so the
structural DuckDB write + unhides happen *before* the position write. A node
that exists at a default position is recoverable; a node that never got
created is not. Comment the ordering with the reason.

### Logging (CLAUDE.md NOTE 2)

- `_save`: log the thread id and whether the lock was contended (`waited=%.4fs`),
  matching the existing `sciduck` `_execute thread=… waited=…` format so the
  two logs read the same way when interleaved.
- `_save` retry path: `WARN [layout] save retry %d/%d after %s: %s`.
- `write_manual_node`: log the DB-write-then-position order explicitly, so a
  future log shows which half completed.

### Tests — `scistack-gui/tests/test_layout_concurrency.py` (new)

Modeled on the existing `tests/test_path_input_history_concurrency.py`
`_hammer` helper (threads + `threading.Barrier` to maximise overlap).

- `test_concurrent_position_writes_do_not_raise` — N threads writing
  positions for distinct node ids; no exception.
- `test_concurrent_writes_do_not_lose_updates` — the real regression: every
  node id written by any thread is present in the final file. Fails today
  (lost update) even where the OS allows the double-open.
- `test_drop_sequence_persists_node` — the exact 11:00:52 shape: a
  `write_manual_node` and a `write_node_position` for the same id fired
  concurrently; assert the manual node exists in `pipeline_store` *and* has a
  position. This is the "node vanished" regression.
- `test_save_failure_leaves_file_intact` — monkeypatch the temp-file write to
  raise mid-`json.dump`; assert the pre-existing file is still valid JSON with
  its old contents (atomicity).
- `test_save_retries_transient_permission_error` — `os.replace` raises
  `PermissionError` once, then succeeds; assert the write lands and the retry
  was logged.
- `test_manual_node_survives_position_write_failure` — position write raises
  permanently; assert the structural row still exists (ordering fix).

### Frontend follow-on — `drop_put_layout_ordering`

`PipelineDAG.tsx`: chain the re-center `put_layout` (line 223) off the
create `put_layout` promise (line 514) instead of firing it independently.
The backend lock is the correctness fix; this removes the race at the source
and drops one redundant file write per drop. Keep both calls — deferring the
create until measurement risks never persisting a node that is never
measured.

No frontend test runner is configured in `frontend/`, so this one is verified
by the backend `test_drop_sequence_persists_node` plus a manual drop check.

---

## Defect B — `add_path` seeds the same directory twice

### Evidence

```
11:01:12 [config] add_path: seeding new scistack.toml with \\fs2.smpp.local\RTO\...\aging-well-abilitylab
11:01:12 [config] add_path: seeding new scistack.toml with y:\LabMembers\...\aging-well-abilitylab
11:01:13 [config] Processing module entry 1/3: \\fs2...\aging-well-abilitylab → Found 15 .py files
11:01:13 [config] Processing module entry 2/3: y:\...\aging-well-abilitylab   → Found 15 .py files
11:01:13 [config] Resolved 34 module files total
```

Consequences in the same log: 35 `shadows previous definition` warnings, and
the `get_registry` discovery error count doubling from 17 (before 11:01:12)
to 36 (after). Every function, PathInput and MATLAB file in the project is
discovered twice.

### Root cause

`_first_write_seed_roots` (`config.py:1033-1050`) seeds both
`_normalize(db_path).parent` and `_normalize(project_root)`, deduping with a
`set[Path]`. Here the DB is opened by UNC (`\\fs2.smpp.local\RTO\...`) and the
project root arrives as a mapped drive (`y:\...`, `from --project-root`).
They are the same directory but never compare equal, because `_normalize`
(`config.py:38-53`) deliberately does *not* canonicalize mapped drives — that
is load-bearing, so `reveal_in_editor` keeps producing paths VS Code will open
without `security.allowedUNCHosts`.

The same string-equality weakness is in `add_path`'s own duplicate check
(`config.py:959-965`) and in `remove_path` (`config.py:1008-1013`): adding
`\\fs2\...\X` when `y:\...\X` is already listed appends a duplicate, and
removing one spelling leaves the other.

### Fix

**`same_dir_identity_check`** — a `_same_path(a, b)` helper in `config.py`
using `os.path.samefile` (which resolves a Windows mapped drive and its UNC
target to the same file id, and a POSIX symlink to its target), wrapped in
`try/except OSError` with a fall back to `_normalize` equality when either
path doesn't exist or the OS refuses. Use it in:

- `_first_write_seed_roots` — dedupe the seed list by identity, **keeping the
  `project_root` spelling** when the two are the same directory. That is the
  spelling the rest of the session uses (entities file, MATLAB
  `project_root=`, `reveal_in_editor`), and it is the non-UNC one.
- `add_path` — the `existing_modules_resolved` / `existing_sources_resolved`
  membership checks.
- `remove_path` — so a remove matches either spelling of the target.

Stored strings keep the caller's spelling in every case; identity is only
used for comparison. The `config.py:38` docstring constraint is untouched.

**`resolved_module_dedup`** — dedupe the resolved file lists by identity at
`config.py:263` (modules) and in `_resolve_glob_paths` (`config.py:346-359`,
covering `matlab.functions` / `matlab.variables` / `matlab.sources`), logging
the number dropped. This is what repairs the config the user *already has on
disk* at `y:\...\aging-well-abilitylab\scistack.toml` — no migration step and
no hand-editing needed, and it also covers a hand-written config that lists a
directory and a file inside it. Preserve first-seen order so shadowing
behaviour for genuinely distinct duplicates is unchanged.

### Logging

- `_first_write_seed_roots`: when a seed is skipped,
  `INFO [config] add_path: seed %s is the same directory as %s — seeding once`
  with both spellings, so the mapped-drive/UNC case is visible in the log
  rather than inferred from a missing line.
- `add_path` / `remove_path`: log when a path matches an existing entry under
  a different spelling.
- `load_config`: `INFO [config] Dropped %d duplicate module file(s)
  (same file via different path spellings)` and the equivalent for each
  MATLAB list. This line appearing in a future log is the direct signal that
  a config has the problem.

### Tests — `scistack-gui/tests/test_config.py` (extend)

Mapped drives don't exist on Linux/macOS, so a symlinked directory stands in
for the same aliasing — `os.path.samefile` treats both the same way.

- `test_first_write_seeds_aliased_root_once` — `db_path` under
  `tmp/link/...`, `project_root` = `tmp/real`, `link -> real`; assert exactly
  one seed entry in the written TOML.
- `test_first_write_keeps_project_root_spelling` — that one entry is the
  `project_root` spelling, not the db-dir spelling.
- `test_first_write_still_seeds_two_genuinely_different_roots` — db dir and
  project root actually distinct; both still seeded (guards the fix
  `_first_write_seed_roots` was originally written for).
- `test_add_path_skips_aliased_existing_entry` — adding `link/x` when
  `real/x` is listed appends nothing.
- `test_remove_path_matches_other_spelling` — removing `link/x` removes the
  `real/x` entry.
- `test_load_config_dedups_aliased_module_files` — a config listing both
  spellings resolves each `.py` once (the on-disk repair path).
- `test_load_config_dedups_aliased_matlab_sources` — same for `.m`.
- `test_normalize_still_preserves_drive_letter_spelling` — explicit guard that
  the fix did not start canonicalizing stored paths (the `config.py:38`
  constraint).

---

## Order of work

1. `layout_write_lock` + `atomic_layout_save` + `manual_node_db_write_first`
   with `test_layout_concurrency.py` — this is the one costing real user work
   (three lost nodes in a two-minute session).
2. `same_dir_identity_check` + `resolved_module_dedup` with the `test_config.py`
   additions — silently doubles all discovery, and the user's config is
   already in the bad state.
3. `drop_put_layout_ordering` in `PipelineDAG.tsx` — cleanup once the backend
   is safe.

## Test commands (for you to run)

```
pytest scistack-gui/tests/test_layout_concurrency.py -v
pytest scistack-gui/tests/test_layout.py -v
pytest scistack-gui/tests/test_config.py -v
pytest scistack-gui/tests/test_project_api.py scistack-gui/tests/test_registry.py -v
pytest scistack-gui/tests -q
```

For the frontend change:

```
cd scistack-gui/frontend && npx tsc --noEmit && npm run build
```

Manual check after step 2, to confirm the on-disk repair: reopen the project
and confirm `Resolved 17 module files total` (not 34) and no
`shadows previous definition` warnings in the log.

## Out of scope

- The `matplotlib` / `statsmodels` import failures and the AST side-effect
  skips in the same log — environment/project issues, not defects here.
- MATLAB terminal run tracking (run `i333udzr` has no completion record in the
  log) — already captured in `plan-matlab-terminal-run-tracking.md`.
- Unifying mapped-drive vs UNC project-root spelling *everywhere* — the
  broader problem tracked in `plan-unify-project-root.md`. This plan only
  stops the config writer from emitting both spellings and stops discovery
  from acting on them twice.
