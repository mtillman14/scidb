# Installation

<!-- Ground truth (source win over prose). Verified against:
     on-disk package folders each with pyproject.toml: scicanonicalhash, path-gen (pkg
     scipathgen), scifor, sciduckdb, scilineage, scidb, scimatlab, scihist, scidb-net;
     declared [dependencies] giving the layer order; dev-install.sh (editable install in
     dependency order — but it has stale paths: "sciscicanonicalhash" typo and a "thunk/scirun"
     comment); run_tests.sh (per-package pytest; scimatlab skipped unless `matlab` on PATH);
     docs/requirements.txt (mkdocs docs build); .readthedocs.yaml.
     NOTE: folder `path-gen` ships package `scipathgen`; folder `scicanonicalhash` ships
     `scicanonicalhash`. Install editable in dependency order. -->

SciStack is a stack of three user-facing layers — `scifor`, `scidb`, `scihist` —
built on a handful of internal packages. For most users a single install brings
in everything; if you only need a lower layer, you can install just that. For
which layer you need, see [Choosing Your Layer](choosing-a-layer.md).

## Prerequisites

- Python 3.10 or later
- `pip` (a virtual environment is recommended)
- For the MATLAB bridge: MATLAB R2021b or later — see [MATLAB Setup](../matlab-setup.md)

## Install the full stack

```bash
pip install scistack
```

This installs the top layer (`scihist`) and everything it depends on, so you can
`from scihist import for_each, configure_database, lineage_fcn` right away.

## Install from the repository (development)

To work on SciStack, clone the repo and install the packages **in editable mode,
in dependency order**. Each layer lives in its own folder, alongside the internal
packages it builds on (documented in [Internals](../internals/index.md)):

```bash
git clone https://github.com/mtillman14/general-sqlite-database
cd general-sqlite-database

# Internal foundation packages (no internal dependencies)
pip install -e ./scicanonicalhash
pip install -e ./path-gen          # ships the `scipathgen` package
pip install -e ./sciduckdb
pip install -e ./scilineage        # provenance engine (depends on scicanonicalhash)

# scifor — user-facing batch iteration (no internal dependencies)
pip install -e ./scifor

# scidb — user-facing storage + DB-backed for_each
pip install -e ./scidb

# scihist — user-facing full pipeline
pip install -e ./scihist

# Bridges (optional)
pip install -e ./scimatlab        # MATLAB bridge
pip install -e ./scidb-net        # networking layer
```

Installing a higher layer pulls in everything below it, so if you only want, say,
batch iteration on plain tables you can stop after `scifor`; for the full
pipeline, install through `scihist`. (The non-user-facing packages above are
described in [Internals](../internals/index.md).)

!!! tip "Convenience script"
    The repo ships `dev-install.sh`, which runs these editable installs in order.
    If you use it, verify it matches the folder names above — the checked-in copy
    has drifted from the current package names.

## Install only the layer you need

You don't have to install everything. Minimal sets:

| You want | Install (in order) |
|---|---|
| Batch iteration on plain tables (`scifor`) | `scifor` |
| Versioned storage + DB `for_each` (`scidb`) | `scicanonicalhash`, `path-gen`, `scifor`, `sciduckdb`, then `scidb` |
| Full pipeline (`scihist`) | all of the `scidb` set, plus `scilineage`, then `scihist` |

## Verify the install

```python
import scihist, scidb, scifor   # the layers you installed
print(scidb.__version__)
```

If the imports succeed, you're ready for the [Quickstart](../quickstart.md).

## Running the tests

The test suites are the source of truth for behavior. From the repo root:

```bash
bash run_tests.sh           # runs pytest for every package
bash run_tests.sh -x -q     # extra flags are forwarded to pytest
```

The `scimatlab` suite needs a MATLAB licence and is skipped automatically unless
`matlab` is on your `PATH`.

## Building the docs

To preview this documentation locally (see [Building These Docs](../project/building-docs.md)):

```bash
pip install -r docs/requirements.txt
mkdocs serve            # live preview at http://127.0.0.1:8000
mkdocs build --strict   # the CI gate; fails on broken nav/links
```

**Next:** [Quickstart](../quickstart.md) ·
[Choosing Your Layer](choosing-a-layer.md) · [MATLAB Setup](../matlab-setup.md)
