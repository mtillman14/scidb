# scistack

Project & environment tooling for the SciStack scientific pipeline framework.

`scistack` is the top-level package that ties the SciStack layers together for
end users who are building and publishing scientific projects. It provides:

- **`scistack.uv_wrapper`** — thin Python wrapper around the `uv` CLI for
  lockfile management (`sync`, `add`, `remove`, `read_lockfile`,
  `is_lockfile_stale`).
- **`scistack.user_config`** — user-global configuration in
  `~/.scistack/config.toml`, including tapped package indexes.
- **`scistack.project`** — project scaffolder that creates the standard
  SciStack project layout (`src/{name}/`, `.scistack/`, `pyproject.toml`,
  `uv.lock`, `{name}.duckdb`).
- **`scistack` CLI** — `scistack project new` and related commands.

Higher-level abstractions (Variables, pipeline functions, for-each execution)
live in `scidb`. The GUI lives in `scistack-gui`. `scistack` is the glue layer
that turns a scidb-using script into a reproducible project.

See `docs/claude/project-library-structure.md` for the full design and
`.claude/project-library-structure.md` for the implementation plan.
