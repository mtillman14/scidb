/**
 * Tests for serverArgs — run with `npm test` in extension/.
 *
 * The regression these lock down: the extension used to show a "How should
 * SciStack discover your pipeline code?" QuickPick and turn the answer into
 * `--module`/`--project`. That step was removed so discovery is always
 * automatic, which only holds if (a) neither flag is ever spawned again and
 * (b) `--project-root` is still passed, since it is now the *only* thing
 * telling the server which folder the project is (`config.resolve_project_root`).
 */

import { test } from 'node:test';
import * as assert from 'node:assert';
import { buildServerArgs } from './serverArgs';

const DB = '/data/experiment.duckdb';
const ROOT = '/home/u/my_study';

test('never passes --module or --project', () => {
  const args = buildServerArgs({
    dbPath: DB,
    schemaKeys: ['subject', 'session'],
    projectRoot: ROOT,
  });
  assert.ok(!args.includes('--module'), `--module in ${args.join(' ')}`);
  assert.ok(!args.includes('--project'), `--project in ${args.join(' ')}`);
});

test('opens the database with the project root of the workspace folder', () => {
  const args = buildServerArgs({ dbPath: DB, projectRoot: ROOT });
  assert.deepStrictEqual(args, [
    '-m',
    'scistack_gui.server',
    '--db',
    DB,
    '--project-root',
    ROOT,
  ]);
});

test('joins schema keys with commas when creating a database', () => {
  const args = buildServerArgs({
    dbPath: DB,
    schemaKeys: ['subject', 'session', 'trial'],
    projectRoot: ROOT,
  });
  const i = args.indexOf('--schema-keys');
  assert.notStrictEqual(i, -1, 'no --schema-keys');
  assert.strictEqual(args[i + 1], 'subject,session,trial');
});

test('omits --schema-keys when opening an existing database', () => {
  assert.ok(!buildServerArgs({ dbPath: DB, projectRoot: ROOT }).includes('--schema-keys'));
  assert.ok(
    !buildServerArgs({ dbPath: DB, schemaKeys: [], projectRoot: ROOT }).includes(
      '--schema-keys'
    ),
    'an empty key list must not spawn a bare --schema-keys'
  );
});

test('omits --project-root when no folder is open in the window', () => {
  // The server then falls back to its own cwd; extension.ts warns about it.
  const args = buildServerArgs({ dbPath: DB });
  assert.ok(!args.includes('--project-root'));
  assert.deepStrictEqual(args, ['-m', 'scistack_gui.server', '--db', DB]);
});
