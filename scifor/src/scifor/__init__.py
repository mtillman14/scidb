"""scifor: Standalone for_each batch execution for data pipelines.

Works with plain DataFrames. No database required.

Example:
    import pandas as pd
    from scifor import set_schema, for_each, Col

    set_schema(["subject", "session"])

    raw_df = pd.DataFrame({
        "subject": [1, 1, 2, 2],
        "session": ["pre", "post", "pre", "post"],
        "emg":     [0.1,  0.2,  0.3,  0.4],
    })

    result = for_each(
        lambda signal: signal.mean(),
        inputs={"signal": raw_df},
        subject=[1, 2],
        session=["pre", "post"],
    )
"""

from .colname import ColName
from .column_selection import ColumnSelection
from .discovery import (
    ModuleWalkError,
    PathInsert,
    WalkResult,
    is_test_modname,
    is_test_path,
    purge_module,
    read_project_name,
    walk_package,
)
from .each_of import EachOf
from .filters import Col, ColFilter, CompoundFilter, NotFilter
from .fixed import Fixed
from .foreach import ColumnFunctionError, ForColumnsError, NoDataError, for_each
from .merge import Merge
from .pathinput import PathInput
from .pathoutput import PathOutput
from .schema import expand_schema_keys, get_schema, set_schema

__version__ = "0.1.0"

__all__ = [
    # Schema
    "set_schema",
    "get_schema",
    "expand_schema_keys",
    # Batch execution
    "for_each",
    "ColumnFunctionError",
    "ForColumnsError",
    "NoDataError",
    # Input wrappers
    "Fixed",
    "Merge",
    "ColumnSelection",
    "ColName",
    "EachOf",
    "PathInput",
    "PathOutput",
    # Filters
    "Col",
    "ColFilter",
    "CompoundFilter",
    "NotFilter",
    # Discovery
    "walk_package",
    "WalkResult",
    "ModuleWalkError",
    "is_test_path",
    "is_test_modname",
    "read_project_name",
    "PathInsert",
    "purge_module",
]
