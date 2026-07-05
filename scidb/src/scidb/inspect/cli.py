"""``scidb`` CLI — thin rendering shell over scidb.inspect.Inspector.

Phase 1 commands: status, vars, schema, show. Every command opens the
database strictly read-only and supports ``--json`` (machine-readable
``dataclasses.asdict`` output).

Also mountable as the ``scistack db`` alias via ``add_db_subparser``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

from ..log import Log
from . import render
from .api import Inspector


class CLIError(Exception):
    """User-facing CLI failure; message printed to stderr, exit code 1."""


# ---------------------------------------------------------------------------
# Database discovery
# ---------------------------------------------------------------------------

def _pyproject_db(start: Path) -> str | None:
    """Find ``[tool.scistack] db = "…"`` in the nearest pyproject.toml upward."""
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            Log.debug("scidb cli: no tomllib/tomli — skipping pyproject.toml discovery")
            return None
    for directory in [start, *start.parents]:
        pyproject = directory / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            Log.warn(f"scidb cli: could not parse {pyproject}: {e}")
            continue
        db = data.get("tool", {}).get("scistack", {}).get("db")
        if db:
            return str((directory / db).resolve()) if not Path(db).is_absolute() else db
    return None


def resolve_db_path(db_flag: str | None, cwd: Path | None = None) -> tuple[str, str]:
    """Resolve the database path → (path, source). Discovery order:
    --db flag > SCIDB_DATABASE env > pyproject [tool.scistack] db > single
    *.duckdb in cwd.
    """
    cwd = cwd or Path.cwd()
    if db_flag:
        return str(db_flag), "--db flag"
    env = os.environ.get("SCIDB_DATABASE")
    if env:
        return env, "SCIDB_DATABASE env var"
    from_pyproject = _pyproject_db(cwd)
    if from_pyproject:
        return from_pyproject, "pyproject.toml [tool.scistack] db"
    candidates = sorted(cwd.glob("*.duckdb"))
    if len(candidates) == 1:
        return str(candidates[0]), "single *.duckdb in cwd"
    if len(candidates) > 1:
        names = ", ".join(c.name for c in candidates)
        raise CLIError(
            f"Multiple .duckdb files in {cwd}: {names}. "
            f"Pick one with --db or set SCIDB_DATABASE."
        )
    raise CLIError(
        "No database found. Pass --db PATH, set SCIDB_DATABASE, add "
        "[tool.scistack] db = \"...\" to pyproject.toml, or run in a "
        "directory containing exactly one .duckdb file."
    )


def _parse_kv(pairs: list[str]) -> dict[str, str]:
    """Parse ``key=value`` args. Values stay strings — schema key values are
    stored as strings (zero-padded keys like "01" must survive verbatim)."""
    out: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise CLIError(f"Expected key=value, got {pair!r}")
        key, value = pair.split("=", 1)
        out[key] = value
    return out


def _emit_json(result) -> None:
    if isinstance(result, list):
        payload = [dataclasses.asdict(r) for r in result]
    else:
        payload = dataclasses.asdict(result)
    print(json.dumps(payload, indent=2, default=str))


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_status(insp: Inspector, args) -> None:
    overview = insp.overview()
    if args.json:
        _emit_json(overview)
    else:
        print(render.render_overview(overview))


def _cmd_vars(insp: Inspector, args) -> None:
    if args.type:
        detail = insp.variable(args.type)
        _emit_json(detail) if args.json else print(render.render_variable_detail(detail))
    else:
        variables = insp.variables()
        _emit_json(variables) if args.json else print(render.render_variables(variables))


def _cmd_schema(insp: Inspector, args) -> None:
    tree = insp.schema_tree()
    if args.json:
        _emit_json(tree)
    elif args.tree:
        print(render.render_schema_tree(tree))
    else:
        print(render.render_schema_summary(tree))


def _cmd_show(insp: Inspector, args) -> None:
    metadata = _parse_kv(args.metadata)
    records = insp.records(
        args.type,
        latest=not args.versions,
        include_excluded=args.include_excluded,
        **metadata,
    )
    if args.json:
        _emit_json(records)
    else:
        print(render.render_records(records, insp._db.dataset_schema_keys))


# ---------------------------------------------------------------------------
# Parser wiring
# ---------------------------------------------------------------------------

def _add_global_args(parser: argparse.ArgumentParser,
                     suppress_defaults: bool = False) -> None:
    """Add the global flags.

    ``suppress_defaults=True`` is for the copies attached to subcommand
    parsers: since Python 3.9 a subparser parses into a *fresh* namespace and
    copies every value back, so a subcommand-level default (db=None,
    json=False) would clobber a flag parsed before the subcommand. With
    default=SUPPRESS, a flag the user didn't pass after the subcommand never
    enters the sub-namespace and the root-parsed value survives.
    """
    d = {"default": argparse.SUPPRESS} if suppress_defaults else {}
    parser.add_argument("--db", **d,
                        help="Path to the .duckdb database (else discovered).")
    parser.add_argument("--json", action="store_true", **d,
                        help="Emit machine-readable JSON instead of tables.")
    parser.add_argument("--no-color", action="store_true", **d,
                        help="Disable colored output (Phase 1 output is uncolored).")
    parser.add_argument("-v", "--verbose", action="store_true", **d,
                        help="Verbose logging (facade call timing etc.).")


def _global_parent() -> argparse.ArgumentParser:
    """Global flags as a parents=[] parser so they are accepted both before
    and after the subcommand (``scidb --json vars`` and ``scidb vars --json``)."""
    parent = argparse.ArgumentParser(add_help=False)
    _add_global_args(parent, suppress_defaults=True)
    return parent


def _add_commands(sub: argparse._SubParsersAction,
                  parent: argparse.ArgumentParser) -> None:
    p = sub.add_parser("status", parents=[parent],
                       help="Database overview: counts, size, last activity.")
    p.set_defaults(_handler=_cmd_status)

    p = sub.add_parser("vars", parents=[parent],
                       help="List variable types, or detail for one.")
    p.add_argument("type", nargs="?", default=None,
                   help="Variable type name for a detailed view.")
    p.set_defaults(_handler=_cmd_vars)

    p = sub.add_parser("schema", parents=[parent],
                       help="Schema keys and realized hierarchy.")
    p.add_argument("--tree", action="store_true", help="Render the full hierarchy tree.")
    p.set_defaults(_handler=_cmd_schema)

    p = sub.add_parser("show", parents=[parent],
                       help="Records at a location (latest per variant).")
    p.add_argument("type", help="Variable type name.")
    p.add_argument("metadata", nargs="*",
                   help="key=value filters (schema keys and branch params; "
                        "values are matched as strings).")
    p.add_argument("--versions", action="store_true",
                   help="Show every saved version, not just the latest per variant.")
    p.add_argument("--include-excluded", action="store_true",
                   help="Include records marked excluded.")
    p.set_defaults(_handler=_cmd_show)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scidb",
        description="Inspect a scidb database (read-only).",
    )
    _add_global_args(parser)
    _add_commands(parser.add_subparsers(dest="command"), _global_parent())
    return parser


def add_db_subparser(sub: argparse._SubParsersAction) -> None:
    """Mount these commands as the ``scistack db`` alias (owning-layer rule:
    scistack/__main__.py calls this; all logic stays in scidb)."""
    db_parser = sub.add_parser("db", help="Inspect a scidb database (read-only).")
    _add_global_args(db_parser)
    _add_commands(db_parser.add_subparsers(dest="db_command"), _global_parent())
    db_parser.set_defaults(_dispatch=dispatch)


def dispatch(args: argparse.Namespace) -> int:
    """Run a parsed inspect command. Shared by ``scidb`` and ``scistack db``."""
    handler = getattr(args, "_handler", None)
    if handler is None:
        build_parser().print_help()
        return 1
    if args.verbose:
        Log.set_level("DEBUG")
    try:
        db_path, source = resolve_db_path(args.db)
        if not Path(db_path).is_file():
            raise CLIError(f"Database not found: {db_path} (from {source})")
        # Same convention as configure_database: scidb.log next to the db file.
        if Log.get_path() is None:
            Log.set_path(str(Path(db_path).parent / "scidb.log"))
        Log.info(f"scidb cli: db={db_path} (resolved via {source})")
        if args.verbose:
            print(f"database: {db_path} (via {source})", file=sys.stderr)
        with Inspector.open(db_path) as insp:
            handler(insp, args)
        return 0
    except CLIError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        # DuckDB lock contention, malformed db, unknown variable, bad filters…
        print(f"Error: {e}", file=sys.stderr)
        Log.error(f"scidb cli failed: {type(e).__name__}: {e}")
        return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return dispatch(args)


if __name__ == "__main__":
    sys.exit(main())
