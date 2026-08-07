# Transition to trunk-based development (main only)

## Context
- `dev` is 26 commits ahead of `main`, zero divergence (main has no commits dev lacks) → merge is a clean fast-forward, no conflicts.
- `publish.yml` already triggers only on `v*` tags and reuses `ci.yml` as a pre-publish gate via `workflow_call` — no change needed there.
- `ci.yml` currently triggers on `push: branches: [main, dev]` plus every `pull_request`.
- `docs.yml` currently triggers on `push: branches: [main, dev]` (path-filtered) plus `pull_request`.
- Decision (confirmed with user): once `dev` is retired, CI tests should run on PRs and on tag-pushes (via the publish gate) only — **not** on direct pushes to `main`.

## Steps

1. **Merge `dev` into `main` locally**
   - `git checkout main`
   - `git merge dev` (fast-forward; no conflicts expected)

2. **Update CI/CD workflow triggers** (on `main`, before pushing)
   - `.github/workflows/ci.yml`: change `on.push.branches` from `[main, dev]` to remove entirely (keep `pull_request` and `workflow_call`). Update the header comment.
   - `.github/workflows/docs.yml`: change `on.push.branches` from `[main, dev]` to `[main]` (drop `dev` only — docs build isn't part of the "tests/publish only on tags" ask, so it keeps running on push to main).
   - `.github/workflows/publish.yml`: no change (already tag-only).
   - Commit this change on `main`.

3. **Push `main` to origin**
   - `git push origin main`
   - Requires your approval before running (affects shared remote state).

4. **Tag the release**
   - Next version tag after `v0.1.16` → `v0.1.17` (confirm version number with you).
   - `git tag v0.1.17`
   - `git push origin v0.1.17`
   - This triggers `publish.yml` (test gate + PyPI publish for all packages).
   - Requires your approval before running.

5. **Delete the `dev` branch** — **only after your explicit approval**
   - `git branch -d dev` (local)
   - `git push origin --delete dev` (remote)

## Not touched
- `gh-pages` branch (unrelated, docs deployment target).
- Existing version tags v0.1.0–v0.1.16.
