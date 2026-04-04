"""
VO2 Max Test Pipeline
=====================

Demonstrates a complete data processing pipeline using the SciStack framework.
Loads raw physiological data from a simulated VO2 max test, combines the
signals, computes rolling averages, and extracts peak metrics.

Framework features showcased:
  - BaseVariable: Type-safe data storage with automatic and custom serialization
  - configure_database: DuckDB (data) + SQLite (lineage) dual-backend setup
  - for_each: Run a function over all schema combinations, tracking variants
  - Provenance queries: Listing pipeline variants and upstream lineage

Usage:
    cd examples/vo2max
    python generate_data.py   # Create dummy CSV files
    python pipeline.py        # Run the pipeline
"""

import numpy as np
import pandas as pd
from pathlib import Path

# =============================================================================
# SCIDB IMPORTS
#
# All core framework components come from the `scidb` package:
#   - BaseVariable: Base class for defining storable data types
#   - configure_database: One-call setup for DuckDB + SQLite backends
#   - for_each: Run a function for every combination of schema values,
#               loading inputs automatically and saving outputs automatically.
#               Constants passed in `inputs` are tracked as pipeline variants
#               so the GUI can show them as ConstantNodes.
# =============================================================================

from scidb import BaseVariable, configure_database, for_each


# =============================================================================
# STEP 1: DEFINE VARIABLE TYPES  [scidb.BaseVariable]
#
# Each variable type maps to a table in the DuckDB database. Subclassing
# BaseVariable automatically registers the type in a global registry, so
# configure_database() can discover and register all types at startup.
#
# Types that store simple data (scalars, numpy arrays, lists) need NO custom
# serialization — SciDuck handles them natively via DuckDB's type system.
#
# Types that store DataFrames or other complex objects should override
# to_db() and from_db() to control how data is serialized to/from rows.
# =============================================================================

class RawTime(BaseVariable):
    """Raw time data (seconds) loaded from CSV.

    Uses native SciDuck storage — no to_db()/from_db() needed for numpy arrays.
    """
    pass


class RawHeartRate(BaseVariable):
    """Raw heart rate data (bpm) loaded from CSV. Native storage."""
    pass


class RawVO2(BaseVariable):
    """Raw VO2 data (mL/min) loaded from CSV. Native storage."""
    pass


class CombinedData(BaseVariable):
    """
    Combined time series with time, HR, and VO2 columns.

    Overrides to_db()/from_db() because the data is a pandas DataFrame
    and we want to preserve the multi-column structure in storage.
    """

    def to_db(self) -> pd.DataFrame:
        # Return the DataFrame directly — each column becomes a DuckDB column
        return self.data

    @classmethod
    def from_db(cls, df: pd.DataFrame) -> pd.DataFrame:
        # Reconstruct the DataFrame from stored columns
        return df


class RollingVO2(BaseVariable):
    """30-second rolling average of VO2. Native storage (numpy array)."""
    pass


class MaxHeartRate(BaseVariable):
    """Peak heart rate during the test. Native storage (scalar)."""
    pass


class MaxVO2(BaseVariable):
    """
    VO2 max: mean of the two highest 30-second rolling VO2 averages.
    Native storage (scalar).
    """
    pass


# =============================================================================
# STEP 2: DEFINE PROCESSING FUNCTIONS
#
# Plain functions (no decorator needed). for_each handles:
#   1. Iterating over all schema combinations (e.g. subject="S01")
#   2. Loading input variables and passing their .data to the function
#   3. Passing constants straight through to the function
#   4. Saving the return value as the output variable type
#   5. Recording version_keys (inputs + constants) in _record_metadata for
#      provenance and GUI pipeline-graph construction
#
# Because for_each auto-unwraps BaseVariable inputs, these functions receive
# plain numpy arrays / DataFrames — no framework types in the math.
# =============================================================================

def load_time(data_dir: str) -> np.ndarray:
    """
    Load time data from a CSV file in data_dir.

    data_dir is a constant — the GUI renders it as a ConstantNode that feeds
    into this function node, making it clear where the raw data comes from.
    """
    df = pd.read_csv(Path(data_dir) / "time_sec.csv")
    return df.iloc[:, 0].values


def load_heart_rate(data_dir: str) -> np.ndarray:
    """Load heart rate data from a CSV file in data_dir."""
    df = pd.read_csv(Path(data_dir) / "heart_rate_bpm.csv")
    return df.iloc[:, 0].values


def load_vo2(data_dir: str) -> np.ndarray:
    """Load VO2 data from a CSV file in data_dir."""
    df = pd.read_csv(Path(data_dir) / "vo2_ml_min.csv")
    return df.iloc[:, 0].values


def combine_signals(
    time: np.ndarray,
    hr: np.ndarray,
    vo2: np.ndarray,
) -> pd.DataFrame:
    """
    Combine three 1D arrays into a single DataFrame.

    for_each loads RawTime, RawHeartRate, and RawVO2 for each subject,
    joins them by schema key, and passes their data here as plain arrays.
    """
    return pd.DataFrame({
        "time_sec": time,
        "heart_rate_bpm": hr,
        "vo2_ml_min": vo2,
    })


def compute_rolling_vo2(
    combined: pd.DataFrame,
    window_seconds: int = 30,
    sample_interval: int = 5,
) -> np.ndarray:
    """
    Compute a rolling average of VO2 over a specified time window.

    window_seconds and sample_interval are constants — the GUI renders them
    as ConstantNodes feeding into this function node.  Changing them creates
    a new pipeline variant, tracked separately in _record_metadata.
    """
    window_size = window_seconds // sample_interval  # 30s / 5s = 6 samples
    rolling_avg = (
        pd.Series(combined["vo2_ml_min"])
        .rolling(window=window_size, min_periods=1)
        .mean()
    )
    return rolling_avg.values


def compute_max_hr(combined: pd.DataFrame) -> float:
    """Extract the peak heart rate from the combined dataset."""
    return float(combined["heart_rate_bpm"].max())


def compute_max_vo2(rolling_vo2: np.ndarray) -> float:
    """
    Compute VO2 max as the mean of the two highest 30-second rolling averages.

    This is a standard definition in exercise physiology: VO2max is reported
    as the average of the two highest consecutive 30-second averages to reduce
    the impact of breath-by-breath noise.
    """
    sorted_vals = np.sort(rolling_vo2)[::-1]  # Descending
    return float(np.mean(sorted_vals[:2]))


# =============================================================================
# STEP 3: CONFIGURE DATABASE AND RUN PIPELINE
# =============================================================================

if __name__ == "__main__":

    # -------------------------------------------------------------------------
    # 3a. Configure the database  [scidb.configure_database]
    #
    # configure_database() sets up two storage backends in a single call:
    #   - DuckDB file: stores all variable data (via SciDuck backend)
    #   - SQLite file: stores lineage/provenance records (via PipelineDB)
    #
    # dataset_schema_keys defines which metadata keys represent the "location"
    # of data. Here, "subject" identifies which person's test this is.
    #
    # This call also auto-registers all BaseVariable subclasses defined above.
    # -------------------------------------------------------------------------

    project_folder = Path(__file__).parent

    data_dir = project_folder / "data"
    db_dir = project_folder

    data_filename = "vo2max_data.duckdb"

    # Clean up previous runs for a fresh demo
    for f in db_dir.glob(f"{data_filename}*"):
        f.unlink()

    db = configure_database(
        dataset_db_path=db_dir / data_filename,
        dataset_schema_keys=["subject"],
    )

    print("Database configured.")
    print(f"  Data storage (DuckDB): {db_dir / data_filename}")
    print(f"  Schema keys: {db.dataset_schema_keys}")
    print()

    # -------------------------------------------------------------------------
    # 3b. Load raw data from CSVs  [for_each with constant data_dir]
    #
    # Each loading function takes data_dir as a constant — the path to the
    # CSV files.  for_each records data_dir in _record_metadata so the GUI
    # shows:  ConstantNode(data_dir) → FunctionNode(load_vo2) → VariableNode(RawVO2)
    #
    # Without this step, RawVO2 would be a root VariableNode in the GUI with
    # no upstream, which doesn't represent a real pipeline.
    # -------------------------------------------------------------------------

    print("--- Loading raw data from CSVs ---")

    data_dir_str = str(data_dir)

    for_each(
        load_time,
        inputs={"data_dir": data_dir_str},
        outputs=[RawTime],
        subject=["S01"],
    )
    for_each(
        load_heart_rate,
        inputs={"data_dir": data_dir_str},
        outputs=[RawHeartRate],
        subject=["S01"],
    )
    for_each(
        load_vo2,
        inputs={"data_dir": data_dir_str},
        outputs=[RawVO2],
        subject=["S01"],
    )

    print("  Saved raw data for subject S01.")
    print()

    # -------------------------------------------------------------------------
    # 3c. Combine signals  [for_each with multiple variable inputs]
    #
    # for_each loads RawTime, RawHeartRate, and RawVO2 for each subject,
    # joins them by the "subject" schema key, and passes their data as plain
    # arrays to combine_signals().
    # -------------------------------------------------------------------------

    print("--- Combining signals ---")

    for_each(
        combine_signals,
        inputs={"time": RawTime, "hr": RawHeartRate, "vo2": RawVO2},
        outputs=[CombinedData],
        subject=["S01"],
    )

    loaded_combined = CombinedData.load(subject="S01")
    print(f"  Combined shape: {loaded_combined.data.shape}")
    print(f"  Columns: {list(loaded_combined.data.columns)}")
    print("  Saved combined data.")
    print()

    # -------------------------------------------------------------------------
    # 3d. Compute rolling VO2 averages  [for_each with constants]
    #
    # window_seconds=30 and sample_interval=5 are constants — the GUI renders
    # them as ConstantNodes.  Running again with different values (e.g.
    # window_seconds=60) would create a new pipeline variant, tracked
    # separately in _record_metadata.
    # -------------------------------------------------------------------------

    print("--- Computing 30-second rolling VO2 averages ---")

    for_each(
        compute_rolling_vo2,
        inputs={"combined": CombinedData, "window_seconds": 30, "sample_interval": 5},
        outputs=[RollingVO2],
        subject=["S01"],
    )

    loaded_rolling = RollingVO2.load(subject="S01")
    print(f"  Rolling VO2 shape: {loaded_rolling.data.shape}")
    print(f"  Rolling VO2 range: [{loaded_rolling.data.min():.0f}, {loaded_rolling.data.max():.0f}] mL/min")
    print("  Saved rolling VO2 averages.")
    print()

    # -------------------------------------------------------------------------
    # 3e. Compute peak metrics  [for_each with scalar results]
    #
    # Scalar results (float, int) are stored natively by SciDuck — no need
    # for custom to_db()/from_db() overrides on MaxHeartRate or MaxVO2.
    # -------------------------------------------------------------------------

    print("--- Computing peak metrics ---")

    for_each(
        compute_max_hr,
        inputs={"combined": CombinedData},
        outputs=[MaxHeartRate],
        subject=["S01"],
    )
    for_each(
        compute_max_vo2,
        inputs={"rolling_vo2": RollingVO2},
        outputs=[MaxVO2],
        subject=["S01"],
    )

    loaded_max_hr = MaxHeartRate.load(subject="S01")
    loaded_max_vo2 = MaxVO2.load(subject="S01")
    print(f"  Max HR:  {loaded_max_hr.data:.0f} bpm")
    print(f"  Max VO2: {loaded_max_vo2.data:.1f} mL/min")
    print("  Saved peak metrics.")
    print()

    # -------------------------------------------------------------------------
    # 3f. Verify: Load data back  [BaseVariable.load]
    #
    # load() queries by metadata and returns the latest matching record.
    # -------------------------------------------------------------------------

    print("--- Verifying saved data ---")

    loaded_max_vo2 = MaxVO2.load(subject="S01")
    loaded_max_hr = MaxHeartRate.load(subject="S01")
    loaded_combined = CombinedData.load(subject="S01")

    print(f"  Loaded Max VO2:  {loaded_max_vo2.data:.1f} mL/min  (record: {loaded_max_vo2.record_id[:16]}...)")
    print(f"  Loaded Max HR:   {loaded_max_hr.data:.0f} bpm  (record: {loaded_max_hr.record_id[:16]}...)")
    print(f"  Loaded combined: {loaded_combined.data.shape}  (record: {loaded_combined.record_id[:16]}...)")
    print()

    # -------------------------------------------------------------------------
    # 3g. Query pipeline variants  [DatabaseManager.list_pipeline_variants]
    #
    # list_pipeline_variants() reads from _record_metadata to show all
    # function/input/constant combinations that were run.  This is the same
    # data the GUI uses to construct the pipeline graph.
    # -------------------------------------------------------------------------

    print("--- Pipeline variants ---")

    variants = db.list_pipeline_variants()
    for v in variants:
        fn = v["function_name"]
        out = v["output_type"]
        inputs_str = ", ".join(f"{k}={val}" for k, val in v["input_types"].items())
        consts_str = ", ".join(f"{k}={val}" for k, val in v["constants"].items())
        all_params = ", ".join(filter(None, [inputs_str, consts_str]))
        print(f"  {fn}({all_params}) → {out}  [{v['record_count']} record(s)]")
    print()

    # -------------------------------------------------------------------------
    # 3h. List all saved versions  [BaseVariable.list_versions]
    # -------------------------------------------------------------------------

    print("--- Saved versions ---")
    for var_type in [RawTime, RawHeartRate, RawVO2, CombinedData,
                     RollingVO2, MaxHeartRate, MaxVO2]:
        versions = var_type.list_versions(subject="S01")
        print(f"  {var_type.__name__}: {len(versions)} version(s)")

    print()
    print("Pipeline complete!")
    print(f"  Data stored in:    {db_dir / 'vo2max_data.duckdb'}")
    print(f"  Lineage stored in: {db_dir / 'vo2max_lineage.db'}")
    print()
    print("To explore in the GUI:")
    print(f"  scistack-gui {db_dir / 'vo2max_data.duckdb'} --module {Path(__file__)}")

    db.close()
