"""
Static parser for MATLAB .m files.

Extracts function signatures and classdef declarations without running MATLAB.
Used by the MATLAB registry to discover functions and variable types from
configured .m file paths.
"""

import logging
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

logger = logging.getLogger(__name__)

# Regex for MATLAB function declaration:
#   function [out1, out2] = name(in1, in2, ...)
#   function out = name(in1, ...)
#   function name(in1, ...)
_FUNCTION_RE = re.compile(
    r"^\s*function\s+"
    r"(?:"
    r"(?:\[([^\]]*)\]\s*=\s*)"    # [out1, out2] = ...
    r"|"
    r"(?:(\w+)\s*=\s*)"          # out = ...
    r")?"
    r"(\w+)"                      # function name
    r"\s*\(([^)]*)\)",            # (param1, param2, ...)
    re.MULTILINE,
)

# Regex for MATLAB classdef: classdef ClassName < ParentClass
_CLASSDEF_RE = re.compile(
    r"^\s*classdef\s+(\w+)\s*<\s*([\w.]+)",
    re.MULTILINE,
)


@dataclass
class MatlabFunctionInfo:
    """Parsed metadata for a MATLAB function file."""

    name: str
    """Function name (from the function declaration)."""

    file_path: Path
    """Absolute path to the .m file."""

    params: list[str]
    """Parameter names (input arguments)."""

    source_hash: str
    """SHA-256 hex digest of the file contents (for lineage)."""

    language: str = "matlab"


def parse_matlab_function(path: Path) -> MatlabFunctionInfo | None:
    """Parse a MATLAB function file and extract its signature.

    Returns ``None`` if the file cannot be read or does not contain a
    valid function declaration.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("Cannot read MATLAB function file %s: %s", path, e)
        return None

    source_hash = sha256(text.encode("utf-8")).hexdigest()

    m = _FUNCTION_RE.search(text)
    if m is None:
        logger.debug("No function declaration found in %s", path)
        return None

    # Group 3 is always the function name.
    fn_name = m.group(3)
    # Group 4 is the parameter list.
    raw_params = m.group(4).strip()
    params = [p.strip() for p in raw_params.split(",") if p.strip()] if raw_params else []

    return MatlabFunctionInfo(
        name=fn_name,
        file_path=path.resolve(),
        params=params,
        source_hash=source_hash,
    )


def parse_matlab_variable(path: Path) -> str | None:
    """Parse a MATLAB classdef file for a BaseVariable subclass.

    Looks for ``classdef Foo < scidb.BaseVariable`` (or any parent path
    ending in ``BaseVariable``). Returns the class name or ``None``.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning("Cannot read MATLAB variable file %s: %s", path, e)
        return None

    m = _CLASSDEF_RE.search(text)
    if m is None:
        return None

    class_name = m.group(1)
    parent = m.group(2)

    # Accept any parent that ends with "BaseVariable" (e.g. scidb.BaseVariable).
    if parent.endswith("BaseVariable"):
        return class_name

    return None
