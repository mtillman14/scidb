"""Deterministic hashing for arbitrary Python objects.

This module provides utilities for creating stable, deterministic hashes
of Python objects, which is essential for cache key computation, data
versioning, and reproducibility.
"""

import hashlib
import json
from typing import Any


def canonical_hash(obj: Any) -> str:
    """
    Generate a deterministic hash for arbitrary Python objects.

    Strategy:
    1. For JSON-serializable primitives (None, bool, int, float, str): use JSON
    2. For numpy ndarrays: shape + dtype + raw bytes; ``object``-dtype arrays are
       hashed BY VALUE (their ``tobytes()`` would be non-deterministic pointers)
    3. For pandas DataFrames: per-column, columns SORTED by name, index IGNORED
       (column order and the index are non-semantic for stored content)
    4. For pandas Series: name + values (index ignored)
    5. For dicts: sort keys, recursively serialize
    6. For lists/tuples: preserve order, recursively serialize
    7. For other objects: raise ValueError

    Determinism note: the hash is invariant to DataFrame column order, the pandas
    index, and object-array memory layout, so logically-identical data always
    hashes the same — even across processes / MATLAB-bridge round-trips.

    Args:
        obj: Any Python object to hash

    Returns:
        16-character hex string (first 64 bits of SHA-256)

    Raises:
        ValueError: If an unserializable object is provided

    Example:
        >>> h = canonical_hash(42)
        >>> len(h) == 16 and all(c in '0123456789abcdef' for c in h)
        True
        >>> canonical_hash(42) == canonical_hash(42)  # Deterministic
        True
        >>> canonical_hash([1, 2, 3]) != canonical_hash([1, 2, 4])  # Content-sensitive
        True
    """
    serialized = _serialize_for_hash(obj)
    return hashlib.sha256(serialized).hexdigest()[:16]


def _serialize_for_hash(obj: Any) -> bytes:
    """Convert object to bytes for hashing."""

    # Primitives - use JSON for stability
    if isinstance(obj, (type(None), bool, int, float, str)):
        return json.dumps(obj).encode("utf-8")

    # Dicts - sort keys for determinism
    if isinstance(obj, dict):
        sorted_items = sorted(obj.items(), key=lambda x: str(x[0]))
        parts = []
        for k, v in sorted_items:
            parts.append(_serialize_for_hash(k))
            parts.append(_serialize_for_hash(v))
        return b"dict:" + b"|".join(parts)

    # Lists/tuples - preserve order
    if isinstance(obj, (list, tuple)):
        type_prefix = b"list:" if isinstance(obj, list) else b"tuple:"
        parts = [_serialize_for_hash(item) for item in obj]
        return type_prefix + b"|".join(parts)

    # Numpy arrays - use shape, dtype, and raw bytes.
    if hasattr(obj, "tobytes") and hasattr(obj, "dtype") and hasattr(obj, "shape"):
        # CRITICAL: an `object`-dtype array stores Python references, so
        # `tobytes()` returns the bytes of POINTER values — non-deterministic
        # across runs/processes. Hash such arrays BY VALUE instead (recurse over
        # the nested Python lists), so e.g. a mixed-type DataFrame column of
        # strings hashes the strings, not their memory addresses.
        if obj.dtype == object:
            return (
                b"ndarray-object:"
                + str(obj.shape).encode()
                + b":"
                + _serialize_for_hash(obj.tolist())
            )
        return (
            b"ndarray:"
            + str(obj.shape).encode()
            + b":"
            + str(obj.dtype).encode()
            + b":"
            + obj.tobytes()
        )

    # Pandas DataFrame — content-canonical hash:
    #  - column ORDER is non-semantic for stored content (storage is keyed by
    #    column NAME), so sort columns → permuting columns can't change the hash;
    #  - the pandas INDEX is not part of the persisted content, so it must NOT
    #    affect the hash (a volatile index from row-splitting otherwise yields
    #    different hashes for identical data);
    #  - serialize PER COLUMN (each column keeps its own dtype) rather than via a
    #    whole-frame `to_numpy()`, which would collapse a mixed-dtype frame to an
    #    object array and hash pointer bytes (see above).
    if hasattr(obj, "to_numpy") and hasattr(obj, "columns"):
        parts = [b"dataframe:"]
        for col in sorted(obj.columns, key=str):
            parts.append(_serialize_for_hash(str(col)))
            parts.append(_serialize_for_hash(obj[col].to_numpy()))
        return b"|".join(parts)

    # Pandas Series — hash name + values by value (index intentionally ignored,
    # consistent with the DataFrame path; object dtype handled above).
    if hasattr(obj, "to_numpy") and hasattr(obj, "name") and not hasattr(obj, "columns"):
        return (
            b"series:"
            + _serialize_for_hash(obj.name)
            + b":"
            + _serialize_for_hash(obj.to_numpy())
        )

    # Python array.array (MATLAB bridge can produce these)
    import array as _array_mod
    if isinstance(obj, _array_mod.array):
        import numpy as np
        return _serialize_for_hash(np.array(obj))

    # Unsupported type
    raise ValueError(f"Unserializable data type: {type(obj)}")


def generate_record_id(
    class_name: str,
    schema_version: int,
    content_hash: str,
    metadata: dict,
) -> str:
    """
    Generate a unique record ID from components.

    The record_id uniquely identifies a record by its type, schema, content,
    and metadata. Useful for addressing/querying versioned data.

    Args:
        class_name: The record type (e.g., "RotationMatrix")
        schema_version: Integer version of the serialization schema
        content_hash: Pre-computed hash of the data content
        metadata: The addressing metadata (subject, trial, etc.)

    Returns:
        16-character hex string

    Example:
        >>> rid = generate_record_id("MyData", 1, "abc123", {"subject": 1})
        >>> len(rid) == 16 and all(c in '0123456789abcdef' for c in rid)
        True
    """
    components = [
        f"class:{class_name}",
        f"schema:{schema_version}",
        f"content:{content_hash}",
        f"meta:{canonical_hash(metadata)}",
    ]
    combined = "|".join(components).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()[:16]
