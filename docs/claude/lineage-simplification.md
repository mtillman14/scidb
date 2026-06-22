# Lineage Simplification — Bipartite Provenance Model

> **⚠️ This is the original DESIGN doc (pre-implementation). For the canonical,
> up-to-date as-built reference see `database-model.md`.** Some details here were
> revised during implementation (e.g. output `record_id` is still derived from
> in-memory metadata, not `invocation_id`; `_record_metadata` became the slimmed
> `_record_save`). Read this for the "why" behind the model.

> Status: **design** (branch `dev-hist`). No code written yet. This document is
> the agreed reference for the redesign. We are in beta with **no existing
> databases**, so this is a **clean replacement** — old structures are deleted,
> not migrated.

## 1. Why

We are consolidating `scihist` into `scidb` because the history machinery is
just composing scidb machinery. While doing so we want the lineage/provenance
system to be **as simple and non-redundant as possible**, and we want a new
capability:

> "Show me the entire processing pipeline, down to the `record_id` level, that
> generated variable X (specified by `record_id`)."

## 2. The problem with today's storage

Provenance is currently recorded **twice**, in two parallel systems:

- **Identity system** (load-bearing): `record_id` + `version_keys` +
  `branch_params`, all JSON-blob columns on `_record_metadata`.
- **Lineage system** (redundant): the `_lineage` table + the `scilineage.LineageFcn`
  wrapper, recording function/inputs/constants/upstream a second time.

Nearly everything in `_lineage` duplicates `version_keys`. The genuinely unique
content (`lineage_hash`, constant `value_hash`) only ever served caching /
content-staleness, not traversal.

Worse, the surviving facts are stored as **opaque JSON strings**:

- `version_keys` — the current node's config: `__fn`, `__fn_hash`, `__inputs`,
  `__constants`, `__upstream` (`{__rid_param: record_id}`), `__output_num`, …
- `branch_params` — the *accumulated* namespaced constants up the whole chain:
  `{"bandpass.low_hz": 20, "rms.window": 100}`.

Because the upstream edges (`__upstream`) live buried inside a JSON string, you
cannot `JOIN` or index on them. That is why traversal needs Python-side parsing
and why `get_upstream_provenance` resorts to a `branch_params`-subset
**heuristic** to guess edges. We want **provably-correct, indexable** edges.

## 3. The core insight

`branch_params` is just **accumulated constants** from the chain — fully
derivable, not a primary fact. And the original reason `version_keys` existed
(disambiguating `my_fcn(a=1)` vs `my_fcn(a=2)`) disappears if we **treat
constants as input records** — leaf nodes with no producing function.

Then a node's complete identity is uniform: **its function + the set of its
inputs**, where inputs (variable *and* constant) are all just upstream
`record_id`s. The data flow is captured entirely by the edge graph.

But edges alone are not enough: an edge is really `record → function call →
record`, and the function call is a first-class thing (it has a function hash,
and a single call can have **many inputs and many outputs**). So we model the
graph as **bipartite**: records (entities) and invocations (activities). This is
the classic provenance shape (cf. W3C PROV entity/activity).

## 4. Schema — seven relational tables

Identity/data: `_record`, `_constant`, `_invocation`, `_invocation_input`,
`_invocation_output`. Audit: `_run`, `_run_invocation`.

```sql
-- Entities: variables AND constants share this table.
-- Variables have a schema_id and a type (class name); their data lives in the
-- existing per-type "<Type>_data" tables.
-- Constants have schema_id NULL, type '__constant__', and their value in _constant.
CREATE TABLE _record (
    record_id      VARCHAR PRIMARY KEY,   -- content-addressed; one row per record
    created_at     VARCHAR NOT NULL,      -- first time this record was seen
    type           VARCHAR NOT NULL,      -- class name, or '__constant__'
    schema_id      INTEGER,               -- NULL for constants (schema-global)
    content_hash   VARCHAR,
    schema_version INTEGER,
    excluded       BOOLEAN DEFAULT FALSE
);
-- NOTE: re-production audit (who/when re-ran a computation) moves to _run.
-- A record is content-addressed and immutable, so it is ONE row, inserted
-- ON CONFLICT DO NOTHING. The old (record_id, timestamp) composite PK that
-- tracked re-saves is replaced by the append-only _run log below.

-- Constant values (parallel to a variable's "<Type>_data" table).
CREATE TABLE _constant (
    record_id   VARCHAR PRIMARY KEY,
    value_repr  VARCHAR,                  -- human-readable rendering (e.g. "20")
    value_type  VARCHAR,                  -- e.g. "int", "str"
    content_hash VARCHAR                  -- hash of the value; drives record_id
);

-- Activities: one row per UNIQUE function call (content-addressed identity).
-- as_table and distribute are IDENTITY-bearing (folded into invocation_id) and
-- therefore invariant per invocation — stored here as queryable columns, not JSON.
-- where is NOT here: it is batch-level and varies independently of identity (see _run).
CREATE TABLE _invocation (
    invocation_id  VARCHAR PRIMARY KEY,
    function_name  VARCHAR NOT NULL,
    function_hash  VARCHAR NOT NULL,
    as_table       VARCHAR[],             -- resolved aggregated param names; hashed into id
    distribute     BOOLEAN DEFAULT FALSE  -- hashed into id
);

-- What was fed into a call, and the argument slot it filled.
CREATE TABLE _invocation_input (
    invocation_id   VARCHAR NOT NULL,
    param_name      VARCHAR NOT NULL,     -- e.g. "signal", "low_hz" (MATLAB: "arg_0")
    input_record_id VARCHAR NOT NULL,     -- a variable OR constant record_id
    PRIMARY KEY (invocation_id, param_name, input_record_id)
);

-- What a call produced. Multiple rows for multi-output functions.
CREATE TABLE _invocation_output (
    invocation_id     VARCHAR NOT NULL,
    output_num        INTEGER NOT NULL,   -- 0 for single-output fns
    output_record_id  VARCHAR NOT NULL,
    PRIMARY KEY (invocation_id, output_num)
);

-- Audit log: one row per for_each EXECUTION (a fresh row every run, even when it
-- reproduces existing invocations). Captures the batch-level "what I did": when,
-- who, and the where= filter the scientist applied — the comprehension layer.
CREATE TABLE _run (
    run_id        VARCHAR PRIMARY KEY,    -- fresh unique id per execution (NOT content-addressed)
    timestamp     VARCHAR NOT NULL,
    user_id       VARCHAR,
    function_name VARCHAR NOT NULL,       -- readability ("run X executed bandpass_filter")
    where_clause  VARCHAR                 -- human-readable filter as issued; audit/display only
);

-- Many-to-many: which invocations a run (re)produced. A re-run inserts a new
-- _run + new links even though the invocations dedup. So every where= ever used
-- is preserved, each stamped with when + who.
CREATE TABLE _run_invocation (
    run_id        VARCHAR NOT NULL,
    invocation_id VARCHAR NOT NULL,
    PRIMARY KEY (run_id, invocation_id)
);
```

`_record` replaces today's `_record_metadata` minus the deleted blob columns
(`version_keys`, `branch_params`, `lineage_hash`). `_schema`, `_variables`, and
the per-type `<Type>_data` tables are unchanged.

Why bipartite (vs. a flat `_edge(output, param, input)` table): a multi-output
call shares one input set across all its outputs. A flat table would **repeat**
every input row (and the function identity) per output — a denormalization with
consistency risk, and it loses "same call?" as a cheap query. The invocation
node stores each shared fact once.

## 5. Identity — how `record_id`s are computed

Content-addressing is preserved and *extended* so that two outputs differing
only by an upstream constant get distinct ids automatically (the job
`__upstream`-in-`version_keys` does today, now structural).

```
constant record_id   = hash("__constant__" | content_hash(value))
                        -- schema-global; same value reused everywhere

invocation_id        = hash(function_hash | as_table | distribute
                            | sorted(input bindings))
                        -- input binding = (param_name, input_record_id)
                        -- where is EXCLUDED — redundant for identity (see §10.1)
                        -- content-addressed: re-running the same call → same id

output record_id     = hash(type | schema_version | content_hash(data)
                            | invocation_id | output_num)

run_id               = fresh unique id per for_each execution (e.g. UUID)
                        -- NOT content-addressed: we WANT a new _run row every
                        -- run, even one that reproduces existing invocations,
                        -- so the audit log captures every execution event.
```

Properties:

- **Idempotent.** Re-running an identical pipeline reproduces every id, so all
  inserts are `ON CONFLICT DO NOTHING`. No duplicate provenance.
- **`lineage_hash` reborn.** The old content-addressed "computation id" we were
  going to delete *is* `invocation_id`. It is no longer a redundant side-record
  — it is structural identity.
- **Raw/manually saved records** are just records with no `_invocation_output`
  row — the upstream walk terminates there (the manual-derivation gap is
  out of scope for now, per our decision).

## 6. `branch_params` becomes a derived view

No longer stored. Computed by walking the invocation graph upward and collecting
the constant nodes, namespaced by their consuming function + param:

```sql
WITH RECURSIVE ancestry(root, rid, depth) AS (
    SELECT record_id, record_id, 0
    FROM _record WHERE record_id = :target
  UNION ALL
    SELECT a.root, ii.input_record_id, a.depth + 1
    FROM ancestry a
    JOIN _invocation_output io ON io.output_record_id = a.rid
    JOIN _invocation_input  ii ON ii.invocation_id   = io.invocation_id
    WHERE a.depth < :max_depth
)
SELECT inv.function_name || '.' || ii.param_name AS key, c.value_repr AS value
FROM ancestry a
JOIN _invocation_output io ON io.output_record_id = a.rid
JOIN _invocation_input  ii ON ii.invocation_id   = io.invocation_id
JOIN _invocation       inv ON inv.invocation_id  = ii.invocation_id
JOIN _constant          c  ON c.record_id        = ii.input_record_id;
```

This is the exact `{fn.param: value}` map we store today, now derived and
indexable.

## 7. `version_keys` decomposition — where each field goes

| Old `version_keys` field | New home | Derived? |
|---|---|---|
| `__fn`, `__fn_hash` | `_invocation.function_name`, `.function_hash` | stored (node attr) |
| `__inputs` (`{param: type}`) | join `_invocation_input` → `_record.type` | derived |
| `__constants` (`{name: value}`) | constant input records (`_constant`) | derived |
| `__upstream` (`{__rid_param: rid}`) | `_invocation_input` (variable inputs) | **is the edge table** |
| `__output_num` | `_invocation_output.output_num` | stored |
| `__as_table`, `__distribute` | `_invocation.as_table`, `.distribute` (hashed into id) | stored (identity) |
| `__where` | `_run.where_clause` (batch-level audit; NOT hashed) | stored (audit) |

So `version_keys` as an opaque blob is **gone**. The irreducible per-node facts
are the function label + identity flags (on `_invocation`); `where` is recorded
per execution on `_run` for the scientist's benefit but plays no role in identity
or traversal.

## 8. Pipeline reconstruction (the new feature)

A recursive CTE over the bipartite graph, terminating at records with no
producing invocation (raw data + constants):

```sql
WITH RECURSIVE pipeline(rid, depth) AS (
    SELECT :target, 0
  UNION ALL
    SELECT ii.input_record_id, p.depth + 1
    FROM pipeline p
    JOIN _invocation_output io ON io.output_record_id = p.rid
    JOIN _invocation_input  ii ON ii.invocation_id   = io.invocation_id
    WHERE p.depth < :max_depth
)
SELECT * FROM pipeline;
```

Joining each `rid` back to `_invocation` (via `_invocation_output`) labels each
node with its function + constants. The result is a **provably-correct DAG** —
every edge is a stored fact, no `branch_params`-subset heuristic. The old
`get_upstream_provenance` heuristic is deleted.

## 9. Load disambiguation — does the new structure earn its keep?

Today `FilteredSignal.load(subject=1, low_hz=20)` is a JSON suffix-match on
`branch_params`. New model — two cases:

**Direct constant (fast path):** the producing call consumed `low_hz` directly.

```sql
SELECT DISTINCT io.output_record_id
FROM _record r
JOIN _invocation_output io ON io.output_record_id = r.record_id
JOIN _invocation_input  ii ON ii.invocation_id   = io.invocation_id
JOIN _constant          c  ON c.record_id = ii.input_record_id
WHERE r.type = 'FilteredSignal' AND r.schema_id = :sid
  AND ii.param_name = 'low_hz' AND c.value_repr = '20';
```

**Upstream constant (general path):** `low_hz` was consumed several steps back.
Filter the §6 derived `branch_params` view for a key ending in `.low_hz` = 20.
Ambiguity (two namespaced keys both ending `.low_hz`) is detectable with
`GROUP BY` / `HAVING COUNT(DISTINCT key) > 1`, replacing today's
`AmbiguousParamError` logic — but now as an indexable join, not string parsing.

This is the case the model has to win, and it does: same semantics, now
relational and indexable.

## 9b. Execution audit — who/when/which filter produced a record

The payoff of the `_run` log. For any output record, list every execution that
produced (or reproduced) it, with timestamp, user, and the `where` filter as the
scientist issued it:

```sql
SELECT run.timestamp, run.user_id, run.where_clause, inv.function_name
FROM _invocation_output io
JOIN _invocation      inv ON inv.invocation_id = io.invocation_id
JOIN _run_invocation  ri  ON ri.invocation_id  = io.invocation_id
JOIN _run            run  ON run.run_id        = ri.run_id
WHERE io.output_record_id = :target
ORDER BY run.timestamp;
```

Because re-runs append new `_run` rows (the invocation itself dedups), a filter
change like `amplitude > 0.1` → `> 0.05` shows up as two audit rows with their
own dates and users — nothing is lost to first-wins. This is the comprehension
layer for scientists: "this result came from `bandpass_filter`, filtered to
`amplitude > 0.05`, run by alice on 2026-06-18."

## 9c. Node completeness / GUI coloring

The GUI needs to color each pipeline node by whether its `for_each` step has been
run on every combination it *should* have. The bipartite design answers this
without a stored expectation table, because the key fact is **computable before
execution**.

### Enabling property

```
invocation_id = hash(function_hash | as_table | distribute | sorted(input bindings))
```

Every term is known ahead of running: `function_hash` from the recipe's source,
the flags from the recipe, and the input bindings from the `record_id`s of the
*currently existing* input records (variable inputs are in the DB; constant
inputs hash from their values). So for any combo you *could* run, you can compute
the `invocation_id` it *would* produce, and check whether that row exists. "Has
this been run?" becomes a membership test against `_invocation`.

### Algorithm

```
expected = []
for combo in plan_combos(recipe, db):          # for_each planning phase — NO execution
    bindings = resolve_input_bindings(combo)    # {param: record_id}, incl. constant records
    inv_id   = hash(fn_hash, as_table, distribute, sorted(bindings))
    expected.append(inv_id)

present = SELECT invocation_id FROM _invocation WHERE invocation_id IN (:expected)

if   len(present) == 0:              color = NOT_RUN     # grey
elif len(present) == len(expected):  color = COMPLETE    # green
else:                                color = PARTIAL     # e.g. "47/50"
```

Step 1 is exactly for_each's combo/variant expansion (`_load_var_type_all` +
cross-product) in **dry-run mode** — scifor already has a dry-run path; expose it
to *return the expected `invocation_id`s* rather than print. The GUI node supplies
the recipe (fn, input types, constants, metadata iterables, `where`, flags); the
DB supplies the current records; the deterministic id bridges them.

Output content hashes can't be predicted without running, but they aren't
needed: an invocation and its `_invocation_output` rows are written together, so
**invocation present ⇒ outputs present**. Membership in `_invocation` is the
whole signal.

### "Stale" collapses into "not-run"

Because the id is content-addressed over both `function_hash` *and* the input
`record_id`s:

- recompute an upstream input → its `record_id` changes → the *expected*
  `invocation_id` shifts → the new one is absent → node shows **needs-run**;
- edit the function → `function_hash` changes → same effect.

No separate staleness comparison is needed. One uniform query ("are the expected
ids present?") makes "never ran" and "ran but inputs/function changed" surface
identically. The stale invocation stays in `_invocation` (intact provenance for
old results) — it just falls out of the *expected* set.

### Policy decision — RESOLVED: color on the full `invocation_id`

Editing a function (changing `function_hash`) **does** turn the node yellow. The
GUI colors on the full `invocation_id`, which includes `function_hash` — a source
edit shifts the expected ids, they're absent, node shows needs-run.

This does **not** contradict the earlier "function-hash mismatch is
traceability-only, not stale" decision, because they answer different questions
at different levels:

- **Record level (unchanged):** an existing output whose producing function no
  longer matches the current source is still valid, traceable lineage. We do not
  delete it or reinstate an equality check that invalidates it. The old
  invocation + outputs stay in the DB intact.
- **GUI node level (this decision):** the node colors yellow because the
  *current recipe* (new `function_hash`) has not been run on these inputs. That
  is a statement about **coverage of the current recipe**, not a claim that the
  old records are invalid.

Both hold simultaneously: old data preserved (traceability honored) **and** the
node signals needs-run (current code not yet executed). See §10.4.

## 10. Open design decisions

1. **Execution flags — RESOLVED.** `as_table` and `distribute` are stored as
   columns on `_invocation` and folded into `invocation_id`. `where` is
   **excluded from identity** but **stored on `_run`** for the scientist's audit
   (see §9b). Reasoning, by the test "does the flag change what the call
   computes/emits, holding the binding set fixed?":
   - **`where` — exclude from identity, record on `_run`.** It only filters
     *which records load* (`_apply_where_filter`, scifor/foreach.py:1057); its
     whole effect on the computation is the surviving input set = the edges
     themselves. Two invocations with the same realized inputs compute
     identically regardless of the `where` that produced them, so including it
     would fragment identity. But it is essential *comprehension* metadata, so it
     lives on the append-only `_run` log — every `where` ever used is preserved
     with its timestamp + user, even when filters overlap onto the same
     invocation. (This is why `where` is a `_run` field, not an `_invocation`
     field: it varies independently of identity.)
   - **`as_table` — include.** It changes the *shape* handed to the function: a
     DataFrame (schema columns kept) vs an unwrapped value
     (scifor/foreach.py:1063-1069). With ≥2 aggregated records the binding set
     already differs (multiple `_invocation_input` rows per param), so no
     collision — but with **exactly one** record the binding set is identical to
     a non-`as_table` call while the computation differs. Real collision →
     `ON CONFLICT DO NOTHING` keeps one row; the two outputs (distinct
     `content_hash`) both point at it → mis-attribution.
   - **`distribute` — include.** Post-call fan-out (`_split_for_distribute` on
     `output_value`, scifor/foreach.py:560-563): same call, but N pieces at a
     lower schema level vs 1 output. Excluding it clashes on the
     `_invocation_output` PK `(invocation_id, output_num=0)` and attributes
     different output structures to one invocation.
2. **Constant value storage.** `_constant` stores `value_repr` + `value_type`.
   Decide whether large/structured constants (arrays, dicts) need full
   serialization or just a hash + repr. Constants are content-addressed and
   schema-global, so they dedup naturally.
3. **API compatibility.** `get_provenance`, `get_upstream_provenance`,
   `get_lineage_inputs`, `get_pipeline_structure`, `has_lineage` get
   reimplemented over the new tables, ideally returning the same dict shapes so
   GUI/MATLAB consumers don't change. Audit callers first via `findReferences`.
4. **Function-source edit recolors a GUI node — RESOLVED.** Color on the full
   `invocation_id` (includes `function_hash`), so a source edit ⇒ needs-run.
   Reconciled with the prior "function-hash mismatch is traceability-only, not
   stale" decision in §9c: record-level lineage stays valid (old data preserved);
   only the GUI's current-recipe-coverage indicator turns yellow.

## 11. What gets deleted (clean replacement)

- `_lineage` table; `_save_lineage`, `_save_lineage_rows_batch`.
- `version_keys`, `branch_params`, `lineage_hash` columns on `_record_metadata`.
- `scilineage.LineageFcn` auto-wrap in `for_each`. **Keep** the free helper
  `scilineage.hashing.compute_function_hash` (already used directly to compute
  `__fn_hash`).
- The `branch_params`-subset heuristic in `get_upstream_provenance`.
- `skip_computed` (`_build_skip_hook`) rewritten to read the new tables
  (function_hash + input edges + constant records) instead of `_lineage`.
- `_for_each_expected` table + `check_node_state()`. Node completeness is now
  computed on demand from current state (§9c), not from a stored snapshot.
- `call_id` / `call_id_from_version_keys`. No longer needed: invocations are
  content-addressed, so distinct call sites that compute the same `invocation_id`
  share it (and `_run` records which execution produced it). The §10.4 decision
  to color on the full `invocation_id` means no `function_hash`-excluding hash is
  required, so `call_id` is deleted outright.

## 12. Sequencing

1. **This doc** (done) — agree the model.
2. Schema + identity helpers (the seven new tables — `_record`, `_constant`,
   `_invocation`, `_invocation_input`, `_invocation_output`, `_run`,
   `_run_invocation` — plus constant records and id computation). §10.1 resolved.
3. Save path: `for_each` writes records + invocations + inputs/outputs, and an
   append-only `_run` + `_run_invocation` per execution.
4. Read side: pipeline reconstruction (§8), derived `branch_params` (§6), load
   disambiguation (§9), execution audit (§9b). Reimplement the provenance API
   (§10.3).
5. Delete old machinery (§11); rewrite `skip_computed`.
6. Tests at each step (logging + regression, per project convention).
```
