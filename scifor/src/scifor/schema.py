"""Module-level schema key registry for scifor."""

_schema_keys: list[str] = []


def set_schema(keys: list[str]) -> None:
    """Set the global schema key list.

    Args:
        keys: Ordered list of schema key names (e.g. ["subject", "session"]).

    Called automatically by ``scidb.configure_database()`` as a side effect.
    Standalone users call this once before using ``for_each``.
    """
    global _schema_keys
    _schema_keys = list(keys)


def get_schema() -> list[str]:
    """Return a copy of the global schema key list."""
    return list(_schema_keys)


def expand_schema_keys(schema_keys: list[str], metadata_iterables: dict) -> dict:
    """Seed ``metadata_iterables`` with an empty list for each requested
    schema key, structural sugar for "iterate over these keys" without
    spelling out ``key=[]`` by hand.

    This is pure bookkeeping — it does no I/O. Actual value resolution for
    the ``[]`` placeholders happens downstream, wherever the caller's own
    empty-list resolver lives (scifor's own DataFrame scan for standalone
    use; scidb's database query when DB-backed). Both scifor.for_each() and
    scidb.for_each() call this same function so the "which keys to iterate"
    bookkeeping is written once and shared.

    Mutually exclusive with an already-populated ``metadata_iterables``:
    callers pass either schema_keys= or explicit **metadata_iterables, not
    both, in the same call.

    Args:
        schema_keys: Schema key names to iterate.
        metadata_iterables: The caller's existing metadata_iterables dict.
                    Must be empty when schema_keys is used.

    Returns:
        A new dict with one ``key: []`` entry per schema key.
    """
    if metadata_iterables:
        raise ValueError(
            "Cannot use both schema_keys and **metadata_iterables. "
            "Use schema_keys for automatic iteration, or **metadata_iterables "
            "for manual control."
        )
    return {key: [] for key in schema_keys}
