"""
GUI test data generator — VO2 max pipeline adapted for for_each.

Seeds test_gui.duckdb with raw data for 3 subjects (RawVO2,
RawHeartRate) and registers the pipeline functions below, but runs
NOTHING — a fresh pipeline starts with an empty canvas, and the user
places/wires/runs each step themselves in the GUI (including running
compute_rolling_vo2 twice, with window_seconds=30 and 60, to get the
two-variant branch this demo is built around).

Safe to import by scistack-gui --module: all execution is guarded
by if __name__ == "__main__".

Run from the workspace root:
    python gui_test_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

from scidb import BaseVariable, configure_database

# from scilineage.src.scilineage import lineage_fcn

# ------------------------------------------------------------------
# Variable types — defined at module level so scistack-gui can import
# them and register them with the DB.
# ------------------------------------------------------------------


class RawVO2(BaseVariable):
    """Raw VO2 signal (mL/min) — one array per subject."""

    pass


class RollingVO2(BaseVariable):
    """Rolling average VO2. Varies by window_seconds (pipeline variant)."""

    pass


class MaxVO2(BaseVariable):
    """VO2 max scalar — mean of the two highest rolling averages."""

    pass


class MaxHeartRate(BaseVariable):
    """Peak heart rate. Demonstrates a second parallel branch."""

    pass


class VO2Summary(BaseVariable):
    """Cohort-level stat summary of MaxVO2 (stat_ endpoint output)."""

    pass


class RawHeartRate(BaseVariable):
    """Raw heart rate signal (bpm)."""

    pass


# ------------------------------------------------------------------
# Processing functions — plain functions, no decorator needed.
# Defined at module level so scistack-gui can find them by name.
# ------------------------------------------------------------------


def compute_rolling_vo2(signal, window_seconds, sample_interval):
    """Rolling average of VO2 over a time window."""
    window_size = window_seconds // sample_interval
    return pd.Series(signal).rolling(window=window_size, min_periods=1).mean().values


def compute_max_vo2(rolling_vo2):
    """VO2 max: mean of the two highest rolling averages."""
    sorted_vals = np.sort(rolling_vo2)[::-1]
    return float(np.mean(sorted_vals[:2]))


def compute_max_hr(signal):
    """Peak heart rate."""
    return float(np.max(signal))


def compute_80_perc_max_hr(max_hr):
    """Max HR * 0.8"""
    return max_hr * 0.8


def compute_50_perc_max_hr(max_hr):
    """Max HR * 0.5"""
    return max_hr * 0.5


# @lineage_fcn
def compute_perc_max_hr(max_hr: int, perc: float):
    """Max HR * perc"""
    return max_hr * perc


def stat_vo2_summary(max_vo2):
    """Cohort summary of MaxVO2 — a stat_ ENDPOINT (endpoint-first GUI
    demo). stat_ functions pool their input rows (as_table default), so
    this receives a DataFrame across the iterated combos."""
    if isinstance(max_vo2, pd.DataFrame):
        vals = np.ravel([np.ravel(v) for v in max_vo2["MaxVO2"]])
    else:
        vals = np.ravel(max_vo2)
    return {
        "mean_max_vo2": float(np.mean(vals)),
        "best_max_vo2": float(np.max(vals)),
        "n_subjects": int(vals.size),
    }


# ------------------------------------------------------------------
# Data seeding — only runs when executed directly, not on import.
# ------------------------------------------------------------------

if __name__ == "__main__":
    db_path = Path("test_gui.duckdb")

    # Remove previous run so we start fresh — this must also clear the
    # layout file (test_gui.layout.json), not just the .duckdb: node
    # positions/manual-node scope assignments there are keyed by ids that
    # can reference stale wiring hashes, call sites, or scopes from a
    # prior schema/pipeline shape. Leaving it around after regenerating
    # the DB is exactly the kind of staleness that produces corrupted-
    # looking canvases (disappearing nodes, edges to nowhere).
    for f in Path(".").glob("test_gui.duckdb*"):
        f.unlink()
    layout_file = Path("test_gui.layout.json")
    if layout_file.exists():
        layout_file.unlink()

    db = configure_database(db_path, ["subject"])
    print(f"Database: {db_path}")
    print(f"Schema keys: {db.dataset_schema_keys}\n")

    subjects = ["S01", "S02", "S03"]

    rng = np.random.default_rng(42)

    print("Seeding raw data...")
    for subject in subjects:
        n = 120  # 120 samples = 10 minutes at 5-second intervals

        ramp = np.linspace(2000, 4200, n)
        noise = rng.normal(0, 150, n)
        vo2 = np.clip(ramp + noise, 1000, 5000)

        hr_ramp = np.linspace(80, 185, n)
        hr_noise = rng.normal(0, 5, n)
        hr = np.clip(hr_ramp + hr_noise, 60, 210)

        RawVO2.save(vo2, subject=subject)
        RawHeartRate.save(hr, subject=subject)
        print(
            f"  {subject}: VO2 [{vo2.min():.0f}, {vo2.max():.0f}], "
            f"HR [{hr.min():.0f}, {hr.max():.0f}]"
        )

    print()

    # Deliberately NOT pre-run: a real new pipeline starts with raw data
    # seeded and its functions registered (import of this module registers
    # them), but with an empty canvas — the user drags each function on,
    # wires it, and clicks Run themselves. Pre-executing here would mean
    # the GUI never actually exercises node placement/wiring/run for this
    # demo, and it's exactly the "click Run in the GUI" path the placement-
    # qualified-id and duplicate-pipeline work needs exercised by hand.
    print("Raw data seeded. Nothing has been run yet — build the pipeline")
    print("interactively in the GUI:")
    print("  1. compute_rolling_vo2(signal=RawVO2, window_seconds, sample_interval) -> RollingVO2")
    print("     (run it twice with window_seconds=30 and 60 to get two variants)")
    print("  2. compute_max_vo2(rolling_vo2=RollingVO2) -> MaxVO2")
    print("  3. compute_max_hr(signal=RawHeartRate) -> MaxHeartRate")
    print("  4. compute_80_perc_max_hr / compute_50_perc_max_hr / compute_perc_max_hr(max_hr, perc)")
    print("  5. stat_vo2_summary(max_vo2=MaxVO2) -> cohort summary")
    print("\nOpen with: scistack-gui --module gui_test_data.py test_gui.duckdb")
    db.close()


class MaxHR_80Perc(BaseVariable):
    pass


class MaxHR_50Perc(BaseVariable):
    pass


class MaxHR_Perc(BaseVariable):
    pass

class RollingHR(BaseVariable):
    pass
