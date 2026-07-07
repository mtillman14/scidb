"""Regression tests for scifor's logging behavior (logging redesign).

Pins the contracts introduced when scifor moved from print() to the
scistacklog facade:
- per-iteration [run]/[skip]/[done] lines are DEBUG, absent at INFO
- the first occurrence of each distinct failure reason logs at WARN
- the end-of-run summary aggregates failure reasons with counts and combos
- periodic progress fires on outermost-key transitions (guarded)
- the final "summary" progress event carries the aggregated counts
- scifor never imports scidb and never writes /tmp/scihist_diag.log
"""

import logging
import os
import sys

import pandas as pd
import pytest

import scifor
import scifor.foreach
from scifor import for_each, set_schema


def setup_function():
    set_schema([])


def make_df(subjects=(1, 2, 3), trials=(1, 2)):
    rows = []
    for s in subjects:
        for t in trials:
            rows.append({"subject": s, "trial": t, "value": float(s * 10 + t)})
    return pd.DataFrame(rows)


def messages(caplog, level=None):
    return [
        r.getMessage() for r in caplog.records
        if r.name == "scifor" and (level is None or r.levelno == level)
    ]


# ---------------------------------------------------------------------------
# Level policy: per-iteration lines are DEBUG
# ---------------------------------------------------------------------------

def test_run_lines_absent_at_info(caplog):
    set_schema(["subject", "trial"])
    with caplog.at_level(logging.INFO, logger="scifor"):
        for_each(lambda value: value.mean(),
                 inputs={"value": make_df()}, subject=[1, 2, 3], trial=[1, 2])
    msgs = messages(caplog)
    assert not any(m.startswith("[run]") for m in msgs)
    assert not any(m.startswith("[done]") for m in msgs)


def test_run_lines_present_at_debug(caplog):
    set_schema(["subject", "trial"])
    with caplog.at_level(logging.DEBUG, logger="scifor"):
        for_each(lambda value: value.mean(),
                 inputs={"value": make_df()}, subject=[1, 2, 3], trial=[1, 2])
    msgs = messages(caplog)
    assert sum(1 for m in msgs if m.startswith("[run]")) == 6
    assert sum(1 for m in msgs if m.startswith("[done]")) == 6


def test_banner_and_done_summary_at_info(caplog):
    set_schema(["subject", "trial"])
    with caplog.at_level(logging.INFO, logger="scifor"):
        for_each(lambda value: value.mean(),
                 inputs={"value": make_df()}, subject=[1, 2, 3], trial=[1, 2])
    msgs = messages(caplog, logging.INFO)
    assert any("for_each(<lambda>) — 6 iterations" in m for m in msgs)
    assert any("subject=3 values [1, 2, 3]" in m for m in msgs)
    assert any("done in" in m and "completed=6, failed=0, total=6" in m
               for m in msgs)


# ---------------------------------------------------------------------------
# Failure aggregation
# ---------------------------------------------------------------------------

def test_summary_aggregates_failure_reasons(caplog):
    set_schema(["subject", "trial"])

    def fn(value):
        # Each combo yields a single scalar; trial-1 combos (value % 10 == 1) fail.
        if value % 10 == 1:
            raise ValueError("bad channel count")
        return float(value)

    with caplog.at_level(logging.DEBUG, logger="scifor"):
        for_each(fn, inputs={"value": make_df()},
                 subject=[1, 2, 3], trial=[1, 2])

    info = messages(caplog, logging.INFO)
    done = [m for m in info if "done in" in m]
    assert done and "completed=3, failed=3, total=6" in done[0]
    failed = [m for m in info if m.startswith("failed:")]
    assert len(failed) == 1
    assert 'failed: 3 × "ValueError: bad channel count"' in failed[0]
    assert "subject=1, trial=1" in failed[0]

    # First occurrence logs at WARN with the traceback attached.
    warns = [r for r in caplog.records
             if r.name == "scifor" and r.levelno == logging.WARNING]
    assert len(warns) == 1
    assert "iteration failed" in warns[0].getMessage()
    assert warns[0].exc_info is not None or warns[0].exc_text

    # Every failing iteration logs a [skip] DEBUG line.
    skips = [m for m in messages(caplog, logging.DEBUG)
             if m.startswith("[skip]")]
    assert len(skips) == 3


def test_summary_caps_listed_combos(caplog):
    set_schema(["subject"])
    df = pd.DataFrame({"subject": list(range(1, 9)),
                       "value": [1.0] * 8})

    def fn(value):
        raise ValueError("always broken")

    with caplog.at_level(logging.INFO, logger="scifor"):
        for_each(fn, inputs={"value": df}, subject=list(range(1, 9)))

    failed = [m for m in messages(caplog, logging.INFO)
              if m.startswith("failed:")]
    assert len(failed) == 1
    assert 'failed: 8 × "ValueError: always broken"' in failed[0]
    assert "(+3 more)" in failed[0]  # 8 combos, 5 listed


def test_summary_progress_event_carries_failure_reasons():
    set_schema(["subject"])
    df = pd.DataFrame({"subject": [1, 2], "value": [1.0, 2.0]})
    events = []

    def fn(value):
        if value == 1.0:
            raise ValueError("boom")
        return float(value)

    for_each(fn, inputs={"value": df}, subject=[1, 2],
             _progress_fn=events.append)

    summaries = [e for e in events if e.get("event") == "summary"]
    assert len(summaries) == 1
    s = summaries[0]
    assert s["total"] == 2 and s["completed"] == 1 and s["failed"] == 1
    assert list(s["failure_reasons"]) == ["ValueError: boom"]
    assert s["failure_reasons"]["ValueError: boom"] == ["subject=1"]


# ---------------------------------------------------------------------------
# Periodic progress
# ---------------------------------------------------------------------------

def test_progress_fires_on_outermost_key_transitions(caplog, monkeypatch):
    monkeypatch.setattr(scifor.foreach, "_PROGRESS_START_DELAY_S", 0.0)
    monkeypatch.setattr(scifor.foreach, "_PROGRESS_MIN_INTERVAL_S", 0.0)
    set_schema(["subject", "trial"])
    with caplog.at_level(logging.INFO, logger="scifor"):
        for_each(lambda value: value.mean(),
                 inputs={"value": make_df()}, subject=[1, 2, 3], trial=[1, 2])
    progress = [m for m in messages(caplog, logging.INFO)
                if m.startswith("progress:")]
    # 3 subject transitions; the very first (subject=1 at combo 0) never logs.
    assert len(progress) == 2
    assert "subject=2 (2/3)" in progress[0]
    assert "2/6 combos" in progress[0]
    assert "subject=3 (3/3)" in progress[1]


def test_progress_respects_min_interval_guard(caplog, monkeypatch):
    monkeypatch.setattr(scifor.foreach, "_PROGRESS_START_DELAY_S", 0.0)
    monkeypatch.setattr(scifor.foreach, "_PROGRESS_MIN_INTERVAL_S", 1000.0)
    set_schema(["subject", "trial"])
    with caplog.at_level(logging.INFO, logger="scifor"):
        for_each(lambda value: value.mean(),
                 inputs={"value": make_df()}, subject=[1, 2, 3], trial=[1, 2])
    progress = [m for m in messages(caplog, logging.INFO)
                if m.startswith("progress:")]
    assert progress == []


def test_no_progress_on_fast_runs_by_default(caplog):
    """Default 5s start delay means short runs emit no progress lines."""
    set_schema(["subject", "trial"])
    with caplog.at_level(logging.INFO, logger="scifor"):
        for_each(lambda value: value.mean(),
                 inputs={"value": make_df()}, subject=[1, 2, 3], trial=[1, 2])
    assert not any(m.startswith("progress:")
                   for m in messages(caplog, logging.INFO))


# ---------------------------------------------------------------------------
# Isolation contracts
# ---------------------------------------------------------------------------

def test_scifor_does_not_import_scidb():
    """scifor must stay scidb-free: it logs via scistacklog directly."""
    set_schema(["subject"])
    df = pd.DataFrame({"subject": [1], "value": [1.0]})
    for_each(lambda value: value.mean(), inputs={"value": df}, subject=[1])
    assert "scidb" not in sys.modules


def test_no_diag_file_written():
    """The hardcoded /tmp/scihist_diag.log dump was removed."""
    diag = "/tmp/scihist_diag.log"
    if os.path.exists(diag):
        os.remove(diag)
    set_schema(["subject"])
    df = pd.DataFrame({"subject": [1, 2], "value": [1.0, 2.0]})

    def fn(value):
        raise ValueError("boom")

    for_each(fn, inputs={"value": df}, subject=[1, 2])
    assert not os.path.exists(diag)
