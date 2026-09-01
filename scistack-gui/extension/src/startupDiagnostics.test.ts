/**
 * Tests for startupDiagnostics — run with `npm test` in extension/.
 *
 * The regression these lock down: a Python environment without scistack_gui
 * used to surface as "Server failed to start — Python process exited
 * (code=1, signal=null)", which names neither the interpreter nor the cause.
 */

import { test } from 'node:test';
import * as assert from 'node:assert';
import {
  diagnoseStartupFailure,
  missingModuleFromStderr,
  parseProbeOutput,
  probeInterpreter,
  InterpreterProbe,
} from './startupDiagnostics';

const PYTHON = '/home/u/.venvs/other/bin/python';

function probe(overrides: Partial<InterpreterProbe> = {}): InterpreterProbe {
  return {
    ok: true,
    executable: PYTHON,
    version: '3.11.8',
    prefix: '/home/u/.venvs/other',
    modules: {
      scistack_gui: { found: true, location: '/site-packages/scistack_gui/__init__.py' },
      scidb: { found: true, location: '/site-packages/scidb/__init__.py' },
      scifor: { found: true, location: '/site-packages/scifor/__init__.py' },
      duckdb: { found: true, location: '/site-packages/duckdb/__init__.py' },
    },
    ...overrides,
  };
}

function withMissing(...names: string[]): InterpreterProbe {
  const p = probe();
  for (const name of names) {
    p.modules![name] = { found: false };
  }
  return p;
}

test('missing scistack_gui names the package, the interpreter, and a fix', () => {
  const d = diagnoseStartupFailure({
    pythonPath: PYTHON,
    interpreterSource: 'active interpreter from the Python extension',
    errorMessage: 'Python process exited (code=1, signal=null)',
    stderr: `${PYTHON}: No module named scistack_gui`,
    exitCode: 1,
    probe: withMissing('scistack_gui'),
  });

  assert.equal(d.kind, 'package_missing');
  assert.ok(d.message.includes(PYTHON), 'message must name the interpreter');
  assert.ok(d.message.includes('scistack_gui'));
  assert.ok(!d.message.includes('code=1'), 'exit code is not the user-facing cause');
  assert.ok(d.installCommand?.startsWith(PYTHON));
  assert.deepEqual(d.actions, ['copyInstallCommand', 'selectInterpreter', 'showOutput']);
  // Detail carries the environment for the Output Channel.
  assert.ok(d.detail.includes('/home/u/.venvs/other'));
  assert.ok(d.detail.includes('active interpreter from the Python extension'));
  assert.ok(d.detail.includes('scistack_gui: NOT FOUND'));
});

test('missing scistack_gui is detected from stderr alone when no probe ran', () => {
  const d = diagnoseStartupFailure({
    pythonPath: PYTHON,
    errorMessage: 'Python process exited (code=1, signal=null)',
    stderr: `${PYTHON}: No module named scistack_gui`,
  });
  assert.equal(d.kind, 'package_missing');
  assert.ok(d.message.includes(PYTHON));
});

test('the configured path and the real sys.executable are both reported', () => {
  const d = diagnoseStartupFailure({
    pythonPath: 'python3',
    errorMessage: 'Python process exited (code=1, signal=null)',
    probe: withMissing('scistack_gui'),
  });
  assert.ok(d.message.includes('python3'));
  assert.ok(d.message.includes(PYTHON), 'resolved interpreter belongs in the message');
});

test('installed gui with a missing scistack dependency is its own diagnosis', () => {
  const d = diagnoseStartupFailure({
    pythonPath: PYTHON,
    errorMessage: 'Python process exited (code=1, signal=null)',
    stderr: [
      'Traceback (most recent call last):',
      '  File "/site-packages/scistack_gui/server.py", line 31, in <module>',
      '    from scidb.log import Log as _Log',
      "ModuleNotFoundError: No module named 'scidb'",
    ].join('\n'),
    probe: withMissing('scidb'),
  });
  assert.equal(d.kind, 'dependency_missing');
  assert.ok(d.message.includes('scidb'));
  assert.ok(d.message.includes(PYTHON));
});

test('an unrunnable interpreter points at interpreter settings, not pip', () => {
  const d = diagnoseStartupFailure({
    pythonPath: 'C:\\nope\\python.exe',
    errorMessage: 'spawn C:\\nope\\python.exe ENOENT',
    probe: { ok: false, spawnError: 'spawn C:\\nope\\python.exe ENOENT' },
  });
  assert.equal(d.kind, 'interpreter_missing');
  assert.ok(d.message.includes('C:\\nope\\python.exe'));
  assert.deepEqual(d.actions, ['selectInterpreter', 'openSettings', 'showOutput']);
});

test('the Windows python3 Store alias reads as a missing interpreter', () => {
  const d = diagnoseStartupFailure({
    pythonPath: 'python3',
    interpreterSource: 'PATH fallback (no Python extension interpreter)',
    errorMessage: 'Python process exited (code=9009, signal=null)',
    probe: {
      ok: false,
      spawnError: 'probe produced no JSON',
      raw: 'Python was not found; run without arguments to install from the Microsoft Store',
    },
  });
  assert.equal(d.kind, 'interpreter_missing');
  assert.ok(d.message.includes('python3'));
  assert.ok(d.detail.includes('PATH fallback'));
});

test('a hung startup is a timeout, not a missing package', () => {
  const d = diagnoseStartupFailure({
    pythonPath: PYTHON,
    errorMessage: 'Python server did not become ready within 60000ms of silence (no progress notification received).',
    probe: probe(),
  });
  assert.equal(d.kind, 'startup_timeout');
  assert.ok(d.message.includes(PYTHON));
});

test('a crash after import surfaces the exception line', () => {
  const d = diagnoseStartupFailure({
    pythonPath: PYTHON,
    errorMessage: 'Python process exited (code=1, signal=null)',
    stderr: [
      'Traceback (most recent call last):',
      '  File "/site-packages/scistack_gui/server.py", line 400, in main',
      'duckdb.IOException: IO Error: Could not set lock on file',
    ].join('\n'),
    probe: probe(),
  });
  assert.equal(d.kind, 'server_error');
  assert.ok(d.message.includes('IO Error: Could not set lock on file'));
});

test('an unclassifiable failure still names the interpreter', () => {
  const d = diagnoseStartupFailure({
    pythonPath: PYTHON,
    errorMessage: 'Python process exited (code=null, signal=SIGKILL)',
    probe: probe(),
  });
  assert.equal(d.kind, 'unknown');
  assert.ok(d.message.includes(PYTHON));
  assert.ok(d.message.includes('SIGKILL'));
});

test('an interpreter path with spaces is quoted in the install command', () => {
  const d = diagnoseStartupFailure({
    pythonPath: 'C:\\Program Files\\Python311\\python.exe',
    errorMessage: 'Python process exited (code=1, signal=null)',
    probe: withMissing('scistack_gui'),
  });
  assert.ok(d.installCommand?.startsWith('"C:\\Program Files\\Python311\\python.exe"'));
});

test('missingModuleFromStderr handles both quoted and bare forms', () => {
  assert.equal(missingModuleFromStderr("ModuleNotFoundError: No module named 'scidb'"), 'scidb');
  assert.equal(missingModuleFromStderr('/usr/bin/python3: No module named scistack_gui'), 'scistack_gui');
  assert.equal(missingModuleFromStderr('all good here'), undefined);
});

test('parseProbeOutput ignores noise printed before the JSON line', () => {
  const parsed = parseProbeOutput(
    'some sitecustomize banner\n{"executable": "/p", "modules": {"scidb": {"found": true}}}\n'
  );
  assert.equal(parsed?.executable, '/p');
  assert.equal(parsed?.ok, true);
  assert.equal(parseProbeOutput('no json here'), null);
});

test('probeInterpreter reports a nonexistent interpreter instead of throwing', async () => {
  const result = await probeInterpreter('/definitely/not/a/python');
  assert.equal(result.ok, false);
  assert.match(result.spawnError ?? '', /ENOENT|not found/i);
});
