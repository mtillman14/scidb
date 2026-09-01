"""
Generate ready-to-paste MATLAB commands for running pipeline functions.

The generated script configures the database, registers variable types,
and calls ``scihist.for_each`` with the correct inputs, outputs, and
schema arguments — all formatted as MATLAB syntax.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _entities_script_lines(
    entities_script: "str | None",
    entities_file: "str | None" = None,
    project_root: "str | None" = None,
) -> list[str]:
    """Lines that bring declared entities into scope, or ``[]``.

    Two sources, because two coexist: the TOML entities file (the one the
    GUI writes, read through ``scidb.entities()``) and a legacy MATLAB
    entities script, which stays readable. Both are emitted when both are
    configured — they declare different names, and dropping either would
    make a name silently undefined at the point the generated command uses
    it.

    ``project_root`` is passed to ``scidb.entities`` explicitly. Without it
    MATLAB resolves the project by walking up from its own **cwd**, which is
    wherever the user's MATLAB happens to be sitting — outside the project
    that finds no config at all, and every declared Parameter/PathInput is
    then silently out of scope (the load logs ``0 variable(s), 0
    parameter(s), 0 path input(s) ... from .``). It is also what tells the
    self-healing classdef materialization in ``+scidb/entities.m`` which
    project's entities file to read.

    Must be emitted AFTER the addpath block (both live on one of those
    directories) and before anything that references a declared entity by
    name.

    Re-run on every generated command rather than once per session. A
    MATLAB script is re-read from disk each time, and ``scidb.entities()``
    re-reads whenever the file's mtime changes, so either way a GUI entity
    edit is visible to a KEPT-WARM session (``matlab_sidecar``) with no
    cache-clearing. That property is why the entities file was a plain
    script rather than a classdef whose Constant properties would be cached
    for the life of the session; TOML keeps it — see
    docs/claude/entity-editability-model.md.
    """
    lines: list[str] = []
    if entities_file:
        call = (
            f"scidb.entities('{_escape_matlab_string(project_root)}');"
            if project_root
            else "scidb.entities();"
        )
        lines += [
            "% Entity declarations (Variables/Parameters/PathInputs) from "
            f"{Path(entities_file).name}",
            call,
            "",
        ]
    if entities_script:
        lines += [
            "% Entity declarations from the MATLAB entities script",
            f"{Path(entities_script).stem};",
            "",
        ]
    return lines




def _project_root_lines(
    project_root: "str | None", path_inputs: "dict | None" = None
) -> list[str]:
    """Lines pinning scifor's resolution base for rootless PathInputs, or ``[]``.

    A ``PathInput`` declared with no ``root_folder`` resolves its relative
    template against the nearest project root found by walking up from the
    **cwd**. Under MATLAB the cwd is a temp script directory, so that walk
    finds the wrong project or none at all and every relative template misses.

    The generated script therefore states the project explicitly. This is
    emitted for every command that knows its project root, not only ones with
    an entities file, so the guarantee never depends on unrelated config.
    ``scidb.entities`` pins the same thing for hand-written scripts (see
    ``scimatlab.bridge.set_pathinput_project_root``); pinning twice is
    idempotent.

    Must come after the pyenv preamble (it is a ``py.*`` call) and before the
    first ``for_each``. Deliberately NOT written into each PathInput's
    ``root_folder``: that is part of the recorded identity of the input, and
    rewriting it is what produced ``__unresolved__`` ghost nodes on the canvas
    — see ``_format_path_input``.
    """
    if not project_root:
        rootless = [
            p for p, pi in (path_inputs or {}).items() if not pi.get("root_folder")
        ]
        if rootless:
            logger.warning(
                "generate_matlab_command: no project root, but %s use a PathInput "
                "with no root_folder — those will resolve against MATLAB's cwd "
                "(a temp script dir) and their relative templates will not be found",
                ", ".join(sorted(rootless)),
            )
        return []
    return [
        "% Resolve rootless PathInput templates against this project, not MATLAB's cwd",
        "py.scimatlab.bridge.set_pathinput_project_root("
        f"'{_escape_matlab_string(project_root)}');",
        "",
    ]


def _unresolvable_var_type_lines(var_types) -> list[str]:
    """Comment lines naming variable types the generated script is about to
    call as ``Type()`` that nothing in this project accounts for.

    A MATLAB variable resolves only if a classdef file for it is on the
    path. Two things can supply one: a .m file the registry parsed, or a
    declaration in the entities file, which ``+scidb/entities.m``
    materializes a stub for at the top of the generated script. A name with
    neither will fail at the ``for_each`` call with ``Unrecognized function
    or variable 'X'`` and no indication of why — which is exactly the
    failure this preflight exists to pre-empt, so it is reported at
    generation time, in the script, and in the log.

    Declared-but-not-yet-materialized names are NOT reported: the entities
    call fixes those before the run reaches them.
    """
    names = sorted({str(t) for t in var_types if t})
    if not names:
        return []

    known: set[str] = set()
    try:
        from scistack_gui import matlab_registry

        known |= set(matlab_registry._matlab_variables)
        config = getattr(matlab_registry, "_config", None)
    except ImportError:  # pragma: no cover - GUI always has this
        config = None

    entities_file = getattr(config, "entities_file", None)
    if entities_file is not None:
        try:
            from scidb.entities import load as _load_entities

            known |= set(_load_entities(entities_file).variables)
        except Exception as e:
            logger.warning(
                "generate_matlab_command: could not read declared variables "
                "from %s (%s); preflight may over-report",
                entities_file,
                e,
            )

    unknown = [n for n in names if n not in known]
    if not unknown:
        return []

    logger.warning(
        "generate_matlab_command: no MATLAB classdef and no entity declaration "
        "for %s — the generated script will fail with 'Unrecognized function "
        "or variable' unless these resolve on the MATLAB path",
        ", ".join(unknown),
    )
    return [
        f"% WARNING: no classdef and no entity declaration found for: "
        f"{', '.join(unknown)}",
        "%          Create the variable in the GUI, or add its .m file to a "
        "configured MATLAB path,",
        "%          or this run will fail with 'Unrecognized function or "
        "variable'.",
        "",
    ]


def generate_matlab_command(
    function_name: str,
    db_path: str,
    schema_keys: list[str],
    variants: list[dict] | None = None,
    schema_filter: dict[str, list] | None = None,
    schema_level: list[str] | None = None,
    addpath_dirs: list[str] | None = None,
    python_executable: str | None = None,
    path_inputs: dict[str, dict] | None = None,
    sweeps: dict[str, list] | None = None,
    output_types: list[str] | None = None,
    project_root: str | None = None,
    entities_script: str | None = None,
    entities_file: str | None = None,
) -> str:
    """Generate a complete MATLAB script to run a pipeline function.

    Parameters
    ----------
    function_name
        Name of the MATLAB function to run (e.g. ``"bandpass_filter"``).
    db_path
        Absolute path to the .duckdb file.
    schema_keys
        Dataset schema keys (e.g. ``["subject", "session"]``).
    variants
        List of variant dicts from the DAG. Each variant has keys:
        ``input_types``, ``output_type``, ``constants``, ``record_count``.
        If empty/None, generates a template command.
    schema_filter
        Optional ``{key: [selected_values]}`` for filtering.
    schema_level
        Optional list of schema keys to iterate over.
    addpath_dirs
        Optional list of directories to add to MATLAB path.
    python_executable
        Optional absolute path to the Python interpreter that MATLAB's
        Python bridge should bind to. When provided, the generated script
        emits a guarded ``pyenv`` preamble that binds (or verifies) the
        interpreter before any ``py.*`` call is made. When ``None``/empty,
        no preamble is emitted (preserves behavior for non-GUI callers).
    sweeps
        Optional ``{param_name: [values]}`` — a Sweep has no DB-history
        representation (always fans out to ``EachOf``/``Sweep`` fresh at
        execution time), so unlike ``path_inputs`` this only ever comes
        from the registry via manual-edge wiring, never DB variants — see
        ``matlab_command_service``'s collection logic.

    Returns
    -------
    str
        A complete, self-contained MATLAB script.
    """
    lines: list[str] = []
    lines.append(f"%% SciStack: Run {function_name}")
    lines.append("% Generated by SciStack GUI — paste into MATLAB Command Window")
    lines.append("")

    # pyenv preamble — must come before any py.* call (i.e. before
    # scihist.configure_database, which internally calls py.scidb.*).
    if python_executable:
        lines.extend(_format_pyenv_preamble(python_executable))
        lines.append("")

    # addpath entries
    if addpath_dirs:
        for d in addpath_dirs:
            lines.append(f"addpath('{_escape_matlab_string(d)}');")
        lines.append("")

    lines.extend(_project_root_lines(project_root, path_inputs))
    lines.extend(_entities_script_lines(entities_script, entities_file, project_root))

    # Configure database
    schema_keys_str = _format_matlab_string_array(schema_keys)
    lines.append("% Configure database (skip if already configured)")
    lines.append(
        f"db = scihist.configure_database('{_escape_matlab_string(db_path)}', "
        f"{schema_keys_str});"
    )
    lines.append("")

    if not variants:
        # No variant info — generate a template, but include any known path
        # inputs/sweeps and output types inferred from manual edges.
        template_inputs: dict[str, str] = {}
        if path_inputs:
            for p, pi in path_inputs.items():
                template_inputs[p] = _format_path_input(pi)
        if sweeps:
            for p, values in sweeps.items():
                template_inputs[p] = _format_sweep(values)
        inputs_str = (
            _format_matlab_struct(template_inputs) if template_inputs else "struct()"
        )
        if output_types:
            outputs_str = _format_matlab_cell([f"{t}()" for t in output_types])
            lines.extend(_unresolvable_var_type_lines(output_types))
        else:
            outputs_str = "{}"
            logger.warning(
                "generate_matlab_command: no output_types for %s — "
                "outputs will be empty, saves will be skipped",
                function_name,
            )
        lines.append("try")
        lines.append("    % Run (fill in inputs/outputs)")
        lines.append(f"    scihist.for_each(@{function_name}, ...")
        lines.append(f"        {inputs_str}, ...")
        lines.append(f"        {outputs_str});")
        lines.append("    scidb.close_database(db);")
        lines.append("catch scistack_err__")
        lines.append(
            "    scidb.Log.err('MATLAB: for_each FAILED: %s', scistack_err__.message);"
        )
        lines.append("    try")
        lines.append("        scidb.close_database(db);")
        lines.append("    catch")
        lines.append(
            "        % close already logged its own error; don't mask the original"
        )
        lines.append("    end")
        lines.append("    rethrow(scistack_err__);")
        lines.append("end")
        return "\n".join(lines)

    # Register variable types
    all_var_types = _collect_var_types(variants)
    lines.extend(_unresolvable_var_type_lines(all_var_types))
    if all_var_types:
        lines.append("% Register variable types")
        for vtype in sorted(all_var_types):
            lines.append(f"scidb.register_variable({vtype}());")
        lines.append("")

    # Wrap all for_each calls in a try/catch so db.close() always runs,
    # even if the run errors out or is interrupted.
    lines.append("try")

    # Generate for_each call for each unique (inputs, constants) group.
    lines.extend(
        _for_each_call_lines(
            function_name,
            _group_variants(variants),
            schema_keys,
            schema_filter,
            schema_level,
            path_inputs,
            matlab_fn="scihist.for_each",
            sweeps=sweeps,
        )
    )

    lines.append("    scidb.close_database(db);")
    lines.append("catch scistack_err__")
    lines.append(
        "    scidb.Log.err('MATLAB: for_each FAILED: %s', scistack_err__.message);"
    )
    lines.append("    try")
    lines.append("        scidb.close_database(db);")
    lines.append("    catch")
    lines.append(
        "        % close already logged its own error; don't mask the original"
    )
    lines.append("    end")
    lines.append("    rethrow(scistack_err__);")
    lines.append("end")
    return "\n".join(lines)


def _collect_var_types(variants: list[dict]) -> set[str]:
    """All BaseVariable class names referenced (as an input or output)
    across a function's variant rows — the set that needs a
    ``scidb.register_variable(...)`` call."""
    all_var_types: set[str] = set()
    for v in variants:
        input_types = v.get("input_types", {})
        if isinstance(input_types, dict):
            all_var_types.update(input_types.values())
        output_type = v.get("output_type", "")
        if output_type:
            all_var_types.add(output_type)
    return all_var_types


def _group_variants(variants: list[dict]) -> list[dict]:
    """Group variant rows by (input_types, constants). Multi-output MATLAB
    functions (e.g. load_csv -> [Time, Force_Left, Force_Right]) surface in
    the DB as one variant row per output_type, all sharing the same inputs
    and constants. They must collapse into a single for_each call whose
    outputs cell lists every output_type.
    """
    grouped: dict[tuple, dict] = {}
    for v in variants:
        input_types = v.get("input_types", {}) or {}
        constants = v.get("constants", {}) or {}
        key = (
            tuple(sorted(input_types.items())) if isinstance(input_types, dict) else (),
            tuple(sorted(constants.items())) if isinstance(constants, dict) else (),
        )
        entry = grouped.setdefault(
            key,
            {
                "input_types": input_types,
                "constants": constants,
                "output_types": [],
            },
        )
        output_type = v.get("output_type", "")
        if output_type and output_type not in entry["output_types"]:
            entry["output_types"].append(output_type)
    return list(grouped.values())


def _for_each_call_lines(
    function_name: str,
    grouped_entries: list[dict],
    schema_keys: list[str],
    schema_filter: dict[str, list] | None,
    schema_level: list[str] | None,
    path_inputs: dict[str, dict] | None,
    matlab_fn: str = "scihist.for_each",
    indent: str = "    ",
    sweeps: dict[str, list] | None = None,
) -> list[str]:
    """One (indented) ``<matlab_fn>(@function_name, ...)`` block per grouped
    (inputs, constants) entry — the call body shared between a single
    function's ready-to-paste command and one node's step registration
    inside a whole-pipeline script (``generate_matlab_pipeline_command``).
    """
    from scistack_gui.api.pipeline import _parse_path_input

    lines: list[str] = []
    for entry in grouped_entries:
        input_types = entry["input_types"]
        output_types_list = entry["output_types"]
        constants = entry["constants"]

        # Build inputs struct — skip PathInput entries (handled via path_inputs).
        inputs_dict = {}
        if isinstance(input_types, dict):
            for param_name, type_name in input_types.items():
                if _parse_path_input(str(type_name)) is None:
                    inputs_dict[param_name] = f"{type_name}()"
        # Add path inputs as scifor.PathInput(...) expressions.
        if path_inputs:
            for param_name, pi in path_inputs.items():
                inputs_dict[param_name] = _format_path_input(pi)
        # Add Parameter values as scidb.Parameter(...) expressions.
        if sweeps:
            for param_name, values in sweeps.items():
                inputs_dict[param_name] = _format_sweep(values)
        # Add constants as scalar values
        for k, val in constants.items():
            inputs_dict[k] = _format_matlab_value(val)

        inputs_str = _format_matlab_struct(inputs_dict)
        outputs_str = (
            _format_matlab_cell([f"{t}()" for t in output_types_list])
            if output_types_list
            else "{}"
        )

        # Build schema kwargs
        iterate_keys = schema_level if schema_level else schema_keys
        schema_str = _format_schema_kwargs(
            iterate_keys, schema_filter, constants, function_name
        )

        lines.append(f"{indent}% Run")
        lines.append(f"{indent}{matlab_fn}(@{function_name}, ...")
        lines.append(f"{indent}    {inputs_str}, ...")
        if schema_str:
            lines.append(f"{indent}    {outputs_str}, ...")
            lines.append(f"{indent}    {schema_str});")
        else:
            lines.append(f"{indent}    {outputs_str});")
        lines.append("")
    return lines


def generate_matlab_pipeline_command(
    pipeline_id: str,
    steps: list[dict],
    db_path: str,
    schema_keys: list[str],
    mode: str = "all",
    target: str = "",
    finalized: bool | None = None,
    skip_computed: bool = True,
    addpath_dirs: list[str] | None = None,
    python_executable: str | None = None,
    project_root: str | None = None,
    entities_script: str | None = None,
    entities_file: str | None = None,
) -> str:
    """Generate a complete MATLAB script that runs a whole GUI pipeline
    scope through ``scidb.Pipeline`` — deferred registration of every
    MATLAB function node's step(s), then one driven run — instead of a
    single function's ``for_each`` call.

    Parameters
    ----------
    pipeline_id
        The GUI pipeline's id/name; becomes the ``scidb.Pipeline(...)``
        name.
    steps
        One entry per MATLAB function node already resolved by the caller
        (``matlab_command_service.generate_matlab_pipeline_command`` — the
        same target-derivation used for per-node runs and Python pipeline
        compilation, see ``execution_service.derive_target_for_node`` /
        ``build_backend_pipeline``). Each entry:
        ``{"function_name": str, "variants": list[dict] | None,
        "schema_filter": dict | None, "schema_level": list[str] | None,
        "path_inputs": dict | None}``. A step with no resolvable variants
        (nothing derivable — never run and no output wiring) is skipped
        with a comment, mirroring the disconnected-wiring skip convention
        in ``code_export_service`` — not an error, since the rest of the
        pipeline can still run.

        Only MATLAB-language function nodes belong in ``steps`` — Python
        function nodes in the same GUI pipeline scope are NOT registered
        here (a MATLAB-only script has no way to register a Python
        ``for_each`` call into the same in-process ``scidb.Pipeline`` — the
        Python interpreter MATLAB loads via ``pyenv``/the sidecar is a
        fresh process with no memory of the GUI server's own compiled
        pipeline). Callers must filter ``steps`` to MATLAB functions only
        and separately warn about any excluded Python steps.
    mode, target, finalized, skip_computed
        Mirror ``execution_service.run_pipeline``'s dispatch: ``"all"`` ->
        ``pipe.run_all()``, ``"until"`` -> ``pipe.run_until(target)``,
        ``"endpoints"`` -> ``pipe.run_endpoints()``. ``"show"`` has no
        MATLAB ``Pipeline.m`` equivalent (no ``show()`` method there) and
        is rejected.

    Returns
    -------
    str
        A complete, self-contained MATLAB script.
    """
    if mode not in ("all", "until", "endpoints"):
        raise ValueError(
            f"generate_matlab_pipeline_command: unsupported mode {mode!r} — "
            "MATLAB Pipeline.m only supports 'all', 'until', 'endpoints' "
            "(mode='show' has no MATLAB Pipeline.m equivalent)"
        )
    if mode == "until" and not target:
        raise ValueError("mode='until' requires a target step name")

    lines: list[str] = []
    lines.append(f"%% SciStack: Run pipeline {pipeline_id}")
    lines.append("% Generated by SciStack GUI — paste into MATLAB Command Window")
    lines.append("")

    # pyenv preamble — must come before any py.* call.
    if python_executable:
        lines.extend(_format_pyenv_preamble(python_executable))
        lines.append("")

    # addpath entries
    if addpath_dirs:
        for d in addpath_dirs:
            lines.append(f"addpath('{_escape_matlab_string(d)}');")
        lines.append("")

    all_step_path_inputs = {
        param: pi
        for step in steps
        for param, pi in (step.get("path_inputs") or {}).items()
    }
    lines.extend(_project_root_lines(project_root, all_step_path_inputs))
    lines.extend(_entities_script_lines(entities_script, entities_file, project_root))

    # Configure database
    schema_keys_str = _format_matlab_string_array(schema_keys)
    lines.append("% Configure database (skip if already configured)")
    lines.append(
        f"db = scihist.configure_database('{_escape_matlab_string(db_path)}', "
        f"{schema_keys_str});"
    )
    lines.append("")

    all_var_types: set[str] = set()
    resolved_steps: list[tuple[str, list[dict], dict]] = []
    skip_comments: list[str] = []
    for step in steps:
        fn_name = step["function_name"]
        variants = step.get("variants")
        if not variants:
            skip_comments.append(
                f"% SKIPPED: '{fn_name}' — no runnable target derived "
                "(never run and no output wiring)"
            )
            continue
        all_var_types.update(_collect_var_types(variants))
        resolved_steps.append((fn_name, _group_variants(variants), step))

    if not resolved_steps:
        raise ValueError(
            f"generate_matlab_pipeline_command: no runnable MATLAB step in "
            f"pipeline {pipeline_id!r} — nothing to register"
        )

    lines.extend(_unresolvable_var_type_lines(all_var_types))
    if all_var_types:
        lines.append("% Register variable types")
        for vtype in sorted(all_var_types):
            lines.append(f"scidb.register_variable({vtype}());")
        lines.append("")

    lines.append(f"pipe = scidb.Pipeline('{_escape_matlab_string(pipeline_id)}');")
    lines.append("")

    # Wrap registration + the driven run in a try/catch so db.close() always
    # runs, even if a step registration or the run itself errors out.
    lines.append("try")
    for fn_name, grouped_entries, step in resolved_steps:
        lines.append(f"    % Register {fn_name} (deferred — runs via pipe below)")
        lines.extend(
            _for_each_call_lines(
                fn_name,
                grouped_entries,
                schema_keys,
                step.get("schema_filter"),
                step.get("schema_level"),
                step.get("path_inputs"),
                matlab_fn="scidb.for_each",
                sweeps=step.get("sweeps"),
            )
        )
    for comment in skip_comments:
        lines.append(f"    {comment}")
    if skip_comments:
        lines.append("")

    skip_str = "true" if skip_computed else "false"
    if mode == "all":
        lines.append(f"    pipe.run_all('skip_computed', {skip_str});")
    elif mode == "until":
        run_line = (
            f"    pipe.run_until('{_escape_matlab_string(target)}', "
            f"'skip_computed', {skip_str}"
        )
        if finalized is not None:
            run_line += f", 'finalized', {'true' if finalized else 'false'}"
        lines.append(run_line + ");")
    else:  # "endpoints"
        run_line = (
            f"    pipe.run_endpoints('skip_computed', {skip_str}, "
            "'include_used', true"
        )
        if finalized is not None:
            run_line += f", 'finalized', {'true' if finalized else 'false'}"
        lines.append(run_line + ");")

    lines.append("    scidb.close_database(db);")
    lines.append("catch scistack_err__")
    lines.append(
        "    scidb.Log.err('MATLAB: pipeline run FAILED: %s', scistack_err__.message);"
    )
    lines.append("    try")
    lines.append("        scidb.close_database(db);")
    lines.append("    catch")
    lines.append(
        "        % close already logged its own error; don't mask the original"
    )
    lines.append("    end")
    lines.append("    rethrow(scistack_err__);")
    lines.append("end")
    return "\n".join(lines)


def _format_path_input(pi: dict) -> str:
    """Format a PathInput info dict as a MATLAB ``scifor.PathInput(...)`` expression.

    The template stored in the layout may already include MATLAB double-quote
    delimiters (e.g. ``"C:\\data\\file.csv"``), or it may be a bare pattern
    string (e.g. ``{subject}/trial_{trial}.mat``). Both forms are handled.

    ``root_folder`` is emitted **only when the declaration has one**. This used
    to substitute the project root for a rootless declaration with a relative
    template, so MATLAB's cwd (a temp script dir) wouldn't decide resolution.
    That fixed resolution by rewriting identity: ``PathInput.to_key()``
    serializes ``(template, root_folder)`` and DB history carries no name, so
    ``graph_builder.resolve_path_input_name`` could no longer content-match the
    run it had just recorded against the declaration that produced it, and the
    canvas grew an ``__unresolved__`` ghost node next to the real one. It also
    meant the same PathInput recorded a different key from the GUI than from
    the user's own MATLAB script.

    Resolution is now pinned separately by ``_project_root_lines`` (see
    ``scifor.pathinput.set_project_root``), which leaves identity alone.
    """
    template = pi.get("template", "")
    root_folder = pi.get("root_folder")

    # If the template is already wrapped in MATLAB double quotes, use it as-is.
    # Otherwise wrap it ourselves.
    if template.startswith('"') and template.endswith('"'):
        matlab_template = template
    else:
        matlab_template = f'"{template}"'

    if root_folder:
        return f'scifor.PathInput({matlab_template}, root_folder="{root_folder}")'
    return f"scifor.PathInput({matlab_template})"


def _format_sweep(values: list) -> str:
    """Format a Parameter's value list as a MATLAB ``scidb.Parameter(...)``
    expression (mirrors ``_format_path_input``'s role for PathInput).

    ``isa(x, 'scifor.EachOf')`` covers a Parameter for free, so ``for_each``
    fans it out with no special handling -- see ``+scidb/Parameter.m``."""
    items = ", ".join(_format_matlab_value(v) for v in values)
    return f"scidb.Parameter({items})"


def _escape_matlab_string(s: str) -> str:
    """Escape single quotes for MATLAB string literals."""
    return s.replace("'", "''")


def _format_pyenv_preamble(python_executable: str) -> list[str]:
    """Return MATLAB lines that bind AND force-load ``pyenv`` to the given interpreter.

    Emits three stages:
      1. Bind: if MATLAB's Python interface is ``NotLoaded``, call
         ``pyenv('Version', python_executable)``. If it is already loaded but
         points to a different interpreter, ``error`` out with
         ``SciStack:PyenvMismatch``.
      2. Force-load: call ``py.sys.version`` (a trivial Python call) inside
         a try/catch. This is required because ``pyenv('Version', ...)`` only
         *configures* Python; it does not actually load it. On some
         MATLAB+venv combinations, the first ``py.*`` call inside a package
         function (e.g. ``scihist.configure_database``) fails with
         "Unrecognized function or variable 'py'" because MATLAB's symbol
         resolver runs before the Python load. Loading Python here — from
         the script's top-level scope — avoids that path entirely.
      3. Diagnostic dump on failure: print MATLAB's ``pyenv`` state to
         stderr and suggest the ``'ExecutionMode', 'OutOfProcess'``
         workaround, then rethrow so the user sees the underlying MATLAB
         error.

    The path is converted to forward slashes (matching ``matlabTerminal.ts``
    convention for MATLAB single-quoted string literals on Windows) and
    single quotes are escaped via ``_escape_matlab_string``.

    Temporary variables use a ``scistack_*__`` namespace suffix and are
    ``clear``ed at the end so the script doesn't leak state into the
    caller's workspace (``run(...)`` evaluates in caller scope).
    """
    # Normalize backslashes (Windows) to forward slashes for the MATLAB literal.
    normalized = python_executable.replace("\\", "/")
    escaped = _escape_matlab_string(normalized)
    return [
        "% Bind MATLAB's Python interface to the scistack-gui interpreter.",
        f"scistack_pyenv_target__ = '{escaped}';",
        "scistack_pyenv__ = pyenv;",
        "% Normalize path separators (MATLAB returns `\\`, our target uses `/`)",
        "% and compare case-insensitively (Windows paths are case-insensitive;",
        "% MATLAB may lowercase what it stores).",
        "scistack_norm_path__ = @(p) strrep(char(p), '\\', '/');",
        'if scistack_pyenv__.Status == "NotLoaded"',
        "    scistack_pyenv__ = pyenv('Version', scistack_pyenv_target__);",
        "elseif ~strcmpi(scistack_norm_path__(scistack_pyenv__.Executable), ...",
        "                scistack_norm_path__(scistack_pyenv_target__))",
        "    error('SciStack:PyenvMismatch', ...",
        "        'MATLAB already loaded Python %s; restart MATLAB to switch to %s.', ...",
        "        scistack_pyenv__.Executable, scistack_pyenv_target__);",
        "end",
        "% Force Python to actually load NOW (at script top-level), so that",
        "% subsequent py.* calls inside package functions (e.g.",
        "% scihist.configure_database) resolve correctly. pyenv('Version', ...)",
        "% only configures Python; it does not load it.",
        "try",
        "    scistack_py_version__ = char(py.sys.version);",
        "    fprintf('[SciStack] Python loaded: %s (%s)\\n', ...",
        "        char(scistack_pyenv__.Executable), strtrim(scistack_py_version__));",
        "catch scistack_py_err__",
        "    fprintf(2, '[SciStack] py.sys.version failed: %s\\n', scistack_py_err__.message);",
        "    fprintf(2, ['[SciStack] pyenv state: Status=%s Version=%s ' ...",
        "        'Executable=%s Library=%s ExecutionMode=%s\\n'], ...",
        "        string(scistack_pyenv__.Status), string(scistack_pyenv__.Version), ...",
        "        string(scistack_pyenv__.Executable), string(scistack_pyenv__.Library), ...",
        "        string(scistack_pyenv__.ExecutionMode));",
        "    fprintf(2, ['[SciStack] Workaround to try: pyenv(''Version'', ''%s'', ' ...",
        "        '''ExecutionMode'', ''OutOfProcess''); py.sys.version\\n'], ...",
        "        scistack_pyenv_target__);",
        "    rethrow(scistack_py_err__);",
        "end",
        "% Pre-import the scidb module so py.scidb.* is warm, and so we can",
        "% distinguish 'py dispatch broken inside functions' from 'scidb module",
        "% not importable' when debugging.",
        "try",
        "    py.importlib.import_module('scidb');",
        "    fprintf('[SciStack] py.scidb import OK\\n');",
        "catch scistack_import_err__",
        "    fprintf(2, '[SciStack] py.importlib.import_module(''scidb'') failed: %s\\n', ...",
        "        scistack_import_err__.message);",
        "    rethrow(scistack_import_err__);",
        "end",
        "clear scistack_pyenv__ scistack_pyenv_target__ scistack_norm_path__ ...",
        "    scistack_py_version__ scistack_py_err__ scistack_import_err__;",
    ]


def _format_matlab_value(val) -> str:
    """Format a Python value as a MATLAB literal."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return str(val)
    if isinstance(val, str):
        return f"'{_escape_matlab_string(val)}'"
    if isinstance(val, (list, tuple)):
        elements = [_format_matlab_value(v) for v in val]
        return f"[{', '.join(elements)}]"
    return f"'{_escape_matlab_string(str(val))}'"


def _format_matlab_struct(inputs_dict: dict[str, str]) -> str:
    """Build a MATLAB ``struct(...)`` expression from a dict.

    Values are already formatted as MATLAB expressions (not quoted again).
    """
    if not inputs_dict:
        return "struct()"
    pairs = []
    for k, v in inputs_dict.items():
        pairs.append(f"'{k}', {v}")
    return f"struct({', '.join(pairs)})"


def _format_matlab_cell(items: list[str]) -> str:
    """Build a MATLAB cell array ``{Item1(), Item2()}``."""
    return "{" + ", ".join(items) + "}"


def _format_matlab_string_array(items: list[str]) -> str:
    """Format a Python list of strings as a MATLAB string array ``["a", "b"]``."""
    if not items:
        return "[]"
    escaped = [f'"{_escape_matlab_string(s)}"' for s in items]
    return "[" + ", ".join(escaped) + "]"


def _format_schema_kwargs(
    iterate_keys: list[str],
    schema_filter: dict[str, list] | None,
    constants: dict,
    function_name: str,
) -> str:
    """Build MATLAB name-value schema keyword arguments for for_each.

    Returns empty string if there are no schema arguments to pass.
    """
    if not iterate_keys:
        return ""

    parts = []
    for key in iterate_keys:
        if schema_filter and key in schema_filter and schema_filter[key]:
            values = schema_filter[key]
            # Format values: numbers as array, strings as string array.
            if all(isinstance(v, (int, float)) for v in values):
                formatted = "[" + " ".join(str(v) for v in values) + "]"
            else:
                formatted = _format_matlab_string_array([str(v) for v in values])
            parts.append(f"'{key}', {formatted}")
        else:
            # No filter for this key — emit [] so scidb.for_each resolves
            # all distinct values from the database.  Without this,
            # PathInput templates that reference {key} won't be substituted.
            parts.append(f"'{key}', []")

    if not parts:
        return ""
    return ", ".join(parts)
