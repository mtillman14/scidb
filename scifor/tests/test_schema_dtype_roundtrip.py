"""Tests for schema-key column dtype round-trip in standalone for_each.

Output metadata columns must come back as EXACTLY the input column's dtype:
int stays int, object/str stays object (values verbatim), categorical stays
categorical (categories + orderedness preserved). Mirrors the MATLAB scifor
type round-trip (TestSciforForEachCategorical section F); see
docs/claude/schema-key-types.md.
"""

import pandas as pd

from scifor import for_each, set_schema


def setup_function():
    # Reset schema before each test
    set_schema([])


# ---------------------------------------------------------------------------
# Plain dtypes
# ---------------------------------------------------------------------------

def test_int_key_column_roundtrips_int():
    """key=[] on an int column: int out, numeric order."""
    set_schema(["subject"])
    df = pd.DataFrame({"subject": [1, 2, 10], "value": [10.0, 20.0, 30.0]})

    result = for_each(lambda x: x, inputs={"x": df}, subject=[])

    assert result["subject"].dtype == df["subject"].dtype
    assert result["subject"].tolist() == [1, 2, 10]
    assert result["output"].tolist() == [10.0, 20.0, 30.0]


def test_int32_key_column_roundtrips_int32():
    """Exact dtype width restores (int32 in, int32 out — not int64)."""
    set_schema(["subject"])
    df = pd.DataFrame({
        "subject": pd.Series([1, 2], dtype="int32"),
        "value": [1.0, 2.0],
    })

    result = for_each(lambda x: x, inputs={"x": df}, subject=[])

    assert str(result["subject"].dtype) == "int32"
    assert result["subject"].tolist() == [1, 2]


def test_string_key_column_roundtrips_verbatim():
    """Zero-padded string keys stay strings, values verbatim — a string
    column is never converted, even when every value looks numeric."""
    set_schema(["trial"])
    df = pd.DataFrame({"trial": ["01", "02", "10"], "value": [1, 2, 3]})

    result = for_each(lambda x: x, inputs={"x": df}, trial=[])

    assert result["trial"].dtype == df["trial"].dtype
    assert result["trial"].tolist() == ["01", "02", "10"]
    assert result["output"].tolist() == [1, 2, 3]


# ---------------------------------------------------------------------------
# Categorical dtypes
# ---------------------------------------------------------------------------

def test_categorical_int_key_column_roundtrips_numeric_order():
    """Int-backed categorical: categorical out (same dtype), rows iterated
    in numeric (not lexical) order — pandas categoricals keep value dtypes,
    so 10 sorts after 2."""
    set_schema(["subject"])
    df = pd.DataFrame({
        "subject": pd.Categorical([1, 2, 10]),
        "value": [10, 20, 30],
    })

    result = for_each(lambda x: x, inputs={"x": df}, subject=[])

    assert isinstance(result["subject"].dtype, pd.CategoricalDtype)
    assert result["subject"].dtype == df["subject"].dtype
    assert result["subject"].tolist() == [1, 2, 10]
    assert result["output"].tolist() == [10, 20, 30]


def test_categorical_ordered_key_column_roundtrips():
    """Categories and orderedness survive the round trip."""
    set_schema(["phase"])
    dtype = pd.CategoricalDtype(["pre", "post"], ordered=True)
    df = pd.DataFrame({
        "phase": pd.Series(["pre", "post"], dtype=dtype),
        "value": [1, 2],
    })

    result = for_each(lambda x: x, inputs={"x": df}, phase=[])

    assert result["phase"].dtype == dtype
    assert result["phase"].cat.ordered
    assert list(result["phase"].cat.categories) == ["pre", "post"]
    # Documents current iteration order: distinct string values sort
    # lexically ("post" < "pre"), not by category order.
    assert result["phase"].tolist() == ["post", "pre"]


def test_explicit_iterable_with_categorical_column():
    """Explicit values still filter a categorical column, and the output
    column dtype follows the input column."""
    set_schema(["subject"])
    df = pd.DataFrame({"subject": pd.Categorical([1, 2]), "value": [10, 20]})

    result = for_each(lambda x: x, inputs={"x": df}, subject=[1, 2])

    assert isinstance(result["subject"].dtype, pd.CategoricalDtype)
    assert result["output"].tolist() == [10, 20]


def test_flatten_mode_restores_dtype():
    """DataFrame outputs (flatten mode) also get metadata dtypes restored."""
    set_schema(["subject"])
    df = pd.DataFrame({"subject": pd.Categorical([1, 2]), "value": [10, 20]})

    result = for_each(
        lambda x: pd.DataFrame({"v": [x, x]}),
        inputs={"x": df},
        subject=[],
    )

    assert isinstance(result["subject"].dtype, pd.CategoricalDtype)
    assert len(result) == 4


# ---------------------------------------------------------------------------
# Keys without a captured dtype, and conflicts
# ---------------------------------------------------------------------------

def test_explicit_iterable_without_column_keeps_own_type():
    """A key with no input DataFrame column keeps the iterable's own type
    (no captured dtype to restore)."""
    set_schema(["group"])

    result = for_each(lambda: 42, inputs={}, group=["A", "B"])

    # The natural dtype pandas gives these values (object on pandas<3,
    # str/StringDtype on pandas>=3) — restore must not have touched it.
    expected_dtype = pd.DataFrame({"group": ["A", "B"]})["group"].dtype
    assert result["group"].dtype == expected_dtype
    assert result["group"].tolist() == ["A", "B"]


def test_conflicting_key_dtypes_do_not_error():
    """Two inputs disagreeing on a key's column dtype: no error; the column
    is left at the natural output dtype (warn logged)."""
    set_schema(["subject"])
    a = pd.DataFrame({"subject": [1, 2], "a": [10, 20]})
    b = pd.DataFrame({"subject": pd.Categorical([1, 2]), "b": [30, 40]})

    result = for_each(lambda x, y: x + y, inputs={"x": a, "y": b}, subject=[])

    assert result["output"].tolist() == [40, 60]
    assert not isinstance(result["subject"].dtype, pd.CategoricalDtype)
