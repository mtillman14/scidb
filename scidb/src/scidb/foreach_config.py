"""ForEachConfig — serializes for_each() computation config into version keys."""

import hashlib
import json
from collections.abc import Callable
from typing import Any

from scilineage.hashing import compute_function_hash


def _compute_fn_hash(fn: Callable) -> str:
    """Compute a stable hash of the function's bytecode and constants.

    Uses bytecode-based hashing (via scilineage.hashing.compute_function_hash),
    which only changes when the function's actual logic changes. Ignores cosmetic
    changes like whitespace, comments, and formatting.

    Returns 16 hex chars (truncated SHA-256) for version_keys storage.

    Args:
        fn: The function to hash (can be plain function or LineageFcn wrapper).

    Returns:
        16-character hex string hash.
    """
    return compute_function_hash(fn, truncate=16)


# The canonical for_each call-site identity is captured by exactly these
# version_keys fields (see ForEachConfig.to_version_keys()).  Anything else
# in a saved version_keys dict — direct constants unpacked as top-level
# keys, ``__upstream``, ``__output_num``, scihist's lineage extras — is
# per-record bookkeeping and must not affect the call_id.
#
# ``__fn_hash`` is intentionally excluded too, so cosmetic source edits to
# the function body don't fork the call site (see ForEachConfig.to_call_id
# docstring for rationale).
#
# ``__where`` is also excluded: a where= filter's only effect on the computation
# is the surviving input set (already folded into invocation_id / ``__inputs``);
# the where_clause string itself is display-only (§10 where= redesign), so two
# call sites differing only by where= share a call_id. (``to_version_keys`` still
# emits ``__where`` because for_each writes it to ``_run.where_clause`` for display.)
_CALL_ID_INCLUDED_KEYS = (
    "__fn",
    "__inputs",
    "__constants",
    "__distribute",
    "__as_table",
)


def call_id_from_version_keys(version_keys: dict) -> str:
    """Compute a 16-hex-char call_id from any version_keys dict.

    Used by both ``ForEachConfig.to_call_id()`` (forward path, before save)
    and ``list_pipeline_variants()`` (reverse path, reconstructing the config
    from the bipartite graph) so the call_id of a freshly built config matches
    the call_id derived from records it eventually wrote.

    Uses a strict allow-list of canonical config keys, ignoring any
    per-record fields that scidb/scihist may have stored alongside.
    """
    keys = {k: version_keys[k] for k in _CALL_ID_INCLUDED_KEYS if k in version_keys}
    payload = json.dumps(keys, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class ForEachConfig:
    """Serializes for_each() computation config into version keys.

    Captures the parts of a for_each() call that affect the computation's
    identity but are not part of the schema metadata: the function, loadable
    inputs (which variable types / Fixed wrappers are used), where= filter,
    and other behavioral flags.

    These keys are merged into save_metadata so that changing the config
    (e.g. switching smoothing=0.2 to smoothing=0.3, or adding a where= filter)
    creates a new version_keys group rather than silently overwriting existing
    results.
    """

    def __init__(
        self,
        fn: Callable,
        inputs: dict[str, Any],
        where=None,
        distribute: bool = False,
        as_table=None,
    ):
        self.fn = fn
        self.inputs = inputs
        self.where = where
        self.distribute = distribute
        self.as_table = as_table

    def to_version_keys(self) -> dict:
        """Return dict of config keys to merge into save_metadata.

        All values are plain Python objects (dicts, strings, bools, lists).
        Consumed in-memory to build save_metadata / the call_id (no longer a
        stored column).
        """
        keys = {}
        keys["__fn"] = getattr(self.fn, "__name__", repr(self.fn))
        keys["__fn_hash"] = _compute_fn_hash(self.fn)
        inputs_dict = self._serialize_inputs()
        if inputs_dict:
            keys["__inputs"] = inputs_dict
        # Always include __constants, even if empty (for consistency)
        direct = self._get_direct_constants()
        keys["__constants"] = direct if direct else {}
        if self.where is not None:
            # where can be a string or a Filter object
            # For RawFilter created from string, preserve original string format
            from .filters import RawFilter

            if isinstance(self.where, str):
                keys["__where"] = self.where
            elif isinstance(self.where, RawFilter) and hasattr(
                self.where, "_original_str"
            ):
                # Preserve original string for string-based filters
                keys["__where"] = self.where._original_str
            elif hasattr(self.where, "to_key"):
                keys["__where"] = self.where.to_key()
            else:
                keys["__where"] = str(self.where)
        if self.distribute:
            keys["__distribute"] = True
        if self.as_table:
            if isinstance(self.as_table, list):
                keys["__as_table"] = sorted(self.as_table)
            elif self.as_table is True:
                keys["__as_table"] = True
        return keys

    def to_call_id(self) -> str:
        """Stable identifier for this for_each() call site, 16 hex chars.

        Hashes the version keys minus ``__fn_hash`` (and other per-record
        fields) so that cosmetic edits to the function source do not fork
        the call site.  Two for_each() calls with the same loadable inputs,
        constants, where, distribute, and as_table settings produce the
        same call_id even if the function body was reformatted between runs.

        Used to disambiguate records produced by the same function invoked
        from multiple call sites — without this, function_name alone collides
        when distinguishing one call site's output from another's.
        """
        return call_id_from_version_keys(self.to_version_keys())

    def _get_direct_constants(self) -> dict:
        """Return scalar constant inputs (non-loadable values).

        ColName and PathOutput markers are excluded: they are resolution
        markers, not real constant values, and their effect is determined per
        combo/column at run time rather than being a fixed scalar. ColName
        resolves from the input variable (already captured in ``__inputs``);
        PathOutput resolves a template into an output path, which is write
        bookkeeping rather than computation identity. Including either raw
        marker object would also break version-key hashing (they are not
        JSON-serializable). PathInput is excluded for the same
        JSON-serializability reason -- despite _is_loadable now excluding it
        (its per-combo resolution moved to scifor's for_each loop), it still
        belongs in ``__inputs`` via its own ``to_key()``, not here.

        A single-valued :class:`~scidb.parameter.Parameter` is **unwrapped to
        its value**. The wrapper is a discovery/documentation aid, never part
        of computation identity: ``Parameter(30)`` and a bare ``30`` are the
        same input and must hash identically, or the same pipeline forks in
        history depending on how it was declared. Without unwrapping, the
        wrapper reached ``canonical_hash`` as an unknown type and raised
        ``ValueError: Unserializable data type``.

        In normal execution a Parameter never actually gets this far --
        ``for_each`` expands it as an ``EachOf`` first, so ``self.inputs``
        already holds the concrete value. This stays as the defence for a
        ``ForEachConfig`` built directly, and as the thing that makes the
        one-value case provably identical either way.
        """
        from scifor import ColName, PathInput, PathOutput

        from .foreach import _is_loadable
        from .parameter import Parameter

        def _unwrap(v):
            if isinstance(v, Parameter) and len(v.alternatives) == 1:
                return v.alternatives[0]
            return v

        return {
            k: _unwrap(v)
            for k, v in self.inputs.items()
            if not _is_loadable(v) and not isinstance(v, (ColName, PathOutput, PathInput))
        }

    def _serialize_inputs(self) -> dict:
        """Serialize loadable inputs to a dict.

        Only includes loadable inputs (variable types, Fixed, ColumnSelection,
        Merge) — constants are already included in save_metadata directly.
        PathInput is included too even though _is_loadable excludes it (its
        resolution moved to scifor's for_each loop, not scidb's variable
        loader) -- it still needs a stable identity in ``__inputs`` via its
        own ``to_key()``, or two different templates would collapse into the
        same version-key group.

        Returns a dict (not JSON string) so it can be carried in the in-memory
        config keys that build save_metadata.
        """
        from scifor import PathInput

        from .foreach import _is_loadable

        result = {}
        for name in sorted(self.inputs):
            spec = self.inputs[name]
            if _is_loadable(spec) or isinstance(spec, PathInput):
                if hasattr(spec, "to_key"):
                    result[name] = spec.to_key()
                elif isinstance(spec, type):
                    result[name] = spec.__name__
                else:
                    result[name] = repr(spec)
        return result
