# Why the first MATLAB "Run" click doesn't run anything

Clicking Run on a MATLAB function node in VS Code goes through the MathWorks
terminal (Tier 2 — see `matlab-run-database-ownership.md`). The very first
click of a session has to *start* MATLAB before it can run anything in it,
and that used to be invisible: the GUI reported it as a successful run
anyway. This note explains the gate that stops that, and its limits.

## The bug (P2 in plan-matlab-terminal-run-tracking.md)

`matlabTerminal.ts::runInMatlabTerminal` calls
`vscode.commands.executeCommand('matlab.openCommandWindow')`, which creates
a `MATLAB`-named terminal object more or less immediately — well before the
actual MATLAB process behind it has finished starting up. As soon as that
terminal object exists, `runInMatlabTerminal` sends the script to it via
`terminal.sendText()` and returns `true` ("dispatched").

`dagPanel.ts::handleMatlabRun` (and its whole-pipeline sibling
`handleMatlabPipelineRun`) then treated "dispatched" as "done":

```ts
const tier = await this.dispatchMatlabCommand(command, runId, undefined);
if (tier !== 'sidecar') { finish(true); }
```

On a cold start, MATLAB is still booting when that `sendText` happens — the
line is queued or dropped — but the GUI already reported `success: true`.
The Runs console shows a green check for a click that executed nothing.

## The fix: `matlabConnectionGate.ts`

There's no public API from the MathWorks extension for "is MATLAB actually
ready" (`activate()` returns `Promise<void>`, 13 commands, no exported
surface — see `matlab-gui-support-analysis.md`). The only observable proxy
is **whether a `MATLAB`-named terminal already exists**:
`matlabTerminal.ts::isMatlabTerminalOpen()`.

`needsMatlabConnectionPrompt(extensionAvailable, terminalAlreadyOpen)` in
`matlabConnectionGate.ts` (vscode-free, unit-tested under `node --test`)
turns that into a decision: prompt to connect only when the extension is
installed *and* no terminal exists yet.

`dagPanel.ts::gateOnMatlabConnection()` wires it up, called at the top of
both `handleMatlabRun` and `handleMatlabPipelineRun`, before
`beginMatlabRun`:

- Terminal already exists (or extension not installed) → gate is a no-op,
  the run proceeds exactly as before.
- No terminal yet → shows an information message ("MATLAB is not connected
  to VS Code yet. Connect now, then click Run again once MATLAB is
  ready."). Clicking **Connect** fires `matlab.openCommandWindow` alone —
  no script is sent. Either way (Connect or Cancel), the click resolves as

  ```ts
  { run_id, success: false, cancelled: true, duration_ms: 0 }
  ```

  which lands on the existing `cancelled` status in
  `RunLogContext.tsx` (distinct from both `done` and `error`) — so it
  reads as "didn't run", not as a success or a failure.

## What this does and doesn't cover

Covers: the specific cold-start case — first click of a session, no
`MATLAB` terminal yet.

Does **not** cover (still open, tracked as Stage 2 in
`plan-matlab-terminal-run-tracking.md`):

- A run dispatched once the terminal exists but MATLAB is still mid-startup
  underneath it (e.g. the user clicks Run again immediately after hitting
  Connect, before MATLAB has actually finished launching). The terminal
  object already exists, so the gate doesn't trigger, and `finish(true)`
  fires on dispatch as before.
- A real run that fails *after* MATLAB is genuinely connected — still
  reports `success: true`.
- The user closing the `MATLAB` terminal tab mid-session: the next click
  re-triggers the connect prompt even if the underlying MATLAB process is
  still alive (heuristic false positive in the safe direction — worst case
  an unnecessary prompt, never a false success).

The actual fix for all of those is Stage 2 of the deferred plan: MATLAB
itself writes `.started`/`.done` marker files via `onCleanup`, and the
extension polls for them instead of assuming dispatch means done. That's a
bigger change (touches `scimatlab`, needs a "stop waiting" affordance) and
is still queued — revisit it the next time a real run's failure shows
green rather than just a connection-only click.

## Files

| File | Role |
| --- | --- |
| `extension/src/matlabConnectionGate.ts` | Pure decision function, unit-tested |
| `extension/src/matlabConnectionGate.test.ts` | Tests |
| `extension/src/matlabTerminal.ts` | `isMatlabTerminalOpen()` — the vscode-dependent proxy signal |
| `extension/src/dagPanel.ts` | `gateOnMatlabConnection()`, called from `handleMatlabRun` / `handleMatlabPipelineRun` |
| `.claude/plan-matlab-terminal-run-tracking.md` | Full P1/P2/Stage 1/Stage 2 plan, "Interim fix" section |
