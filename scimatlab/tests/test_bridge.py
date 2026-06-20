"""Tests for the MATLAB-SciStack Python bridge.

These tests verify that the proxy classes satisfy the duck-typing
contracts of scilineage without requiring MATLAB.
"""

import sys
from hashlib import sha256
from pathlib import Path

# Add source paths for the monorepo packages
_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_root / "src"))
sys.path.insert(0, str(_root / "scilineage" / "src"))
sys.path.insert(0, str(_root / "canonical-hash" / "src"))
sys.path.insert(0, str(_root / "sciduckdb" / "src"))
sys.path.insert(0, str(_root / "path-gen" / "src"))
sys.path.insert(0, str(_root / "scimatlab" / "src"))

import numpy as np
import pytest

from scimatlab.bridge import (
    MatlabLineageFcn,
    register_matlab_variable,
    get_surrogate_class,
    split_flat_to_lists,
)
from scidb.variable import BaseVariable


# ---------------------------------------------------------------------------
# MatlabLineageFcn proxy tests
# ---------------------------------------------------------------------------

class TestMatlabLineageFcn:
    """Verify MatlabLineageFcn is a usable node-state handle."""

    def test_has_required_attributes(self):
        t = MatlabLineageFcn("abc123", "my_function")
        assert hasattr(t, "hash")
        assert hasattr(t, "fcn")
        assert hasattr(t, "unpack_output")
        assert t.fcn.__name__ == "my_function"
        assert t.unpack_output is False

    def test_hash_is_deterministic(self):
        t1 = MatlabLineageFcn("abc123", "f")
        t2 = MatlabLineageFcn("abc123", "f")
        assert t1.hash == t2.hash
        assert len(t1.hash) == 64  # Full SHA-256 hex

    def test_hash_changes_with_source(self):
        t1 = MatlabLineageFcn("abc123", "f")
        t2 = MatlabLineageFcn("def456", "f")
        assert t1.hash != t2.hash

    def test_hash_changes_with_unpack_output(self):
        t1 = MatlabLineageFcn("abc123", "f", unpack_output=False)
        t2 = MatlabLineageFcn("abc123", "f", unpack_output=True)
        assert t1.hash != t2.hash

    def test_hash_recipe(self):
        """The handle hash is sha256(f"{source_hash}-{unpack_output}")."""
        source_hash = sha256(b"test_source").hexdigest()
        t = MatlabLineageFcn(source_hash, "f", unpack_output=False)
        expected = sha256(f"{source_hash}-False".encode()).hexdigest()
        assert t.hash == expected


# ---------------------------------------------------------------------------
# Variable registration tests
# ---------------------------------------------------------------------------

class TestVariableRegistration:

    def test_register_creates_subclass(self):
        cls = register_matlab_variable("TestMatlabVar_1")
        assert issubclass(cls, BaseVariable)
        assert cls.__name__ == "TestMatlabVar_1"
        assert cls.schema_version == 1

    def test_register_with_schema_version(self):
        cls = register_matlab_variable("TestMatlabVar_2", schema_version=3)
        assert cls.schema_version == 3

    def test_register_idempotent(self):
        cls1 = register_matlab_variable("TestMatlabVar_3")
        cls2 = register_matlab_variable("TestMatlabVar_3")
        assert cls1 is cls2

    def test_get_surrogate_class(self):
        register_matlab_variable("TestMatlabVar_4")
        cls = get_surrogate_class("TestMatlabVar_4")
        assert cls.__name__ == "TestMatlabVar_4"

    def test_get_surrogate_class_not_registered(self):
        import pytest
        with pytest.raises(ValueError, match="not registered"):
            get_surrogate_class("NonExistentType_xyz")

    def test_registered_in_all_subclasses(self):
        register_matlab_variable("TestMatlabVar_5")
        assert "TestMatlabVar_5" in BaseVariable._all_subclasses


# ---------------------------------------------------------------------------
# split_flat_to_lists tests
# ---------------------------------------------------------------------------

class TestSplitFlatToLists:
    """Verify split_flat_to_lists correctly splits flat arrays into Python lists."""

    def test_float_split(self):
        """Float64 array split into 3 equal-length lists."""
        flat = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], dtype=np.float64)
        lengths = np.array([2, 2, 2], dtype=np.int64)
        result = split_flat_to_lists(flat, lengths)
        assert result == [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
        # Verify native Python types
        assert all(isinstance(x, float) for sublist in result for x in sublist)

    def test_bool_split(self):
        """Bool array split into lists of True/False."""
        flat = np.array([True, False, True, True], dtype=bool)
        lengths = np.array([2, 2], dtype=np.int64)
        result = split_flat_to_lists(flat, lengths)
        assert result == [[True, False], [True, True]]
        assert all(isinstance(x, bool) for sublist in result for x in sublist)

    def test_variable_lengths(self):
        """Different sub-list lengths (1, 3, 2)."""
        flat = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0], dtype=np.float64)
        lengths = np.array([1, 3, 2], dtype=np.int64)
        result = split_flat_to_lists(flat, lengths)
        assert result == [[10.0], [20.0, 30.0, 40.0], [50.0, 60.0]]

    def test_empty_sublists(self):
        """Some zero-length entries produce empty lists."""
        flat = np.array([1.0, 2.0, 3.0], dtype=np.float64)
        lengths = np.array([0, 2, 0, 1, 0], dtype=np.int64)
        result = split_flat_to_lists(flat, lengths)
        assert result == [[], [1.0, 2.0], [], [3.0], []]

    def test_empty_input(self):
        """Empty flat array + empty lengths = empty result."""
        flat = np.array([], dtype=np.float64)
        lengths = np.array([], dtype=np.int64)
        result = split_flat_to_lists(flat, lengths)
        assert result == []

    def test_int_split(self):
        """Integer array split into lists."""
        flat = np.array([1, 2, 3, 4, 5], dtype=np.int64)
        lengths = np.array([3, 2], dtype=np.int64)
        result = split_flat_to_lists(flat, lengths)
        assert result == [[1, 2, 3], [4, 5]]
        assert all(isinstance(x, int) for sublist in result for x in sublist)

    def test_single_element_sublists(self):
        """Each sub-list has exactly one element."""
        flat = np.array([10.0, 20.0, 30.0], dtype=np.float64)
        lengths = np.array([1, 1, 1], dtype=np.int64)
        result = split_flat_to_lists(flat, lengths)
        assert result == [[10.0], [20.0], [30.0]]
