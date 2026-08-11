"""
Unit tests for scistack_gui.domain.graph_builder.

All functions are pure — no DB or fixtures required.
"""

import json

from scistack_gui.domain.graph_builder import (
    AggregatedData,
    aggregate_variants,
    auto_clean_pending_constants,
    build_constant_nodes,
    build_edges,
    build_function_nodes,
    build_manual_node,
    build_path_input_nodes,
    build_variable_nodes,
    candidate_edge_id,
    filter_hidden,
    find_cycle,
    fn_node_id,
    hidden_wirings,
    inbound_edge_candidates,
    merge_manual_nodes,
    overlay_saved_path_inputs,
    parse_path_input,
    pending_value_group_coverage,
    wiring_disconnected_fkeys,
    wiring_id,
    wirings_downstream_of,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cid(seed: str = "default") -> str:
    """Synthesize a 16-hex call_id for tests.  Stable per seed string."""
    import hashlib

    return hashlib.sha256(seed.encode()).hexdigest()[:16]


def _variant(fn, out, inputs=None, constants=None, count=1, call_id=None):
    return {
        "function_name": fn,
        "output_type": out,
        "call_id": call_id
        or _cid(
            f"{fn}:{json.dumps(constants or {}, sort_keys=True)}:{json.dumps(inputs or {}, sort_keys=True)}"
        ),
        "input_types": inputs or {},
        "constants": constants or {},
        "record_count": count,
    }


def _fkey(fn, *, inputs=None, constants=None) -> tuple[str, str]:
    """Build the FnKey that ``_variant(fn, ..., inputs, constants, ...)`` produces."""
    return (
        fn,
        _cid(
            f"{fn}:{json.dumps(constants or {}, sort_keys=True)}:{json.dumps(inputs or {}, sort_keys=True)}"
        ),
    )


# ---------------------------------------------------------------------------
# parse_path_input
# ---------------------------------------------------------------------------


class TestParsePathInput:
    def test_json_format(self):
        val = json.dumps(
            {
                "__type": "PathInput",
                "template": "{subject}/raw.csv",
                "root_folder": "/data",
            }
        )
        result = parse_path_input(val)
        assert result == {"template": "{subject}/raw.csv", "root_folder": "/data"}

    def test_json_format_no_root_folder(self):
        val = json.dumps({"__type": "PathInput", "template": "{subject}/raw.csv"})
        result = parse_path_input(val)
        assert result["template"] == "{subject}/raw.csv"
        assert result["root_folder"] is None

    def test_json_wrong_type_returns_none(self):
        val = json.dumps({"__type": "Other", "template": "x"})
        assert parse_path_input(val) is None

    def test_legacy_format(self):
        val = "PathInput('{subject}/raw.csv', root_folder=PosixPath('/data'))"
        result = parse_path_input(val)
        assert result["template"] == "{subject}/raw.csv"
        assert result["root_folder"] == "/data"

    def test_legacy_format_no_root(self):
        val = "PathInput('{subject}/raw.csv')"
        result = parse_path_input(val)
        assert result["template"] == "{subject}/raw.csv"
        assert result["root_folder"] is None

    def test_plain_string_returns_none(self):
        assert parse_path_input("RawEMG") is None

    def test_malformed_json_returns_none(self):
        assert parse_path_input("{not valid json}") is None


# ---------------------------------------------------------------------------
# aggregate_variants
# ---------------------------------------------------------------------------


class TestAggregateVariants:
    def test_basic_variant_parsed(self):
        variants = [
            _variant(
                "bandpass", "Filtered", inputs={"signal": "Raw"}, constants={"hz": 20}
            )
        ]
        agg = aggregate_variants(variants, listed_var_names=set())
        fkey = _fkey("bandpass", inputs={"signal": "Raw"}, constants={"hz": 20})
        assert "Filtered" in agg.all_var_types
        assert "Raw" in agg.all_var_types
        assert fkey in agg.fn_outputs
        assert "Filtered" in agg.fn_outputs[fkey]
        assert agg.fn_input_params[fkey]["signal"] == "Raw"
        assert "hz" in agg.fn_constants[fkey]

    def test_const_counts_accumulated(self):
        variants = [
            _variant("f", "Out", constants={"hz": 10}, count=3),
            _variant("f", "Out", constants={"hz": 20}, count=5),
        ]
        agg = aggregate_variants(variants, listed_var_names=set())
        # Two distinct call sites — one per constant value.
        assert agg.const_counts["hz"]["10"] == 3
        assert agg.const_counts["hz"]["20"] == 5
        assert len(agg.fn_input_params) == 2

    def test_path_input_parsed_and_not_added_to_var_types(self):
        pi_json = json.dumps({"__type": "PathInput", "template": "{s}/f.csv"})
        variants = [_variant("f", "Out", inputs={"path": pi_json})]
        agg = aggregate_variants(variants, listed_var_names=set())
        assert "path" in agg.path_inputs
        assert agg.path_inputs["path"]["template"] == "{s}/f.csv"
        assert "path" not in agg.all_var_types

    def test_path_input_function_set_accumulated(self):
        pi_json = json.dumps({"__type": "PathInput", "template": "{s}/f.csv"})
        variants = [
            _variant("f1", "Out1", inputs={"path": pi_json}),
            _variant("f2", "Out2", inputs={"path": pi_json}),
        ]
        agg = aggregate_variants(variants, listed_var_names=set())
        # path_inputs[name]["functions"] now holds FnKey tuples
        f1_key = _fkey("f1", inputs={"path": pi_json})
        f2_key = _fkey("f2", inputs={"path": pi_json})
        assert agg.path_inputs["path"]["functions"] == {f1_key, f2_key}

    def test_listed_var_names_added(self):
        agg = aggregate_variants([], listed_var_names={"ExtraVar"})
        assert "ExtraVar" in agg.all_var_types

    def test_fn_variants_map_populated(self):
        variants = [_variant("f", "Out", constants={"k": 1})]
        agg = aggregate_variants(variants, listed_var_names=set())
        fkey = _fkey("f", constants={"k": 1})
        assert len(agg.fn_variants_map[fkey]) == 1
        assert agg.fn_variants_map[fkey][0]["constants"] == {"k": 1}

    def test_empty_variants(self):
        agg = aggregate_variants([], listed_var_names=set())
        assert agg.all_var_types == set()

    def test_pathinput_only_function_registered_in_fn_input_params(self):
        """A PathInput-only function still gets a FnKey entry."""
        pi_json = json.dumps({"__type": "PathInput", "template": "{subject}/raw.csv"})
        variants = [_variant("loadFile", "Loaded", inputs={"filepath": pi_json})]
        agg = aggregate_variants(variants, listed_var_names=set())
        fkey = _fkey("loadFile", inputs={"filepath": pi_json})
        assert fkey in agg.fn_input_params
        assert agg.fn_input_params[fkey] == {}
        assert "Loaded" in agg.fn_outputs[fkey]

    def test_pathinput_only_function_with_constants(self):
        pi_json = json.dumps({"__type": "PathInput", "template": "{subject}/raw.csv"})
        variants = [
            _variant(
                "loadFile",
                "Loaded",
                inputs={"filepath": pi_json},
                constants={"hz": 100},
            )
        ]
        agg = aggregate_variants(variants, listed_var_names=set())
        fkey = _fkey("loadFile", inputs={"filepath": pi_json}, constants={"hz": 100})
        assert fkey in agg.fn_input_params
        assert agg.fn_input_params[fkey] == {}
        assert "hz" in agg.fn_constants[fkey]

    def test_mixed_pathinput_and_variable_inputs(self):
        pi_json = json.dumps({"__type": "PathInput", "template": "{subject}/raw.csv"})
        variants = [
            _variant("process", "Out", inputs={"filepath": pi_json, "signal": "Raw"})
        ]
        agg = aggregate_variants(variants, listed_var_names=set())
        fkey = _fkey("process", inputs={"filepath": pi_json, "signal": "Raw"})
        assert fkey in agg.fn_input_params
        assert agg.fn_input_params[fkey]["signal"] == "Raw"
        assert "filepath" not in agg.fn_input_params[fkey]

    def test_call_id_threaded_through_to_fn_keys(self):
        """Two call sites of the same fn produce two distinct FnKeys."""
        variants = [
            _variant("bp", "Out", constants={"hz": 10}),
            _variant("bp", "Out", constants={"hz": 50}),
        ]
        agg = aggregate_variants(variants, listed_var_names=set())
        keys = [k for k in agg.fn_input_params if k[0] == "bp"]
        assert len(keys) == 2
        # Distinct call_ids
        assert keys[0][1] != keys[1][1]

    def test_variant_missing_call_id_skipped(self):
        """Defensive: a variant lacking call_id is dropped (with a warning)."""
        v = _variant("f", "Out")
        v.pop("call_id")
        agg = aggregate_variants([v], listed_var_names=set())
        assert agg.fn_input_params == {}


# ---------------------------------------------------------------------------
# filter_hidden
# ---------------------------------------------------------------------------


class TestFilterHidden:
    def _agg(self):
        variants = [
            _variant(
                "bandpass", "Filtered", inputs={"signal": "Raw"}, constants={"hz": 20}
            ),
            _variant("normalize", "Normed", inputs={"signal": "Filtered"}),
        ]
        agg = aggregate_variants(variants, listed_var_names=set())
        bp_key = _fkey("bandpass", inputs={"signal": "Raw"}, constants={"hz": 20})
        agg.path_inputs["mypath"] = {"template": "{s}/f.csv", "functions": {bp_key}}
        return agg

    def test_hide_var_removes_from_all_var_types(self):
        agg = self._agg()
        filter_hidden(agg, {"var__Raw"})
        assert "Raw" not in agg.all_var_types

    def test_hide_var_removes_from_fn_input_params(self):
        agg = self._agg()
        bp_key = _fkey("bandpass", inputs={"signal": "Raw"}, constants={"hz": 20})
        filter_hidden(agg, {"var__Raw"})
        assert "signal" not in agg.fn_input_params.get(bp_key, {})

    def test_hide_var_removes_from_fn_outputs(self):
        agg = self._agg()
        bp_key = _fkey("bandpass", inputs={"signal": "Raw"}, constants={"hz": 20})
        filter_hidden(agg, {"var__Filtered"})
        assert "Filtered" not in agg.fn_outputs.get(bp_key, set())

    def test_hide_fn_removes_params_and_outputs(self):
        agg = self._agg()
        bp_key = _fkey("bandpass", inputs={"signal": "Raw"}, constants={"hz": 20})
        filter_hidden(agg, {fn_node_id(*bp_key)})
        assert bp_key not in agg.fn_input_params
        assert bp_key not in agg.fn_outputs
        assert bp_key not in agg.fn_constants

    def test_hide_legacy_fn_id_is_ignored(self):
        """Legacy ``fn__{name}`` IDs (no call_id) don't match composite FnKeys
        and are silently ignored — there is no single canonical node to hide."""
        agg = self._agg()
        bp_key = _fkey("bandpass", inputs={"signal": "Raw"}, constants={"hz": 20})
        filter_hidden(agg, {"fn__bandpass"})
        assert bp_key in agg.fn_input_params

    def test_hide_const_removes_from_const_counts(self):
        agg = self._agg()
        filter_hidden(agg, {"const__hz"})
        assert "hz" not in agg.const_counts
        assert "hz" not in agg.const_fns

    def test_hide_path_input(self):
        agg = self._agg()
        filter_hidden(agg, {"pathInput__mypath"})
        assert "mypath" not in agg.path_inputs

    def test_empty_hidden_ids_is_noop(self):
        agg = self._agg()
        before_vars = set(agg.all_var_types)
        filter_hidden(agg, set())
        assert agg.all_var_types == before_vars

    def test_strip_var_type_values_false_preserves_fn_outputs(self):
        """strip_var_type_values=False: hiding an output var must NOT scrub
        it out of fn_outputs — required so wiring_id (computed from
        fn_outputs downstream) stays stable when the caller hides one of a
        function's own output variables."""
        agg = self._agg()
        bp_key = _fkey("bandpass", inputs={"signal": "Raw"}, constants={"hz": 20})
        filter_hidden(agg, {"var__Filtered"}, strip_var_type_values=False)
        assert "Filtered" in agg.fn_outputs.get(bp_key, set())

    def test_strip_var_type_values_false_preserves_fn_input_params(self):
        agg = self._agg()
        bp_key = _fkey("bandpass", inputs={"signal": "Raw"}, constants={"hz": 20})
        filter_hidden(agg, {"var__Raw"}, strip_var_type_values=False)
        assert agg.fn_input_params.get(bp_key, {}).get("signal") == "Raw"

    def test_strip_var_type_values_false_still_removes_all_var_types(self):
        """all_var_types is display-only (never feeds wiring_id) — safe to
        strip regardless of strip_var_type_values."""
        agg = self._agg()
        filter_hidden(agg, {"var__Raw"}, strip_var_type_values=False)
        assert "Raw" not in agg.all_var_types

    def test_strip_var_type_values_false_still_removes_hidden_fn(self):
        """Explicitly-hidden function call sites must still drop out
        regardless of strip_var_type_values — only the VALUE-level var-type
        scrubbing on surviving call sites is gated."""
        agg = self._agg()
        bp_key = _fkey("bandpass", inputs={"signal": "Raw"}, constants={"hz": 20})
        filter_hidden(agg, {fn_node_id(*bp_key)}, strip_var_type_values=False)
        assert bp_key not in agg.fn_input_params
        assert bp_key not in agg.fn_outputs

    def test_hiding_output_var_does_not_change_wiring_id(self):
        """Regression: hiding a function's own output variable node must not
        change the function's wiring_id, or the canvas node loses its saved
        scope placement and vanishes from non-root scopes (the bug this
        param exists to fix)."""
        agg = self._agg()
        bp_key = _fkey("bandpass", inputs={"signal": "Raw"}, constants={"hz": 20})
        before_wid = wiring_id(
            "bandpass",
            agg.fn_input_params[bp_key],
            agg.fn_outputs[bp_key],
        )
        filter_hidden(agg, {"var__Filtered"}, strip_var_type_values=False)
        after_wid = wiring_id(
            "bandpass",
            agg.fn_input_params[bp_key],
            agg.fn_outputs[bp_key],
        )
        assert before_wid == after_wid


# ---------------------------------------------------------------------------
# auto_clean_pending_constants
# ---------------------------------------------------------------------------


class TestAutoCleanPendingConstants:
    def _one_wiring_agg(self, hz_value=20):
        variants = [
            _variant(
                "bandpass",
                "Filtered",
                inputs={"signal": "Raw"},
                constants={"hz": hz_value},
            ),
        ]
        return aggregate_variants(variants, listed_var_names=set())

    def test_removes_value_already_in_db(self):
        pending = {"hz": {"20", "30"}}
        agg = self._one_wiring_agg(hz_value=20)
        cleaned, removals = auto_clean_pending_constants(pending, agg)
        assert "20" not in cleaned["hz"]
        assert "30" in cleaned["hz"]
        assert ("hz", "20") in removals

    def test_nothing_to_clean(self):
        pending = {"hz": {"99"}}
        agg = self._one_wiring_agg(hz_value=20)
        cleaned, removals = auto_clean_pending_constants(pending, agg)
        assert cleaned["hz"] == {"99"}
        assert removals == []

    def test_empty_pending(self):
        agg = self._one_wiring_agg(hz_value=20)
        cleaned, removals = auto_clean_pending_constants({}, agg)
        assert cleaned == {}

    def test_no_consuming_wiring_never_cleans(self):
        """A constant with no real call site yet must never be auto-cleaned —
        an empty required-groups set is a vacuous match, not a real one."""
        pending = {"hz": {"20"}}
        agg = aggregate_variants([], listed_var_names=set())
        cleaned, removals = auto_clean_pending_constants(pending, agg)
        assert cleaned["hz"] == {"20"}
        assert removals == []

    def test_does_not_clean_until_every_sibling_wiring_has_run(self):
        """Regression: two function nodes share a name (compute_rolling_vo2)
        but are wired to different inputs/outputs (RawVO2->RollingVO2 vs.
        RawHeartRate->RollingHR) and both consume the same constant. Once
        ONE wiring runs with the new value, the value must stay pending for
        the OTHER wiring — it hasn't been re-run and would otherwise
        silently drop its (correct) pending/yellow indicator."""
        variants = [
            _variant(
                "compute_rolling_vo2",
                "RollingVO2",
                inputs={"signal": "RawVO2"},
                constants={"window_seconds": 60},
            ),
            _variant(
                "compute_rolling_vo2",
                "RollingHR",
                inputs={"signal": "RawHeartRate"},
                constants={"window_seconds": 30},
            ),
        ]
        agg = aggregate_variants(variants, listed_var_names=set())
        pending = {"window_seconds": {"60"}}
        cleaned, removals = auto_clean_pending_constants(pending, agg)
        assert cleaned["window_seconds"] == {"60"}
        assert removals == []

    def test_cleans_once_every_sibling_wiring_has_run(self):
        """Once BOTH wirings have a real record at the staged value, it's
        safe to auto-clean."""
        variants = [
            _variant(
                "compute_rolling_vo2",
                "RollingVO2",
                inputs={"signal": "RawVO2"},
                constants={"window_seconds": 60},
            ),
            _variant(
                "compute_rolling_vo2",
                "RollingHR",
                inputs={"signal": "RawHeartRate"},
                constants={"window_seconds": 60},
            ),
        ]
        agg = aggregate_variants(variants, listed_var_names=set())
        pending = {"window_seconds": {"60"}}
        cleaned, removals = auto_clean_pending_constants(pending, agg)
        assert cleaned["window_seconds"] == set()
        assert ("window_seconds", "60") in removals


# ---------------------------------------------------------------------------
# pending_value_group_coverage
# ---------------------------------------------------------------------------


class TestPendingValueGroupCoverage:
    def _sibling_wiring_agg(self, *, vo2_hz=60, hr_hz=30):
        """Same fn name, two different wirings (RawVO2->RollingVO2 vs.
        RawHeartRate->RollingHR), sharing the constant `window_seconds` —
        the exact shape from the reported bug: running one shouldn't leave
        it waiting on the other."""
        variants = [
            _variant(
                "compute_rolling_vo2",
                "RollingVO2",
                inputs={"signal": "RawVO2"},
                constants={"window_seconds": vo2_hz},
            ),
            _variant(
                "compute_rolling_vo2",
                "RollingHR",
                inputs={"signal": "RawHeartRate"},
                constants={"window_seconds": hr_hz},
            ),
        ]
        agg = aggregate_variants(variants, listed_var_names=set())
        return agg

    def test_group_coverage_scoped_per_wiring(self):
        agg = self._sibling_wiring_agg(vo2_hz=25, hr_hz=30)
        coverage = pending_value_group_coverage({"window_seconds": {"25"}}, agg)
        covered_groups = coverage[("window_seconds", "25")]
        assert covered_groups == {
            (
                "compute_rolling_vo2",
                wiring_id("compute_rolling_vo2", {"signal": "RawVO2"}, {"RollingVO2"}),
            )
        }

    def test_no_coverage_when_no_wiring_has_run_it(self):
        agg = self._sibling_wiring_agg(vo2_hz=60, hr_hz=30)
        coverage = pending_value_group_coverage({"window_seconds": {"25"}}, agg)
        assert coverage[("window_seconds", "25")] == set()


# ---------------------------------------------------------------------------
# build_variable_nodes
# ---------------------------------------------------------------------------


class TestBuildVariableNodes:
    def test_node_structure(self):
        nodes = build_variable_nodes(
            {"RawEMG"}, record_counts={"RawEMG": 4}, run_states={}
        )
        assert len(nodes) == 1
        n = nodes[0]
        assert n["id"] == "var__RawEMG"
        assert n["type"] == "variableNode"
        assert n["data"]["label"] == "RawEMG"
        assert n["data"]["total_records"] == 4

    def test_run_state_from_map(self):
        nodes = build_variable_nodes({"A"}, {}, run_states={"var__A": "pending"})
        assert nodes[0]["data"]["run_state"] == "pending"

    def test_default_run_state_green(self):
        nodes = build_variable_nodes({"A"}, {}, run_states={})
        assert nodes[0]["data"]["run_state"] == "green"

    def test_sorted_output(self):
        nodes = build_variable_nodes({"C", "A", "B"}, {}, {})
        labels = [n["data"]["label"] for n in nodes]
        assert labels == ["A", "B", "C"]

    def test_zero_records_when_missing(self):
        nodes = build_variable_nodes({"X"}, {}, {})
        assert nodes[0]["data"]["total_records"] == 0


# ---------------------------------------------------------------------------
# build_constant_nodes
# ---------------------------------------------------------------------------


class TestBuildConstantNodes:
    def test_node_structure(self):
        const_counts = {"hz": {"10": 3, "20": 5}}
        nodes = build_constant_nodes(const_counts, pending_constants={})
        assert len(nodes) == 1
        n = nodes[0]
        assert n["id"] == "const__hz"
        assert n["type"] == "constantNode"
        assert n["data"]["label"] == "hz"
        values = {v["value"] for v in n["data"]["values"]}
        assert values == {"10", "20"}

    def test_pending_value_appended(self):
        const_counts = {"hz": {"10": 3}}
        nodes = build_constant_nodes(const_counts, pending_constants={"hz": {"99"}})
        values = {v["value"] for v in nodes[0]["data"]["values"]}
        assert "99" in values

    def test_pending_not_duplicated_if_already_in_counts(self):
        const_counts = {"hz": {"10": 3}}
        nodes = build_constant_nodes(const_counts, pending_constants={"hz": {"10"}})
        values = [v["value"] for v in nodes[0]["data"]["values"]]
        assert values.count("10") == 1

    def test_pending_record_count_is_zero(self):
        const_counts = {"hz": {"10": 3}}
        nodes = build_constant_nodes(const_counts, pending_constants={"hz": {"99"}})
        pending_entry = next(
            v for v in nodes[0]["data"]["values"] if v["value"] == "99"
        )
        assert pending_entry["record_count"] == 0


# ---------------------------------------------------------------------------
# overlay_saved_path_inputs
# ---------------------------------------------------------------------------


class TestOverlaySavedPathInputs:
    def test_updates_existing_entry(self):
        path_inputs = {
            "mypath": {"template": "", "root_folder": None, "functions": {"f"}}
        }
        saved = [{"name": "mypath", "template": "{s}/file.csv", "root_folder": "/data"}]
        result = overlay_saved_path_inputs(path_inputs, saved)
        assert result["mypath"]["template"] == "{s}/file.csv"
        assert result["mypath"]["root_folder"] == "/data"

    def test_adds_new_entry_from_saved(self):
        result = overlay_saved_path_inputs(
            {}, [{"name": "newpath", "template": "{s}/x.csv"}]
        )
        assert "newpath" in result
        assert result["newpath"]["functions"] == set()

    def test_does_not_overwrite_template_if_saved_empty(self):
        path_inputs = {
            "p": {"template": "existing", "root_folder": None, "functions": set()}
        }
        saved = [{"name": "p", "template": "", "root_folder": None}]
        result = overlay_saved_path_inputs(path_inputs, saved)
        # Empty template should not overwrite existing.
        assert result["p"]["template"] == "existing"


# ---------------------------------------------------------------------------
# build_path_input_nodes
# ---------------------------------------------------------------------------


class TestBuildPathInputNodes:
    def test_node_structure(self):
        path_inputs = {
            "mypath": {
                "template": "{s}/f.csv",
                "root_folder": "/data",
                "functions": set(),
            }
        }
        nodes = build_path_input_nodes(path_inputs)
        assert len(nodes) == 1
        n = nodes[0]
        assert n["id"] == "pathInput__mypath"
        assert n["type"] == "pathInputNode"
        assert n["data"]["template"] == "{s}/f.csv"
        assert n["data"]["root_folder"] == "/data"


# ---------------------------------------------------------------------------
# build_function_nodes
# ---------------------------------------------------------------------------


class TestBuildFunctionNodes:
    BP_CID = _cid("bp-test")
    BP_KEY = ("bandpass", BP_CID)
    BP_NODE = f"fn__bandpass__{BP_CID}"

    def _make(self, **overrides):
        defaults = {
            "fn_input_params": {self.BP_KEY: {"signal": "Raw"}},
            "fn_outputs": {self.BP_KEY: {"Filtered"}},
            "fn_constants": {self.BP_KEY: {"hz"}},
            "fn_variants_map": {self.BP_KEY: []},
            "fn_params_map": {"bandpass": ["signal", "hz"]},
            "run_states": {self.BP_NODE: "green"},
            "matlab_functions": set(),
            "saved_configs": {"bandpass": None},
        }
        defaults.update(overrides)
        return build_function_nodes(**defaults)

    def test_node_structure(self):
        nodes = self._make()
        assert len(nodes) == 1
        n = nodes[0]
        assert n["id"] == self.BP_NODE
        assert n["type"] == "functionNode"
        assert n["data"]["label"] == "bandpass"
        assert n["data"]["call_id"] == self.BP_CID

    def test_run_state_applied(self):
        nodes = self._make(run_states={self.BP_NODE: "pending"})
        assert nodes[0]["data"]["run_state"] == "pending"

    def test_matlab_language_flag(self):
        nodes = self._make(matlab_functions={"bandpass"})
        assert nodes[0]["data"]["language"] == "matlab"

    def test_non_matlab_has_no_language_flag(self):
        nodes = self._make()
        assert "language" not in nodes[0]["data"]

    def test_saved_config_applied(self):
        nodes = self._make(
            saved_configs={"bandpass": {"schemaFilter": {"subject": [1]}}}
        )
        assert nodes[0]["data"]["schemaFilter"] == {"subject": [1]}

    def test_unknown_param_filled_with_empty_string(self):
        nodes = self._make(
            fn_input_params={self.BP_KEY: {"signal": "Raw"}},
            fn_constants={},
            fn_params_map={"bandpass": ["signal", "low_hz"]},
        )
        assert nodes[0]["data"]["input_params"].get("low_hz") == ""

    def test_output_types_sorted(self):
        nodes = self._make(fn_outputs={self.BP_KEY: {"C", "A", "B"}})
        assert nodes[0]["data"]["output_types"] == ["A", "B", "C"]

    def test_constant_params_ordered_by_signature_not_alphabetically(self):
        # Regression: compute_rolling_vo2(signal, window_seconds, sample_interval)
        # — alphabetical sort would put sample_interval before window_seconds,
        # flipping the order from what the manual (pre-run) node showed.
        nodes = self._make(
            fn_constants={self.BP_KEY: {"window_seconds", "sample_interval"}},
            fn_params_map={"bandpass": ["signal", "window_seconds", "sample_interval"]},
        )
        assert nodes[0]["data"]["constant_params"] == [
            "window_seconds",
            "sample_interval",
        ]

    def test_input_params_ordered_by_signature_not_alphabetically(self):
        nodes = self._make(
            fn_input_params={self.BP_KEY: {"zeta": "Z", "alpha": "A"}},
            fn_constants={},
            fn_params_map={"bandpass": ["zeta", "alpha"]},
        )
        assert list(nodes[0]["data"]["input_params"].keys()) == ["zeta", "alpha"]

    def test_two_call_sites_produce_two_nodes(self):
        cid_a, cid_b = _cid("a"), _cid("b")
        ka, kb = ("bandpass", cid_a), ("bandpass", cid_b)
        nodes = build_function_nodes(
            fn_input_params={ka: {"signal": "Raw"}, kb: {"signal": "Raw"}},
            fn_outputs={ka: {"Filtered"}, kb: {"Filtered"}},
            fn_constants={ka: {"hz"}, kb: {"hz"}},
            fn_variants_map={
                ka: [{"constants": {"hz": 20}}],
                kb: [{"constants": {"hz": 50}}],
            },
            fn_params_map={"bandpass": ["signal", "hz"]},
            run_states={
                f"fn__bandpass__{cid_a}": "green",
                f"fn__bandpass__{cid_b}": "red",
            },
            matlab_functions=set(),
            saved_configs={"bandpass": None},
        )
        ids = {n["id"] for n in nodes}
        assert ids == {f"fn__bandpass__{cid_a}", f"fn__bandpass__{cid_b}"}
        states = {n["id"]: n["data"]["run_state"] for n in nodes}
        assert states[f"fn__bandpass__{cid_a}"] == "green"
        assert states[f"fn__bandpass__{cid_b}"] == "red"


# ---------------------------------------------------------------------------
# build_edges
# ---------------------------------------------------------------------------


class TestBuildEdges:
    F_CID = _cid("f-call")
    F_KEY = ("f", F_CID)
    F_NODE = f"fn__f__{F_CID}"

    def test_var_to_fn_edge(self):
        edges = build_edges(
            fn_input_params={self.F_KEY: {"signal": "Raw"}},
            fn_outputs={self.F_KEY: set()},
            const_fns={},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
        )
        assert any(
            e["source"] == "var__Raw" and e["target"] == self.F_NODE for e in edges
        )

    def test_fn_to_var_edge(self):
        edges = build_edges(
            fn_input_params={},
            fn_outputs={self.F_KEY: {"Out"}},
            const_fns={},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
        )
        assert any(
            e["source"] == self.F_NODE and e["target"] == "var__Out" for e in edges
        )

    def test_const_to_fn_edge(self):
        edges = build_edges(
            fn_input_params={},
            fn_outputs={},
            const_fns={"hz": {self.F_KEY}},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
        )
        assert any(
            e["source"] == "const__hz" and e["target"] == self.F_NODE for e in edges
        )

    def test_path_input_to_fn_edge(self):
        edges = build_edges(
            fn_input_params={},
            fn_outputs={},
            const_fns={},
            path_inputs={
                "mypath": {
                    "template": "",
                    "root_folder": None,
                    "functions": {self.F_KEY},
                }
            },
            manual_edges=[],
            hidden_ids=set(),
        )
        assert any(
            e["source"] == "pathInput__mypath" and e["target"] == self.F_NODE
            for e in edges
        )

    def test_manual_edge_included(self):
        me = {
            "id": "manual-1",
            "source": "uuid-var",
            "target": self.F_NODE,
            "sourceHandle": "",
            "targetHandle": "in__x",
        }
        edges = build_edges({}, {}, {}, {}, [me], set())
        assert any(e["id"] == "manual-1" for e in edges)

    def test_manual_edge_skipped_if_hidden(self):
        me = {
            "id": "manual-1",
            "source": "uuid-var",
            "target": self.F_NODE,
            "sourceHandle": "",
            "targetHandle": "",
        }
        edges = build_edges({}, {}, {}, {}, [me], hidden_ids={"uuid-var"})
        assert not any(e["id"] == "manual-1" for e in edges)

    def test_no_duplicate_edges(self):
        # Same var→fn from two params should only produce one edge.
        edges = build_edges(
            fn_input_params={self.F_KEY: {"a": "Raw", "b": "Raw"}},
            fn_outputs={},
            const_fns={},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
        )
        var_to_fn = [
            e for e in edges if e["source"] == "var__Raw" and e["target"] == self.F_NODE
        ]
        assert len(var_to_fn) == 1

    def test_manual_edge_not_duplicated_if_already_in_db_edges(self):
        edge_id = f"e__Raw__f__{self.F_CID}"
        edges = build_edges(
            fn_input_params={self.F_KEY: {"signal": "Raw"}},
            fn_outputs={},
            const_fns={},
            path_inputs={},
            manual_edges=[
                {
                    "id": edge_id,
                    "source": "var__Raw",
                    "target": self.F_NODE,
                    "sourceHandle": "",
                    "targetHandle": "in__signal",
                }
            ],
            hidden_ids=set(),
        )
        matching = [e for e in edges if e["id"] == edge_id]
        assert len(matching) == 1

    def test_two_call_sites_produce_distinct_edges_to_same_input(self):
        cid_a, cid_b = _cid("a"), _cid("b")
        ka, kb = ("f", cid_a), ("f", cid_b)
        edges = build_edges(
            fn_input_params={ka: {"signal": "Raw"}, kb: {"signal": "Raw"}},
            fn_outputs={ka: {"Out"}, kb: {"Out"}},
            const_fns={},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
        )
        targets = {
            e["target"]
            for e in edges
            if e["source"] == "var__Raw" and e["target"].startswith("fn__f__")
        }
        assert targets == {f"fn__f__{cid_a}", f"fn__f__{cid_b}"}

    # --- hidden_edge_ids: excluded from rendering, never affects other categories ---

    def test_hidden_var_to_fn_edge_excluded(self):
        edges = build_edges(
            fn_input_params={self.F_KEY: {"signal": "Raw"}},
            fn_outputs={},
            const_fns={},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
            hidden_edge_ids={f"e__Raw__f__{self.F_CID}"},
        )
        assert not any(e["source"] == "var__Raw" for e in edges)

    def test_hidden_fn_to_var_edge_excluded(self):
        edges = build_edges(
            fn_input_params={},
            fn_outputs={self.F_KEY: {"Out"}},
            const_fns={},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
            hidden_edge_ids={f"e__f__{self.F_CID}__Out"},
        )
        assert not any(e["target"] == "var__Out" for e in edges)

    def test_hidden_const_to_fn_edge_excluded(self):
        edges = build_edges(
            fn_input_params={},
            fn_outputs={},
            const_fns={"hz": {self.F_KEY}},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
            hidden_edge_ids={f"e__hz__f__{self.F_CID}"},
        )
        assert not any(e["source"] == "const__hz" for e in edges)

    def test_hidden_path_input_to_fn_edge_excluded(self):
        edges = build_edges(
            fn_input_params={},
            fn_outputs={},
            const_fns={},
            path_inputs={
                "mypath": {
                    "template": "",
                    "root_folder": None,
                    "functions": {self.F_KEY},
                }
            },
            manual_edges=[],
            hidden_ids=set(),
            hidden_edge_ids={f"e__mypath__f__{self.F_CID}"},
        )
        assert not any(e["source"] == "pathInput__mypath" for e in edges)

    def test_hidden_edge_id_only_excludes_matching_edge(self):
        # Hiding the var->fn edge id must not touch the const->fn edge on
        # the SAME function.
        edges = build_edges(
            fn_input_params={self.F_KEY: {"signal": "Raw"}},
            fn_outputs={},
            const_fns={"hz": {self.F_KEY}},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
            hidden_edge_ids={f"e__Raw__f__{self.F_CID}"},
        )
        assert not any(e["source"] == "var__Raw" for e in edges)
        assert any(e["source"] == "const__hz" for e in edges)

    def test_hidden_edge_ids_none_defaults_to_no_filtering(self):
        edges = build_edges(
            fn_input_params={self.F_KEY: {"signal": "Raw"}},
            fn_outputs={},
            const_fns={},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
        )
        assert any(e["source"] == "var__Raw" for e in edges)


# ---------------------------------------------------------------------------
# Disconnected wirings — hidden_wirings, wiring_disconnected_fkeys,
# wirings_downstream_of, candidate_edge_id, inbound_edge_candidates
# ---------------------------------------------------------------------------


class TestInboundEdgeCandidates:
    def test_builds_all_three_categories(self):
        ids = inbound_edge_candidates(
            "f", "wid123", var_types=["Raw"], const_names=["hz"], path_names=["p"]
        )
        assert ids == ["e__Raw__f__wid123", "e__hz__f__wid123", "e__p__f__wid123"]

    def test_empty_by_default(self):
        assert inbound_edge_candidates("f", "wid123") == []


class TestHiddenWirings:
    F_CID = _cid("f-call")
    F_KEY = ("f", F_CID)

    def test_hidden_var_input_marks_wiring(self):
        wid = wiring_id("f", {"signal": "Raw"}, set())
        result = hidden_wirings(
            fn_input_params={self.F_KEY: {"signal": "Raw"}},
            fn_outputs={},
            fn_constants={},
            path_inputs={},
            hidden_edge_ids={f"e__Raw__f__{wid}"},
        )
        assert result == {("f", wid)}

    def test_hidden_const_input_marks_wiring(self):
        wid = wiring_id("f", {}, set())
        result = hidden_wirings(
            fn_input_params={self.F_KEY: {}},
            fn_outputs={},
            fn_constants={self.F_KEY: {"hz"}},
            path_inputs={},
            hidden_edge_ids={f"e__hz__f__{wid}"},
        )
        assert result == {("f", wid)}

    def test_hidden_path_input_marks_wiring(self):
        wid = wiring_id("f", {}, set())
        result = hidden_wirings(
            fn_input_params={self.F_KEY: {}},
            fn_outputs={},
            fn_constants={},
            path_inputs={"mypath": {"functions": {self.F_KEY}}},
            hidden_edge_ids={f"e__mypath__f__{wid}"},
        )
        assert result == {("f", wid)}

    def test_hidden_output_edge_does_not_mark_wiring(self):
        # fn -> var (output) hides are cosmetic only — never disconnect.
        wid = wiring_id("f", {}, {"Out"})
        result = hidden_wirings(
            fn_input_params={self.F_KEY: {}},
            fn_outputs={self.F_KEY: {"Out"}},
            fn_constants={},
            path_inputs={},
            hidden_edge_ids={f"e__f__{wid}__Out"},
        )
        assert result == set()

    def test_no_hidden_edges_is_empty(self):
        result = hidden_wirings(
            fn_input_params={self.F_KEY: {"signal": "Raw"}},
            fn_outputs={},
            fn_constants={},
            path_inputs={},
            hidden_edge_ids=set(),
        )
        assert result == set()

    def test_every_call_site_of_a_wiring_recomputes_same_wiring(self):
        # Two call sites (different constant values) of the SAME wiring —
        # hiding the shared var input marks the wiring once, not per-call-site.
        ka, kb = ("f", _cid("a")), ("f", _cid("b"))
        wid = wiring_id("f", {"signal": "Raw"}, set())
        result = hidden_wirings(
            fn_input_params={ka: {"signal": "Raw"}, kb: {"signal": "Raw"}},
            fn_outputs={},
            fn_constants={},
            path_inputs={},
            hidden_edge_ids={f"e__Raw__f__{wid}"},
        )
        assert result == {("f", wid)}

    def test_manual_reconnect_to_same_handle_clears_disconnected(self):
        # A manual edge onto the SAME handle (in__signal) a hidden inbound
        # edge used to feed — even with a DIFFERENT source variable — must
        # clear the disconnected state (the "stuck disconnected" bug).
        wid = wiring_id("f", {"signal": "Raw"}, set())
        result = hidden_wirings(
            fn_input_params={self.F_KEY: {"signal": "Raw"}},
            fn_outputs={},
            fn_constants={},
            path_inputs={},
            hidden_edge_ids={f"e__Raw__f__{wid}"},
            manual_edges=[
                {
                    "target": fn_node_id("f", wid),
                    "targetHandle": "in__signal",
                    "source": "var__Other",
                }
            ],
        )
        assert result == set()

    def test_manual_reconnect_to_different_handle_stays_disconnected(self):
        # A manual edge onto an UNRELATED handle does not cover the hidden
        # one — the wiring must stay disconnected.
        wid = wiring_id("f", {"signal": "Raw"}, set())
        result = hidden_wirings(
            fn_input_params={self.F_KEY: {"signal": "Raw"}},
            fn_outputs={},
            fn_constants={},
            path_inputs={},
            hidden_edge_ids={f"e__Raw__f__{wid}"},
            manual_edges=[
                {
                    "target": fn_node_id("f", wid),
                    "targetHandle": "in__other_param",
                    "source": "var__Other",
                }
            ],
        )
        assert result == {("f", wid)}

    def test_partial_reconnection_stays_disconnected(self):
        # Two hidden handles (var + const); only the var one is covered by
        # a manual edge. The wiring must stay disconnected until BOTH are.
        wid = wiring_id("f", {"signal": "Raw"}, set())
        result = hidden_wirings(
            fn_input_params={self.F_KEY: {"signal": "Raw"}},
            fn_outputs={},
            fn_constants={self.F_KEY: {"hz"}},
            path_inputs={},
            hidden_edge_ids={f"e__Raw__f__{wid}", f"e__hz__f__{wid}"},
            manual_edges=[
                {
                    "target": fn_node_id("f", wid),
                    "targetHandle": "in__signal",
                    "source": "var__Other",
                }
            ],
        )
        assert result == {("f", wid)}

    def test_manual_edge_scope_suffixed_target_still_matches(self):
        # A manual edge targeting a scope-placed node id (canonical id ::
        # pipeline_id) must still be recognized as covering the handle.
        wid = wiring_id("f", {"signal": "Raw"}, set())
        result = hidden_wirings(
            fn_input_params={self.F_KEY: {"signal": "Raw"}},
            fn_outputs={},
            fn_constants={},
            path_inputs={},
            hidden_edge_ids={f"e__Raw__f__{wid}"},
            manual_edges=[
                {
                    "target": f"{fn_node_id('f', wid)}::pipe_xyz",
                    "targetHandle": "in__signal",
                    "source": "var__Other",
                }
            ],
        )
        assert result == set()


class TestWiringDisconnectedFkeys:
    def test_maps_wirings_back_to_call_sites(self):
        ka, kb = ("f", _cid("a")), ("f", _cid("b"))
        wid = wiring_id("f", {"signal": "Raw"}, set())
        result = wiring_disconnected_fkeys(
            fn_input_params={ka: {"signal": "Raw"}, kb: {"signal": "Raw"}},
            fn_outputs={},
            wirings={("f", wid)},
        )
        assert result == {ka, kb}

    def test_unrelated_wiring_not_included(self):
        ka = ("f", _cid("a"))
        other_wid = wiring_id("f", {"signal": "Other"}, set())
        result = wiring_disconnected_fkeys(
            fn_input_params={ka: {"signal": "Raw"}},
            fn_outputs={},
            wirings={("f", other_wid)},
        )
        assert result == set()

    def test_empty_wirings_is_empty(self):
        result = wiring_disconnected_fkeys(
            fn_input_params={("f", _cid()): {}}, fn_outputs={}, wirings=set()
        )
        assert result == set()


class TestWiringsDownstreamOf:
    def test_direct_consumer_marked_downstream(self):
        a_key, b_key = ("A", _cid("a")), ("B", _cid("b"))
        wid_a = wiring_id("A", {}, {"Out"})
        wid_b = wiring_id("B", {"x": "Out"}, set())
        result = wirings_downstream_of(
            fn_input_params={a_key: {}, b_key: {"x": "Out"}},
            fn_outputs={a_key: {"Out"}, b_key: set()},
            seed_wirings={("A", wid_a)},
        )
        assert result == {("B", wid_b)}

    def test_transitive_chain_marked_downstream(self):
        a_key = ("A", _cid("a"))
        b_key = ("B", _cid("b"))
        c_key = ("C", _cid("c"))
        wid_a = wiring_id("A", {}, {"Mid"})
        wid_b = wiring_id("B", {"x": "Mid"}, {"Final"})
        wid_c = wiring_id("C", {"y": "Final"}, set())
        result = wirings_downstream_of(
            fn_input_params={a_key: {}, b_key: {"x": "Mid"}, c_key: {"y": "Final"}},
            fn_outputs={a_key: {"Mid"}, b_key: {"Final"}, c_key: set()},
            seed_wirings={("A", wid_a)},
        )
        assert result == {("B", wid_b), ("C", wid_c)}

    def test_seed_itself_excluded_from_result(self):
        # A both produces AND consumes "Out" (self-referencing wiring) — a
        # naive BFS would re-add the seed to its own downstream set.
        a_key = ("A", _cid("a"))
        wid_a = wiring_id("A", {"x": "Out"}, {"Out"})
        result = wirings_downstream_of(
            fn_input_params={a_key: {"x": "Out"}},
            fn_outputs={a_key: {"Out"}},
            seed_wirings={("A", wid_a)},
        )
        assert result == set()

    def test_unrelated_wiring_not_marked(self):
        a_key = ("A", _cid("a"))
        unrelated_key = ("U", _cid("u"))
        wid_a = wiring_id("A", {}, {"Out"})
        wid_u = wiring_id("U", {}, {"Unrelated"})
        result = wirings_downstream_of(
            fn_input_params={a_key: {}, unrelated_key: {}},
            fn_outputs={a_key: {"Out"}, unrelated_key: {"Unrelated"}},
            seed_wirings={("A", wid_a)},
        )
        assert ("U", wid_u) not in result

    def test_empty_seed_is_empty(self):
        assert wirings_downstream_of({}, {}, set()) == set()


class TestCandidateEdgeId:
    F_CID = _cid("f-call")
    F_NODE = f"fn__f__{F_CID}"

    def test_var_to_fn(self):
        assert candidate_edge_id("var__Raw", self.F_NODE) == f"e__Raw__f__{self.F_CID}"

    def test_const_to_fn(self):
        assert candidate_edge_id("const__hz", self.F_NODE) == f"e__hz__f__{self.F_CID}"

    def test_path_input_to_fn(self):
        assert (
            candidate_edge_id("pathInput__mypath", self.F_NODE)
            == f"e__mypath__f__{self.F_CID}"
        )

    def test_fn_to_var(self):
        assert (
            candidate_edge_id(self.F_NODE, "var__Out") == f"e__f__{self.F_CID}__Out"
        )

    def test_matches_build_edges_own_id_construction(self):
        # candidate_edge_id must never drift from what build_edges actually
        # produces — round-trip through a real build_edges call.
        f_key = ("f", self.F_CID)
        edges = build_edges(
            fn_input_params={f_key: {"signal": "Raw"}},
            fn_outputs={},
            const_fns={},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
        )
        real_id = next(e["id"] for e in edges if e["source"] == "var__Raw")
        assert candidate_edge_id("var__Raw", self.F_NODE) == real_id

    def test_placement_qualified_target_stripped(self):
        placed = f"{self.F_NODE}::main"
        assert (
            candidate_edge_id("var__Raw", placed) == f"e__Raw__f__{self.F_CID}"
        )

    def test_two_opaque_ids_returns_none(self):
        assert candidate_edge_id("uuid-a", "uuid-b") is None

    def test_var_to_non_fn_target_returns_none(self):
        assert candidate_edge_id("var__Raw", "const__hz") is None

    def test_two_fn_nodes_returns_none(self):
        assert candidate_edge_id(self.F_NODE, f"fn__g__{_cid('g')}") is None


# ---------------------------------------------------------------------------
# build_manual_node
# ---------------------------------------------------------------------------


class TestBuildManualNode:
    def test_variable_node(self):
        n = build_manual_node(
            "uuid-1",
            {"type": "variableNode", "label": "MyVar", "config": None},
            pending_constants={},
            manual_fn_state=None,
            resolved_input_params=None,
            resolved_output_types=None,
            matlab_functions=set(),
        )
        assert n["id"] == "uuid-1"
        assert n["type"] == "variableNode"
        assert n["data"]["run_state"] == "red"
        assert n["data"]["total_records"] == 0

    def test_constant_node_with_pending(self):
        n = build_manual_node(
            "uuid-2",
            {"type": "constantNode", "label": "hz", "config": None},
            pending_constants={"hz": {"42"}},
            manual_fn_state=None,
            resolved_input_params=None,
            resolved_output_types=None,
            matlab_functions=set(),
        )
        assert n["type"] == "constantNode"
        vals = {v["value"] for v in n["data"]["values"]}
        assert "42" in vals

    def test_function_node(self):
        n = build_manual_node(
            "uuid-3",
            {"type": "functionNode", "label": "my_fn", "config": None},
            pending_constants={},
            manual_fn_state="pending",
            resolved_input_params={"signal": "Raw"},
            resolved_output_types=["Filtered"],
            matlab_functions=set(),
        )
        assert n["type"] == "functionNode"
        assert n["data"]["run_state"] == "pending"
        assert n["data"]["input_params"] == {"signal": "Raw"}
        assert n["data"]["output_types"] == ["Filtered"]

    def test_function_node_matlab_language(self):
        n = build_manual_node(
            "uuid-4",
            {"type": "functionNode", "label": "my_fn", "config": None},
            pending_constants={},
            manual_fn_state="red",
            resolved_input_params={},
            resolved_output_types=[],
            matlab_functions={"my_fn"},
        )
        assert n["data"]["language"] == "matlab"

    def test_path_input_node(self):
        n = build_manual_node(
            "uuid-5",
            {"type": "pathInputNode", "label": "mypath", "config": None},
            pending_constants={},
            manual_fn_state=None,
            resolved_input_params=None,
            resolved_output_types=None,
            matlab_functions=set(),
        )
        assert n["type"] == "pathInputNode"
        assert n["data"]["template"] == ""

    def test_function_node_default_state_red(self):
        n = build_manual_node(
            "uuid-6",
            {"type": "functionNode", "label": "fn", "config": None},
            pending_constants={},
            manual_fn_state=None,
            resolved_input_params={},
            resolved_output_types=[],
            matlab_functions=set(),
        )
        assert n["data"]["run_state"] == "red"


# ---------------------------------------------------------------------------
# merge_manual_nodes
# ---------------------------------------------------------------------------


class TestMergeManualNodes:
    def _db_node(self, node_id, ntype, label):
        return {"id": node_id, "type": ntype, "data": {"label": label}}

    def test_manual_node_not_in_db_added(self):
        existing = [self._db_node("var__Raw", "variableNode", "Raw")]
        manual = {"uuid-new": {"type": "variableNode", "label": "NewVar"}}
        to_add, _ = merge_manual_nodes(existing, manual, saved_positions={})
        assert "uuid-new" in to_add

    def test_manual_node_already_in_db_skipped(self):
        existing = [self._db_node("var__Raw", "variableNode", "Raw")]
        manual = {"var__Raw": {"type": "variableNode", "label": "Raw"}}
        to_add, _ = merge_manual_nodes(existing, manual, saved_positions={})
        assert "var__Raw" not in to_add

    def test_graduated_node_produces_graduation_action(self):
        """Graduation targets the manual node's OWN placement
        (canonical_id::pipeline_id), not the bare canonical id — this is
        what lets two same-label manual nodes in different scopes
        graduate independently instead of racing for one shared slot."""
        existing = [self._db_node("var__Raw", "variableNode", "Raw")]
        manual = {"uuid-old": {"type": "variableNode", "label": "Raw", "pipeline_id": "main"}}
        to_add, graduations = merge_manual_nodes(existing, manual, saved_positions={})
        assert "uuid-old" not in to_add
        assert len(graduations) == 1
        assert graduations[0].old_id == "uuid-old"
        assert graduations[0].new_id == "var__Raw::main"

    def test_graduation_skipped_if_own_placement_already_exists(self):
        # If THIS scope's placement is already positioned, do not re-graduate.
        existing = [self._db_node("var__Raw", "variableNode", "Raw")]
        manual = {"uuid-old": {"type": "variableNode", "label": "Raw", "pipeline_id": "main"}}
        to_add, graduations = merge_manual_nodes(
            existing, manual, saved_positions={"var__Raw::main": {"x": 10, "y": 20}}
        )
        assert "uuid-old" in to_add
        assert len(graduations) == 0

    def test_same_label_different_scopes_graduate_independently(self):
        """The core regression test for the placement rework: two manual
        nodes with the SAME label in DIFFERENT scopes (e.g. a duplicated
        pipeline re-running identical, unedited wiring) must both
        graduate to their OWN placement, not collide over one shared slot
        (the bug: an earlier design stole the position from whichever
        scope claimed it second)."""
        existing = [self._db_node("var__Raw", "variableNode", "Raw")]
        manual = {
            "uuid-a": {"type": "variableNode", "label": "Raw", "pipeline_id": "main"},
            "uuid-b": {"type": "variableNode", "label": "Raw", "pipeline_id": "pipe_dup"},
        }
        to_add, graduations = merge_manual_nodes(existing, manual, saved_positions={})
        assert to_add == []
        assert len(graduations) == 2
        new_ids = {g.new_id for g in graduations}
        assert new_ids == {"var__Raw::main", "var__Raw::pipe_dup"}

    def test_empty_manual_nodes(self):
        existing = [self._db_node("var__Raw", "variableNode", "Raw")]
        to_add, graduations = merge_manual_nodes(existing, {}, saved_positions={})
        assert to_add == []
        assert graduations == []

    def test_function_graduation_with_single_call_site(self):
        """One DB-derived call site → manual fn graduates to that call_id
        (as its own placement in its own scope)."""
        cid = _cid("only")
        existing = [self._db_node(f"fn__bp__{cid}", "functionNode", "bp")]
        manual = {"uuid-old": {"type": "functionNode", "label": "bp", "pipeline_id": "main"}}
        to_add, graduations = merge_manual_nodes(existing, manual, saved_positions={})
        assert "uuid-old" not in to_add
        assert len(graduations) == 1
        assert graduations[0].new_id == f"fn__bp__{cid}::main"

    def test_function_no_graduation_when_multiple_call_sites(self):
        """Multiple DB-derived call sites for the same fn → manual node stays
        independent (we cannot pick a canonical target unambiguously)."""
        cid_a, cid_b = _cid("a"), _cid("b")
        existing = [
            self._db_node(f"fn__bp__{cid_a}", "functionNode", "bp"),
            self._db_node(f"fn__bp__{cid_b}", "functionNode", "bp"),
        ]
        manual = {"uuid-old": {"type": "functionNode", "label": "bp"}}
        to_add, graduations = merge_manual_nodes(existing, manual, saved_positions={})
        assert "uuid-old" in to_add
        assert graduations == []


# ---------------------------------------------------------------------------
# MATLAB param-name handles (Fix B)
# ---------------------------------------------------------------------------


class TestMatlabParamNameHandles:
    """Exercises the path where MATLAB param names differ from Variable class
    names (e.g. ``output1 → Result``), to prove the graph_builder uses the
    explicit mapping rather than any naming convention."""

    EX_CID = _cid("fn_ex-call")
    EX_KEY = ("fn_ex", EX_CID)
    EX_NODE = f"fn__fn_ex__{EX_CID}"

    def _make_nodes(self, **overrides):
        defaults = {
            "fn_input_params": {self.EX_KEY: {}},
            "fn_outputs": {self.EX_KEY: {"Result"}},
            "fn_constants": {self.EX_KEY: set()},
            "fn_variants_map": {self.EX_KEY: []},
            "fn_params_map": {"fn_ex": []},
            "run_states": {},
            "matlab_functions": {"fn_ex"},
            "saved_configs": {"fn_ex": None},
            "matlab_output_order": {"fn_ex": ["output1"]},
            "matlab_param_to_class": {"fn_ex": {"output1": "Result"}},
        }
        defaults.update(overrides)
        return build_function_nodes(**defaults)

    def test_handles_use_param_name_not_class_name(self):
        nodes = self._make_nodes()
        assert nodes[0]["data"]["output_types"] == ["output1"]

    def test_edges_use_param_name_in_source_handle(self):
        edges = build_edges(
            fn_input_params={},
            fn_outputs={self.EX_KEY: {"Result"}},
            const_fns={},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
            matlab_param_to_class={"fn_ex": {"output1": "Result"}},
        )
        fn_to_var = [e for e in edges if e.get("source") == self.EX_NODE]
        assert len(fn_to_var) == 1
        assert fn_to_var[0]["target"] == "var__Result"
        assert fn_to_var[0]["sourceHandle"] == "out__output1"

    def test_multi_output_preserves_signature_order(self):
        cid = _cid("load_csv-call")
        key = ("load_csv", cid)
        nodes = build_function_nodes(
            fn_input_params={key: {}},
            fn_outputs={key: {"Time", "Force_Left", "Force_Right"}},
            fn_constants={key: set()},
            fn_variants_map={key: []},
            fn_params_map={"load_csv": []},
            run_states={},
            matlab_functions={"load_csv"},
            saved_configs={"load_csv": None},
            matlab_output_order={"load_csv": ["time", "force_left", "force_right"]},
            matlab_param_to_class={
                "load_csv": {
                    "time": "Time",
                    "force_left": "Force_Left",
                    "force_right": "Force_Right",
                }
            },
        )
        assert nodes[0]["data"]["output_types"] == ["time", "force_left", "force_right"]

    def test_non_matlab_fn_unaffected(self):
        cid = _cid("py-call")
        key = ("py_fn", cid)
        edges = build_edges(
            fn_input_params={},
            fn_outputs={key: {"Out"}},
            const_fns={},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
            matlab_param_to_class={},
        )
        node_id = f"fn__py_fn__{cid}"
        fn_to_var = [e for e in edges if e.get("source") == node_id]
        assert fn_to_var[0]["sourceHandle"] == "out__Out"

    def test_unmapped_class_falls_back_to_class_handle(self):
        edges = build_edges(
            fn_input_params={},
            fn_outputs={self.EX_KEY: {"Unmapped"}},
            const_fns={},
            path_inputs={},
            manual_edges=[],
            hidden_ids=set(),
            matlab_param_to_class={"fn_ex": {}},
        )
        fn_to_var = [e for e in edges if e.get("source") == self.EX_NODE]
        assert fn_to_var[0]["sourceHandle"] == "out__Unmapped"


# ---------------------------------------------------------------------------
# Wiring grouping (group_call_sites_by_wiring + migration helpers)
# ---------------------------------------------------------------------------

from scistack_gui.domain.graph_builder import (  # noqa: E402
    group_call_sites_by_wiring,
    legacy_edge_rewrites,
    legacy_position_adoptions,
    wiring_id,
)


def _two_site_agg():
    """Two call sites of one fn differing ONLY in a constant value."""
    agg = AggregatedData()
    a = ("bp", "a" * 16)
    b = ("bp", "b" * 16)
    for fkey, hz in ((a, 20), (b, 50)):
        agg.fn_input_params[fkey] = {"signal": "Raw"}
        agg.fn_outputs[fkey] = {"Filtered"}
        agg.fn_constants[fkey] = {"low_hz"}
        agg.fn_variants_map[fkey] = [{"constants": {"low_hz": hz}}]
    agg.const_fns["low_hz"] = {a, b}
    agg.all_var_types = {"Raw", "Filtered"}
    return agg, a, b


class TestWiringId:
    def test_deterministic_and_constant_independent(self):
        wid = wiring_id("bp", {"signal": "Raw"}, {"Filtered"})
        assert wid == wiring_id("bp", {"signal": "Raw"}, {"Filtered"})
        assert len(wid) == 16

    def test_different_wiring_different_id(self):
        base = wiring_id("bp", {"signal": "Raw"}, {"Filtered"})
        assert wiring_id("bp", {"signal": "Other"}, {"Filtered"}) != base
        assert wiring_id("bp", {"signal": "Raw"}, {"Smoothed"}) != base
        assert wiring_id("other", {"signal": "Raw"}, {"Filtered"}) != base


class TestGroupCallSitesByWiring:
    def test_same_wiring_groups_to_one_key(self):
        agg, a, b = _two_site_agg()
        states = {
            fn_node_id(*a): "green",
            fn_node_id(*b): "red",
            "var__Filtered": "red",
        }

        grouped, node_states, member_map = group_call_sites_by_wiring(agg, states)

        wid = wiring_id("bp", {"signal": "Raw"}, {"Filtered"})
        gkey = ("bp", wid)
        assert list(grouped.fn_input_params) == [gkey]
        # Variant rows keep per-call-site call_id and state.
        rows = grouped.fn_variants_map[gkey]
        by_hz = {r["constants"]["low_hz"]: r for r in rows}
        assert by_hz[20]["state"] == "green" and by_hz[20]["call_id"] == "a" * 16
        assert by_hz[50]["state"] == "red" and by_hz[50]["call_id"] == "b" * 16
        # Node state = worst member; var states pass through.
        assert node_states[fn_node_id("bp", wid)] == "red"
        assert node_states["var__Filtered"] == "red"
        # const edge targets re-keyed to the group.
        assert grouped.const_fns["low_hz"] == {gkey}
        # member map records both legacy ids.
        assert set(member_map[fn_node_id("bp", wid)]) == {
            fn_node_id(*a),
            fn_node_id(*b),
        }

    def test_different_wiring_stays_separate(self):
        agg = AggregatedData()
        k1 = ("bp", "a" * 16)
        k2 = ("bp", "b" * 16)
        agg.fn_input_params[k1] = {"signal": "Raw"}
        agg.fn_outputs[k1] = {"Filtered"}
        agg.fn_input_params[k2] = {"signal": "Other"}
        agg.fn_outputs[k2] = {"Filtered"}

        grouped, _, _ = group_call_sites_by_wiring(agg, {})

        assert len(grouped.fn_input_params) == 2

    def test_staged_pending_value_synthesizes_row_and_pending_state(self):
        agg, a, b = _two_site_agg()
        states = {fn_node_id(*a): "green", fn_node_id(*b): "green"}

        grouped, node_states, _ = group_call_sites_by_wiring(
            agg, states, pending_constants={"low_hz": {"99"}}
        )

        wid = wiring_id("bp", {"signal": "Raw"}, {"Filtered"})
        rows = grouped.fn_variants_map[("bp", wid)]
        staged = [r for r in rows if r.get("staged")]
        assert staged == [
            {"constants": {"low_hz": "99"}, "state": "pending", "staged": True}
        ]
        # A green group with a staged value downgrades to pending, not red.
        assert node_states[fn_node_id("bp", wid)] == "pending"

    def test_group_already_covering_staged_value_stays_green(self):
        """Regression for the bug where running one of two compute_rolling_vo2
        nodes (sharing a constant, different signals) left it stuck on
        "pending" until the sibling node was also (re)run. Once a group's
        OWN real member already recorded the newly-staged value, that
        group must not get a synthesized pending row for it — only the
        sibling wiring that hasn't run it yet should."""
        vo2 = ("compute_rolling_vo2", "a" * 16)
        hr = ("compute_rolling_vo2", "b" * 16)
        agg = AggregatedData()
        agg.fn_input_params[vo2] = {"signal": "RawVO2"}
        agg.fn_outputs[vo2] = {"RollingVO2"}
        agg.fn_constants[vo2] = {"window_seconds"}
        agg.fn_variants_map[vo2] = [{"constants": {"window_seconds": "25"}}]
        agg.fn_input_params[hr] = {"signal": "RawHeartRate"}
        agg.fn_outputs[hr] = {"RollingHR"}
        agg.fn_constants[hr] = {"window_seconds"}
        agg.fn_variants_map[hr] = [{"constants": {"window_seconds": "30"}}]
        agg.const_fns["window_seconds"] = {vo2, hr}
        states = {fn_node_id(*vo2): "green", fn_node_id(*hr): "green"}

        grouped, node_states, _ = group_call_sites_by_wiring(
            agg, states, pending_constants={"window_seconds": {"25"}}
        )

        vo2_wid = wiring_id(
            "compute_rolling_vo2", {"signal": "RawVO2"}, {"RollingVO2"}
        )
        hr_wid = wiring_id(
            "compute_rolling_vo2", {"signal": "RawHeartRate"}, {"RollingHR"}
        )
        vo2_rows = grouped.fn_variants_map[("compute_rolling_vo2", vo2_wid)]
        hr_rows = grouped.fn_variants_map[("compute_rolling_vo2", hr_wid)]
        # VO2 already ran 25 -> no synthesized staged row, node stays green.
        assert not any(r.get("staged") for r in vo2_rows)
        assert node_states[fn_node_id("compute_rolling_vo2", vo2_wid)] == "green"
        # HR hasn't run 25 -> gets the staged row and downgrades to pending.
        assert any(r.get("staged") for r in hr_rows)
        assert node_states[fn_node_id("compute_rolling_vo2", hr_wid)] == "pending"


class TestLegacyMigrationHelpers:
    GROUP = fn_node_id("bp", "c" * 16)
    LEGACY_A = fn_node_id("bp", "a" * 16)
    LEGACY_B = fn_node_id("bp", "b" * 16)

    def test_first_member_position_adopted_others_dropped(self):
        member_map = {self.GROUP: [self.LEGACY_A, self.LEGACY_B]}
        positions = {
            "main": {self.LEGACY_A: {"x": 1, "y": 2}, self.LEGACY_B: {"x": 3, "y": 4}}
        }

        adoptions, drops = legacy_position_adoptions(member_map, positions)

        assert adoptions == [{"new_id": self.GROUP, "scope": "main", "x": 1, "y": 2}]
        assert set(drops) == {self.LEGACY_A, self.LEGACY_B}

    def test_scope_of_adopted_position_is_kept(self):
        member_map = {self.GROUP: [self.LEGACY_A]}
        positions = {"pipe_sub": {self.LEGACY_A: {"x": 5, "y": 6}}}

        adoptions, _ = legacy_position_adoptions(member_map, positions)

        assert adoptions[0]["scope"] == "pipe_sub"

    def test_already_placed_group_only_drops_legacy_keys(self):
        member_map = {self.GROUP: [self.LEGACY_A]}
        positions = {
            "main": {self.GROUP: {"x": 9, "y": 9}, self.LEGACY_A: {"x": 1, "y": 2}}
        }

        adoptions, drops = legacy_position_adoptions(member_map, positions)

        assert adoptions == []
        assert drops == [self.LEGACY_A]

    def test_manual_edges_rewritten_to_group_id(self):
        member_map = {self.GROUP: [self.LEGACY_A]}
        edges = [
            {"id": "m1", "source": "var__Raw", "target": self.LEGACY_A},
            {"id": "m2", "source": self.LEGACY_A, "target": "var__Filtered"},
            {"id": "m3", "source": "var__Raw", "target": "var__Filtered"},
        ]

        rewrites = legacy_edge_rewrites(member_map, edges)

        assert {r["id"] for r in rewrites} == {"m1", "m2"}
        assert all(self.GROUP in (r["source"], r["target"]) for r in rewrites)


# ---------------------------------------------------------------------------
# find_cycle
# ---------------------------------------------------------------------------


class TestFindCycle:
    def test_no_edges_no_cycle(self):
        assert find_cycle([], "a", "b") is None

    def test_self_loop_is_a_cycle(self):
        assert find_cycle([], "a", "a") == ["a", "a"]

    def test_disjoint_edges_no_cycle(self):
        edges = [{"source": "a", "target": "b"}, {"source": "c", "target": "d"}]
        assert find_cycle(edges, "b", "c") is None

    def test_direct_two_node_cycle(self):
        # a -> b already exists; adding b -> a would close it.
        edges = [{"source": "a", "target": "b"}]
        path = find_cycle(edges, "b", "a")
        assert path == ["b", "a", "b"]

    def test_transitive_cycle_detected(self):
        # a -> b -> c already exists; adding c -> a would close it.
        edges = [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
        ]
        path = find_cycle(edges, "c", "a")
        assert path == ["c", "a", "b", "c"]

    def test_reverse_direction_is_not_a_cycle(self):
        # a -> b exists; adding a -> b again (or a totally different forward
        # edge) is not a cycle just because both touch the same nodes.
        edges = [{"source": "a", "target": "b"}]
        assert find_cycle(edges, "a", "c") is None

    def test_mixed_db_derived_and_manual_edges(self):
        # Real DB-derived data-wiring: fn output feeds a variable that's
        # already consumed as this fn's own input (data-lineage edge). A
        # NEW manual edge from that variable back to the function's input
        # would close the loop even though no OTHER manual edge is involved.
        edges = [
            {"source": "fn__f__abc123", "target": "var__Out"},
            {"source": "var__In", "target": "fn__f__abc123"},
        ]
        path = find_cycle(edges, "var__Out", "var__In")
        assert path == ["var__Out", "var__In", "fn__f__abc123", "var__Out"]
