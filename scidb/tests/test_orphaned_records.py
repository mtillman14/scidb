"""
Regression tests for orphaned records in _record_metadata.

An orphaned record exists in _record_metadata but has no corresponding row in the
variable's data table.  This can happen when a previous save used an unexpected
schema key (e.g. a prior for_each run with distribute=True saved an output with
schema keys the user didn't intend), or when a save partially failed.

Two symptoms:
  1. load_all_as_df (spread layout) returns rows with NaN data for orphaned records.
  2. Orphaned records that have a non-null schema key value (e.g. distribute=1) prevent
     that column from being identified as all-null, so it is not dropped before being
     sent to MATLAB — causing a spurious column in the Merge constituent table.

Fix: use INNER JOIN instead of LEFT JOIN when assembling the spread DataFrame from
(meta_df, data_df), so orphaned records are excluded rather than NaN-filled.
"""

import json
import pytest

from scidb import BaseVariable, configure_database

SCHEMA = ["subject", "session", "distribute"]


@pytest.fixture
def db(tmp_path):
    db = configure_database(tmp_path / "test.duckdb", SCHEMA)
    yield db
    db.close()


class Grouping(BaseVariable):
    pass


def _inject_orphan(db, type_name, subject, distribute=None):
    """Directly insert a _record_metadata row with no matching data row.

    This simulates a record that was written to _record_metadata (e.g. by a buggy
    prior for_each run) but whose data row was never written to {type_name}_data.
    """
    # Ensure the variable is registered
    duck = db._duck

    # Get or create a schema_id for the given schema values
    schema_vals = {"subject": str(subject) if subject is not None else None}
    if distribute is not None:
        schema_vals["distribute"] = str(distribute)
    else:
        schema_vals["distribute"] = None
    schema_vals["session"] = None

    # Build the schema INSERT
    col_names = ", ".join(f'"{k}"' for k in SCHEMA)
    col_placeholders = ", ".join(["?"] * len(SCHEMA))
    schema_values = [schema_vals.get(k) for k in SCHEMA]
    duck.con.execute(
        f"INSERT OR IGNORE INTO _schema ({col_names}) VALUES ({col_placeholders})",
        schema_values,
    )
    schema_id_row = duck.con.execute(
        f"SELECT schema_id FROM _schema WHERE "
        + " AND ".join(
            f'"{k}" IS ?' if v is None else f'"{k}" = ?'
            for k, v in zip(SCHEMA, schema_values)
        ),
        schema_values,
    ).fetchone()
    schema_id = schema_id_row[0]

    # Insert a phantom record_metadata row (no corresponding data row)
    import hashlib, time
    phantom_rid = "phantom" + hashlib.md5(
        f"{type_name}{subject}{distribute}{time.time()}".encode()
    ).hexdigest()[:10]
    duck.con.execute(
        "INSERT INTO _record_metadata "
        "(record_id, variable_name, schema_id, version_keys, content_hash, branch_params, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        [phantom_rid, type_name, schema_id, "{}", "deadbeef" * 2, "{}"],
    )
    return phantom_rid


class TestOrphanedRecordsExcluded:
    def test_no_nan_rows_from_orphaned_record(self, db):
        """Orphaned record in _record_metadata must not appear as NaN row in spread load."""
        Grouping.save("SHAM", subject=1, session="A")
        Grouping.save("STIM", subject=2, session="A")

        _inject_orphan(db, "Grouping", subject=None, distribute=None)

        result = db.load_all_as_df(Grouping, layout="spread", stringify_schema=True)

        # Should have exactly the 2 real records — not 3
        assert len(result) == 2, f"Expected 2 rows, got {len(result)}: {result}"

        # Data column must not contain NaN
        assert result["Grouping"].notna().all(), \
            f"NaN data values found:\n{result}"

    def test_distribute_column_dropped_when_only_orphan_has_it(self, db):
        """A schema key that is non-null only in an orphaned record must be treated as
        all-null after the orphan is excluded, so the Python Merge fix can drop it."""
        Grouping.save("SHAM", subject=1, session="A")
        Grouping.save("STIM", subject=2, session="A")

        # Inject orphan with distribute=1 (simulates prior buggy for_each output)
        _inject_orphan(db, "Grouping", subject=None, distribute=1)

        result = db.load_all_as_df(Grouping, layout="spread", stringify_schema=True)

        # distribute must be all-null in the 2 valid rows (none were saved with distribute)
        assert len(result) == 2
        assert result["distribute"].isna().all(), \
            f"distribute column has unexpected non-null values:\n{result['distribute']}"

    def test_valid_records_unaffected(self, db):
        """INNER JOIN must not drop valid records that have data."""
        Grouping.save("SHAM",   subject=1, session="A")
        Grouping.save("STIM",   subject=2, session="A")
        Grouping.save("ONWARD", subject=3, session="A")

        result = db.load_all_as_df(Grouping, layout="spread", stringify_schema=True)

        assert len(result) == 3
        assert set(result["Grouping"].tolist()) == {"SHAM", "STIM", "ONWARD"}
