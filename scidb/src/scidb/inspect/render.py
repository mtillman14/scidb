"""Pure renderers: Inspector dataclasses → terminal text.

No database access here — every function takes facade result objects and
returns a string. This keeps renderers unit-testable against hand-built
fixtures (golden-file friendly) and lets the CLI/GUI share the facade.
"""

from __future__ import annotations

from .api import (
    DbOverview,
    RecordSummary,
    SchemaNode,
    SchemaTree,
    VariableDetail,
    VariableSummary,
)


def format_table(headers: list[str], rows: list[list]) -> str:
    """Plain ASCII table. None renders as empty; everything else via str()."""
    cells = [[("" if v is None else str(v)) for v in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in cells:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    lines = [
        "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)).rstrip(),
        "  ".join("-" * w for w in widths),
    ]
    for row in cells:
        lines.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip())
    return "\n".join(lines)


def _human_size(n_bytes: int) -> str:
    size = float(n_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024


def render_overview(o: DbOverview) -> str:
    lines = [
        f"database          {o.db_path}  ({_human_size(o.db_size_bytes)})",
        f"schema keys       {', '.join(o.schema_keys)}",
        f"schema locations  {o.n_schema_locations}",
        f"variables         {o.n_variables}",
        f"records           {o.n_records}"
        + (f"  ({o.n_excluded_records} excluded)" if o.n_excluded_records else ""),
        f"invocations       {o.n_invocations}",
        f"runs              {o.n_runs}",
        f"last save         {o.last_save or '-'}",
        f"last run          {o.last_run or '-'}",
    ]
    return "\n".join(lines)


def render_variables(variables: list[VariableSummary]) -> str:
    if not variables:
        return "(no variables registered)"
    return format_table(
        ["variable", "level", "records", "variants", "last saved", "dtype"],
        [
            [
                v.name,
                v.schema_level,
                v.record_count if not v.excluded_count
                else f"{v.record_count} (+{v.excluded_count} excl)",
                v.variant_count,
                v.last_saved,
                (v.dtype or "")[:40],
            ]
            for v in variables
        ],
    )


def render_variable_detail(v: VariableDetail) -> str:
    lines = [
        f"variable       {v.name}",
        f"schema level   {v.schema_level or '-'}",
        f"dtype          {v.dtype or '-'}",
        f"description    {v.description or '-'}",
        f"records        {v.record_count}"
        + (f"  ({v.excluded_count} excluded)" if v.excluded_count else ""),
        f"variants       {v.variant_count}",
        f"last saved     {v.last_saved or '-'}",
        f"data columns   {', '.join(v.data_columns) or '-'}",
    ]
    if v.records_by_level:
        lines.append("records by schema level:")
        for level, n in sorted(v.records_by_level.items()):
            lines.append(f"  {level:<12} {n}")
    return "\n".join(lines)


def render_schema_summary(tree: SchemaTree) -> str:
    """Per-level rollup: how many realized locations and records at each level."""
    locations: dict[str, int] = {}
    records: dict[str, int] = {}

    def walk(node: SchemaNode):
        if node.schema_id is not None and node.schema_level is not None:
            locations[node.schema_level] = locations.get(node.schema_level, 0) + 1
            records[node.schema_level] = records.get(node.schema_level, 0) + node.record_count
        for c in node.children:
            walk(c)

    for root in tree.roots:
        walk(root)

    lines = [f"schema keys: {', '.join(tree.schema_keys)}"]
    if locations:
        # Report in hierarchy order (levels are schema key names).
        ordered = [k for k in tree.schema_keys if k in locations]
        ordered += [k for k in locations if k not in tree.schema_keys]
        lines.append(format_table(
            ["level", "locations", "records"],
            [[lvl, locations[lvl], records[lvl]] for lvl in ordered],
        ))
    else:
        lines.append("(no schema locations realized yet)")
    return "\n".join(lines)


def render_schema_tree(tree: SchemaTree) -> str:
    lines = [f"schema keys: {', '.join(tree.schema_keys)}"]

    def walk(node: SchemaNode, prefix: str, is_last: bool):
        branch = "└─ " if is_last else "├─ "
        count = f"  {node.record_count} records" if node.record_count else ""
        lines.append(f"{prefix}{branch}{node.key}={node.value}{count}")
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, c in enumerate(node.children):
            walk(c, child_prefix, i == len(node.children) - 1)

    if not tree.roots:
        lines.append("(no schema locations realized yet)")
    for i, root in enumerate(tree.roots):
        walk(root, "", i == len(tree.roots) - 1)
    return "\n".join(lines)


def render_records(records: list[RecordSummary], schema_keys: list[str]) -> str:
    if not records:
        return "(no matching records)"
    # Only show schema columns that at least one record uses.
    used_keys = [k for k in schema_keys if any(k in r.schema for r in records)]
    headers = ["record_id", *used_keys, "saved", "user", "v", "excluded"]
    rows = [
        [
            r.record_id,
            *[r.schema.get(k, "") for k in used_keys],
            r.timestamp,
            r.user_id,
            r.schema_version,
            "yes" if r.excluded else "",
        ]
        for r in records
    ]
    return format_table(headers, rows)
