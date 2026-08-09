"""
Unit tests for scistack_gui.domain.variant_resolver.

All functions are pure — no DB or fixtures required.
"""

from scistack_gui.domain.variant_resolver import (
    build_inferred_variants,
    build_schema_kwargs,
    compute_call_id,
    deduplicate_variants,
    filter_disconnected_targets,
    filter_hidden_targets,
    filter_variants,
    hidden_call_ids_for_fn,
    merge_pending_constants,
    resolve_target_call_id,
)

# ---------------------------------------------------------------------------
# build_inferred_variants
# ---------------------------------------------------------------------------


class TestBuildInferredVariants:
    def test_no_constants_single_output(self):
        result = build_inferred_variants(
            input_types={"signal": ["RawEMG"]},
            output_types=["Filtered"],
            inferred_constants={},
        )
        assert result == [
            {
                "input_types": {"signal": ["RawEMG"]},
                "output_type": "Filtered",
                "constants": {},
            }
        ]

    def test_no_constants_multiple_outputs(self):
        result = build_inferred_variants(
            input_types={"signal": ["Raw"]},
            output_types=["A", "B"],
            inferred_constants={},
        )
        assert len(result) == 2
        output_types = {v["output_type"] for v in result}
        assert output_types == {"A", "B"}
        assert all(v["constants"] == {} for v in result)

    def test_single_constant_cross_products_with_outputs(self):
        result = build_inferred_variants(
            input_types={},
            output_types=["Out"],
            inferred_constants={"low_hz": [10, 20]},
        )
        assert len(result) == 2
        constant_values = {v["constants"]["low_hz"] for v in result}
        assert constant_values == {10, 20}

    def test_two_constants_full_cross_product(self):
        result = build_inferred_variants(
            input_types={},
            output_types=["Out"],
            inferred_constants={"a": [1, 2], "b": ["x", "y"]},
        )
        assert len(result) == 4
        combos = {(v["constants"]["a"], v["constants"]["b"]) for v in result}
        assert combos == {(1, "x"), (1, "y"), (2, "x"), (2, "y")}

    def test_constants_with_multiple_outputs(self):
        result = build_inferred_variants(
            input_types={},
            output_types=["A", "B"],
            inferred_constants={"k": [1, 2]},
        )
        # 2 constant values × 2 outputs = 4
        assert len(result) == 4

    def test_empty_output_types_returns_empty(self):
        result = build_inferred_variants(
            input_types={"x": ["T"]},
            output_types=[],
            inferred_constants={},
        )
        assert result == []

    def test_input_types_preserved_in_all_variants(self):
        inputs = {"signal": ["Raw"], "ref": ["Ref"]}
        result = build_inferred_variants(
            input_types=inputs,
            output_types=["Out"],
            inferred_constants={"k": [1, 2]},
        )
        for v in result:
            assert v["input_types"] is inputs


# ---------------------------------------------------------------------------
# filter_variants
# ---------------------------------------------------------------------------


class TestFilterVariants:
    def _make_variants(self, const_dicts):
        return [
            {"input_types": {}, "output_type": "Out", "constants": c}
            for c in const_dicts
        ]

    def test_exact_match(self):
        variants = self._make_variants([{"hz": 10}, {"hz": 20}])
        result = filter_variants(variants, selected_variants=[{"hz": 10}])
        assert len(result) == 1
        assert result[0]["constants"]["hz"] == 10

    def test_no_match_returns_all(self):
        variants = self._make_variants([{"hz": 10}, {"hz": 20}])
        result = filter_variants(variants, selected_variants=[{"hz": 99}])
        assert result == variants

    def test_multiple_selected_matches_each(self):
        variants = self._make_variants([{"hz": 10}, {"hz": 20}, {"hz": 30}])
        result = filter_variants(variants, selected_variants=[{"hz": 10}, {"hz": 30}])
        assert len(result) == 2
        values = {v["constants"]["hz"] for v in result}
        assert values == {10, 30}

    def test_string_value_matching(self):
        # selected values stored as strings should still match typed values.
        variants = self._make_variants([{"hz": 10}])
        result = filter_variants(variants, selected_variants=[{"hz": "10"}])
        assert len(result) == 1

    def test_subset_matching(self):
        # selected is a subset of constants in each variant.
        variants = self._make_variants([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        result = filter_variants(variants, selected_variants=[{"a": 1}])
        assert len(result) == 1
        assert result[0]["constants"]["a"] == 1


# ---------------------------------------------------------------------------
# deduplicate_variants
# ---------------------------------------------------------------------------


class TestDeduplicateVariants:
    def _make(self, consts):
        return [
            {"input_types": {}, "output_type": "Out", "constants": c} for c in consts
        ]

    def test_no_duplicates_unchanged(self):
        variants = self._make([{"hz": 10}, {"hz": 20}])
        result = deduplicate_variants(variants)
        assert len(result) == 2

    def test_exact_duplicate_removed(self):
        variants = self._make([{"hz": 10}, {"hz": 10}])
        result = deduplicate_variants(variants)
        assert len(result) == 1

    def test_first_occurrence_kept(self):
        v1 = {"input_types": {}, "output_type": "A", "constants": {"hz": 10}}
        v2 = {"input_types": {}, "output_type": "B", "constants": {"hz": 10}}
        result = deduplicate_variants([v1, v2])
        assert result == [v1]

    def test_empty_list(self):
        assert deduplicate_variants([]) == []

    def test_empty_constants_deduplicated(self):
        variants = self._make([{}, {}])
        result = deduplicate_variants(variants)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# merge_pending_constants
# ---------------------------------------------------------------------------


class TestMergePendingConstants:
    def _make(self, const_dicts, out="Out"):
        return [
            {"input_types": {"x": ["T"]}, "output_type": out, "constants": c}
            for c in const_dicts
        ]

    def test_new_pending_value_added(self):
        variants = self._make([{"hz": 10}])
        result = merge_pending_constants(variants, {"hz": {"20"}})
        const_values = {v["constants"]["hz"] for v in result}
        assert 20 in const_values or "20" in const_values

    def test_existing_value_not_duplicated(self):
        variants = self._make([{"hz": 10}])
        result = merge_pending_constants(variants, {"hz": {"10"}})
        hz_values = [v["constants"]["hz"] for v in result]
        assert hz_values.count(10) + hz_values.count("10") == 1

    def test_pending_constant_not_in_fn_ignored(self):
        variants = self._make([{"hz": 10}])
        result = merge_pending_constants(variants, {"other_param": {"99"}})
        assert len(result) == 1

    def test_empty_pending_returns_unchanged(self):
        variants = self._make([{"hz": 10}])
        result = merge_pending_constants(variants, {})
        assert result == variants

    def test_empty_variants_returns_unchanged(self):
        result = merge_pending_constants([], {"hz": {"20"}})
        assert result == []

    def test_cross_product_with_other_constants(self):
        # hz: [10, 20] already exist; pending scale: ["2"]
        # Should add 2 new variants (one per existing hz value).
        variants = self._make([{"hz": 10, "scale": 1}, {"hz": 20, "scale": 1}])
        result = merge_pending_constants(variants, {"scale": {"2"}})
        scales = [v["constants"]["scale"] for v in result]
        assert 2 in scales or "2" in scales
        # The new scale value should pair with each hz value.
        new_variants = [v for v in result if str(v["constants"]["scale"]) == "2"]
        hz_vals = {v["constants"]["hz"] for v in new_variants}
        assert hz_vals == {10, 20}

    def test_coercion_numeric_string_to_int(self):
        variants = self._make([{"hz": 10}])
        result = merge_pending_constants(variants, {"hz": {"42"}})
        new = [v for v in result if v["constants"]["hz"] != 10]
        assert len(new) == 1
        assert new[0]["constants"]["hz"] == 42

    def test_coercion_non_numeric_stays_string(self):
        variants = self._make([{"mode": "fast"}])
        result = merge_pending_constants(variants, {"mode": {"slow"}})
        new = [v for v in result if v["constants"]["mode"] != "fast"]
        assert new[0]["constants"]["mode"] == "slow"


# ---------------------------------------------------------------------------
# compute_call_id
# ---------------------------------------------------------------------------


class TestComputeCallId:
    def _target(self, constants=None, input_types=None):
        return {
            "input_types": input_types or {"signal": "RawEMG"},
            "output_type": "Out",
            "constants": constants or {"hz": 10},
        }

    def test_matches_real_call_id_from_version_keys(self):
        from scidb.foreach_config import call_id_from_version_keys

        result = compute_call_id("bandpass_filter", self._target())
        expected = call_id_from_version_keys(
            {
                "__fn": "bandpass_filter",
                "__inputs": {"signal": "RawEMG"},
                "__constants": {"hz": 10},
            }
        )
        assert result == expected

    def test_distribute_false_matches_distribute_omitted(self):
        assert compute_call_id(
            "fn", self._target(), distribute=False
        ) == compute_call_id("fn", self._target())

    def test_distribute_true_changes_id(self):
        assert compute_call_id(
            "fn", self._target(), distribute=True
        ) != compute_call_id("fn", self._target(), distribute=False)

    def test_as_table_list_is_order_independent(self):
        assert compute_call_id(
            "fn", self._target(), as_table=["b", "a"]
        ) == compute_call_id("fn", self._target(), as_table=["a", "b"])

    def test_as_table_matches_real_call_id_from_version_keys(self):
        from scidb.foreach_config import call_id_from_version_keys

        result = compute_call_id("fn", self._target(), as_table=["b", "a"])
        expected = call_id_from_version_keys(
            {
                "__fn": "fn",
                "__inputs": {"signal": "RawEMG"},
                "__constants": {"hz": 10},
                "__as_table": ["a", "b"],
            }
        )
        assert result == expected

    def test_multi_type_input_returns_none(self):
        target = self._target(input_types={"signal": ["RawEMG", "RawEEG"]})
        assert compute_call_id("fn", target) is None

    def test_single_item_list_input_resolved_not_none(self):
        target = self._target(input_types={"signal": ["RawEMG"]})
        assert compute_call_id("fn", target) is not None
        assert compute_call_id("fn", target) == compute_call_id(
            "fn", self._target(input_types={"signal": "RawEMG"})
        )


# ---------------------------------------------------------------------------
# hidden_call_ids_for_fn
# ---------------------------------------------------------------------------


class TestHiddenCallIdsForFn:
    # parse_fn_node_id only recognizes a 16-hex-char suffix as a call_id
    # (shorter/non-hex suffixes are treated as legacy manual ids and
    # silently ignored) -- these must be realistic 16-hex ids or the
    # parse itself (not the function-name filter) would swallow them.
    _CID_A = "0123456789abcdef"
    _CID_B = "fedcba9876543210"

    def test_filters_to_matching_function(self):
        hidden = {
            f"fn__bandpass_filter__{self._CID_A}",
            f"fn__other_fn__{self._CID_B}",
        }
        assert hidden_call_ids_for_fn(hidden, "bandpass_filter") == {self._CID_A}

    def test_no_matches_returns_empty(self):
        hidden = {f"fn__other_fn__{self._CID_B}"}
        assert hidden_call_ids_for_fn(hidden, "bandpass_filter") == set()

    def test_ignores_non_fn_ids(self):
        hidden = {"var__Filtered", "const__hz", "fn__bandpass_filter"}
        assert hidden_call_ids_for_fn(hidden, "bandpass_filter") == set()

    def test_ignores_non_hex_short_suffix(self):
        """A random 6-char manual-node suffix (not a real call_id) must
        not be mistaken for one."""
        hidden = {"fn__bandpass_filter__abc123"}
        assert hidden_call_ids_for_fn(hidden, "bandpass_filter") == set()


# ---------------------------------------------------------------------------
# resolve_target_call_id / filter_hidden_targets
# ---------------------------------------------------------------------------


class TestFilterHiddenTargets:
    def _target(self, constants, call_id=None, input_types=None):
        t = {
            "input_types": input_types or {"signal": "RawEMG"},
            "output_type": "Out",
            "constants": constants,
        }
        if call_id is not None:
            t["call_id"] = call_id
        return t

    def test_no_hidden_ids_returns_unchanged(self):
        targets = [self._target({"hz": 10}, call_id="abc")]
        assert filter_hidden_targets(targets, "fn", set(), {}) == targets

    def test_real_call_id_hidden_dropped(self):
        targets = [self._target({"hz": 10}, call_id="abc")]
        assert filter_hidden_targets(targets, "fn", {"abc"}, {}) == []

    def test_real_call_id_not_hidden_kept(self):
        targets = [self._target({"hz": 10}, call_id="abc")]
        assert len(filter_hidden_targets(targets, "fn", {"other"}, {})) == 1

    def test_overridden_target_never_trusts_stale_call_id(self):
        # constants say hz=20 but the call_id field is left over from
        # before an override touched it (still says the hz=10 combo) —
        # hiding by the stale id must NOT match; only the freshly
        # recomputed id (matching the CURRENT constants) should.
        target = self._target({"hz": 20}, call_id="stale-id-for-hz-10")
        fresh_id = compute_call_id("fn", target)

        kept = filter_hidden_targets(
            [target], "fn", {"stale-id-for-hz-10"}, {"hz": {"20"}}
        )
        assert kept == [target]

        dropped = filter_hidden_targets([target], "fn", {fresh_id}, {"hz": {"20"}})
        assert dropped == []

    def test_untouched_target_reuses_real_call_id_not_recomputed(self):
        # constants weren't touched by any pending override -> the real
        # call_id is trusted as-is, even if it wouldn't match a freshly
        # computed hash (simulating legacy/out-of-band call_ids).
        target = self._target({"hz": 10}, call_id="legacy-id")
        assert filter_hidden_targets([target], "fn", {"legacy-id"}, {}) == []

    def test_never_run_combo_hidden_via_computed_id(self):
        target = self._target({"hz": 10})  # no call_id at all yet
        cid = compute_call_id("fn", target)
        assert filter_hidden_targets([target], "fn", {cid}, {}) == []

    def test_unresolvable_multitype_target_never_filtered(self):
        target = self._target({"hz": 10}, input_types={"signal": ["A", "B"]})
        result = filter_hidden_targets([target], "fn", {"anything"}, {})
        assert result == [target]

    def test_resolve_target_call_id_matches_filter_behavior(self):
        target = self._target({"hz": 10}, call_id="abc")
        assert resolve_target_call_id("fn", target, set()) == "abc"
        assert (
            resolve_target_call_id("fn", target, {"hz"}) == compute_call_id("fn", target)
        )


class TestFilterDisconnectedTargets:
    def _target(self, input_types=None, output_type="Out", constants=None):
        return {
            # `or` would silently treat an explicitly-passed {} as "use the
            # default" (empty dict is falsy) — tests below rely on {} being
            # respected as-is (e.g. a constant-only target with no var inputs).
            "input_types": {"signal": "RawEMG"} if input_types is None else input_types,
            "output_type": output_type,
            "constants": constants or {},
        }

    def test_no_hidden_edges_returns_unchanged(self):
        targets = [self._target()]
        assert filter_disconnected_targets(targets, "fn", set()) == targets

    def test_disconnected_var_input_dropped(self):
        from scistack_gui.domain.graph_builder import wiring_id

        target = self._target({"signal": "RawEMG"})
        wid = wiring_id("fn", {"signal": "RawEMG"}, {"Out"})
        hidden = {f"e__RawEMG__fn__{wid}"}
        assert filter_disconnected_targets([target], "fn", hidden) == []

    def test_disconnected_constant_input_dropped(self):
        from scistack_gui.domain.graph_builder import wiring_id

        target = self._target({}, constants={"low_hz": 20})
        wid = wiring_id("fn", {}, {"Out"})
        hidden = {f"e__low_hz__fn__{wid}"}
        assert filter_disconnected_targets([target], "fn", hidden) == []

    def test_unrelated_hidden_edge_keeps_target(self):
        target = self._target({"signal": "RawEMG"})
        assert filter_disconnected_targets([target], "fn", {"e__Other__fn__deadbeef"}) == [
            target
        ]

    def test_every_variant_of_disconnected_wiring_dropped_not_just_one(self):
        # Two constant-value variants of the SAME wiring — disconnecting
        # the shared var input drops the WHOLE wiring, not one combo.
        from scistack_gui.domain.graph_builder import wiring_id

        t1 = self._target({"signal": "RawEMG"}, constants={"hz": 10})
        t2 = self._target({"signal": "RawEMG"}, constants={"hz": 20})
        wid = wiring_id("fn", {"signal": "RawEMG"}, {"Out"})
        hidden = {f"e__RawEMG__fn__{wid}"}
        assert filter_disconnected_targets([t1, t2], "fn", hidden) == []

    def test_different_wiring_of_same_function_name_unaffected(self):
        # compute_rolling_vo2 fed by RawVO2 in one wiring, RawHeartRate in
        # another — disconnecting one must not touch the other.
        from scistack_gui.domain.graph_builder import wiring_id

        vo2 = self._target({"signal": "RawVO2"})
        hr = self._target({"signal": "RawHeartRate"})
        wid_vo2 = wiring_id("fn", {"signal": "RawVO2"}, {"Out"})
        hidden = {f"e__RawVO2__fn__{wid_vo2}"}
        assert filter_disconnected_targets([vo2, hr], "fn", hidden) == [hr]

    def test_multitype_input_list_checked_per_element(self):
        from scistack_gui.domain.graph_builder import wiring_id

        target = self._target({"signal": ["A", "B"]})
        wid = wiring_id("fn", {"signal": ["A", "B"]}, {"Out"})
        hidden = {f"e__B__fn__{wid}"}
        assert filter_disconnected_targets([target], "fn", hidden) == []

    def test_empty_targets_returns_empty(self):
        assert filter_disconnected_targets([], "fn", {"anything"}) == []


# ---------------------------------------------------------------------------
# build_schema_kwargs
# ---------------------------------------------------------------------------


class TestBuildSchemaKwargs:
    def test_no_filter_no_level_returns_all(self):
        result = build_schema_kwargs(
            schema_level=None,
            all_schema_keys=["subject", "session"],
            schema_filter=None,
            distinct_values={"subject": [1, 2], "session": ["pre", "post"]},
        )
        assert result == {"subject": [1, 2], "session": ["pre", "post"]}

    def test_schema_level_limits_keys(self):
        result = build_schema_kwargs(
            schema_level=["subject"],
            all_schema_keys=["subject", "session"],
            schema_filter=None,
            distinct_values={"subject": [1, 2], "session": ["pre", "post"]},
        )
        assert result == {"subject": [1, 2]}
        assert "session" not in result

    def test_schema_filter_narrows_values(self):
        result = build_schema_kwargs(
            schema_level=None,
            all_schema_keys=["subject", "session"],
            schema_filter={"subject": [1]},
            distinct_values={"subject": [1, 2], "session": ["pre", "post"]},
        )
        assert result["subject"] == [1]
        assert result["session"] == ["pre", "post"]

    def test_schema_filter_empty_list_falls_back_to_distinct(self):
        result = build_schema_kwargs(
            schema_level=None,
            all_schema_keys=["subject"],
            schema_filter={"subject": []},
            distinct_values={"subject": [1, 2, 3]},
        )
        assert result["subject"] == [1, 2, 3]

    def test_schema_level_and_filter_combined(self):
        result = build_schema_kwargs(
            schema_level=["subject"],
            all_schema_keys=["subject", "session"],
            schema_filter={"subject": [2]},
            distinct_values={"subject": [1, 2], "session": ["pre"]},
        )
        assert result == {"subject": [2]}

    def test_key_missing_from_distinct_returns_empty_list(self):
        result = build_schema_kwargs(
            schema_level=None,
            all_schema_keys=["subject"],
            schema_filter=None,
            distinct_values={},
        )
        assert result == {"subject": []}
