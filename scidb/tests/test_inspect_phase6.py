"""Phase 6 tests: pick — record-id selection (facade, drill-down, CLI).

Contract under test: stdout carries ONLY the selected record_id (so
``open-plot $(scidb pick …)`` composes); menus/tables for humans go to
stderr; ambiguity without --interactive/--table/--json fails.
"""

import json

import numpy as np
import pytest
from scidb.inspect import Inspector, render
from scidb.inspect.cli import main
from scidb.inspect.pick import PickAborted, drill_down, variant_label

from scidb import BaseVariable, configure_database, for_each

SCHEMA_KEYS = ["subject", "session"]


class P6Raw(BaseVariable):
    schema_version = 1


class P6Out(BaseVariable):
    schema_version = 1


def gain6(signal, k):
    return signal * k


def build_p6_db(db_path):
    db = configure_database(db_path, SCHEMA_KEYS)
    # Zero-padded subjects; two variants of P6Out per location.
    for subj in ("01", "02"):
        P6Raw.save(np.array([float(subj)]), subject=subj, session="1")
    for k in (1, 2):
        for_each(
            gain6,
            {"signal": P6Raw, "k": k},
            [P6Out],
            subject=["01", "02"],
            session=["1"],
        )
    db.close()


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("p6") / "p6.duckdb"
    build_p6_db(path)
    return path


@pytest.fixture
def insp(db_path):
    with Inspector.open(db_path) as inspector:
        yield inspector


def scripted(*answers):
    """A chooser that returns pre-scripted indices and records the prompts."""
    queue = list(answers)
    asked = []

    def choose(title, labels):
        asked.append((title, list(labels)))
        return queue.pop(0)

    choose.asked = asked
    return choose


class TestPickFacade:
    def test_candidates_carry_variant_info(self, insp):
        cands = insp.pick("P6Out", subject="01")
        assert len(cands) == 2
        assert {c.branch_params["gain6.k"] for c in cands} == {"1", "2"}
        assert all(c.function_name == "gain6" for c in cands)
        assert all(c.schema == {"subject": "01", "session": "1"} for c in cands)
        assert all(c.saved for c in cands)

    def test_raw_records_have_no_function(self, insp):
        (cand,) = insp.pick("P6Raw", subject="01")
        assert cand.function_name is None
        assert cand.branch_params == {}

    def test_zero_padded_schema_values_verbatim(self, insp):
        cands = insp.pick("P6Out", subject="01")
        assert all(c.schema["subject"] == "01" for c in cands)


class TestDrillDown:
    def test_asks_only_disambiguating_levels(self, insp):
        # All 4 P6Out candidates: subject differs, session doesn't.
        cands = insp.pick("P6Out")
        choose = scripted(0, 1)  # subject=01, then variant k=2
        chosen = drill_down(cands, SCHEMA_KEYS, choose)
        titles = [t for t, _ in choose.asked]
        assert titles == ["Select subject:", "Select variant:"]  # session skipped
        assert chosen.schema["subject"] == "01"
        assert chosen.branch_params["gain6.k"] == "2"

    def test_variant_menu_order_is_deterministic(self, insp):
        """Regression: candidates arrive newest-save-first from _find_record
        (run-dependent); the variant menu must be sorted by label so the same
        index always means the same variant."""
        cands = insp.pick("P6Out", subject="01")
        for ordering in (cands, list(reversed(cands))):
            choose = scripted(0)
            drill_down(list(ordering), SCHEMA_KEYS, choose)
            ((_, labels),) = choose.asked
            assert "gain6.k=1" in labels[0]
            assert "gain6.k=2" in labels[1]

    def test_variant_menu_skipped_when_schema_settles_it(self, insp):
        cands = insp.pick("P6Raw")  # one raw record per subject, no variants
        choose = scripted(1)
        chosen = drill_down(cands, SCHEMA_KEYS, choose)
        assert [t for t, _ in choose.asked] == ["Select subject:"]
        assert chosen.schema["subject"] == "02"

    def test_single_candidate_asks_nothing(self, insp):
        cands = insp.pick("P6Out", subject="01", k=1)
        choose = scripted()
        assert drill_down(cands, SCHEMA_KEYS, choose) is cands[0]
        assert choose.asked == []

    def test_abort_propagates(self, insp):
        cands = insp.pick("P6Out")

        def aborting(title, labels):
            raise PickAborted()

        with pytest.raises(PickAborted):
            drill_down(cands, SCHEMA_KEYS, aborting)

    def test_empty_candidates_raise(self):
        with pytest.raises(ValueError):
            drill_down([], SCHEMA_KEYS, scripted())

    def test_variant_label_shapes(self, insp):
        (raw,) = insp.pick("P6Raw", subject="01")
        assert "(raw save)" in variant_label(raw)
        variant = insp.pick("P6Out", subject="01", k=2)[0]
        assert "gain6" in variant_label(variant)
        assert "gain6.k=2" in variant_label(variant)


class TestCli:
    def _rid_of(self, db_path, *filters):
        with Inspector.open(db_path) as insp:
            kv = dict(f.split("=") for f in filters)
            kv = {k: (int(v) if k == "k" else v) for k, v in kv.items()}
            (cand,) = insp.pick("P6Out", **kv)
            return cand.record_id

    def test_unambiguous_prints_only_the_rid(self, db_path, capsys):
        expected = self._rid_of(db_path, "subject=01", "k=1")
        assert main(["--db", str(db_path), "pick", "P6Out", "subject=01", "k=1"]) == 0
        out = capsys.readouterr().out
        assert out == f"{expected}\n"  # nothing else on stdout — composable

    def test_ambiguous_fails_with_table_on_stderr(self, db_path, capsys):
        assert main(["--db", str(db_path), "pick", "P6Out", "subject=01"]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""  # $(…) must capture nothing
        assert "gain6.k" in captured.err  # the disambiguation table
        assert "narrow" in captured.err

    def test_table_mode(self, db_path, capsys):
        assert main(["--db", str(db_path), "pick", "P6Out", "--table"]) == 0
        out = capsys.readouterr().out
        assert "record_id" in out and "gain6.k" in out
        assert out.count("\n") >= 5  # header + rule + 4 candidates

    def test_json_mode(self, db_path, capsys):
        assert (
            main(["--db", str(db_path), "pick", "P6Out", "subject=01", "--json"]) == 0
        )
        payload = json.loads(capsys.readouterr().out)
        assert len(payload) == 2
        assert {c["branch_params"]["gain6.k"] for c in payload} == {"1", "2"}

    def test_interactive_flow(self, db_path, capsys, monkeypatch):
        answers = iter(["1", "2"])  # subject=01, then variant #2
        monkeypatch.setattr("builtins.input", lambda: next(answers))
        assert main(["--db", str(db_path), "pick", "P6Out", "--interactive"]) == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().splitlines()
        assert len(lines) == 1 and len(lines[0]) >= 8  # just the record_id
        assert "Select subject:" in captured.err
        assert "Select variant:" in captured.err

    def test_interactive_without_type_offers_variables(
        self, db_path, capsys, monkeypatch
    ):
        # Choose the P6Raw-ish entry then drill to one record. Variable menu
        # order comes from insp.variables() (alphabetical).
        answers = iter(["2", "1"])  # 2nd variable, then subject=01
        monkeypatch.setattr("builtins.input", lambda: next(answers))
        assert main(["--db", str(db_path), "pick", "--interactive"]) == 0
        captured = capsys.readouterr()
        assert "Select variable:" in captured.err
        assert len(captured.out.strip().splitlines()) == 1

    def test_interactive_cancel(self, db_path, capsys, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda: "q")
        assert main(["--db", str(db_path), "pick", "P6Out", "--interactive"]) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "selection cancelled" in captured.err

    def test_invalid_then_valid_choice_reprompts(self, db_path, capsys, monkeypatch):
        answers = iter(["zzz", "99", "1", "1"])
        monkeypatch.setattr("builtins.input", lambda: next(answers))
        assert main(["--db", str(db_path), "pick", "P6Out", "--interactive"]) == 0
        assert "invalid choice" in capsys.readouterr().err

    def test_no_type_without_interactive_fails(self, db_path, capsys):
        assert main(["--db", str(db_path), "pick"]) == 1
        assert "variable type" in capsys.readouterr().err

    def test_no_match_fails(self, db_path, capsys):
        assert main(["--db", str(db_path), "pick", "P6Out", "subject=99"]) == 1
        assert "No P6Out records" in capsys.readouterr().err


class TestRenderer:
    def test_pick_table_has_param_columns(self, insp):
        text = render.render_pick_table(insp.pick("P6Out"), SCHEMA_KEYS)
        assert "gain6.k" in text
        assert "record_id" in text
        raw_text = render.render_pick_table(insp.pick("P6Raw"), SCHEMA_KEYS)
        assert "(raw)" in raw_text
