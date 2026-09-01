/**
 * Tests for MatlabRunTracker — run with `npm test` in extension/.
 *
 * The regression these lock down (todo #13): while MATLAB owns the DuckDB
 * file lock, the DB file-watcher used to fire a DAG refresh on every WAL
 * write MATLAB made *during* the run. Every one of those refreshes issued
 * graph RPCs against a database the GUI cannot open, which is how a single
 * MATLAB run wedged the whole UI.
 */

import { test } from 'node:test';
import * as assert from 'node:assert';
import { MatlabRunTracker } from './matlabRunTracker';

test('db changes refresh immediately when no MATLAB run is active', () => {
  const tracker = new MatlabRunTracker();
  assert.equal(tracker.isActive, false);
  assert.equal(tracker.noteDbChange(), true);
  // Nothing was withheld, so there is nothing to replay.
  assert.equal(tracker.takeDeferredRefresh(), false);
});

test('db changes are withheld while MATLAB owns the database', () => {
  const tracker = new MatlabRunTracker();
  tracker.begin('run-1');

  assert.equal(tracker.isActive, true);
  assert.equal(tracker.noteDbChange(), false);
  assert.equal(tracker.noteDbChange(), false);

  tracker.end('run-1');
  assert.equal(tracker.isActive, false);
  // Many withheld changes collapse into exactly one replayed refresh.
  assert.equal(tracker.takeDeferredRefresh(), true);
  assert.equal(tracker.takeDeferredRefresh(), false);
});

test('a MATLAB run that wrote nothing costs no refresh', () => {
  const tracker = new MatlabRunTracker();
  tracker.begin('run-1');
  tracker.end('run-1');
  assert.equal(tracker.takeDeferredRefresh(), false);
});

test('the database stays owned until the LAST concurrent run ends', () => {
  const tracker = new MatlabRunTracker();
  tracker.begin('run-1');
  tracker.begin('run-2');
  tracker.noteDbChange();

  tracker.end('run-1');
  assert.equal(tracker.isActive, true, 'run-2 still holds the database');
  assert.equal(tracker.noteDbChange(), false);

  tracker.end('run-2');
  assert.equal(tracker.isActive, false);
  assert.equal(tracker.takeDeferredRefresh(), true);
});

test('onAllFinished fires once, when the last run clears', () => {
  const tracker = new MatlabRunTracker();
  let fired = 0;
  tracker.onAllFinished(() => { fired++; });

  tracker.begin('run-1');
  tracker.begin('run-2');
  tracker.end('run-1');
  assert.equal(fired, 0, 'still one run in flight');

  tracker.end('run-2');
  assert.equal(fired, 1);
});

test('run_done for a Python run is not mistaken for a MATLAB one', () => {
  const tracker = new MatlabRunTracker();
  let fired = 0;
  tracker.onAllFinished(() => { fired++; });

  // extension.ts calls end() for EVERY run_done; untracked ids must be
  // inert, or a Python run would clear MATLAB's ownership.
  assert.equal(tracker.end('python-run'), false);
  assert.equal(tracker.end(undefined), false);
  assert.equal(fired, 0);

  tracker.begin('matlab-run');
  assert.equal(tracker.end('python-run'), false);
  assert.equal(tracker.isActive, true);
  assert.equal(tracker.end('matlab-run'), true);
  assert.equal(fired, 1);
});
