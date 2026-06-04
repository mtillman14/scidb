# scimatlab — the MATLAB bridge

!!! info "Internal package"
    In MATLAB you write `scifor.*` and `scidb.*` directly — you never reference
    `scimatlab` by name. This page describes the bridge that makes that work. For
    setup and usage, see [MATLAB Setup](../matlab-setup.md).

`scimatlab` exposes SciStack's surfaces to MATLAB, providing
`scidb.BaseVariable` and `scidb.LineageFcn` (with full lineage tracking and
caching) from MATLAB code. All hashing, lineage computation, and database
operations are **delegated to Python** via MATLAB's `py.` interface — the MATLAB
layer is a thin wrapper, so the same pipelines run identically from either
language.

## What it owns

- **MATLAB class definitions** mirroring the Python `scidb` / lineage API.
- **Type round-trips** between MATLAB tables/structs and the Python layer.
- **`py.`-based delegation** so there is a single source of truth (Python) for
  hashing, versioning, and lineage.

## Requirements

- MATLAB R2021b or later (for `name=value` argument syntax)
- Python 3.10+ with `scidb` and `scimatlab` installed
- MATLAB's Python environment configured (`pyenv`)

See [MATLAB Setup](../matlab-setup.md) for the full walkthrough.
