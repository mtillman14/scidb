"""Fixed metadata wrapper for DataFrame inputs in for_each."""

from typing import Any


class Fixed:
    """
    Wrapper to specify fixed metadata overrides for a DataFrame input.

    Use this when an input should be filtered with different metadata
    than the current iteration's metadata.

    Works with plain DataFrames (filtered per-iteration using schema key columns).

    Example:
        # Always filter baseline to session="pre", regardless of current session
        for_each(
            compare_to_baseline,
            inputs={
                "baseline": Fixed(raw_df, session="pre"),
                "current": raw_df,
            },
            subject=subjects,
            session=sessions,
        )
    """

    def __init__(self, data: Any, **fixed_metadata: Any):
        """
        Args:
            data: A pandas DataFrame to filter per iteration,
                  or another scifor wrapper (Merge, ColumnSelection).
            **fixed_metadata: Metadata values that override the iteration metadata.
        """
        self.data = data
        self.fixed_metadata = fixed_metadata

    def to_key(self) -> str:
        """Return a canonical string for use as a version key."""
        from .column_selection import ColumnSelection

        if isinstance(self.data, ColumnSelection):
            inner_key = self.data.to_key()
        elif isinstance(self.data, type):
            inner_key = self.data.__name__
        else:
            inner_key = repr(self.data)
        sorted_kv = ", ".join(
            f"{k}={v!r}" for k, v in sorted(self.fixed_metadata.items())
        )
        if sorted_kv:
            return f"Fixed({inner_key}, {sorted_kv})"
        return f"Fixed({inner_key})"
