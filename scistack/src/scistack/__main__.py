"""
``scistack`` CLI entry point.

Usage:
    scistack project new <name> --schema-keys subject session
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scistack",
        description="SciStack project & environment tooling.",
    )
    sub = parser.add_subparsers(dest="command")

    # --- project new ---
    proj = sub.add_parser("project", help="Project management commands.")
    proj_sub = proj.add_subparsers(dest="project_command")
    new = proj_sub.add_parser("new", help="Scaffold a new SciStack project.")
    new.add_argument("name", help="Project name (lowercase, underscores, starts with a letter).")
    new.add_argument(
        "--schema-keys",
        nargs="+",
        required=True,
        help="Metadata keys that define the dataset schema (e.g. subject session).",
    )
    new.add_argument(
        "--parent-dir",
        type=Path,
        default=Path.cwd(),
        help="Parent directory for the project folder (default: current directory).",
    )
    new.add_argument(
        "--no-uv-sync",
        action="store_true",
        help="Skip running 'uv sync' after scaffolding.",
    )

    args = parser.parse_args(argv)

    if args.command == "project" and args.project_command == "new":
        return _cmd_project_new(args)

    parser.print_help()
    return 1


def _cmd_project_new(args: argparse.Namespace) -> int:
    from scistack.project import scaffold_project, validate_project_name

    try:
        validate_project_name(args.name)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    try:
        project_root = scaffold_project(
            parent_dir=args.parent_dir,
            name=args.name,
            schema_keys=args.schema_keys,
            run_uv_sync=not args.no_uv_sync,
        )
    except FileExistsError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Created project: {project_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
