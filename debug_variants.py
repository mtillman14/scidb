"""Debug script to understand the variant duplication issue."""

import json
import tempfile
from pathlib import Path

import numpy as np

from scidb import BaseVariable, configure_database, for_each

SCHEMA = ["subject", "session"]


class RawSignal(BaseVariable):
    pass


class Filtered(BaseVariable):
    pass


class Spikes(BaseVariable):
    pass


def bandpass(signal, low_hz):
    return signal * low_hz


def detect_spikes(signal, threshold):
    if isinstance(signal, np.ndarray):
        return (signal > threshold).astype(float)
    return float(signal > threshold)


# Create temp database
with tempfile.TemporaryDirectory() as tmpdir:
    db = configure_database(Path(tmpdir) / "debug.duckdb", SCHEMA)

    # Setup data
    for subj in ["S01", "S02"]:
        RawSignal.save(np.array([1.0, 2.0]), subject=subj, session="1")

    # Create filtered variants
    for low_hz in [20, 30]:
        for_each(
            bandpass,
            {"signal": RawSignal, "low_hz": low_hz},
            [Filtered],
            subject=["S01", "S02"],
            session=["1"],
        )

    # Create spikes - this is where duplicates appear
    print("\n=== Running detect_spikes with threshold=0.5 ===")
    for_each(
        detect_spikes,
        {"signal": Filtered, "threshold": 0.5},
        [Spikes],
        subject=["S01", "S02"],
        session=["1"],
    )

    # Check what was saved
    print("\n=== Inspecting Spikes records in database ===")
    sql = """
        SELECT record_id, variable_name, version_keys, branch_params
        FROM _record_metadata
        WHERE variable_name = 'Spikes'
        ORDER BY record_id
    """
    rows = db._duck._fetchall(sql)

    print(f"Found {len(rows)} Spikes records")
    for i, (rid, _vname, vk_json, bp_json) in enumerate(rows):
        vk = json.loads(vk_json)
        bp = json.loads(bp_json)

        # Strip __upstream for comparison
        vk_stripped = {k: v for k, v in vk.items() if k != "__upstream"}

        print(f"\nRecord {i + 1}: {rid[:12]}")
        print(f"  __upstream: {vk.get('__upstream', {})}")
        print(f"  branch_params: {bp}")
        print(
            f"  version_keys (stripped): {json.dumps(vk_stripped, sort_keys=True, indent=2)}"
        )

    # Check list_pipeline_variants
    print("\n=== list_pipeline_variants output ===")
    variants = db.list_pipeline_variants(output_type="Spikes")
    print(f"Found {len(variants)} Spikes variant(s)")
    for v in variants:
        print(f"  {v}")

    db.close()
