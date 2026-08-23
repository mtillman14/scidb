"""
Generate synthetic breath-by-breath CPET (cardiopulmonary exercise test) data.

Simulates one CSV per subject/session, where each row is a single breath:
  - "time (sec)": cumulative time of the breath, strictly increasing but
    irregularly spaced (breathing is not metronomic), spanning 0-600 sec.
  - "vo2 (kg/mL/min)": oxygen uptake for that breath. Trends upward over
    the test (ramp protocol) but is noisy breath-to-breath, so any given
    breath is not guaranteed to be higher than the previous one.

Subjects/sessions (breath count differs per file since each session has a
different, randomly varying breathing rate):
  - SS01: two sessions (SS01_01_CPET.csv, SS01_02_CPET.csv)
  - SS02: one session  (SS02_01_CPET.csv)
  - SS03: one session  (SS03_01_CPET.csv)

Usage:
    python generate_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

TEST_DURATION_SEC = 600.0

# (subject, session) -> unique seed
SESSIONS = [
    ("SS01", "01", 101),
    ("SS01", "02", 102),
    ("SS02", "01", 201),
    ("SS03", "01", 301),
]


def generate_session(seed: int) -> pd.DataFrame:
    """Generate one breath-by-breath CPET session."""
    rng = np.random.default_rng(seed)

    # Irregular breath-to-breath intervals (breathing rate rises with
    # exercise intensity, so mean interval shortens over the test).
    mean_interval_start = rng.uniform(2.2, 3.2)  # sec/breath at rest
    mean_interval_end = rng.uniform(0.8, 1.4)  # sec/breath near peak effort

    times = [0.0]
    while times[-1] < TEST_DURATION_SEC:
        frac = times[-1] / TEST_DURATION_SEC
        mean_interval = mean_interval_start + (mean_interval_end - mean_interval_start) * frac
        interval = rng.gamma(shape=4.0, scale=mean_interval / 4.0)
        times.append(times[-1] + interval)
    times = np.array(times[:-1])  # drop the point that overshot 600 sec
    n = len(times)
    t_norm = times / TEST_DURATION_SEC

    # VO2 ramp: resting ~5 mL/kg/min rising to a peak between 35-55 mL/kg/min,
    # plus breath-to-breath noise so the trend is upward but not monotonic.
    vo2_peak = rng.uniform(35, 55)
    vo2_rest = rng.uniform(4, 7)
    vo2_base = vo2_rest + (vo2_peak - vo2_rest) * t_norm**1.3
    vo2_noise = rng.normal(0, 1, n) * (0.12 * vo2_base)
    vo2 = np.round(np.clip(vo2_base + vo2_noise, 0, None), 2)

    return pd.DataFrame({"time (sec)": np.round(times, 2), "vo2 (kg/mL/min)": vo2})


if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parent.parent / "data"

    for subject, session, seed in SESSIONS:
        subject_dir = data_dir / subject
        subject_dir.mkdir(parents=True, exist_ok=True)

        df = generate_session(seed)
        out_path = subject_dir / f"{subject}_{session}_CPET.csv"
        df.to_csv(out_path, index=False)

        print(
            f"{out_path.relative_to(data_dir.parent)}: {len(df)} breaths, "
            f"time {df['time (sec)'].iloc[0]:.1f}-{df['time (sec)'].iloc[-1]:.1f} sec, "
            f"vo2 {df['vo2 (kg/mL/min)'].min():.1f}-{df['vo2 (kg/mL/min)'].max():.1f}"
        )
