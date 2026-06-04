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

SciStack is a stack of small packages, each in its own folder. You install the
ones for the layer you want — and because every package depends only on the ones
below it, the install order follows the layers. For which layer you need, see
[Choosing Your Layer](choosing-a-layer.md).

## Prerequisites

- Python 3.10 or later
- `pip` (a virtual environment is recommended)
- For the MATLAB bridge: MATLAB R2021b or later — see [MATLAB Setup](../matlab-setup.md)

## Install from the repository

Clone the repo, then install the packages **in editable mode, in dependency
order**. Each folder is a separate installable package:

```bash
git clone https://github.com/mtillman14/general-sqlite-database
cd general-sqlite-database

# Layer 0 — no internal dependencies
pip install -e ./scicanonicalhash
pip install -e ./path-gen          # ships the `scipathgen` package
pip install -e ./scifor
pip install -e ./sciduckdb

# Layer 1 — provenance (depends on scicanonicalhash)
pip install -e ./scilineage

# Layer 2 — storage + DB-backed for_each (depends on the above)
pip install -e ./scidb

# Layer 3 — top layers (depend on scidb)
pip install -e ./scihist
pip install -e ./scimatlab        # MATLAB bridge (optional)
pip install -e ./scidb-net        # optional networking layer
```

Installing a higher layer pulls in the layers below it, so if you only want, say,
batch iteration on plain tables you can stop after `scifor`; for the full
pipeline, install through `scihist`.

!!! tip "Convenience script"
    The repo ships `dev-install.sh`, which runs these editable installs in order.
    If you use it, verify it matches the folder names above — the checked-in copy
    has drifted from the current package names.

## Install only the layer you need

You don't have to install everything. Minimal sets:

| You want | Install (in order) |
|---|---|
| Batch iteration on plain tables (`scifor`) | `scifor` |
| Provenance for a function graph (`scilineage`) | `scicanonicalhash`, then `scilineage` |
| Versioned storage + DB `for_each` (`scidb`) | `scicanonicalhash`, `path-gen`, `scifor`, `sciduckdb`, then `scidb` |
| Full pipeline (`scihist`) | all of the `scidb` set, plus `scilineage`, then `scihist` |

## Verify the install

```python
import scihist, scidb, scifor, scilineage   # the layers you installed
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
