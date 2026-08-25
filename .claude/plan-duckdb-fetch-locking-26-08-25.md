# Plan: fix unlocked DuckDB execute→fetch (crash) + DatabaseManager._execute AttributeError

Date: 2026-08-25

## Symptom

During GUI testing, a `GET /pipeline` request died mid-flight:

```
_duckdb.InternalException: INTERNAL Error: Attempted to dereference shared_ptr that is NULL!
  pipeline_store.py:1178, in list_path_input_history
    for r in _duck(db)._execute(sql, params).fetchall()
```

`examples/vo2max/scidb.log` shows 6 graph builds started, only 5 completed. The
build at 17:40:54.003 stops dead after "Converting to AggregatedData format"
and logs nothing further — no ERROR line reached the log at all, because the
exception propagated out to uvicorn's stderr.

## Root cause

### Defect A — execute and fetch straddle the lock

`sciduckdb/src/sciduckdb/sciduckdb.py:749-753` states the contract:

> DuckDB's Python connection returns itself from `execute()`, so `execute()`
> and `fetchXxx()` share the same connection state. All callers that fetch
> results must hold `_lock` for the entire execute+fetch sequence.

`_execute` releases `_lock` when its `with` block exits (line 766) — *before*
the caller's `.fetchall()` runs. Another thread calling `execute()` on the
shared connection in that window tears down the pending result, and DuckDB
fails the null-pointer assertion.

The log shows the exact collision. Both handlers are sync `def`, so FastAPI
runs each on its own threadpool thread against one shared `SciDuck`:

```
17:40:54.002  GET /path-inputs        <- thread A, touches the DB
17:40:54.003  Starting graph build    <- thread B
17:40:54.028  ...CRASH in list_path_input_history
```

Earlier builds survived only because nothing overlapped them. This is
intermittent and load-dependent — it will keep recurring during GUI use.

### Defect B — `_execute` called on a `DatabaseManager`

`DatabaseManager` (`scidb/src/scidb/database.py:590`) defines no `_execute` and
has no `__getattr__` delegation; the method lives on `SciDuck`, reached via
`db._duck`. Two call sites call it directly on a `DatabaseManager`:

- `scidb/src/scidb/foreach.py:3025` — raises `AttributeError`, immediately
  swallowed by a bare `except Exception: row = None`. The dtype-metadata lookup
  has therefore **never** worked; it always silently falls back to
  `view_name()`.
- `scimatlab/src/scimatlab/bridge.py:2010` — no guard; raises outright whenever
  that path runs.

## Call sites (complete — repo scanned for the multi-line pattern)

| Site | Defect |
|---|---|
| `scistack-gui/scistack_gui/pipeline_store.py:1178` `list_path_input_history` | A (the observed crash) |
| `scistack-gui/scistack_gui/pipeline_store.py:1143` `lookup_path_input_name` | A (same bug, not yet triggered) |
| `scidb/src/scidb/foreach.py:3025` `_resolve_colname_from_db` | A + B |
| `scimatlab/src/scimatlab/bridge.py:2010` `get_data_column_name` | A + B |

`_fetchall` (line 896) and `_fetchdf` (line 922) are the correct helpers — they
hold `_lock` across execute *and* fetch. There is no `_fetchone`, which is why
all four sites reached for the raw call.

## Changes

Per CLAUDE.md NOTE 3, the fix lives in the owning layer: sciduckdb owns
connection locking, so it gains the missing primitive and the callers just use
it.

### 1. `sciduckdb` — add the missing locked primitive

- Add `_fetchone(sql, params=None)` next to `_fetchall`, same shape: hold
  `_lock` across execute+fetch, same debug/exception logging, same
  `_recover_from_autocommit_failure()` on failure.
- Add public alias `fetchone()` (mirrors the existing `fetchall()` alias, which
  exists because MATLAB cannot reach underscore methods).
- Strengthen the `_execute` docstring/NOTE into an explicit warning that its
  return value must not be fetched from.

### 2. Convert the four call sites

- `pipeline_store.list_path_input_history` → `_fetchall`
- `pipeline_store.lookup_path_input_name` → `_fetchall`
- `foreach._resolve_colname_from_db` → `_duck(...)._fetchone`, and narrow the
  bare `except Exception` so a missing attribute or a real DB error can no
  longer masquerade as "no dtype row". Only a genuine "row absent" result may
  take the `view_name()` fallback.
- `bridge.get_data_column_name` → same, via `_duck`.

Both B-sites reach the SciDuck via `db._duck` (`DatabaseManager` always sets
it, `database.py:652`). Note the input contract is `DatabaseManager`, not
"either type": both functions read `db.dataset_schema_keys` a line earlier,
which `SciDuck` does not have (it has `dataset_schema`). An initial
`getattr(db, "_duck", db)` here was misleading — it implied a bare `SciDuck`
would work when the function would already have failed above it.

### 3. Logging (CLAUDE.md NOTE 2)

- Wrap the graph-build orchestration body in `api/pipeline.py` with
  `logger.exception` so a failure lands in `scidb.log` instead of vanishing to
  uvicorn stderr, then re-raise. The whole reason this took a round-trip to
  diagnose is that the log showed only an absence.
- Log at DEBUG in `_resolve_colname_from_db` / `get_data_column_name` when the
  dtype row is genuinely missing and the `view_name()` fallback is taken —
  that path was silently active and nobody could see it.

### 4. Tests (CLAUDE.md NOTE 2)

- **Bug-class guard:** a test that scans the repo source for
  `_execute(...).fetch*()` (multi-line aware, skipping `.venv`) and fails with
  the offending file:line. This is a whole class of defect, not one line — a
  single-line grep would have missed three of the four sites.
- **Concurrency regression:** hammer `GET /pipeline` and `GET /path-inputs`
  from multiple threads against one shared connection; assert no
  `InternalException` and no 500s.
- **Defect B regression:** assert `_resolve_colname_from_db` returns the real
  dtype-derived column name (proving the query now executes), and that a DB
  error propagates rather than being swallowed into the fallback.

## Verification

Hand the user the pytest command; do not run python/pytest here
(CLAUDE.md, and `feedback_user_runs_tests`).
