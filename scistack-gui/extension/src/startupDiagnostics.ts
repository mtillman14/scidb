/**
 * startupDiagnostics — turn a failed server launch into an actionable message.
 *
 * When `python -m scistack_gui.server` never reaches "ready", the raw failure
 * the extension sees is useless ("Python process exited (code=1, signal=null)").
 * The real cause is almost always one of:
 *
 *   - the interpreter path does not exist (bad scistack.pythonPath, no python3)
 *   - the interpreter is a different environment that lacks scistack_gui
 *   - scistack_gui is installed but one of its scistack deps (scidb, ...) is not
 *   - the server started but crashed or hung
 *
 * `probeInterpreter` asks the interpreter what it actually is and which
 * packages it can see; `diagnoseStartupFailure` is a pure function that turns
 * the probe plus the captured stderr into a message naming the interpreter.
 *
 * Nothing here imports `vscode`, so it can be unit-tested under `node --test`.
 */

import { spawn } from 'child_process';

/** Modules the server needs before it can emit its first notification. */
export const REQUIRED_MODULES = ['scistack_gui', 'scidb', 'scifor', 'duckdb'];

export interface ModuleProbe {
  found: boolean;
  location?: string | null;
  error?: string;
}

export interface InterpreterProbe {
  /** False when the interpreter could not be run at all. */
  ok: boolean;
  /** Set when spawning the interpreter failed (e.g. ENOENT). */
  spawnError?: string;
  /** sys.executable — the interpreter that actually ran, after any shim. */
  executable?: string;
  version?: string;
  /** sys.prefix — the venv/conda env root. */
  prefix?: string;
  modules?: Record<string, ModuleProbe>;
  /** Raw stderr, when the probe itself failed in an unexpected way. */
  raw?: string;
}

export type StartupFailureKind =
  | 'interpreter_missing'
  | 'package_missing'
  | 'dependency_missing'
  | 'startup_timeout'
  | 'server_error'
  | 'unknown';

export type StartupAction =
  | 'showOutput'
  | 'selectInterpreter'
  | 'openSettings'
  | 'copyInstallCommand';

export interface StartupDiagnosis {
  kind: StartupFailureKind;
  /** One-line notification text. Always names the interpreter. */
  message: string;
  /** Multi-line block for the Output Channel. */
  detail: string;
  /** Buttons to offer, in order. */
  actions: StartupAction[];
  /** Command to put on the clipboard for `copyInstallCommand`, if offered. */
  installCommand?: string;
}

export interface StartupFailureContext {
  /** The interpreter path the extension asked to spawn. */
  pythonPath: string;
  /** Where that path came from, e.g. "scistack.pythonPath setting". */
  interpreterSource?: string;
  /** Args passed to it, for the Output Channel detail block. */
  args?: string[];
  /** Message of the error that rejected waitForReady(). */
  errorMessage: string;
  /** Captured stderr from the child (tail is fine). */
  stderr?: string;
  exitCode?: number | null;
  probe?: InterpreterProbe;
}

// The probe deliberately uses importlib.util.find_spec rather than import:
// it must not execute package code (slow, and side effects), and it must be
// able to report "scistack_gui is here but scidb is not".
const PROBE_SCRIPT = [
  'import json, sys',
  'info = {"executable": sys.executable, "version": sys.version.split()[0], "prefix": sys.prefix, "modules": {}}',
  'try:',
  '    import importlib.util as u',
  'except Exception:',
  '    u = None',
  `for name in (${REQUIRED_MODULES.map((m) => `"${m}"`).join(', ')}):`,
  '    entry = {}',
  '    try:',
  '        spec = u.find_spec(name) if u else None',
  '        if spec is None:',
  '            entry["found"] = False',
  '        else:',
  '            entry["found"] = True',
  '            entry["location"] = getattr(spec, "origin", None)',
  '    except Exception as e:',
  '        entry["found"] = False',
  '        entry["error"] = "%s: %s" % (type(e).__name__, e)',
  '    info["modules"][name] = entry',
  'print(json.dumps(info))',
].join('\n');

/**
 * Ask an interpreter what it is and which scistack packages it can see.
 *
 * Never throws: every failure mode is reported in the returned object, since
 * this only ever runs on a path that is already an error path.
 */
export function probeInterpreter(
  pythonPath: string,
  timeoutMs = 10000,
): Promise<InterpreterProbe> {
  return new Promise((resolve) => {
    let settled = false;
    const done = (probe: InterpreterProbe) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(probe);
    };

    let proc;
    try {
      proc = spawn(pythonPath, ['-c', PROBE_SCRIPT], {
        stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (err) {
      resolve({ ok: false, spawnError: String(err) });
      return;
    }

    const timer = setTimeout(() => {
      proc.kill();
      done({ ok: false, spawnError: `probe timed out after ${timeoutMs}ms` });
    }, timeoutMs);

    let stdout = '';
    let stderr = '';
    proc.stdout?.on('data', (d: Buffer) => (stdout += d.toString()));
    proc.stderr?.on('data', (d: Buffer) => (stderr += d.toString()));

    proc.on('error', (err: Error) => done({ ok: false, spawnError: err.message }));

    proc.on('close', () => {
      const parsed = parseProbeOutput(stdout);
      if (parsed) {
        done(parsed);
      } else {
        done({ ok: false, spawnError: 'probe produced no JSON', raw: (stdout + stderr).trim() });
      }
    });
  });
}

/** Extract the probe's JSON line, ignoring anything a sitecustomize printed. */
export function parseProbeOutput(stdout: string): InterpreterProbe | null {
  const lines = stdout.split('\n').map((l) => l.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i--) {
    if (!lines[i].startsWith('{')) continue;
    try {
      const info = JSON.parse(lines[i]) as Partial<InterpreterProbe>;
      if (info.modules) return { ok: true, ...info } as InterpreterProbe;
    } catch {
      // keep scanning upwards
    }
  }
  return null;
}

/** `No module named 'x'` / `No module named x` → `x`, else undefined. */
export function missingModuleFromStderr(stderr: string): string | undefined {
  const m = /No module named ['"]?([\w.]+)['"]?/.exec(stderr);
  return m ? m[1] : undefined;
}

/**
 * True when the text says the interpreter could not be executed at all.
 *
 * Includes the Windows "python3" App Execution Alias, which exists on PATH
 * but only advertises the Microsoft Store — from the extension's side it is
 * a missing interpreter, not a missing package.
 */
function isUnrunnable(text: string): boolean {
  return /ENOENT|not found|cannot find the (file|path) specified|No such file or directory|Microsoft Store/i.test(
    text,
  );
}

function pipInstallCommand(pythonPath: string): string {
  const quoted = /\s/.test(pythonPath) ? `"${pythonPath}"` : pythonPath;
  return `${quoted} -m pip install scistack-gui`;
}

/** Last few non-empty stderr lines — the part of a traceback that matters. */
function stderrTail(stderr: string, maxLines: number): string {
  const lines = stderr.split('\n').map((l) => l.trimEnd()).filter((l) => l.trim());
  return lines.slice(-maxLines).join('\n');
}

/**
 * Classify a startup failure. Pure: all I/O has already happened.
 */
export function diagnoseStartupFailure(ctx: StartupFailureContext): StartupDiagnosis {
  const stderr = ctx.stderr ?? '';
  const probe = ctx.probe;
  const python = ctx.pythonPath;
  const runtimePath = probe?.executable && probe.executable !== python
    ? `${python} (resolved to ${probe.executable})`
    : python;

  const detailLines: string[] = [
    `Interpreter (configured): ${python}`,
  ];
  if (ctx.interpreterSource) detailLines.push(`Interpreter source: ${ctx.interpreterSource}`);
  if (probe?.executable) detailLines.push(`Interpreter (sys.executable): ${probe.executable}`);
  if (probe?.prefix) detailLines.push(`Environment (sys.prefix): ${probe.prefix}`);
  if (probe?.version) detailLines.push(`Python version: ${probe.version}`);
  if (ctx.args) detailLines.push(`Command: ${python} ${ctx.args.join(' ')}`);
  if (ctx.exitCode !== undefined && ctx.exitCode !== null) {
    detailLines.push(`Exit code: ${ctx.exitCode}`);
  }
  if (probe?.modules) {
    detailLines.push('Packages:');
    for (const name of REQUIRED_MODULES) {
      const mod = probe.modules[name];
      if (!mod) continue;
      const status = mod.found
        ? `found${mod.location ? ` at ${mod.location}` : ''}`
        : `NOT FOUND${mod.error ? ` (${mod.error})` : ''}`;
      detailLines.push(`  - ${name}: ${status}`);
    }
  }
  if (probe && !probe.ok && probe.spawnError) {
    detailLines.push(`Interpreter probe failed: ${probe.spawnError}`);
  }
  if (probe?.raw) detailLines.push(`Probe output: ${probe.raw}`);
  detailLines.push(`Failure: ${ctx.errorMessage}`);
  const tail = stderrTail(stderr, 20);
  if (tail) detailLines.push('Server stderr (tail):', tail);
  const detail = detailLines.join('\n');

  const finish = (
    kind: StartupFailureKind,
    message: string,
    actions: StartupAction[],
    installCommand?: string,
  ): StartupDiagnosis => ({ kind, message, detail, actions, installCommand });

  // 1. The interpreter itself is not runnable.
  const unrunnable =
    isUnrunnable(ctx.errorMessage) ||
    (probe !== undefined &&
      !probe.ok &&
      isUnrunnable(`${probe.spawnError ?? ''}\n${probe.raw ?? ''}`));
  if (unrunnable) {
    return finish(
      'interpreter_missing',
      `SciStack: cannot run the Python interpreter "${python}". ` +
        `Set scistack.pythonPath, or pick an interpreter with the Python extension.`,
      ['selectInterpreter', 'openSettings', 'showOutput'],
    );
  }

  // 2. scistack_gui is absent from this environment — the common case.
  const stderrMissing = missingModuleFromStderr(stderr);
  const guiProbeMissing = probe?.modules?.scistack_gui?.found === false;
  if (guiProbeMissing || stderrMissing === 'scistack_gui') {
    return finish(
      'package_missing',
      `SciStack: the Python environment "${runtimePath}" does not have scistack_gui installed. ` +
        `Install it there, or switch to the environment that has it.`,
      ['copyInstallCommand', 'selectInterpreter', 'showOutput'],
      pipInstallCommand(python),
    );
  }

  // 3. scistack_gui is present but something it imports is not.
  const depProbeMissing = REQUIRED_MODULES.filter(
    (m) => m !== 'scistack_gui' && probe?.modules?.[m]?.found === false,
  );
  const missingDep = depProbeMissing[0] ?? (stderrMissing && stderrMissing !== 'scistack_gui'
    ? stderrMissing
    : undefined);
  if (missingDep) {
    return finish(
      'dependency_missing',
      `SciStack: the Python environment "${runtimePath}" has scistack_gui but is missing "${missingDep}", ` +
        `which the server imports at startup.`,
      ['copyInstallCommand', 'selectInterpreter', 'showOutput'],
      pipInstallCommand(python),
    );
  }

  // 4. Started, but never said "ready".
  if (/did not become ready/.test(ctx.errorMessage)) {
    return finish(
      'startup_timeout',
      `SciStack: the server on "${runtimePath}" started but never became ready. ` +
        `See the SciStack output for what it was doing.`,
      ['showOutput'],
    );
  }

  // 5. It ran and crashed: surface the exception line, not the exit code.
  // Dotted names too: "duckdb.IOException: ...", not just "ValueError: ...".
  const excLine = /^\s*([\w.]*(?:Error|Exception|Exit|Interrupt)\b.*)$/m.exec(tail);
  if (excLine) {
    return finish(
      'server_error',
      `SciStack: the server on "${runtimePath}" crashed during startup — ${excLine[1].trim()}`,
      ['showOutput'],
    );
  }

  return finish(
    'unknown',
    `SciStack: the server on "${runtimePath}" failed to start — ${ctx.errorMessage}`,
    ['showOutput'],
  );
}
