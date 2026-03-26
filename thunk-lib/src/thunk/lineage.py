"""Lineage extraction for provenance tracking.

This module provides utilities for extracting lineage information from
ThunkOutputs and converting it to a storable format.

Example:
    from thunk import thunk
    from thunk.lineage import extract_lineage, get_raw_value

    @thunk
    def process_signal(raw_data, calibration):
        return raw_data * calibration

    result = process_signal(data, 2.5)

    # Extract lineage for storage
    lineage = extract_lineage(result)
    print(lineage.function_name)  # 'process_signal'
    print(lineage.inputs)  # Input descriptors
    print(lineage.constants)  # Constant values like 2.5

    # Get the raw value for storage
    raw_value = get_raw_value(result)  # The actual computed array
"""

from dataclasses import dataclass, field
from typing import Any

from .core import ThunkOutput
from .inputs import classify_inputs, InputKind, is_trackable_variable


@dataclass
class LineageRecord:
    """
    Represents the provenance of a single computed value.

    Attributes:
        function_name: Name of the function that produced the output
        function_hash: Hash of the function bytecode
        inputs: List of input descriptors (variables with identifiers)
        constants: List of constant input descriptors (literals)
    """

    function_name: str
    function_hash: str
    inputs: list[dict] = field(default_factory=list)
    constants: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a dictionary for JSON serialization."""
        return {
            "function_name": self.function_name,
            "function_hash": self.function_hash,
            "inputs": self.inputs,
            "constants": self.constants,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LineageRecord":
        """Create a LineageRecord from a dictionary."""
        return cls(
            function_name=data["function_name"],
            function_hash=data["function_hash"],
            inputs=data.get("inputs", []),
            constants=data.get("constants", []),
        )


def extract_lineage(thunk_output: ThunkOutput) -> LineageRecord:
    """
    Extract lineage information from a ThunkOutput.

    Traverses the input graph to capture:
    - Function name and hash
    - Input variables (with their identifiers if saved)
    - Constant values

    Args:
        thunk_output: The ThunkOutput to extract lineage from

    Returns:
        LineageRecord containing the provenance information
    """
    pt = thunk_output.pipeline_thunk

    # Classify all inputs using the shared classifier
    classified = classify_inputs(pt.inputs)

    # Separate into inputs (variables/thunks) and constants
    inputs = []
    constants = []

    for c in classified:
        if c.kind == InputKind.CONSTANT:
            constants.append(c.to_lineage_dict())
        else:
            inputs.append(c.to_lineage_dict())

    return LineageRecord(
        function_name=pt.thunk.fcn.__name__,
        function_hash=pt.thunk.hash,
        inputs=inputs,
        constants=constants,
    )


def get_raw_value(data: Any) -> Any:
    """
    Unwrap ThunkOutput to get raw value, or return as-is.

    This is used when saving a variable whose data might be wrapped
    in a ThunkOutput from a thunked computation.

    Args:
        data: Either a ThunkOutput or a raw value

    Returns:
        The raw data (unwrapped if ThunkOutput, otherwise unchanged)
    """
    if isinstance(data, ThunkOutput):
        return data.data
    return data


def get_upstream_lineage(
    thunk_output: ThunkOutput,
    max_depth: int = 100,
) -> list[dict]:
    """
    Get lineage information for all upstream computations.

    Traverses the full in-memory chain, extracting lineage for all
    upstream computations.

    Args:
        thunk_output: The ThunkOutput to start from
        max_depth: Maximum recursion depth

    Returns:
        List of lineage dicts, one per upstream computation
    """
    lineages = []
    visited = set()

    def traverse(thunk: ThunkOutput, depth: int) -> None:
        if depth <= 0:
            return

        thunk_id = id(thunk)
        if thunk_id in visited:
            return
        visited.add(thunk_id)

        # Extract lineage for this thunk
        lineage = extract_lineage(thunk)
        lineages.append(lineage.to_dict())

        # Recurse into input ThunkOutputs
        for name, value in thunk.pipeline_thunk.inputs.items():
            if isinstance(value, ThunkOutput):
                traverse(value, depth - 1)
            elif is_trackable_variable(value):
                # Check if unsaved variable wraps a ThunkOutput
                inner = getattr(value, "data", None)
                if isinstance(inner, ThunkOutput):
                    traverse(inner, depth - 1)

    traverse(thunk_output, max_depth)
    return lineages
