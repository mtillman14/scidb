"""Custom exceptions for scidb."""


class SciStackError(Exception):
    """Base exception for all scidb errors."""

    pass


class NotRegisteredError(SciStackError):
    """Raised when trying to save/load an unregistered variable type."""

    pass


class NotFoundError(SciStackError):
    """Raised when no matching data is found for the given metadata."""

    pass


class DatabaseNotConfiguredError(SciStackError):
    """Raised when trying to use implicit database before configuration."""

    pass


class ReservedMetadataKeyError(SciStackError):
    """Raised when user tries to use a reserved metadata key."""

    pass


class AmbiguousVersionError(SciStackError):
    """Raised when load() matches multiple variants and no branch filter narrows to one."""

    pass


class AmbiguousParamError(SciStackError):
    """Raised when a bare param name matches multiple namespaced keys in branch_params."""

    pass


class PipelineCycleError(SciStackError):
    """Raised when a Pipeline's variable-type dependency graph has a cycle.

    The one-step case is a function registered as consuming and producing
    the same variable type.
    """

    pass


class SchemaKeyTypeError(SciStackError):
    """Raised when a schema key's spelling is ambiguous or violates its type.

    Two situations:
    - A PathInput numeric fallback had to bridge spellings (e.g. trial=1
      matched "001" on disk) for a schema key with no declared type — the
      dataset has proven the spelling ambiguous, so the user must declare
      the key numeric or string via configure_database(schema_key_types=...).
    - A key declared "numeric" received a value that is not numeric.
    """

    # scifor.for_each aborts the whole run on this error instead of
    # recording a per-combo skip: the failure is a configuration problem
    # that would repeat identically for every combo.
    scifor_fatal = True


class DatabaseLockedError(SciStackError):
    """Raised when the database file is locked by another session.

    DuckDB allows one read-write connection (or multiple read-only ones);
    opening while a GUI/MATLAB session or another process holds the file
    raises this instead of a raw DuckDB IO error.
    """

    pass
