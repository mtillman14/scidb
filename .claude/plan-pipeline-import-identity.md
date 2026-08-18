# Fix: hidden pipelines block re-import; give pipelines a stable identity

## Context

Import/export for pipelines/sub-pipelines was added very recently
(`portability_service.py`, `plan-pipeline-import-export.md`). The user hid
(soft-deleted) a previously-imported pipeline named "test (imported)" and
tried to re-import the same file, and got a raw `400: a pipeline named
'test (imported)' already exists` — the import failed instead of restoring
the hidden pipeline.

**Root cause:** `import_pipeline_document` pre-computes a name-collision-
avoidance set from `ps.list_pipelines(db)`, which excludes hidden
pipelines (`portability_service.py:478`). It uses that set to pick a
non-colliding name via `_unique_name`. But the actual creation call,
`pipeline_store.create_pipeline`, rejects names against **all** pipelines,
hidden included (`pipeline_store.py:614-621`, deliberately, per its own
comment and `test_duplicate_name_rejected_even_when_hidden`). So when the
colliding name belongs to a *hidden* pipeline, `_unique_name` thinks the
name is free, and `create_pipeline` then raises — the exact bug.
Separately, the **root** pipeline of an import is currently *never*
matched against an existing local pipeline at all (only non-root
submodules get content-based dedup, matched by name) — so even a byte-
identical re-import of something you already have (hidden or not) always
creates a redundant "(imported)" copy instead of restoring/reusing it.

This also surfaces the user's broader question: should sub-pipeline names
be globally unique at all, given pipelines get shared across users via
import/export? **Decision (confirmed with user):** no. Identity should be
a stable id, independent of the display name; two pipelines from two
different users may legitimately share a name with different content, and
that's fine — names get auto-suffixed on collision, never blocked.

## Design

`_pipelines.pipeline_id` already *is* exactly what's needed for that
identity: a UUID minted once at creation (`pipe_{uuid4().hex[:12]}`,
`pipeline_store.py:622`) and already carried through export as each
pipeline's `pipeline_id` (`portability_service.py` export). The only
change needed is to stop discarding it on import (today import always
mints a brand-new id — `import_pipeline_document`'s docstring: "never
reuses/collides with local ids") and instead **preserve it whenever
possible**, using it as the identity key for the reuse decision. No new
schema/column needed.

Unified rule, applied uniformly to root **and** every submodule in the
closure (removing today's special-cased "root is never reused"):

1. **Local pipeline exists with this exact `pipeline_id`, content
   matches** (via the existing `_content_signature` comparison, recursive
   through children) → **reuse it as-is**. If it's hidden, unhide it. No
   new pipeline is created. (Fixes the reported bug: re-importing an
   unchanged, hidden pipeline just un-hides it.)
2. **Local pipeline exists with this exact `pipeline_id`, content
   differs** (the user edited their copy, or independently diverged) →
   **fork**: mint a fresh id, and pick a name via `_unique_name` against
   *all* local names (hidden included). The existing local pipeline is
   left untouched.
3. **No local pipeline has this `pipeline_id`** (first time this identity
   has been seen locally) → create it, **preserving the imported id**,
   with the name suffixed via `_unique_name` only if that *name* (not id)
   collides with something already local (hidden included). This is the
   "two different users, same name, different content" case — both
   coexist under distinct ids.

This also fixes the latent hidden-name-collision gap (case 2/3's
`_unique_name` call will now be seeded from *all* pipeline names, not just
visible ones, matching what `create_pipeline` actually enforces).

## Files changed

### `scistack-gui/scistack_gui/pipeline_store.py`
- `create_pipeline(db, name, pipeline_id: str | None = None)`: accepts an
  optional explicit id (used by import to preserve identity); default
  `None` mints fresh as before.
- New `get_pipeline(db, pipeline_id) -> dict | None`: single-pipeline
  lookup by id, regardless of hidden state.
- New `list_all_pipelines(db) -> list[dict]`: like `list_pipelines` but
  without the `WHERE NOT hidden` filter.

### `scistack-gui/scistack_gui/services/portability_service.py`
- Rewrote `_resolve_pipeline`: dropped the `is_root` param (identity-based
  resolution applies uniformly). New logic per the 3 cases above, using
  `ps.get_pipeline(db, old_pid)` for the identity lookup.
- `import_pipeline_document`: `existing_names` now seeded from
  `ps.list_all_pipelines(db)`; call site drops the root flag.
- Added `logger.info`/`logger.warning` at each resolution branch (reuse,
  unhide, fork, fresh-preserve, signature-comparison-failure).
- Updated the module docstring's "Submodule dedup" paragraph to describe
  the unified identity-based rule.

### `scistack-gui/tests/test_portability.py`
- `TestExportImportSameDatabase`: `test_roundtrip_preserves_wiring_and_config`
  replaced by `test_unchanged_reimport_is_a_noop_reuse` (same-db unchanged
  reimport now reuses, doesn't duplicate) and
  `test_reimport_after_local_edit_forks_and_preserves_original` (diverged
  content forks, original untouched).
- `TestExportImportCrossDatabase.test_recursive_submodule_export_and_import`:
  `new_child != child` → `new_child == child` (identity preserved into a
  database that never saw it before).
- `TestSubmoduleContentDedup`: docstring + tests updated for root now
  participating in reuse (renamed
  `test_reimporting_reuses_identical_content_root_and_submodule`,
  `test_recursive_reuse_through_nested_submodules` now expects all 3
  levels reused, `test_submodule_with_same_name_but_different_identity_is_not_reused`
  and `test_parent_not_reused_when_a_nested_child_differs_by_identity`
  renamed/re-commented for the identity-first mechanism).
- New `TestHiddenPipelineReimport` class: `test_reimport_of_hidden_pipeline_unhides_instead_of_erroring`
  and `test_reimport_name_collision_with_unrelated_hidden_pipeline_is_suffixed`
  — direct regression tests for the reported bug.

### Frontend
No changes — the error round-trip is generic; it simply won't fire for
this case anymore.

## Verification

Since Python isn't available in this environment, run these yourself:

```
cd /workspace/scistack-gui && python -m pytest tests/test_portability.py tests/test_pipeline_scopes.py -q
```

Manual UI check:
1. Export a pipeline, hide it (Submodules/hypothesis restore panel).
2. Re-import the same file → should silently reappear (unhidden), no
   error dialog, no duplicate in the list.
3. Edit the reappeared pipeline's content, then re-import the same
   original file again → should create a new, distinct "(imported)"-
   suffixed pipeline alongside your edited one, no error.

## Open item

`scope_service.duplicate_pipeline` (the manual "duplicate" UI action)
still does *not* auto-suffix on name collision — it raises `create_pipeline`'s
`ValueError` straight through if the user types an already-taken name.
That's an existing, separate manual-input flow (not part of this bug) and
is left untouched here.

## Docs

Written to `docs/claude/pipeline-import-identity.md` — captures the
identity-based import/reuse model for future reference (user confirmed
2026-08-14).
