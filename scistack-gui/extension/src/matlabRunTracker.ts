/**
 * Tracks which MATLAB runs currently own the DuckDB database.
 *
 * Why this exists: the GUI's Python server deliberately drops its DuckDB
 * file lock between requests (see `scistack_gui/db.py`) so that MATLAB can
 * open the same database. MATLAB then holds that lock for the whole run.
 * Any GUI request issued in that window can only fail — and the DB
 * file-watcher in `extension.ts` is otherwise happy to fire a `dag_updated`
 * on every WAL write MATLAB makes *during* the run, i.e. to generate
 * exactly those doomed requests, repeatedly.
 *
 * So: mark a run in flight when we dispatch it to MATLAB, note (rather than
 * act on) DB changes while it is, and replay one refresh when MATLAB lets
 * go. Deliberately free of any `vscode` import so it can be unit-tested
 * under `node --test` (see tsconfig.test.json).
 */

export class MatlabRunTracker {
  private inFlight = new Set<string>();
  private refreshPending = false;
  private finishedCallbacks: (() => void)[] = [];

  /** Mark a MATLAB run as owning the database from now until its run_done. */
  begin(runId: string): void {
    this.inFlight.add(runId);
  }

  /**
   * Clear a run's mark. Safe to call for every run_done — Python runs are
   * simply absent from the set. Returns whether this was a tracked MATLAB
   * run, and fires the finished callbacks once the last one clears.
   */
  end(runId: string | undefined): boolean {
    if (!runId) return false;
    const wasTracked = this.inFlight.delete(runId);
    if (wasTracked && this.inFlight.size === 0) {
      this.finishedCallbacks.forEach(cb => cb());
    }
    return wasTracked;
  }

  /** Whether any MATLAB run currently holds the database. */
  get isActive(): boolean {
    return this.inFlight.size > 0;
  }

  /**
   * Called by the DB file-watcher. Returns true when the caller should
   * refresh the DAG now; false when MATLAB owns the database, in which case
   * the change is remembered for {@link takeDeferredRefresh}.
   */
  noteDbChange(): boolean {
    if (this.isActive) {
      this.refreshPending = true;
      return false;
    }
    return true;
  }

  /**
   * Consume the deferred refresh, if any. Returns true at most once per
   * withheld change — a MATLAB run that wrote nothing costs no re-fetch.
   */
  takeDeferredRefresh(): boolean {
    if (!this.refreshPending) return false;
    this.refreshPending = false;
    return true;
  }

  /** Register a callback fired when the LAST in-flight MATLAB run ends. */
  onAllFinished(callback: () => void): void {
    this.finishedCallbacks.push(callback);
  }
}
