# scipathgen — metadata → file paths

!!! info "Internal package"
    `scidb` uses it to resolve on-disk data referenced by metadata. You rarely
    call it directly. (Ships from the `path-gen` folder as the `scipathgen` package.)

`scipathgen` generates file paths from a template and metadata value combinations.
When your pipeline references data that lives on disk rather than in the database,
this is what turns `subject=1, trial=3` into a concrete path.

## What it owns

- **Template-based path generation** — given a template like
  `"{subject}/trial_{trial}.mat"`, a root folder, and metadata ranges, it produces
  every resulting path with its associated metadata attached.

It has no SciStack dependencies. `scidb` uses it for path-addressed inputs and
outputs (see `PathInput` / `PathOutput` in the
[Batch Processing API](../api/for-each.md)).
