"""Tests for scifor.for_each's schema_keys= parameter (standalone, no DB).

schema_keys= is structural sugar for "iterate over these schema key names" —
equivalent to passing key=[] for each one by hand, then letting the existing
empty-list DataFrame-scan resolver (_distinct_values_from_inputs) fill in the
values. scidb.for_each's schema_keys= (DB-backed) reuses the same
expand_schema_keys() helper this exercises.
"""

import pandas as pd
import pytest

from scifor import for_each, set_schema
from scifor.schema import expand_schema_keys


def setup_function():
    set_schema([])


def make_df(subjects=(1, 2), sessions=("pre", "post"), data_col="emg"):
    rows = []
    for s in subjects:
        for sess in sessions:
            rows.append({"subject": s, "session": sess, data_col: float(s) + 0.1})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# expand_schema_keys() — pure unit tests
# ---------------------------------------------------------------------------


class TestExpandSchemaKeys:
    def test_seeds_empty_lists(self):
        result = expand_schema_keys(["subject", "session"], {})
        assert result == {"subject": [], "session": []}

    def test_raises_if_metadata_iterables_populated(self):
        with pytest.raises(ValueError, match="Cannot use both"):
            expand_schema_keys(["subject"], {"session": ["pre"]})

    def test_empty_schema_keys_list(self):
        assert expand_schema_keys([], {}) == {}


# ---------------------------------------------------------------------------
# for_each(schema_keys=...) — full iteration
# ---------------------------------------------------------------------------


class TestForEachSchemaKeys:
    def test_schema_keys_resolves_from_dataframe(self):
        """schema_keys=[...] auto-resolves each key's values by scanning inputs,
        identical to passing key=[] explicitly."""
        set_schema(["subject", "session"])
        df = make_df(subjects=(1, 2), sessions=("pre", "post"))

        result = for_each(
            lambda emg: emg,
            inputs={"emg": df},
            schema_keys=["subject", "session"],
        )

        assert len(result) == 4
        assert set(result["subject"].unique()) == {1, 2}
        assert set(result["session"].unique()) == {"pre", "post"}

    def test_schema_keys_matches_explicit_empty_lists(self):
        """schema_keys=["subject","session"] must behave the same as
        subject=[], session=[] (the pre-existing spelled-out form)."""
        set_schema(["subject", "session"])
        df = make_df()

        via_schema_keys = for_each(
            lambda emg: emg, inputs={"emg": df}, schema_keys=["subject", "session"]
        )
        via_explicit = for_each(
            lambda emg: emg, inputs={"emg": df}, subject=[], session=[]
        )

        assert len(via_schema_keys) == len(via_explicit) == 4
        assert set(zip(via_schema_keys["subject"], via_schema_keys["session"])) == set(
            zip(via_explicit["subject"], via_explicit["session"])
        )

    def test_schema_keys_subset_is_aggregation(self):
        """Requesting fewer keys than the full schema aggregates over the
        rest — same underlying mechanism as scidb's aggregation mode,
        which is a property of scifor's per-combo filtering, not something
        schema_keys adds."""
        set_schema(["subject", "session"])
        df = make_df(subjects=(1, 2), sessions=("pre", "post"))

        received = []

        def fn(emg):
            received.append(len(emg) if hasattr(emg, "__len__") else 1)
            return 0

        for_each(fn, inputs={"emg": df}, schema_keys=["subject"])

        # One call per subject; each receives both sessions' rows (2), not 1.
        assert received == [2, 2]

    def test_schema_keys_conflicts_with_metadata_iterables(self):
        set_schema(["subject", "session"])
        df = make_df()

        with pytest.raises(ValueError, match="Cannot use both"):
            for_each(
                lambda emg: emg,
                inputs={"emg": df},
                schema_keys=["subject"],
                session=["pre"],
            )
