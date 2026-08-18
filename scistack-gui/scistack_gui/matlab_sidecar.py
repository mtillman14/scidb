"""
Standalone/browser MATLAB sidecar (Stage 3, plan-matlab-pipeline-execution.md).

A lazily-started, kept-warm MATLAB process the Python backend drives
directly over its own stdin/stdout REPL — for environments with no VS Code
+ MathWorks terminal integration (``matlabTerminal.ts``/``dagPanel.ts``,
which handle Tier 2). No new ``.m`` file is needed: MATLAB's own
command-line REPL *is* the "server".

Protocol: a command is wrapped in an outer ``try/catch`` that ALWAYS
``disp``s exactly one sentinel line before returning to the prompt — a
success sentinel on the normal path, an error sentinel (carrying the
caught exception's message) in the catch — regardless of whether the
command text itself already has its own inner try/catch (Stage 1's
generated scripts do; nesting is valid MATLAB and the outer catch also
guards commands with no error handling of their own). ``run_command``
writes the wrapped text, then reads stdout lines from a background reader
thread via a queue until one of the two sentinels appears.

No real MATLAB environment exists in this dev sandbox (see the plan
doc's note) — this module is exercised here only via mocked
``subprocess.Popen``; real verification needs the user's own MATLAB
install.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from queue import Empty, Queue
from typing import Callable

logger = logging.getLogger(__name__)

DONE_SENTINEL = "__SCISTACK_SIDECAR_DONE__"
ERROR_SENTINEL = "__SCISTACK_SIDECAR_ERROR__"


def _wrap_for_sentinel(command_text: str) -> str:
    """Wrap arbitrary MATLAB text so the REPL always emits exactly one of
    the two sentinels before returning to the prompt, whether or not
    ``command_text`` raises (or already has its own try/catch)."""
    return (
        "try\n"
        f"{command_text}\n"
        f"    disp('{DONE_SENTINEL}');\n"
        "catch scistack_sidecar_err__\n"
        f"    disp(['{ERROR_SENTINEL}: ' scistack_sidecar_err__.message]);\n"
        "end\n"
    )


class MatlabSidecar:
    """One lazily-started, kept-warm MATLAB process, driven over its own
    stdin/stdout. Not safe for concurrent ``run_command`` calls from
    multiple threads at once — callers (``api/run.py``) serialize access
    via the module-level singleton + the existing per-run-id execution
    model (one MATLAB pipeline run at a time)."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._stdout_queue: "Queue[str | None]" = Queue()
        self._reader_thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> bool:
        """Launch MATLAB if not already running. Returns False (no
        exception) if ``matlab`` isn't on PATH — the caller falls back to
        the copy-paste command instead."""
        if self.is_running:
            return True
        matlab_bin = shutil.which("matlab")
        if matlab_bin is None:
            logger.warning("MatlabSidecar.start: 'matlab' not found on PATH")
            return False
        logger.info("MatlabSidecar.start: launching %s", matlab_bin)
        self._proc = subprocess.Popen(
            [matlab_bin, "-nodesktop", "-nosplash", "-nodisplay"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._reader_thread = threading.Thread(
            target=self._read_stdout, daemon=True, name="MatlabSidecar-reader"
        )
        self._reader_thread.start()
        logger.info("MatlabSidecar.start: MATLAB process started (pid=%s)", self._proc.pid)
        return True

    def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                self._stdout_queue.put(line)
        finally:
            # Process' stdout closed (exited or was killed) — unblock any
            # in-flight run_command wait with an explicit "no more output"
            # sentinel rather than hanging forever.
            self._stdout_queue.put(None)

    def stop(self) -> None:
        """Kill the sidecar process — used for best-effort cancellation
        (``force_cancel_run``) and to recover from a wedged/dead process.
        Safe to call when nothing is running."""
        if self._proc is None:
            return
        logger.info("MatlabSidecar.stop: terminating MATLAB process (pid=%s)", self._proc.pid)
        try:
            self._proc.kill()
        except Exception:
            logger.exception("MatlabSidecar.stop: failed to kill MATLAB process")
        self._proc = None
        self._reader_thread = None
        # Drain any output queued from the dying process so a subsequent
        # start()+run_command() begins with a clean queue.
        while True:
            try:
                self._stdout_queue.get_nowait()
            except Empty:
                break

    def run_command(
        self,
        command_text: str,
        on_line: Callable[[str], None],
        timeout: float | None = None,
    ) -> bool:
        """Write ``command_text`` to MATLAB's stdin, relaying each stdout
        line to ``on_line`` as it arrives, until the wrapper's sentinel
        appears. Returns True on the success sentinel, False on the error
        sentinel (the error line itself is still relayed to ``on_line``
        first, so the caller's run console shows the MATLAB error message).

        Raises RuntimeError if the sidecar isn't running (call ``start()``
        first) or MATLAB's process exits mid-command; raises TimeoutError
        if ``timeout`` elapses with no sentinel seen.
        """
        if not self.is_running:
            raise RuntimeError("MatlabSidecar.run_command: sidecar is not running")
        proc = self._proc
        assert proc is not None and proc.stdin is not None

        wrapped = _wrap_for_sentinel(command_text)
        logger.info(
            "MatlabSidecar.run_command: writing %d-char wrapped command", len(wrapped)
        )
        proc.stdin.write(wrapped)
        proc.stdin.flush()

        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise TimeoutError(
                    f"MatlabSidecar.run_command: timed out after {timeout}s"
                )
            try:
                line = self._stdout_queue.get(timeout=remaining)
            except Empty:
                raise TimeoutError(
                    f"MatlabSidecar.run_command: timed out after {timeout}s"
                ) from None
            if line is None:
                raise RuntimeError(
                    "MatlabSidecar.run_command: MATLAB process exited before "
                    "completion"
                )
            if DONE_SENTINEL in line:
                logger.info("MatlabSidecar.run_command: done sentinel seen")
                return True
            if ERROR_SENTINEL in line:
                logger.warning("MatlabSidecar.run_command: error sentinel seen: %s", line.strip())
                on_line(line)
                return False
            on_line(line)


# ---------------------------------------------------------------------------
# Process-wide singleton (mirrors scistack_gui.db's `_db` module-level
# singleton pattern) — kept warm across pipeline runs instead of relaunching
# MATLAB (slow to start) on every request.
# ---------------------------------------------------------------------------

_sidecar: MatlabSidecar | None = None
_sidecar_lock = threading.Lock()


def get_sidecar() -> MatlabSidecar:
    """The process-wide ``MatlabSidecar`` singleton. No MATLAB process is
    launched until the first ``start()``/``run_command()`` call actually
    needs one."""
    global _sidecar
    with _sidecar_lock:
        if _sidecar is None:
            _sidecar = MatlabSidecar()
        return _sidecar


def sidecar_capable() -> bool:
    """True if ``matlab`` is on PATH — the cheap capability check the
    Stage 4 routing ladder uses BEFORE committing to a sidecar launch."""
    return shutil.which("matlab") is not None
