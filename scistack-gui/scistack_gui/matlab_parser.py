"""
Static parser for MATLAB .m files.

Extracts function signatures and classdef declarations without running MATLAB.
Used by the MATLAB registry to discover functions and variable types from
configured .m file paths.
"""

import logging
import re
from dataclasses import dataclass, field
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
    r"(?:\[([^\]]*)\]\s*=\s*)"  # [out1, out2] = ...
    r"|"
    r"(?:(\w+)\s*=\s*)"  # out = ...
    r")?"
    r"(\w+)"  # function name
    r"\s*\(([^)]*)\)",  # (param1, param2, ...)
    re.MULTILINE,
)

# Regex for MATLAB classdef: classdef ClassName < ParentClass
_CLASSDEF_RE = re.compile(
    r"^\s*classdef\s+(\w+)\s*<\s*([\w.]+)",
    re.MULTILINE,
)

# MATLAB block comments: a line containing only `%{`, everything up to a
# line containing only `%}`. Stripped before either regex above runs, so
# example code inside a block comment (a common way scientists leave
# "here's how to call this" notes) never false-positives as a real
# function/classdef declaration.
_BLOCK_COMMENT_RE = re.compile(
    r"^[ \t]*%\{[ \t]*$.*?^[ \t]*%\}[ \t]*$\n?",
    re.DOTALL | re.MULTILINE,
)

# MATLAB line continuation (`...` through end of line, including any
# trailing comment) followed by the leading whitespace of the next line.
# Collapsed to a single space before matching so a signature split across
# multiple lines doesn't leak "...\n    " into a captured parameter name.
_LINE_CONTINUATION_RE = re.compile(r"\.\.\.[^\n]*\n[ \t]*")


def _preprocess_for_parsing(text: str) -> str:
    """Strip block comments and collapse line continuations before either
    parser regex runs. Never applied to the bytes used for ``source_hash`` —
    only to the text used to locate function/classdef declarations."""
    text = _BLOCK_COMMENT_RE.sub("", text)
    text = _LINE_CONTINUATION_RE.sub(" ", text)
    return text


def _extract_docstring(text: str, after_pos: int) -> str | None:
    """Collect MATLAB help text: the run of ``%``-prefixed comment lines
    starting immediately after ``after_pos`` (the end of the function
    declaration), stopping at the first line that isn't a comment —
    including a blank line, matching how MATLAB's own ``help`` command
    finds the H1/help block. Returns ``None`` if there is no such block.
    """
    line_end = text.find("\n", after_pos)
    remainder = text[line_end + 1 :] if line_end != -1 else ""
    doc_lines: list[str] = []
    for line in remainder.splitlines():
        stripped = line.strip()
        if not stripped.startswith("%"):
            break
        # Drop the leading '%' and at most one following space.
        content = stripped[1:]
        if content.startswith(" "):
            content = content[1:]
        doc_lines.append(content)
    if not doc_lines:
        return None
    return "\n".join(doc_lines)


@dataclass
class MatlabFunctionInfo:
    """Parsed metadata for a MATLAB function file."""

    name: str
    """Function name (from the function declaration)."""

    file_path: Path | None
    """Absolute path to the .m file. ``None`` for a manually-declared
    reference to a MATLAB built-in/toolbox function — there is no backing
    .m file to point at (see scistack_gui.api.builtin_functions)."""

    params: list[str]
    """Parameter names (input arguments)."""

    source_hash: str
    """SHA-256 hex digest of the file contents (for lineage)."""

    n_outputs: int = 0
    """Number of declared output arguments (0 = void, 1 = scalar, 2+ = multi)."""

    output_names: list[str] = field(default_factory=list)
    """Names of declared output arguments, in order."""

    docstring: str | None = None
    """Help text: the contiguous ``%``-comment lines immediately following
    the function declaration (MATLAB's own ``help``/H1-line convention).
    ``None`` if the function has no such comment block."""

    language: str = "matlab"


def parse_matlab_function(path: Path) -> MatlabFunctionInfo | None:
    """Parse a MATLAB function file and extract its signature.

    Returns ``None`` if the file cannot be read, does not contain a valid
    function declaration, or contains a ``classdef`` declaration (any
    ``function`` inside such a file is a method belonging to that class,
    never a standalone pipeline function).
    """
    logger.debug("[matlab_parser] Parsing function file: %s", path)
    try:
        raw = path.read_bytes()
    except OSError as e:
        logger.warning(
            "[matlab_parser] Cannot read MATLAB function file %s: %s", path, e
        )
        return None

    # Hash raw bytes so the digest matches MATLAB's fileread() which
    # preserves \r\n line endings (read_text would normalise them away).
    logger.debug("[matlab_parser] Computing source hash")
    source_hash = sha256(raw).hexdigest()
    text = _preprocess_for_parsing(raw.decode("utf-8", errors="replace"))

    # A file containing ANY classdef declaration — not just a BaseVariable
    # one — never also defines a standalone pipeline function: MATLAB's
    # one-file-one-entity rule means a `function` match inside such a file
    # is always a method (constructor, a TestMethodSetup/Test method, ...),
    # not top-level callable code. Without this check, folder-scan discovery
    # over e.g. a `matlab.unittest.TestCase` test suite mis-registers each
    # test class's local setup helper (often named identically across many
    # files, e.g. `resetSchema`/`addPaths`) as if it were real pipeline
    # code, silently overwriting same-named registrations from other files
    # (see matlab_registry._register_matlab_function's "shadows previous
    # definition" warning — regression test in test_matlab.py).
    if _CLASSDEF_RE.search(text):
        logger.debug(
            "[matlab_parser] %s contains a classdef; skipping function "
            "extraction (any 'function' inside it belongs to that class)",
            path,
        )
        return None

    logger.debug("[matlab_parser] Searching for function declaration")
    m = _FUNCTION_RE.search(text)
    if m is None:
        logger.debug("[matlab_parser] No function declaration found in %s", path)
        return None

    # Group 3 is always the function name.
    fn_name = m.group(3)
    logger.debug("[matlab_parser] Found function: %s", fn_name)
    # Group 4 is the parameter list.
    raw_params = m.group(4).strip()
    params = (
        [p.strip() for p in raw_params.split(",") if p.strip()] if raw_params else []
    )
    logger.debug("[matlab_parser] Function has %d parameters", len(params))

    # Count output arguments and extract names from the declaration.
    #   Group 1: "[out1, out2]" → count comma-separated names
    #   Group 2: "out"          → single output
    #   Neither:                → void (0 outputs)
    if m.group(1) is not None:
        output_names = [o.strip() for o in m.group(1).split(",") if o.strip()]
        n_outputs = len(output_names)
    elif m.group(2) is not None:
        output_names = [m.group(2).strip()]
        n_outputs = 1
    else:
        output_names = []
        n_outputs = 0
    logger.debug("[matlab_parser] Function has %d outputs", n_outputs)

    docstring = _extract_docstring(text, m.end())
    logger.debug(
        "[matlab_parser] Function %s has docstring: %s",
        fn_name,
        docstring is not None,
    )

    logger.debug("[matlab_parser] Successfully parsed function: %s", fn_name)
    return MatlabFunctionInfo(
        name=fn_name,
        # The caller (config._resolve_glob_paths) already normalizes paths
        # to an absolute, non-symlink-followed form. We deliberately do NOT
        # call .resolve() here because on Windows it canonicalizes mapped
        # drives (y:\...) to UNC (\\server\share\...), which VS Code refuses
        # to open without security.allowedUNCHosts — breaking the GUI's
        # reveal_in_editor feature.
        file_path=path,
        params=params,
        source_hash=source_hash,
        n_outputs=n_outputs,
        output_names=output_names,
        docstring=docstring,
    )


def parse_matlab_variable(path: Path) -> str | None:
    """Parse a MATLAB classdef file for a BaseVariable subclass.

    Looks for ``classdef Foo < scidb.BaseVariable`` (or any parent path
    ending in ``BaseVariable``). Returns the class name or ``None``.
    """
    logger.debug("[matlab_parser] Parsing variable classdef file: %s", path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.warning(
            "[matlab_parser] Cannot read MATLAB variable file %s: %s", path, e
        )
        return None
    text = _preprocess_for_parsing(text)

    logger.debug("[matlab_parser] Searching for classdef declaration")
    m = _CLASSDEF_RE.search(text)
    if m is None:
        logger.debug("[matlab_parser] No classdef declaration found in %s", path)
        return None

    class_name = m.group(1)
    parent = m.group(2)
    logger.debug("[matlab_parser] Found classdef: %s < %s", class_name, parent)

    # Accept any parent that ends with "BaseVariable" (e.g. scidb.BaseVariable).
    if parent.endswith("BaseVariable"):
        logger.debug("[matlab_parser] Class %s is a BaseVariable subclass", class_name)
        return class_name

    logger.debug(
        "[matlab_parser] Class %s does not inherit from BaseVariable", class_name
    )
    return None


# MATLAB has no module-level globals, so a Python-style ``NAME =
# PathInput(...)``/``NAME = Sweep(...)`` binding doesn't translate
# directly. Convention: a "value getter" — a zero-argument function whose
# body constructs and returns a scifor.PathInput/scifor.Sweep (or the
# scidb re-export) — stands in for it, named after the object it exposes
# (mirrors the existing one-function-per-file rule already enforced for
# regular functions). See docs/claude/code-discovery-categories.md.
_PATHINPUT_VALUE_RE = re.compile(r"=\s*(?:scifor\.|scidb\.)?PathInput\s*\(")
_SWEEP_VALUE_RE = re.compile(r"=\s*(?:scifor\.|scidb\.)?Sweep\s*\(")


def _getter_context(
    path: Path, value_re: "re.Pattern[str]"
) -> "tuple[str, str] | None":
    """Shared location logic for classification (``_parse_value_getter``)
    AND literal extraction (``extract_path_input_literal``/
    ``extract_sweep_literal``): a zero-arg function whose body (up to the
    next function declaration, or EOF) contains a construction matching
    ``value_re``. Static regex only — never runs MATLAB, matching this
    file's "extract without running MATLAB" principle. Returns
    ``(fn_name, body_text)`` or ``None``.
    """
    try:
        raw = path.read_bytes()
    except OSError as e:
        logger.warning("[matlab_parser] Cannot read MATLAB file %s: %s", path, e)
        return None
    text = _preprocess_for_parsing(raw.decode("utf-8", errors="replace"))

    # Same one-file-one-entity rule as parse_matlab_function: a classdef
    # file's "function" matches are always methods, never a getter.
    if _CLASSDEF_RE.search(text):
        return None

    m = _FUNCTION_RE.search(text)
    if m is None:
        return None
    fn_name = m.group(3)
    raw_params = m.group(4).strip()
    if raw_params:
        return None  # a value getter takes no arguments

    # Search only this function's own body — up to the next function
    # declaration (if any) or end of file — so a getter sitting above an
    # unrelated function in the same file doesn't false-positive on the
    # unrelated function's own construction.
    body = text[m.end() :]
    next_fn = _FUNCTION_RE.search(body)
    if next_fn is not None:
        body = body[: next_fn.start()]
    if value_re.search(body) is None:
        return None
    return fn_name, body


def _parse_value_getter(path: Path, value_re: "re.Pattern[str]") -> str | None:
    """Shared implementation for ``parse_matlab_path_input``/
    ``parse_matlab_sweep``. Returns the function's name (the object's
    exposed identity) or ``None``."""
    ctx = _getter_context(path, value_re)
    return ctx[0] if ctx is not None else None


def parse_matlab_path_input(path: Path) -> str | None:
    """Parse a MATLAB "PathInput getter" file. See ``_parse_value_getter``."""
    return _parse_value_getter(path, _PATHINPUT_VALUE_RE)


def parse_matlab_sweep(path: Path) -> str | None:
    """Parse a MATLAB "Sweep getter" file. See ``_parse_value_getter``."""
    return _parse_value_getter(path, _SWEEP_VALUE_RE)


# ---------------------------------------------------------------------------
# Best-effort literal extraction — construct a REAL PathInput/Sweep object
# from a getter's construction call, when its arguments are simple literals
# (quoted strings / numbers). Still purely static text (no MATLAB run): a
# construction whose arguments reference a MATLAB variable/expression
# rather than a literal returns None, and the caller falls back to
# name-only tracking (see matlab_registry.py). See
# docs/claude/code-discovery-categories.md.
# ---------------------------------------------------------------------------

_MATLAB_NUMBER_RE = re.compile(r"^[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?$")


def _extract_call_args(body: str, value_re: "re.Pattern[str]") -> str | None:
    """The raw text between the matching parens of the FIRST construction
    call in ``body`` matching ``value_re`` (``value_re`` must end its match
    right after the opening ``(``, as ``_PATHINPUT_VALUE_RE``/
    ``_SWEEP_VALUE_RE`` do). Returns ``None`` if no match, or the parens
    are unbalanced (malformed/unparseable)."""
    m = value_re.search(body)
    if m is None:
        return None
    start = m.end()
    depth = 1
    i = start
    n = len(body)
    while i < n and depth > 0:
        c = body[i]
        if c in "'\"":
            quote = c
            i += 1
            while i < n:
                if body[i] == quote:
                    if i + 1 < n and body[i + 1] == quote:
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return body[start : i - 1]


def _split_matlab_args(args_text: str) -> list[str]:
    """Split a MATLAB argument list on top-level commas, respecting quoted
    strings (both ``'...'`` and ``"..."``, each with MATLAB's doubled-quote
    escaping) and nested brackets, so a comma inside a string literal or a
    nested ``[...]``/``{...}`` never splits there."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    i = 0
    n = len(args_text)
    while i < n:
        c = args_text[i]
        if c in "'\"":
            quote = c
            current.append(c)
            i += 1
            while i < n:
                current.append(args_text[i])
                if args_text[i] == quote:
                    if i + 1 < n and args_text[i + 1] == quote:
                        current.append(args_text[i + 1])
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if c in "([{":
            depth += 1
            current.append(c)
            i += 1
            continue
        if c in ")]}":
            depth -= 1
            current.append(c)
            i += 1
            continue
        if c == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(c)
        i += 1
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_matlab_literal_token(token: str) -> "tuple[bool, object]":
    """``(True, value)`` if *token* is a simple MATLAB literal (a quoted
    string or a number), else ``(False, None)`` — a MATLAB variable
    reference, function call, or expression is deliberately NOT evaluated
    (this never runs MATLAB)."""
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"":
        quote = token[0]
        inner = token[1:-1]
        return True, inner.replace(quote * 2, quote)
    if _MATLAB_NUMBER_RE.match(token):
        return True, (
            float(token) if ("." in token or "e" in token.lower()) else int(token)
        )
    return False, None


def extract_path_input_literal(path: Path) -> "tuple[str, str | None] | None":
    """Best-effort ``(template, root_folder)`` from a PathInput getter's
    construction call. ``None`` if it isn't a simple literal call (e.g. the
    template is a MATLAB variable) — the caller then falls back to
    name-only tracking (matlab_registry.py)."""
    ctx = _getter_context(path, _PATHINPUT_VALUE_RE)
    if ctx is None:
        return None
    _, body = ctx
    args_text = _extract_call_args(body, _PATHINPUT_VALUE_RE)
    if args_text is None:
        return None
    args = _split_matlab_args(args_text)
    if not args:
        return None
    ok, template = _parse_matlab_literal_token(args[0])
    if not ok or not isinstance(template, str):
        return None
    root_folder: str | None = None
    i = 1
    while i < len(args) - 1:
        ok_key, key = _parse_matlab_literal_token(args[i])
        if ok_key and key == "root_folder":
            ok_val, val = _parse_matlab_literal_token(args[i + 1])
            if ok_val and isinstance(val, str):
                root_folder = val
            i += 2
            continue
        i += 1
    return template, root_folder


def extract_sweep_literal(path: Path) -> "list | None":
    """Best-effort value list from a Sweep getter's construction call.
    ``None`` if it isn't ALL simple literals (any single non-literal value
    — a MATLAB variable/expression — invalidates the whole list rather
    than silently dropping just that one value)."""
    ctx = _getter_context(path, _SWEEP_VALUE_RE)
    if ctx is None:
        return None
    _, body = ctx
    args_text = _extract_call_args(body, _SWEEP_VALUE_RE)
    if args_text is None:
        return None
    args = _split_matlab_args(args_text)
    if not args:
        return None
    values = []
    for tok in args:
        ok, val = _parse_matlab_literal_token(tok)
        if not ok:
            return None
        values.append(val)
    return values


def classify_matlab_file(
    path: Path,
) -> tuple[str, str] | tuple[str, MatlabFunctionInfo] | None:
    """Classify a single .m file as a variable, PathInput getter, Sweep
    getter, or a function by content, for folder-scan discovery (no
    explicit ``matlab.functions``/``matlab.variables`` split available).

    Mirrors how Python's ``_scan_module_functions``/``_scan_module_path_inputs``/
    ``_scan_module_sweeps`` classify each imported object dynamically
    rather than requiring the config to pre-sort files. Tries the classdef
    parse first (cheaper, and a ``BaseVariable`` classdef with methods
    would otherwise also match the function regex), then the value-getter
    checks (a getter also matches the plain function regex — zero args,
    one output — so it must be checked BEFORE ``parse_matlab_function``).

    Returns ``("variable", class_name)``, ``("path_input", name)``,
    ``("sweep", name)``, ``("function", MatlabFunctionInfo)``, or ``None``
    if the file is none of those (e.g. a script with no function
    declaration, or unreadable).
    """
    var_name = parse_matlab_variable(path)
    if var_name is not None:
        return ("variable", var_name)

    pi_name = parse_matlab_path_input(path)
    if pi_name is not None:
        return ("path_input", pi_name)

    sweep_name = parse_matlab_sweep(path)
    if sweep_name is not None:
        return ("sweep", sweep_name)

    fn_info = parse_matlab_function(path)
    if fn_info is not None:
        return ("function", fn_info)

    return None
