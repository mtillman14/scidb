"""Unit tests for the ``Constant`` primitive and ``constant()`` factory."""

from __future__ import annotations

import pytest

from scidb import Constant, constant


# ---------------------------------------------------------------------------
# Scalar transparency
# ---------------------------------------------------------------------------
class TestScalarTransparency:
    def test_int_addition(self):
        sampling_rate = constant(1000, description="Hz")
        assert sampling_rate + 1 == 1001
        assert 1 + sampling_rate == 1001

    def test_int_arithmetic(self):
        x = constant(10)
        assert x - 3 == 7
        assert 20 - x == 10
        assert x * 4 == 40
        assert 2 * x == 20
        assert x / 2 == 5
        assert 20 / x == 2
        assert x // 3 == 3
        assert x % 3 == 1
        assert x ** 2 == 100
        assert -x == -10
        assert abs(constant(-5)) == 5

    def test_float_arithmetic(self):
        weight = constant(0.25, description="reg weight")
        assert weight + 0.25 == 0.5
        assert weight * 4 == 1.0
        assert float(weight) == 0.25

    def test_comparisons(self):
        x = constant(10)
        assert x == 10
        assert x != 11
        assert x < 11
        assert x <= 10
        assert x > 9
        assert x >= 10
        # Reverse comparisons
        assert 10 == x
        assert 9 < x

    def test_comparison_between_constants(self):
        a = constant(5)
        b = constant(10)
        assert a < b
        assert a != b
        assert a == constant(5)

    def test_bool_coercion(self):
        assert bool(constant(1)) is True
        assert bool(constant(0)) is False
        assert bool(constant("hello")) is True
        assert bool(constant("")) is False

    def test_hash(self):
        x = constant(42)
        d = {x: "answer"}
        assert d[42] == "answer"
        assert hash(x) == hash(42)

    def test_int_index(self):
        # Allows use as an index / slice argument.
        x = constant(3)
        assert list(range(x)) == [0, 1, 2]
        assert [10, 20, 30, 40][x] == 40

    def test_str_transparency(self):
        name = constant("session_a", description="default session")
        assert name + "_v2" == "session_a_v2"
        assert "session" in name
        assert len(name) == len("session_a")
        assert name.upper() == "SESSION_A"

    def test_repr_contains_value_and_description(self):
        x = constant(1000, description="sampling rate")
        r = repr(x)
        assert "1000" in r
        assert "sampling rate" in r

    def test_fstring_formatting(self):
        x = constant(0.12345)
        assert f"{x:.2f}" == "0.12"
        y = constant(255)
        assert f"{y:04d}" == "0255"
        z = constant("name")
        assert f"{z:>8}" == "    name"


# ---------------------------------------------------------------------------
# Container transparency
# ---------------------------------------------------------------------------
class TestContainerTransparency:
    def test_tuple_indexing(self):
        bandpass = constant((1.0, 40.0), description="bandpass Hz")
        assert bandpass[0] == 1.0
        assert bandpass[1] == 40.0
        low, high = bandpass
        assert (low, high) == (1.0, 40.0)
        assert len(bandpass) == 2

    def test_list_iteration(self):
        channels = constant([0, 1, 2, 3])
        assert list(channels) == [0, 1, 2, 3]
        assert list(reversed(channels)) == [3, 2, 1, 0]
        assert 2 in channels
        assert 99 not in channels
        assert channels[1:3] == [1, 2]

    def test_dict_access(self):
        config = constant({"fs": 1000, "n_channels": 32})
        assert config["fs"] == 1000
        assert "fs" in config
        assert set(config) == {"fs", "n_channels"}
        assert config.get("n_channels") == 32

    def test_nested_container(self):
        cfg = constant({"band": (1.0, 40.0), "notch": 60})
        assert cfg["band"][0] == 1.0
        assert cfg["notch"] + 1 == 61


# ---------------------------------------------------------------------------
# isinstance detection (critical for discovery scanner)
# ---------------------------------------------------------------------------
class TestIsInstance:
    def test_scalar_constant_is_constant(self):
        x = constant(1000)
        assert isinstance(x, Constant)

    def test_tuple_constant_is_constant(self):
        x = constant((1.0, 40.0))
        assert isinstance(x, Constant)

    def test_dict_constant_is_constant(self):
        x = constant({"a": 1})
        assert isinstance(x, Constant)

    def test_raw_value_is_not_constant(self):
        assert not isinstance(1000, Constant)
        assert not isinstance((1.0, 40.0), Constant)
        assert not isinstance({"a": 1}, Constant)


# ---------------------------------------------------------------------------
# Description and source location capture
# ---------------------------------------------------------------------------
class TestMetadataCapture:
    def test_description_captured(self):
        x = constant(1000, description="Sampling rate in Hz")
        assert x.description == "Sampling rate in Hz"

    def test_description_defaults_to_empty(self):
        x = constant(1000)
        assert x.description == ""

    def test_source_file_captured(self):
        x = constant(1000, description="Hz")
        # Should point at this test file.
        assert x.source_file.endswith("test_constant.py")

    def test_source_line_captured(self):
        import inspect as _inspect
        expected_line = _inspect.currentframe().f_lineno + 1
        x = constant(1000, description="Hz")
        assert x.source_line == expected_line

    def test_different_call_sites_get_different_locations(self):
        a = constant(1, description="a")
        b = constant(2, description="b")
        # Same file, different lines.
        assert a.source_file == b.source_file
        assert a.source_line != b.source_line
        assert b.source_line == a.source_line + 1


# ---------------------------------------------------------------------------
# Attribute passthrough (__getattr__)
# ---------------------------------------------------------------------------
class TestAttributePassthrough:
    def test_string_methods(self):
        s = constant("hello")
        assert s.upper() == "HELLO"
        assert s.startswith("he")

    def test_list_methods(self):
        lst = constant([3, 1, 2])
        # Non-mutating method access through passthrough.
        assert lst.count(1) == 1
        assert lst.index(2) == 2

    def test_metadata_attrs_take_precedence_over_value_attrs(self):
        # Even if the wrapped value had a ``description`` attribute, our
        # slot should win. Use an object that has one.
        class Holder:
            description = "value's own description"

        x = Constant(Holder(), description="constant description")
        assert x.description == "constant description"


# ---------------------------------------------------------------------------
# Direct constructor (bypassing the factory)
# ---------------------------------------------------------------------------
class TestDirectConstructor:
    def test_direct_construction_sets_empty_location(self):
        x = Constant(42, description="answer")
        assert x.description == "answer"
        assert x.source_file == ""
        assert x.source_line == 0

    def test_slots_reject_arbitrary_attrs(self):
        x = constant(1)
        with pytest.raises(AttributeError):
            x.some_new_attr = 5  # type: ignore[misc]
