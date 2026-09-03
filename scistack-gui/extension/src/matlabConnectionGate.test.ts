/**
 * Tests for matlabConnectionGate — run with `npm test` in extension/.
 *
 * Regression: the first "Run" click on a MATLAB function node, before any
 * MATLAB terminal exists, only starts the connection — MATLAB hasn't run
 * anything — but was reported as a successful run anyway. See
 * plan-matlab-terminal-run-tracking.md, problem P2.
 */

import { test } from 'node:test';
import * as assert from 'node:assert';
import { needsMatlabConnectionPrompt } from './matlabConnectionGate';

test('first click with no MATLAB terminal yet prompts to connect', () => {
  assert.equal(needsMatlabConnectionPrompt(true, false), true);
});

test('a click once the MATLAB terminal already exists runs normally', () => {
  assert.equal(needsMatlabConnectionPrompt(true, true), false);
});

test('no MathWorks extension installed never prompts (falls through to sidecar/clipboard)', () => {
  assert.equal(needsMatlabConnectionPrompt(false, false), false);
  assert.equal(needsMatlabConnectionPrompt(false, true), false);
});
