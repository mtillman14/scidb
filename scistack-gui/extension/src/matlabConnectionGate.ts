/**
 * Decides whether a MATLAB "Run" click should be treated as connecting to
 * MATLAB rather than dispatching a run.
 *
 * Why this matters: `runInMatlabTerminal` (matlabTerminal.ts) calls
 * `matlab.openCommandWindow` and sends the script the moment a `MATLAB`
 * terminal object exists, but on the very first click of a VS Code session
 * that terminal has just been created and the MATLAB process behind it has
 * not finished starting — so nothing actually runs. `handleMatlabRun`
 * (dagPanel.ts) used to call this "dispatched" and report it as a
 * successful run regardless (see plan-matlab-terminal-run-tracking.md,
 * problem P2). Gating on terminal existence turns that specific case into
 * a "connect, don't run yet" prompt instead of a false success.
 *
 * This is a heuristic, not a true connection check — the MathWorks
 * extension exposes no API for MATLAB's actual readiness, only whether a
 * terminal object exists. A run dispatched to a terminal that exists but
 * whose MATLAB process is still starting (e.g. the user clicks Run again
 * immediately after connecting) is not caught by this and remains covered
 * only by the deferred Stage 2 fix (run markers written by MATLAB itself).
 *
 * Deliberately free of any `vscode` import so it can be unit-tested under
 * `node --test` (see tsconfig.test.json).
 */
export function needsMatlabConnectionPrompt(
  matlabExtensionAvailable: boolean,
  matlabTerminalAlreadyOpen: boolean,
): boolean {
  return matlabExtensionAvailable && !matlabTerminalAlreadyOpen;
}
