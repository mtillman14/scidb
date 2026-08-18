"""
Manual built-in/library function references.

Validates and registers a reference to a function the user did NOT write
themselves (e.g. ``numpy.mean``, ``pandas.read_csv``, a Python stdlib
call, or a native MATLAB command like ``mean``) as a normal function node,
alongside — never instead of — auto-discovered functions from the user's
own code. Shared by both the FastAPI route (``api/builtin_functions.py``)
and the JSON-RPC handler (``server.py``, VS Code extension mode).

Python references are restricted to the standard library plus numpy/pandas
(exactly what this feature is scoped to, not a general import backdoor).
MATLAB references are validated by shelling out to a real MATLAB
installation (``matlab -batch "disp(exist(...))"``) since there is no
lightweight way to confirm a MATLAB builtin/toolbox function exists
without one.

Manually-declared builtins aren't rediscovered by scanning disk, so they
are persisted (see ``pipeline_store.write_builtin_function``) and replayed
via :func:`replay_persisted_builtins` after every startup DB init and
every registry refresh (``pipeline_service.refresh_module``), both of
which clear the in-memory function registries.
"""

from __future__ import annotations

import importlib
import logging
import re
import shutil
import subprocess
import sysconfig
from pathlib import Path

from scistack_gui import registry
from scistack_gui.matlab_parser import MatlabFunctionInfo

logger = logging.getLogger(__name__)

# Python: importable module roots this feature is scoped to (plus the
# standard library itself, checked separately). Not a general
# arbitrary-import backdoor — matches exactly what was asked for.
_ALLOWED_PY_PACKAGE_ROOTS = {"numpy", "pandas"}

# MATLAB: a strict identifier check BEFORE the name ever touches a
# constructed shell command — never interpolate raw user input otherwise.
_MATLAB_IDENTIFIER_RE = re.compile(r"^[A-Za-z]\w*$")

_MATLAB_EXIST_TIMEOUT_S = 30


def create_builtin_function(language: str, reference: str) -> dict:
    language = (language or "").strip().lower()
    reference = (reference or "").strip()
    logger.info(
        "[builtin_function_service] create_builtin_function request: "
        "language=%r reference=%r",
        language,
        reference,
    )

    if not reference:
        return {"ok": False, "error": "Enter a function name or reference."}

    if language == "python":
        return _create_python_builtin(reference)
    if language == "matlab":
        return _create_matlab_builtin(reference)
    return {"ok": False, "error": f"Unknown language: {language!r}"}


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


def _resolve_python_builtin(reference: str) -> tuple[dict | None, str | None, object]:
    """Validate *reference* and resolve it to a real callable.

    Returns ``(error_response, None, None)`` on failure, or
    ``(None, qualified_name, fn)`` on success. Shared by creation (which
    also persists) and replay-on-refresh (which doesn't need to persist
    again, but does need to re-validate — cheap for Python, unlike MATLAB).
    """
    if "." in reference:
        module_path, _, attr_name = reference.rpartition(".")
    else:
        module_path, attr_name = "builtins", reference

    if not attr_name.isidentifier():
        return (
            {"ok": False, "error": f"'{reference}' is not a valid Python reference."},
            None,
            None,
        )

    if module_path != "builtins":
        root = module_path.split(".")[0]
        if root not in _ALLOWED_PY_PACKAGE_ROOTS:
            try:
                root_mod = importlib.import_module(root)
            except ImportError:
                return (
                    {"ok": False, "error": f"'{root}' is not installed or not importable."},
                    None,
                    None,
                )
            if not _is_stdlib_module(root_mod):
                return (
                    {
                        "ok": False,
                        "error": (
                            f"'{root}' is not allowed — built-in function references "
                            "are restricted to the Python standard library, numpy, "
                            "and pandas."
                        ),
                    },
                    None,
                    None,
                )

    try:
        mod = importlib.import_module(module_path)
    except ImportError as e:
        return {"ok": False, "error": f"Could not import '{module_path}': {e}"}, None, None

    fn = getattr(mod, attr_name, None)
    if fn is None:
        return (
            {"ok": False, "error": f"'{attr_name}' not found in '{module_path}'."},
            None,
            None,
        )
    if not callable(fn):
        return {"ok": False, "error": f"'{reference}' is not callable."}, None, None

    qualified_name = attr_name if module_path == "builtins" else f"{module_path}.{attr_name}"
    return None, qualified_name, fn


def _is_stdlib_module(mod) -> bool:
    """True if *mod* lives in the standard library.

    Deliberately avoids ``sys.stdlib_module_names`` (Python 3.10+ only —
    this project's floor is 3.9): a module with no ``__file__`` is a
    built-in/frozen module (``sys``, ``itertools`` — definitely stdlib);
    otherwise check whether its file lives under the interpreter's stdlib
    directory.
    """
    file = getattr(mod, "__file__", None)
    if file is None:
        return True
    stdlib_dir = Path(sysconfig.get_paths()["stdlib"]).resolve()
    try:
        Path(file).resolve().relative_to(stdlib_dir)
        return True
    except ValueError:
        return False


def _create_python_builtin(reference: str) -> dict:
    error, qualified_name, fn = _resolve_python_builtin(reference)
    if error is not None:
        return error

    registry.register_builtin_function(qualified_name, fn)
    _persist_builtin(qualified_name, "python")

    logger.info("[builtin_function_service] Registered Python builtin: %s", qualified_name)
    return {"ok": True, "name": qualified_name}


# ---------------------------------------------------------------------------
# MATLAB
# ---------------------------------------------------------------------------


def _create_matlab_builtin(reference: str) -> dict:
    if not _MATLAB_IDENTIFIER_RE.match(reference):
        return {
            "ok": False,
            "error": "MATLAB function names must be a plain identifier "
            "(letters, digits, underscore, starting with a letter).",
        }

    matlab_exe = shutil.which("matlab")
    if matlab_exe is None:
        return {
            "ok": False,
            "error": "MATLAB was not found on PATH. MATLAB must be installed "
            "and on PATH to validate a built-in function reference.",
        }

    # `reference` is already validated against a strict identifier regex
    # above, so it's safe to interpolate into the MATLAB literal below —
    # never do this before that check has run.
    try:
        result = subprocess.run(
            [matlab_exe, "-batch", f"disp(exist('{reference}'))"],
            capture_output=True,
            text=True,
            timeout=_MATLAB_EXIST_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timed out waiting for MATLAB to respond."}
    except OSError as e:
        return {"ok": False, "error": f"Could not run MATLAB: {e}"}

    exists_code = _last_nonblank_line(result.stdout)
    if exists_code is None or exists_code == "0" or not exists_code.isdigit():
        logger.info(
            "[builtin_function_service] MATLAB exist('%s') == %r; rejecting",
            reference,
            exists_code,
        )
        return {
            "ok": False,
            "error": f"MATLAB does not recognize '{reference}' as a function, "
            "built-in, or class (exist() returned 0).",
        }

    _register_matlab_builtin_in_memory(reference)
    _persist_builtin(reference, "matlab")

    logger.info("[builtin_function_service] Registered MATLAB builtin: %s", reference)
    return {"ok": True, "name": reference}


def _last_nonblank_line(text: str | None) -> str | None:
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else None


def _register_matlab_builtin_in_memory(reference: str) -> None:
    from scistack_gui import matlab_registry

    info = MatlabFunctionInfo(
        name=reference,
        file_path=None,
        params=[],
        source_hash="",
        n_outputs=0,
        output_names=[],
    )
    matlab_registry.register_builtin_function(info)


# ---------------------------------------------------------------------------
# Persistence / replay
# ---------------------------------------------------------------------------


def _persist_builtin(name: str, language: str) -> None:
    from scistack_gui import pipeline_store
    from scistack_gui.db import get_db

    pipeline_store.write_builtin_function(get_db(), name, language)


def replay_persisted_builtins(db) -> dict:
    """Re-register every persisted manual builtin function reference.

    Called after startup DB init and after every registry refresh
    (``registry.load_from_config``/``refresh_all`` and
    ``matlab_registry.load_from_config``/``refresh_all`` all clear the
    in-memory registries — builtins have no file on disk to be
    rediscovered from, so they must be explicitly replayed).

    Python references are cheaply re-validated (a plain import — catches
    e.g. numpy having been uninstalled since). MATLAB references are
    NOT re-validated by shelling out to MATLAB again — that's slow and
    would make every refresh fail hard if MATLAB happens to be
    momentarily unavailable; a MATLAB builtin already passed validation
    once, at creation time, and that's trusted on replay.
    """
    from scistack_gui import pipeline_store

    rows = pipeline_store.get_builtin_functions(db)
    counts = {"python": 0, "matlab": 0}
    failed = []
    for row in rows:
        name, language = row["name"], row["language"]
        if language == "python":
            error, qualified_name, fn = _resolve_python_builtin(name)
            if error is not None:
                failed.append({"name": name, "error": error["error"]})
                continue
            registry.register_builtin_function(qualified_name, fn)
            counts["python"] += 1
        elif language == "matlab":
            _register_matlab_builtin_in_memory(name)
            counts["matlab"] += 1
        else:
            logger.warning(
                "[builtin_function_service] Unknown language %r for persisted builtin %r",
                language,
                name,
            )

    if failed:
        logger.warning(
            "[builtin_function_service] Failed to restore %d persisted builtin(s): %s",
            len(failed),
            failed,
        )
    logger.info("[builtin_function_service] Replayed persisted builtins: %s", counts)
    return {"counts": counts, "failed": failed}
