# Plan: six fixes from the 2026-09-01 scidb.log triage

Source: `/workspace/scidb.log`, one session 21:01:48 → 21:13:29. No ERROR lines;
the MATLAB run of `loadDelsysEMGOneFile` succeeded end to end. These six items are
things that worked *despite* a defect, or that make the log harder to read next time.

Suggested order: **4 → 1 → 2 → 5 → 6 → 3**. Item 4 is a confirmed one-field bug with
real consequences. Items 5 and 6 are quick log hygiene that will make every future
triage easier. Item 3 is the biggest and spans three layers, so it goes last.

---

## Item 4 — MATLAB output wiring can't be re-derived from the database

**Confirmed root cause. This is a real bug, not a guess.**

### The problem in plain language

When a MATLAB function saves a result, scidb records *which output slot* the result
came from — output #0, output #1, and so on. That number is what lets the GUI later
say "the second return value of this function is a `RawEMG`" and draw the edge from
the function node to the variable node.

The number is written to the database correctly. It is also read back correctly. But
on the way from the database to the GUI, one function forgets to copy it into the
dictionary it hands over. So the GUI always sees "no output number" for every MATLAB
function, and falls back to reading the answer off a manual edge the user drew by hand.

That is why the log says:

```
scidb.log:2286  matlab_param_to_class: fn=loadDelsysEMGOneFile output_type='RawEMG'
                has output_num=None — DB source contributes nothing for this variant
scidb.log:2287  from_db_output_num={} from_manual_edges={'loaded_data': 'RawEMG'}
```

The pipeline currently holds together only because of that manual edge. Delete the
edge and the function-to-variable connection vanishes from the canvas, even though
the database knows perfectly well what it should be.

### Where it is

- `scidb/src/scidb/provenance_query.py:814` — `pipeline_variants()` **does** return
  `output_num` for every variant.
- `scidb/src/scidb/database.py:3811-3817` — `get_aggregated_variants()` builds the
  per-variant dict with `input_types`, `constants`, `output_type`, `record_count`
  — and drops `output_num` on the floor.
- `scistack-gui/scistack_gui/api/pipeline.py:586` — reads `v.get("output_num")`,
  which is therefore always `None`.

### The fix

Add `"output_num": v.get("output_num")` to the variant dict in `database.py:3811`.
The fix belongs in scidb, not the GUI — the GUI is already asking the right question.

### Logging and tests

- The existing `logger.info` at `api/pipeline.py:593` is exactly the right diagnostic
  and already caught this. Leave it. After the fix it should stop firing for
  `loadDelsysEMGOneFile`.
- **scidb test:** save a two-output MATLAB-style function, call
  `get_aggregated_variants()`, assert each variant carries the `output_num` that
  `list_pipeline_variants()` reported for it. This is the regression guard — the
  contract is "the aggregation must not lose fields the variant query supplies."
- **GUI test:** build a pipeline for a MATLAB function with **no** manual edges and
  assert the function-to-output edge still appears. That is the user-visible symptom
  and nothing currently covers it.

---

## Item 1 — The duplicate-declaration warning is self-inflicted

### The problem in plain language

`RawEMG` is declared once, in `scistack_entities.toml`. During a scan, scistack reads
that declaration and then *writes a MATLAB classdef stub file* for it, so MATLAB code
can refer to the type. Then, a few microseconds later, the same scan notices there are
now two files mentioning `RawEMG` — the TOML and the stub it just generated — and warns
that the variable is "declared in more than one place," resolving the tie in favour of
the generated file.

The system is competing with its own output. Worse, the tie-break is "the last one
scanned wins," so which declaration is authoritative depends on directory walk order.

From the log, all within 2ms:

```
scidb.log:1516  [stubs] Materialized classdef for declared variable 'RawEMG' at .../RawEMG.m
scidb.log:1518  WARN Variable 'RawEMG' is declared in more than one place:
                .../scistack_entities.toml and .../RawEMG.m. The last one scanned wins.
scidb.log:1519  Registered MATLAB variable: RawEMG (.../RawEMG.m)
```

### Where it is

- `scistack-gui/scistack_gui/matlab_registry.py:334` — after materializing the stub,
  calls `_register_matlab_variable(name, target)`.
- `scistack-gui/scistack_gui/matlab_registry.py:607` — that in turn calls
  `registry._register_variable(var_name, source=str(path))` with the **stub's** path.
- `scistack-gui/scistack_gui/registry.py:604-613` — sees a source different from the
  one recorded by the TOML load, and warns.

Note that `matlab_registry.py:296-306` already has the right instinct — it refuses to
materialize a stub that would shadow a *hand-written* classdef. The gap is that once it
does materialize one, nothing tells the variable registry that the stub and the TOML are
the same declaration.

### The fix

Make the stub's registration inherit the declaring source instead of claiming a new one.
Concretely: give `_register_matlab_variable` an optional `declared_by` argument; when the
path is a stub scistack itself generated, pass the originating TOML path through to
`registry._register_variable`. Re-registering the same source is already a no-op, so the
warning stops firing and the TOML stays authoritative by construction.

Per the project ethos that the entities TOML is the only writable declaration surface,
the TOML must win — not "whichever was scanned last."

### Logging and tests

- Replace the vanished WARN with a DEBUG line stating that a generated stub was
  attributed to its TOML origin, so the linkage is still observable.
- Keep the WARN for the case it was written for: two *genuinely independent*
  declarations (a hand-written classdef plus a TOML entry).
- **Test:** scan a project with one TOML-declared variable, twice. Assert no
  "declared in more than one place" warning on either pass, and that the resolved
  source is the TOML. A second scan matters — the first creates the stub, the second
  is where a naive fix would still trip.
- **Test:** a hand-written classdef *and* a TOML entry for the same name still warns.

---

## Item 2 — Library functions silently override the project's own functions

### The problem in plain language

After the shared code-libraries folder was added to the scan path, the MATLAB registry
went from 20 functions to 121. Two of the new ones had the same names as functions the
project already defined, and the library versions won:

```
scidb.log:1464  WARN MATLAB function 'plot_EMG_timeseries_SPM' from
                .../data-analytics-code-libraries/libraries/table-spm/matlab/
                shadows previous definition from .../aging-well-abilitylab/src/plot_EMG_timeseries_SPM.m
scidb.log:1436  WARN MATLAB function 'energy_tkeo' ... (library shadows library)
```

A shared library beating the project's own source is backwards. If you edit your local
`plot_EMG_timeseries_SPM.m`, your edit does nothing — and the only sign is one WARN in a
554KB log. As with item 1, the tie-break is scan order rather than a stated rule.

### Where it is

`scistack-gui/scistack_gui/matlab_registry.py:570-584` — `_register_matlab_function`
warns and then unconditionally overwrites, so the last file scanned wins. There is
currently no notion of where a definition came from.

### The fix

Introduce an explicit precedence rule instead of relying on walk order: **a definition
whose file lives under the project root beats one that doesn't.** Within the same tier,
keep the existing first-wins-or-last-wins behaviour but say so out loud.

Implementation sketch: `_register_matlab_function` compares the incoming
`info.file_path` and the incumbent's against the project root and keeps the
higher-precedence one.

The same reasoning applies to the Python side (`registry.py:931`, where `get_age_group`
shadows twice), so it is worth checking whether one shared helper can serve both — the
project has a standing preference against duplicating this kind of logic across layers.

### Logging and tests

- Reword the message to state the outcome, not just the collision: *"library definition
  X ignored; project definition at Y takes precedence"* at INFO, and keep WARN only for
  a genuine same-tier ambiguity where the choice really is arbitrary.
- **Test:** register a project function and a same-named library function in **both**
  orders; assert the project one wins both times. Order-independence is the whole point.
- **Test:** two same-tier collisions still warn.

---

## Item 5 — Lock contention is handled correctly but logged very loudly

### The problem in plain language

While MATLAB held the DuckDB file lock for ~2.8 seconds during its save, the GUI
retried 33 times and then succeeded. The retry behaviour is correct and the outcome
was right. Two things are worth improving.

First, the noise: every single attempt emits a WARN *and* an INFO — 66 log lines for
one three-second wait, with no line stating the thing you actually want to know
("acquired after 2.8s, 11 retries").

Second, the cost: three RPCs blocked hard behind it — `get_pipeline` 3069ms,
`list_hypotheses` 2955ms, `get_hidden_pipelines` 2940ms. Those are the three slowest
RPCs in the entire session by an order of magnitude, and the 5.0s retry budget was
more than half consumed. It worked this time; a slower save would have hit the ceiling.

### Where it is

- `scistack-gui/scistack_gui/db.py:242-247` — WARN on every blocked reopen.
- `scistack-gui/scistack_gui/db.py:197-204` — INFO on every retry decision.
- `scistack-gui/scistack_gui/db.py:187-196` — the give-up path, which already logs well.

### The fix

Log the *episode*, not each attempt:

- First blocked attempt → WARN (as today), so the event is still visible at default level.
- Subsequent attempts → DEBUG.
- On success after any wait → one INFO summary: total wait, attempt count, who held it.
- Give-up path → unchanged; it is already a good message.

Leave the retry interval and the 5.0s budget alone for now. Do **not** raise the budget
as part of this work: the summary line is what will tell us whether the ceiling is
actually too low, and guessing before we have that number is how a 5s wait becomes a 15s
wait that nobody notices.

### Logging and tests

- The new summary line is itself the diagnostic — it turns "was there contention?" into
  a single greppable line with a number attached.
- **Test:** simulate a lock that clears after N attempts; assert exactly one WARN, one
  INFO summary containing the attempt count, and no per-attempt INFO at default level.
- **Test:** the give-up path still raises and still logs its existing WARN.

---

## Item 6 — Nearly half the log file is one message repeated 24 times

### The problem in plain language

`main_plot_all.py` can't be imported safely because it would run ~78 top-level
statements on import. That is correct behaviour and the explanation is genuinely useful
— it names every offending call and line number, and tells the user to wrap them in
`if __name__ == "__main__":`.

The problem is that the full ~4,000-character explanation is re-logged at WARN on
**every** registry fetch. It appeared 24 times. Measured on this log:

```
total: 554,135 bytes    in lines >1000 chars: 242,054 bytes (44%)
```

Nearly half the log is one message the reader already understood the first time, and it
pushes genuinely rare events far apart.

### Where it is

`scistack-gui/scistack_gui/services/pipeline_service.py:219` — logs
`len(load_errors)` **and** the entire `load_errors` payload on every `get_registry` call.

### The fix

Split what is logged from what is returned:

- Keep returning the full `load_errors` payload in the RPC response — the GUI panel
  needs it, and that is not where the bloat lives.
- At WARN, log the count and the source filenames only.
- Log the full per-file reasons once, at discovery time (where `registry.py` already
  logs "Refusing to import ..." with the complete detail), and at DEBUG here.

The full reason is not lost — it stays exactly where a reader would look for it, at the
moment the file was actually skipped.

### Logging and tests

- **Test:** with N load errors present, assert the WARN text contains the count and the
  source names but not the full reason string, and that the returned dict still contains
  the complete payload. The point is that trimming the log must not trim the API.

---

## Item 3 — A GUI run can't be traced to the records it produced

Largest item; spans scidb, scimatlab, and the GUI. Do it last.

### The problem in plain language

When you press Run, the GUI mints a short run id — `wa0mggq6`. When MATLAB finishes and
scidb writes provenance, scidb mints a *different* id — `865900ee84564732`. Nothing
anywhere connects the two.

```
scidb.log:2110  Parsed request: run_id=wa0mggq6, function=loadDelsysEMGOneFile, language=matlab
scidb.log:2179  [provenance] recorded run_id=865900ee84564732 for 1 record(s)
```

So you cannot answer "I pressed Run at 21:11 — which records did that produce?"

There is a second half to this. The earlier run `ysc74kuh` (`scidb.log:2080`, 21:04:57)
generated an 8,274-character MATLAB command and then produced *nothing at all* — no
success, no failure, no abandonment. The GUI dispatched it to the MATLAB terminal and
lost track of it. This matches the already-known terminal-run-tracking gap; the log
confirms it is real and not theoretical.

### Where it is

- `scistack-gui/scistack_gui/server.py:600` — the GUI's run id is minted or received here.
- `scistack-gui/scistack_gui/server.py:~633` — `route_matlab_single_run` hands the run to
  the host; the run id stops here.
- `scidb/src/scidb/foreach.py:4996-5006` — `record_run` is called without any
  caller-supplied id.
- `scidb/src/scidb/provenance_save.py:337-344` — `record_run` has no parameter for one.

### The fix

Thread the GUI's run id through as a *correlation* id, without changing what scidb's own
`run_id` means:

1. `provenance_save.record_run` accepts an optional `client_run_id` and stores it on the
   `_run` row (new nullable column). scidb's own `run_id` stays the primary key — this is
   purely an added link.
2. `foreach` passes it through from the run configuration.
3. The generated MATLAB command carries the GUI's run id, so it arrives with the save.
4. The GUI logs both ids together at dispatch.

Even step 4 alone — logging `run_id=wa0mggq6 → provenance run_id=...` — closes most of the
day-to-day diagnostic gap, so it is worth landing first and independently.

**Deliberately out of scope:** making terminal runs report real completion status. That
is the separate deferred problem, and it needs its own design (the known trap is that
reaching for `external_db_access` there is the wrong answer). This item only makes runs
*traceable*, not *tracked*. Worth saying plainly so the smaller fix doesn't get read as
solving the bigger one.

### Logging and tests

- Log the two ids together at both ends — that pairing is the whole deliverable.
- **scidb test:** `record_run(..., client_run_id="abc123")` stores and reads back the id;
  omitting it still works and leaves NULL.
- **GUI test:** the generated MATLAB command contains the dispatched run id.
- **Integration test:** a full MATLAB-path run leaves a `_run` row whose `client_run_id`
  equals the id the GUI issued.

---

## Also worth folding in — optional, ~15 minutes total

Not part of items 1-6; listed because they touch the same files and are nearly free.

- `scimatlab/src/scimatlab/matlab/+scidb/close_database.m:34` — the log line reads
  `DuckDB lock RELEASED: ` with an empty value. `db_path` is captured at line 21 from
  `db.path`, which is apparently already unavailable by then; the `catch` at line 22
  silently leaves it blank. Capture the path earlier, or log `(path unavailable)`.
- `scistack-gui/scistack_gui/server.py` — `failed to start debugpy listener:
  debugpy.listen() has already been called` (`scidb.log:2083`) fires on every run after
  the first. Guard with a module-level flag; DEBUG, not WARN.
- `[layout] scoping migration: moving 0 flat position(s)` runs on every `get_layout`.
  Log only when the count is non-zero.
- `scistack_entities.toml` is parsed twice per command generation
  (`scidb.log:2262`, `:2266`).

---

## Notes on layering

- Item 4 is entirely scidb — the GUI already asks correctly.
- Items 1 and 2 are GUI-registry decisions, but item 1 touches stub writing, which lives
  in scimatlab; keep the stub writer ignorant of registry bookkeeping and pass the origin
  down rather than having the writer register anything itself.
- Item 3 is genuinely cross-layer and is the one place where a shared change is required.
- Items 5 and 6 are GUI-only.

## Open question for review

Item 2's precedence rule assumes **project beats library, always**. That is my
recommendation, but it is a policy call — if there is a case where a library is meant
to override project code (a vendored fix, say), tell me and I'll make precedence
configurable instead of fixed.
