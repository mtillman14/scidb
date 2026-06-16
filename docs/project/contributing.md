# Contributing & Dev Setup

<!-- Ground truth (source win over prose). Verified against:
     repo layout: each package in its own folder with src/<pkg>/ + tests/; folders
     scicanonicalhash, path-gen (scipathgen), scifor, sciduckdb, scilineage, scidb, scimatlab,
     scihist, scidb-net; dev-install.sh (editable install in dependency order — has drifted
     paths); run_tests.sh (per-package pytest; scimatlab skipped unless `matlab` on PATH);
     declared [dependencies] giving the layer order; CLAUDE.md (fixes belong in the matching
     scistack layer; add logging + regression tests when fixing). -->

SciStack is a monorepo of small, single-responsibility packages. This page covers
getting a development environment running and the conventions for changes.

## Repository layout

Each package is its own folder with a `src/<package>/` module and a `tests/`
suite:

```
general-sqlite-database/
  scicanonicalhash/   path-gen/ (scipathgen)   scifor/   sciduckdb/
  scilineage/         scidb/                    scihist/  scimatlab/   scidb-net/
  docs/               mkdocs.yml                run_tests.sh   dev-install.sh
```

The dependency direction (and therefore install/build order) is
`scihist → scidb → {scifor, sciduckdb, scicanonicalhash, scipathgen}` and
`scihist → scilineage → scicanonicalhash`. See
[Architecture & Layers](../concepts/architecture.md) for the full graph.

## Set up a dev environment

Install every package in **editable** mode, in dependency order, so changes in one
package are picked up by the others without reinstalling:

```bash
git clone https://github.com/mtillman14/general-sqlite-database
cd general-sqlite-database
# editable install, lowest layer first — see Installation for the full ordered list
```

The full ordered command list is in [Installation](../getting-started/installation.md).
The repo also ships `dev-install.sh` as a convenience; if you use it, confirm its
folder names match the current packages before running.

## Run the tests

The test suites are the **source of truth** for behavior — when documentation or
intuition disagrees with a test, the test wins. Run them all from the repo root:

```bash
bash run_tests.sh           # pytest for every package
bash run_tests.sh -x -q     # flags are forwarded to pytest
```

`scimatlab` needs a MATLAB licence and is skipped automatically unless `matlab` is
on your `PATH`. To run one package's suite directly, invoke `pytest` in its folder.

## Conventions

A few project-specific norms (from `CLAUDE.md`):

- **Fix things in the layer that owns them.** A storage bug belongs in `scidb` /
  `sciduckdb`, an iteration bug in `scifor`, a provenance bug in `scilineage`, and
  so on — not patched a layer up. Only genuinely GUI-specific issues live in the
  GUI layer.
- **When fixing a bug, add observability and a regression test.** Prefer adding
  logging (or timing) around the affected internals, and a test that pins the
  corrected behavior so it can't silently regress.
- **Keep changes consistent with the surrounding code** — match the existing
  naming, structure, and idioms of the package you're editing.

## Documentation changes

Docs live in `docs/` and are built with MkDocs. The prose is reconciled against
the package tests, so when you change behavior, update the affected page(s) and
verify with a strict build — see [Building These Docs](building-docs.md).

**Next:** [Building These Docs](building-docs.md) ·
[Architecture & Layers](../concepts/architecture.md) ·
[Installation](../getting-started/installation.md)
