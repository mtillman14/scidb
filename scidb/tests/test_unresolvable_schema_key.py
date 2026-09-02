"""A schema key nothing can fill must not zero out the whole run.

``key=[]`` means "all levels", so a caller iterating a schema level asks for
every key that way. When records are saved at a coarser level, the deeper key
has no values at all — and an empty list in the Cartesian product used to make
``for_each`` build ZERO combos and report a clean, silent, wrong success.

The same decision already existed for PathInput discovery, which drops a key a
static template can never supply rather than leaving it empty. This applies it
to the database source.
"""

import numpy as np
import pytest

import scifor as _scifor
from scidb import BaseVariable, configure_database, for_each

SCHEMA = ["subject", "trial"]


@pytest.fixture
def db(tmp_path):
    _scifor.set_schema([])
    db = configure_database(tmp_path / "test_unresolvable.duckdb", SCHEMA)
    yield db
    _scifor.set_schema([])
    db.close()


class Coarse(BaseVariable):
    pass


class Result(BaseVariable):
    pass


def test_empty_deeper_key_is_dropped_not_multiplied_to_zero(db):
    """Records live at subject level; `trial` has no values anywhere."""
    for subject in (1, 2, 3):
        Coarse.save(np.array([float(subject)]), subject=subject)

    calls = []
    for_each(
        lambda x: calls.append(x) or float(np.max(x)),
        {"x": Coarse},
        [Result],
        subject=[],
        trial=[],
        save=False,
    )

    assert len(calls) == 3, "trial=[] must not collapse the run to zero combos"


def test_all_keys_empty_still_means_zero(db):
    """An empty database is genuinely zero iterations — it must not silently
    become one data-less call."""
    calls = []
    for_each(
        lambda x: calls.append(x) or 0.0,
        {"x": Coarse},
        [Result],
        subject=[],
        trial=[],
        save=False,
    )

    assert calls == []


def test_explicit_values_for_the_deeper_key_are_untouched(db):
    """Only auto-filled (empty-list) keys are droppable; an explicit value is
    caller intent and still constrains the run.

    Same records as the first test — the ONLY difference is ``trial=[7]``
    instead of ``trial=[]``. If the drop rule reached explicit values too,
    ``trial`` would vanish and this would call the function three times on the
    subject-level records. It must find nothing at trial 7 instead.
    """
    for subject in (1, 2, 3):
        Coarse.save(np.array([float(subject)]), subject=subject)

    calls = []
    for_each(
        lambda x: calls.append(x) or 0.0,
        {"x": Coarse},
        [Result],
        subject=[],
        trial=[7],
        save=False,
    )

    assert calls == [], "an explicit trial=[7] must still constrain the run"
