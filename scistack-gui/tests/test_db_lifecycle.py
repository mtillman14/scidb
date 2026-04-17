"""
Tests for the DuckDB connection lifecycle — verifies that the Python
process releases the file lock between requests so MATLAB can access
the same database.
"""
import duckdb
import pytest


@pytest.fixture
def db_path(tmp_path):
    """Create a minimal SciStack database for lifecycle tests."""
    p = tmp_path / "test.duckdb"
    con = duckdb.connect(str(p))
    con.execute("CREATE TABLE _schema (schema_id INTEGER, subject INTEGER)")
    con.execute("INSERT INTO _schema VALUES (1, 1)")
    con.close()
    return p


@pytest.fixture(autouse=True)
def _reset_db_module():
    """Reset db.py module-level state between tests."""
    from scistack_gui import db as db_mod

    old_db = db_mod._db
    old_path = db_mod._db_path
    old_open = db_mod._db_open
    old_ref = db_mod._db_refcount
    yield
    db_mod._db = old_db
    db_mod._db_path = old_path
    db_mod._db_open = old_open
    db_mod._db_refcount = old_ref


class TestAcquireReleaseCycle:
    """Verify that acquire/release correctly opens and closes the connection."""

    def test_release_closes_when_refcount_zero(self, db_path):
        from scistack_gui.db import init_db, acquire_db_connection, release_db_connection
        import scistack_gui.db as db_mod

        init_db(db_path)
        assert db_mod._db_open is True

        # Simulate close_initial_connection
        db_mod._db._duck.close()
        db_mod._db_open = False

        # Acquire opens it
        acquire_db_connection()
        assert db_mod._db_open is True
        assert db_mod._db_refcount == 1

        # Release closes it
        release_db_connection()
        assert db_mod._db_open is False
        assert db_mod._db_refcount == 0

    def test_nested_acquire_keeps_open(self, db_path):
        from scistack_gui.db import init_db, acquire_db_connection, release_db_connection
        import scistack_gui.db as db_mod

        init_db(db_path)
        db_mod._db._duck.close()
        db_mod._db_open = False

        acquire_db_connection()
        acquire_db_connection()
        assert db_mod._db_refcount == 2

        release_db_connection()
        assert db_mod._db_open is True  # still held by 1 caller
        assert db_mod._db_refcount == 1

        release_db_connection()
        assert db_mod._db_open is False
        assert db_mod._db_refcount == 0

    def test_second_process_can_open_after_release(self, db_path):
        """After Python releases the lock, another connection can open the file."""
        from scistack_gui.db import init_db, acquire_db_connection, release_db_connection

        init_db(db_path)
        acquire_db_connection()
        release_db_connection()

        # Simulate MATLAB opening the same file
        con2 = duckdb.connect(str(db_path))
        rows = con2.execute("SELECT COUNT(*) FROM _schema").fetchall()
        assert rows[0][0] >= 1
        con2.close()

    def test_reacquire_after_external_close(self, db_path):
        """Python can reacquire the connection after MATLAB releases it."""
        from scistack_gui.db import init_db, acquire_db_connection, release_db_connection
        import scistack_gui.db as db_mod

        db = init_db(db_path)
        acquire_db_connection()
        release_db_connection()
        # Connection now closed

        # Simulate MATLAB opening and closing
        con2 = duckdb.connect(str(db_path))
        con2.execute("CREATE TABLE IF NOT EXISTS _test (x INTEGER)")
        con2.close()

        # Python reacquires
        acquire_db_connection()
        assert db_mod._db_open is True
        # Can query the table MATLAB created
        rows = db._duck._fetchall("SELECT * FROM _test")
        assert rows is not None
        release_db_connection()


class TestMatlabCommandIncludesCleanup:
    """Verify the generated MATLAB script always calls db.close()."""

    def test_template_has_close(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="my_func",
            db_path="/data/test.duckdb",
            schema_keys=["subject"],
        )
        # Must have db.close() in both try and catch branches
        assert cmd.count("db.close()") == 2
        assert "catch scistack_err__" in cmd

    def test_variants_has_close(self):
        from scistack_gui.api.matlab_command import generate_matlab_command

        cmd = generate_matlab_command(
            function_name="my_func",
            db_path="/data/test.duckdb",
            schema_keys=["subject"],
            variants=[{
                "input_types": {"x": "RawData"},
                "output_type": "ProcessedData",
                "constants": {},
                "record_count": 1,
            }],
        )
        assert cmd.count("db.close()") == 2
        assert "catch scistack_err__" in cmd
