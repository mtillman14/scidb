"""Tests for the display-side variant discriminator (``variant_identity_batch``).

Two records can sit at the same ``(type, schema_id)`` and be distinguishable
only by the *body* of the function that produced them. The supersession keys
used by ``load`` and node state deliberately call those two records the same
variant (newest wins). The display layers cannot — they show both at once, so
they need a name for each. That is what these tests pin down.

See ``docs/claude/function-version-variants.md``.
"""

import numpy as np
import pytest

import scifor as _scifor
from scidb import BaseVariable, configure_database, for_each
from scidb.provenance import SAVE_FUNCTION_NAME
from scidb.provenance_query import (
    producing_function_versions_batch,
    variant_identity_batch,
)

SCHEMA = ["subject", "session"]


@pytest.fixture
def db(tmp_path):
    _scifor.set_schema([])
    db = configure_database(tmp_path / "test_variant_identity.duckdb", SCHEMA)
    yield db
    _scifor.set_schema([])
    db.close()


class RawSignal(BaseVariable):
    pass


class Loaded(BaseVariable):
    pass


# ---------------------------------------------------------------------------
# Two source versions of ONE function.
#
# ``__name__`` is what lands in ``_invocation.function_name`` (via
# ForEachConfig.to_version_keys' ``__fn``), while ``function_hash`` is an AST
# hash of the source. Assigning both the same ``__name__`` therefore models
# exactly the reported scenario: the user edited the body of one function and
# re-ran it.
# ---------------------------------------------------------------------------


def _load_body_v1(signal):
    return signal * 2


def _load_body_v2(signal):
    return signal * 3


def _load_body_v3(signal):
    return signal + 7


for _fn in (_load_body_v1, _load_body_v2, _load_body_v3):
    _fn.__name__ = "load_signal"


def _seed_raw(db, subjects=(1,), sessions=("A",)):
    for subj in subjects:
        for sess in sessions:
            RawSignal.save(np.arange(5.0), db=db, subject=subj, session=sess)


def _run(body, db):
    for_each(
        body,
        inputs={"signal": RawSignal},
        outputs=[Loaded],
        subject=[1],
        session=["A"],
    )


def _loaded_record_ids(db):
    rows = db._duck._fetchall(
        "SELECT record_id FROM _record WHERE type = ? "
        "AND COALESCE(excluded, FALSE) = FALSE",
        ["Loaded"],
    )
    return [row[0] for row in rows]


# ---------------------------------------------------------------------------
# Direct-graph helper for the edge cases that for_each cannot easily produce
# ---------------------------------------------------------------------------


def _inject(db, record_id, schema_id, timestamp, fn_name=None, fn_hash=None):
    """Insert one Loaded record, optionally with a producing invocation."""
    duck = db._duck
    duck.con.execute(
        "INSERT INTO _record "
        "(record_id, created_at, type, schema_id, content_hash, schema_version, excluded) "
        "VALUES (?, ?, 'Loaded', ?, ?, 1, FALSE)",
        [record_id, timestamp, schema_id, "ab" * 32],
    )
    duck.con.execute(
        "INSERT INTO _record_save (record_id, timestamp) VALUES (?, ?)",
        [record_id, timestamp],
    )
    if fn_hash is not None:
        inv_id = f"inv_{record_id}"
        duck.con.execute(
            "INSERT INTO _invocation "
            "(invocation_id, function_name, function_hash, as_table, distribute) "
            "VALUES (?, ?, ?, ?, FALSE)",
            [inv_id, fn_name, fn_hash, []],
        )
        duck.con.execute(
            "INSERT INTO _invocation_output "
            "(invocation_id, output_num, output_record_id) VALUES (?, 0, ?)",
            [inv_id, record_id],
        )
    return record_id


def _schema_id(db, subject="1", session="A"):
    return db._duck._get_or_create_schema_id(
        "session", {"subject": subject, "session": session}
    )


# ---------------------------------------------------------------------------
# The reported scenario
# ---------------------------------------------------------------------------


class TestFunctionBodyEdit:
    def test_two_bodies_produce_two_labelled_versions(self, db):
        """Edit the body, re-run: two records at one location, two version labels.

        This is the exact failure the GUI showed as `records[2], variants[1]`,
        both labelled "(raw)".
        """
        _seed_raw(db)
        _run(_load_body_v1, db)
        _run(_load_body_v2, db)

        rids = _loaded_record_ids(db)
        assert len(rids) == 2, "a body edit must produce a second record"

        ident = variant_identity_batch(db._duck, rids)

        hashes = {ident[r]["fn_hash"] for r in rids}
        assert len(hashes) == 2, "the two bodies must hash differently"

        versions = {ident[r]["fn_version"] for r in rids}
        assert versions == {"v1", "v2"}

        assert all(ident[r]["fn_name"] == "load_signal" for r in rids)
        assert sum(1 for r in rids if ident[r]["is_latest"]) == 1

    def test_latest_is_the_second_run(self, db):
        _seed_raw(db)
        _run(_load_body_v1, db)
        first = set(_loaded_record_ids(db))
        _run(_load_body_v2, db)

        rids = _loaded_record_ids(db)
        ident = variant_identity_batch(db._duck, rids)

        latest = [r for r in rids if ident[r]["is_latest"]]
        assert len(latest) == 1
        assert latest[0] not in first, "the newly written record is the latest"
        assert ident[latest[0]]["fn_version"] == "v2"

    def test_ordinals_are_stable_when_a_third_version_appears(self, db):
        """A new version appends v3; it must not renumber v1/v2 under the user."""
        _seed_raw(db)
        _run(_load_body_v1, db)
        _run(_load_body_v2, db)

        rids_before = _loaded_record_ids(db)
        before = {
            r: variant_identity_batch(db._duck, rids_before)[r]["fn_version"]
            for r in rids_before
        }

        _run(_load_body_v3, db)

        rids_after = _loaded_record_ids(db)
        after = variant_identity_batch(db._duck, rids_after)

        for rid, label in before.items():
            assert after[rid]["fn_version"] == label, (
                f"{rid} was {label} and must stay {label}"
            )
        assert after[[r for r in rids_after if r not in before][0]]["fn_version"] == "v3"


class TestSingleVersionUnchanged:
    def test_one_version_emits_no_discriminator(self, db):
        """The ordinary case must keep today's clean labels — no v1 suffix
        appearing on every record in every existing project."""
        _seed_raw(db)
        _run(_load_body_v1, db)

        rids = _loaded_record_ids(db)
        assert len(rids) == 1
        ident = variant_identity_batch(db._duck, rids)

        assert ident[rids[0]]["fn_version"] is None
        assert ident[rids[0]]["is_latest"] is True
        assert ident[rids[0]]["fn_name"] == "load_signal"
        assert ident[rids[0]]["fn_hash"]

    def test_re_running_the_same_body_does_not_fork_a_version(self, db):
        """Same source twice = one version, however many records it wrote."""
        _seed_raw(db)
        _run(_load_body_v1, db)
        _run(_load_body_v1, db)

        rids = _loaded_record_ids(db)
        ident = variant_identity_batch(db._duck, rids)

        assert {ident[r]["fn_version"] for r in rids} == {None}
        assert all(ident[r]["is_latest"] for r in rids), (
            "is_latest is a property of the version, so every record of the "
            "only version is latest"
        )


class TestRawRecords:
    def test_raw_record_has_no_function_version(self, db):
        _seed_raw(db)
        rids = [
            row[0]
            for row in db._duck._fetchall(
                "SELECT record_id FROM _record WHERE type = ?", ["RawSignal"]
            )
        ]
        ident = variant_identity_batch(db._duck, rids)

        for rid in rids:
            assert ident[rid]["fn_name"] is None
            assert ident[rid]["fn_hash"] is None
            assert ident[rid]["fn_version"] is None
            assert ident[rid]["is_latest"] is None
            assert ident[rid]["saved_at"], "a raw record still has a save time"

    def test_save_anchor_is_not_a_function_version(self, db):
        """The synthetic ``__save__`` invocation anchors direct-save kwargs; it is
        not a real function and must not be labelled as a version."""
        sid = _schema_id(db)
        rid = _inject(
            db,
            "rec_save_anchor",
            sid,
            "2026-09-06T10:00:00",
            fn_name=SAVE_FUNCTION_NAME,
            fn_hash="",
        )
        versions = producing_function_versions_batch(db._duck, [rid])
        assert versions == {}

        ident = variant_identity_batch(db._duck, [rid])
        assert ident[rid]["fn_version"] is None
        assert ident[rid]["fn_name"] is None


class TestScoping:
    def test_labels_do_not_depend_on_the_requested_subset(self, db):
        """Ordinals are computed over every record at the location, so asking
        about one record gives it the same label as asking about all of them."""
        _seed_raw(db)
        _run(_load_body_v1, db)
        _run(_load_body_v2, db)

        rids = _loaded_record_ids(db)
        full = variant_identity_batch(db._duck, rids)
        for rid in rids:
            subset = variant_identity_batch(db._duck, [rid])
            assert subset[rid]["fn_version"] == full[rid]["fn_version"]
            assert subset[rid]["is_latest"] == full[rid]["is_latest"]

    def test_ordinals_are_numbered_per_type_not_per_location(self, db):
        """One hash must get ONE ordinal across every location of the type.

        Plot Studio turns fn_version into a single factor column spanning all
        locations, so numbering per location — letting h1 be "v1" at subject=1
        and "v2" at subject=2 — would make that column incoherent.
        """
        sid_a = _schema_id(db, subject="1")
        sid_b = _schema_id(db, subject="2")
        a1 = _inject(db, "a1", sid_a, "2026-09-06T10:00:00", "load_signal", "h1")
        a2 = _inject(db, "a2", sid_a, "2026-09-06T11:00:00", "load_signal", "h2")
        # subject=2 only ever ran the SECOND body.
        b2 = _inject(db, "b2", sid_b, "2026-09-06T11:30:00", "load_signal", "h2")

        ident = variant_identity_batch(db._duck, [a1, a2, b2])

        assert ident[a1]["fn_version"] == "v1"
        assert ident[a2]["fn_version"] == "v2"
        assert ident[b2]["fn_version"] == "v2", (
            "h2 is v2 everywhere — the same code cannot be v2 here and v1 there"
        )

    def test_is_latest_is_resolved_per_location(self, db):
        """Pinning 'latest' must keep each location's own newest version, or a
        subject never re-run under the newest code vanishes from the figure."""
        sid_a = _schema_id(db, subject="1")
        sid_b = _schema_id(db, subject="2")
        a1 = _inject(db, "a1", sid_a, "2026-09-06T10:00:00", "load_signal", "h1")
        a2 = _inject(db, "a2", sid_a, "2026-09-06T11:00:00", "load_signal", "h2")
        # subject=2 was never re-run: h1 is still the newest thing it has.
        b1 = _inject(db, "b1", sid_b, "2026-09-06T10:30:00", "load_signal", "h1")

        ident = variant_identity_batch(db._duck, [a1, a2, b1])

        assert ident[a1]["is_latest"] is False
        assert ident[a2]["is_latest"] is True
        assert ident[b1]["is_latest"] is True, (
            "subject=2's only version is its latest, even though it is the "
            "older code globally"
        )
        # ...and it still carries the type-wide ordinal, so the plot can name it.
        assert ident[b1]["fn_version"] == "v1"


class TestOrdering:
    def test_latest_follows_the_most_recent_write_not_the_ordinal(self, db):
        """Re-running an OLDER version makes it latest again — 'latest' means
        most recently written, which is what a plot should show."""
        sid = _schema_id(db)
        v1_old = _inject(db, "v1old", sid, "2026-09-06T10:00:00", "load_signal", "h1")
        v2 = _inject(db, "v2", sid, "2026-09-06T11:00:00", "load_signal", "h2")
        v1_new = _inject(db, "v1new", sid, "2026-09-06T12:00:00", "load_signal", "h1")

        ident = variant_identity_batch(db._duck, [v1_old, v2, v1_new])

        # h1 was seen first, so it keeps ordinal v1 even though it is now latest.
        assert ident[v1_old]["fn_version"] == "v1"
        assert ident[v1_new]["fn_version"] == "v1"
        assert ident[v2]["fn_version"] == "v2"

        assert ident[v1_new]["is_latest"] is True
        assert ident[v1_old]["is_latest"] is True, "same version, so also latest"
        assert ident[v2]["is_latest"] is False

    def test_excluded_records_do_not_create_versions(self, db):
        sid = _schema_id(db)
        keep = _inject(db, "keep", sid, "2026-09-06T10:00:00", "load_signal", "h1")
        gone = _inject(db, "gone", sid, "2026-09-06T11:00:00", "load_signal", "h2")
        db._duck.con.execute(
            "UPDATE _record SET excluded = TRUE WHERE record_id = ?", [gone]
        )

        ident = variant_identity_batch(db._duck, [keep])
        assert ident[keep]["fn_version"] is None, (
            "the excluded record's version must not make the location ambiguous"
        )
        assert ident[keep]["is_latest"] is True


class TestBranchParamsUnchanged:
    def test_constants_still_surface_as_branch_params(self, db):
        """The existing discriminator keeps working and coexists with versions."""

        def scale(signal, factor):
            return signal * factor

        _seed_raw(db)
        for factor in (2, 3):
            for_each(
                scale,
                inputs={"signal": RawSignal, "factor": factor},
                outputs=[Loaded],
                subject=[1],
                session=["A"],
            )

        rids = _loaded_record_ids(db)
        ident = variant_identity_batch(db._duck, rids)

        factors = {
            tuple(sorted(ident[r]["branch_params"].items())): r for r in rids
        }
        assert len(factors) == 2, "two constant variants stay distinguishable"
        # One function body, so no version discriminator is needed on top.
        assert {ident[r]["fn_version"] for r in rids} == {None}


class TestEdges:
    def test_empty_input(self, db):
        assert variant_identity_batch(db._duck, []) == {}
        assert producing_function_versions_batch(db._duck, []) == {}

    def test_unknown_record_id_is_absent(self, db):
        ident = variant_identity_batch(db._duck, ["does_not_exist"])
        assert ident["does_not_exist"]["fn_version"] is None
        assert ident["does_not_exist"]["branch_params"] == {}
