"""
Node position persistence.

Positions are stored in a JSON file alongside the .duckdb file:
  experiment.duckdb  →  experiment.layout.json

Format: { "node_id": { "x": float, "y": float }, ... }
"""

import json
from pathlib import Path
from scistack_gui.db import get_db_path


def _layout_path() -> Path:
    return get_db_path().with_suffix('.layout.json')


def read_layout() -> dict[str, dict]:
    p = _layout_path()
    if not p.exists():
        return {}
    with p.open() as f:
        return json.load(f)


def write_node_position(node_id: str, x: float, y: float) -> None:
    layout = read_layout()
    layout[node_id] = {"x": x, "y": y}
    p = _layout_path()
    with p.open("w") as f:
        json.dump(layout, f, indent=2)
