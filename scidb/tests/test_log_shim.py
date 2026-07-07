"""Regression: scidb.log must keep re-exporting the scistacklog facade.

MATLAB's +scidb/Log.m delegates via py.scidb.log.Log.*, and many modules
import ``from scidb.log import Log`` — this import path is a public contract
even though the implementation moved to the scistacklog package.

Also pins the level policy contracts that Stage 3 established:
- configure_database writes a run-context header and the log file
- [timing] summaries are INFO (present in the file at the default level);
  the MATLAB timing-archive grep workflow depends on them
- per-record/per-column internals are DEBUG (absent at the default level)
"""

import numpy as np

import scidb
from scidb.log import Log as shim_log
from scistacklog import Log as real_log


def test_scidb_log_reexports_scistacklog_facade():
    assert shim_log is real_log


def test_scidb_package_export_matches():
    assert scidb.Log is real_log


class _ShimVar(scidb.BaseVariable):
    schema_version = 1


def test_configure_database_writes_run_context_header(db, tmp_path):
    log_text = (tmp_path / "scidb.log").read_text(encoding="utf-8")
    assert "configure_database:" in log_text
    assert "python=" in log_text
    assert "pid=" in log_text


def test_timing_summary_in_file_at_default_level(db, tmp_path):
    db.save_batch(_ShimVar, [
        (np.array([1.0, 2.0]), {"subject": "S01", "trial": "1"}),
        (np.array([3.0, 4.0]), {"subject": "S01", "trial": "2"}),
    ])
    log_text = (tmp_path / "scidb.log").read_text(encoding="utf-8")
    assert "[timing] save_batch(_ShimVar):" in log_text
    # Per-phase timing table is DEBUG-only (and phase names carry no
    # numbering — snake_case operations only).
    assert "  save_batch canonical_hash" not in log_text


def test_per_record_internals_absent_at_default_level(db, tmp_path):
    _ShimVar.save(np.array([1.0, 2.0]), subject="S01", trial="1")
    log_text = (tmp_path / "scidb.log").read_text(encoding="utf-8")
    # DEBUG-tier internals must not reach the file at the INFO default.
    assert "save_variable(_ShimVar): metadata=" not in log_text
    assert "[content_hash]" not in log_text
    # But the one-line save outcome (INFO) is present.
    assert "save_variable(_ShimVar): saved -> record_id=" in log_text
