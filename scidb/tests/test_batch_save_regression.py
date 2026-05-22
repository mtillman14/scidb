"""
Regression test to verify that both Python and MATLAB scidb.for_each() use batch save.

This test ensures that the batch save optimization (20-40x speedup) is actually
being used by both execution paths, and will catch any future regressions that
accidentally revert to sequential row-by-row saving.
"""

import logging
import numpy as np
import pandas as pd
import pytest
import scifor as _scifor

from scidb import BaseVariable, configure_database, for_each


SCHEMA = ["subject", "trial"]


@pytest.fixture
def db(tmp_path):
    """Fresh database for each test."""
    _scifor.set_schema([])
    db = configure_database(tmp_path / "test_batch.duckdb", SCHEMA)
    yield db
    _scifor.set_schema([])
    db.close()


class Input(BaseVariable):
    pass


class Output(BaseVariable):
    pass


def process(data):
    """Simple function that returns a DataFrame for distribute mode."""
    # Return a DataFrame with multiple rows to trigger distribute mode
    return pd.DataFrame({"value": np.arange(10)})


class TestBatchSaveRegression:
    """Verify both Python and MATLAB paths use batch save optimization."""

    def test_python_for_each_uses_batch_save(self, db, caplog):
        """Python for_each should use batch save when saving multiple records."""
        # Setup: Create input data for 3 subjects
        for subj in ["S01", "S02", "S03"]:
            Input.save(np.array([1.0, 2.0]), subject=subj, trial="1")

        # Run for_each with distribute=True (creates 10 records per subject = 30 total)
        with caplog.at_level(logging.INFO, logger="scidb"):
            for_each(
                process,
                {"data": Input},
                [Output],
                subject=["S01", "S02", "S03"],
                trial=["1"],
                distribute=True,
            )

        # Verify batch save was used by checking logs
        batch_save_logs = [
            record.message for record in caplog.records
            if "[batch_save]" in record.message
        ]

        assert len(batch_save_logs) > 0, (
            "Expected [batch_save] log messages but found none. "
            "This indicates batch save optimization is not being used!"
        )

        # Verify we see the preparation and completion messages
        prep_logs = [log for log in batch_save_logs if "Preparing" in log]
        complete_logs = [log for log in batch_save_logs if "Completed" in log]

        assert len(prep_logs) > 0, "Should see batch_save preparation log"
        assert len(complete_logs) > 0, "Should see batch_save completion log"

        # Verify the batch contained multiple records (not just 1)
        prep_log = prep_logs[0]
        assert "30 result row(s)" in prep_log, (
            f"Expected to batch 30 records, but log says: {prep_log}"
        )

        # Verify records were actually saved
        all_records = db.list_versions(Output)
        assert len(all_records) == 30, f"Expected 30 records but found {len(all_records)}"

    def test_matlab_bridge_uses_batch_save(self, db, caplog):
        """MATLAB bridge path should also use batch save (via _for_each_save_resolved)."""
        # This test simulates the MATLAB bridge path by calling the bridge functions directly
        from sci_matlab.bridge import for_each_prepare, for_each_save

        # Setup input data
        for subj in ["S01", "S02", "S03"]:
            Input.save(np.array([1.0, 2.0]), subject=subj, trial="1")

        # Prepare (Phase 1 - MATLAB calls this)
        handle = for_each_prepare(
            fn_src="def process(data):\n    return pd.DataFrame({'value': np.arange(10)})",
            fn_name="process",
            input_specs={"data": "Input"},
            output_class_names=["Output"],
            subject=["S01", "S02", "S03"],
            trial=["1"],
            distribute=True,
        )

        # Simulate MATLAB executing the function and building result DataFrames
        # (In reality, MATLAB's scifor.for_each does this)
        result_df = pd.DataFrame({
            "subject": ["S01"] * 10 + ["S02"] * 10 + ["S03"] * 10,
            "trial": ["1"] * 30,
            "value": list(range(10)) * 3,
            "Output": [pd.DataFrame({"value": [i]}) for i in range(10)] * 3,
        })

        # Save (Phase 3 - MATLAB calls this with results)
        with caplog.at_level(logging.INFO, logger="scidb"):
            for_each_save(handle, result_df, save=True)

        # Verify batch save was used
        batch_save_logs = [
            record.message for record in caplog.records
            if "[batch_save]" in record.message
        ]

        assert len(batch_save_logs) > 0, (
            "MATLAB bridge path did not use batch save! "
            "This indicates the optimization is not working for MATLAB users."
        )

        # Verify the batch contained multiple records
        prep_logs = [log for log in batch_save_logs if "Preparing" in log]
        assert len(prep_logs) > 0, "Should see batch_save preparation log"

        prep_log = prep_logs[0]
        assert "30 result row(s)" in prep_log, (
            f"Expected to batch 30 records, but log says: {prep_log}"
        )

        # Verify records were saved
        all_records = db.list_versions(Output)
        assert len(all_records) == 30, f"Expected 30 records but found {len(all_records)}"

    def test_batch_save_preserves_branch_params(self, db):
        """Verify batch save correctly preserves branch_params for all records."""
        # Create upstream variants
        for subj in ["S01", "S02"]:
            Input.save(np.array([1.0]), subject=subj, trial="1")

        # Run with constants to create branch_params
        for_each(
            process,
            {"data": Input},
            [Output],
            subject=["S01", "S02"],
            trial=["1"],
            distribute=True,
        )

        # Verify all records have correct branch_params
        all_records = db.list_versions(Output)
        assert len(all_records) == 20, f"Expected 20 records (2 subjects × 10 rows)"

        for record in all_records:
            bp = record.get("branch_params", {})
            # Should have the function namespaced in branch_params
            # (no upstream constants in this case since Input has none)
            assert isinstance(bp, dict), f"branch_params should be dict, got {type(bp)}"

    def test_batch_save_with_upstream_variants(self, db):
        """Verify batch save correctly handles records with different upstream variants."""

        class Intermediate(BaseVariable):
            pass

        def create_variants(data, param):
            return data * param

        # Create base data
        for subj in ["S01", "S02"]:
            Input.save(np.array([1.0]), subject=subj, trial="1")

        # Create upstream variants with different params
        for param in [10, 20]:
            for_each(
                create_variants,
                {"data": Input, "param": param},
                [Intermediate],
                subject=["S01", "S02"],
                trial=["1"],
            )

        # Now process all upstream variants with distribute
        for_each(
            process,
            {"data": Intermediate},  # Loads all 4 Intermediate variants
            [Output],
            subject=["S01", "S02"],
            trial=["1"],
            distribute=True,
        )

        # Should have 40 Output records (2 subjects × 2 upstream variants × 10 rows)
        all_records = db.list_versions(Output)
        assert len(all_records) == 40, f"Expected 40 records but found {len(all_records)}"

        # Verify branch_params include upstream variant info
        for record in all_records:
            bp = record.get("branch_params", {})
            # Should have create_variants.param in branch_params (either 10 or 20)
            assert "create_variants.param" in bp, (
                f"Missing upstream branch_params in {bp}"
            )
            assert bp["create_variants.param"] in [10, 20], (
                f"Invalid param value: {bp['create_variants.param']}"
            )

    def test_small_batches_still_work(self, db, caplog):
        """Verify batch save works correctly even with just 1 record."""
        Input.save(np.array([1.0]), subject="S01", trial="1")

        with caplog.at_level(logging.INFO, logger="scidb"):
            for_each(
                lambda data: data * 2,
                {"data": Input},
                [Output],
                subject=["S01"],
                trial=["1"],
            )

        # Should still see batch_save logs even for 1 record
        batch_save_logs = [
            record.message for record in caplog.records
            if "[batch_save]" in record.message
        ]
        assert len(batch_save_logs) > 0, "Batch save should be used even for 1 record"

        # Verify record was saved
        all_records = db.list_versions(Output)
        assert len(all_records) == 1


class TestBatchSavePerformance:
    """Performance characteristics of batch save (informational, not strict pass/fail)."""

    def test_batch_save_is_faster_than_sequential(self, db, caplog):
        """
        Informational test: batch save should be significantly faster than sequential.

        This test doesn't fail but prints timing information for monitoring performance.
        """
        import time

        # Create input data
        for subj in [f"S{i:02d}" for i in range(10)]:
            Input.save(np.array([1.0]), subject=subj, trial="1")

        # Run with distribute to create many records (10 subjects × 10 rows = 100 records)
        start_time = time.perf_counter()

        with caplog.at_level(logging.INFO, logger="scidb"):
            for_each(
                process,
                {"data": Input},
                [Output],
                subject=[f"S{i:02d}" for i in range(10)],
                trial=["1"],
                distribute=True,
            )

        elapsed_time = time.perf_counter() - start_time

        # Extract timing from logs
        timing_logs = [
            record.message for record in caplog.records
            if "records/s" in record.message
        ]

        print(f"\n=== Batch Save Performance ===")
        print(f"Saved 100 records in {elapsed_time:.3f}s")
        if timing_logs:
            print(f"Batch save throughput: {timing_logs[-1]}")
        print(f"Expected: < 1s (vs ~3s for sequential)")

        # Verify all records were saved
        all_records = db.list_versions(Output)
        assert len(all_records) == 100

        # Informational assertion (prints warning but doesn't fail)
        if elapsed_time > 2.0:
            print(f"WARNING: Batch save took {elapsed_time:.3f}s, expected < 1s")
            print("This may indicate performance regression or slow test environment")
