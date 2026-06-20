"""The @pipeline marker — replacement for @lineage_fcn.

@pipeline tags a PLAIN function (no wrapping, raw return value) so discover.py
finds it and for_each can read its options. See
.claude/remove-lineage-fcn.md.
"""

import types

from scidb import pipeline
from scidb.pipeline import (
    GENERATES_FILE_ATTR,
    PIPELINE_FLAG,
    UNPACK_OUTPUT_ATTR,
    is_pipeline_function,
)
from scidb.discover import discover_module


def test_bare_marker_tags_and_returns_plain_function():
    @pipeline
    def f(x):
        return x + 1

    assert is_pipeline_function(f)
    assert getattr(f, PIPELINE_FLAG) is True
    assert getattr(f, UNPACK_OUTPUT_ATTR) is False
    # Not wrapped — calling returns the raw value, not a result object.
    assert f(1) == 2


def test_called_marker_carries_options():
    @pipeline(unpack_output=True, generates_file="{subject}/out.csv")
    def g(x):
        return x, x * 2

    assert is_pipeline_function(g)
    assert getattr(g, UNPACK_OUTPUT_ATTR) is True
    assert getattr(g, GENERATES_FILE_ATTR) == "{subject}/out.csv"
    assert g(3) == (3, 6)  # raw tuple, not wrapped


def test_plain_function_is_not_a_pipeline_function():
    def h(x):
        return x

    assert not is_pipeline_function(h)


def test_discover_module_finds_pipeline_functions():
    mod = types.ModuleType("fake_pipeline_mod")

    @pipeline
    def step(x):
        return x

    # Attribute it to this module (discover filters by __module__).
    step.__module__ = "fake_pipeline_mod"
    mod.step = step

    def helper(x):  # plain, untagged → not discovered
        return x
    helper.__module__ = "fake_pipeline_mod"
    mod.helper = helper

    exports = discover_module(mod)
    assert step in exports.functions
    assert helper not in exports.functions
