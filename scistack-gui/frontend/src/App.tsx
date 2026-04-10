/**
 * Root application component.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────┐
 *   │  header: SciStack + db name                 │
 *   ├───────────────────────────────┬─────────────┤
 *   │  PipelineDAG (left 3/4)       │  sidebar    │
 *   │                               │  (right 1/4)│
 *   └───────────────────────────────┴─────────────┘
 */

import { useEffect, useState, useCallback } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import PipelineDAG from "./components/DAG/PipelineDAG";
import Sidebar from "./components/Sidebar/Sidebar";
import { RunLogProvider } from "./context/RunLogContext";
import { SelectedNodeProvider } from "./context/SelectedNodeContext";
import { callBackend } from "./api";

/**
 * Startup diagnostics reported by the backend's get_info response.
 * Populated by Phase 8 (stale lockfile handling): when a project is opened
 * with an out-of-date uv.lock the backend tries to run `uv sync`, and any
 * failure shows up here as a blocking error so the user never interacts
 * with a broken venv.
 */
interface StartupError {
  kind: string;
  message: string;
  details: string;
  blocking: boolean;
}

interface InfoResponse {
  db_name: string;
  startup_errors?: StartupError[];
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    display: "flex",
    flexDirection: "column",
    width: "100%",
    height: "100%",
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 18px",
    background: "#1a1a2e",
    color: "#fff",
    fontSize: 14,
    flexShrink: 0,
  },
  title: {
    fontWeight: 700,
    fontSize: 16,
    letterSpacing: 0.5,
  },
  separator: {
    opacity: 0.4,
  },
  dbName: {
    fontFamily: "monospace",
    opacity: 0.8,
  },
  refreshBtn: {
    marginLeft: "auto",
    padding: "4px 12px",
    background: "#2a2a4a",
    color: "#ccc",
    border: "1px solid #3a3a5a",
    borderRadius: 4,
    cursor: "pointer",
    fontSize: 12,
    fontFamily: "inherit",
  },
  schemaKeys: {
    opacity: 0.6,
    fontSize: 12,
  },
  body: {
    display: "flex",
    flexDirection: "row",
    flex: 1,
    minHeight: 0,
  },
  dagArea: {
    flex: 3,
    minWidth: 0,
    minHeight: 0,
  },
  sidebar: {
    flex: 1,
    minWidth: 0,
    borderLeft: "1px solid #2a2a4a",
    background: "#12122a",
  },
  // --- Blocking startup-error dialog (Phase 8: stale lockfile handling) ---
  startupOverlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(0, 0, 0, 0.75)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 10000,
  },
  startupDialog: {
    background: "#1a1a2e",
    color: "#eee",
    border: "1px solid #ff4d4f",
    borderRadius: 6,
    padding: "20px 24px",
    maxWidth: 720,
    maxHeight: "80vh",
    overflow: "auto",
    boxShadow: "0 10px 40px rgba(0, 0, 0, 0.6)",
  },
  startupDialogTitle: {
    fontSize: 16,
    fontWeight: 700,
    color: "#ff4d4f",
    marginBottom: 12,
  },
  startupDialogMessage: {
    fontSize: 13,
    lineHeight: 1.5,
    marginBottom: 12,
    whiteSpace: "pre-wrap" as const,
  },
  startupDialogDetails: {
    background: "#0f0f1e",
    border: "1px solid #2a2a4a",
    borderRadius: 4,
    padding: 10,
    fontFamily: "monospace",
    fontSize: 11,
    whiteSpace: "pre-wrap" as const,
    maxHeight: 260,
    overflow: "auto",
    color: "#ccc",
  },
  startupDialogFooter: {
    marginTop: 16,
    fontSize: 12,
    opacity: 0.75,
  },
};

export default function App() {
  const [schema, setSchema] = useState<{ keys: string[] }>({ keys: [] });
  const [dbName, setDbName] = useState("");
  const [restarting, setRestarting] = useState(false);
  const [startupErrors, setStartupErrors] = useState<StartupError[]>([]);

  const handleRestart = useCallback(async () => {
    setRestarting(true);
    try {
      // Host-side method handled by the VS Code extension: kills and respawns
      // the Python subprocess so edits to scistack_gui server code AND the
      // user's pipeline module are picked up.
      await callBackend("restart_python");
    } catch (err) {
      console.error("Restart failed:", err);
    } finally {
      setRestarting(false);
    }
  }, []);

  useEffect(() => {
    callBackend("get_schema")
      .then((d) => setSchema(d as { keys: string[] }))
      .catch(console.error);
    callBackend("get_info")
      .then((d) => {
        const info = d as InfoResponse;
        setDbName(info.db_name);
        setStartupErrors(info.startup_errors ?? []);
      })
      .catch(console.error);
  }, []);

  // Phase 8: any blocking startup error pauses the whole UI.
  const blockingErrors = startupErrors.filter((e) => e.blocking);

  return (
    <RunLogProvider>
      <SelectedNodeProvider>
        <div style={styles.root}>
          <header style={styles.header}>
            <span style={styles.title}>SciStack</span>
            <span style={styles.separator}>|</span>
            <span style={styles.dbName}>{dbName || "loading…"}</span>
            <button
              style={styles.refreshBtn}
              onClick={handleRestart}
              disabled={restarting}
              title="Restart the Python process to pick up edits to server or pipeline code"
            >
              {restarting ? "Restarting..." : "Restart"}
            </button>
            {schema.keys.length > 0 && (
              <span style={styles.schemaKeys}>
                schema: [{schema.keys.join(", ")}]
              </span>
            )}
          </header>
          <ReactFlowProvider>
            <div style={styles.body}>
              <div style={styles.dagArea}>
                <PipelineDAG />
              </div>
              <div style={styles.sidebar}>
                <Sidebar />
              </div>
            </div>
          </ReactFlowProvider>
          {blockingErrors.length > 0 && (
            <StartupErrorDialog errors={blockingErrors} />
          )}
        </div>
      </SelectedNodeProvider>
    </RunLogProvider>
  );
}

/**
 * Blocking modal shown when the backend reports a startup-time error
 * (e.g. failed `uv sync`). There's no dismiss button on purpose — the
 * user needs to fix the problem and restart the project rather than
 * interact with a broken venv.
 */
function StartupErrorDialog({ errors }: { errors: StartupError[] }) {
  return (
    <div style={styles.startupOverlay} role="alertdialog" aria-modal="true">
      <div style={styles.startupDialog}>
        <div style={styles.startupDialogTitle}>
          Project failed to open cleanly
        </div>
        {errors.map((err, i) => (
          <div key={`${err.kind}-${i}`} style={{ marginBottom: 16 }}>
            <div style={styles.startupDialogMessage}>{err.message}</div>
            {err.details && (
              <pre style={styles.startupDialogDetails}>{err.details}</pre>
            )}
          </div>
        ))}
        <div style={styles.startupDialogFooter}>
          Fix the problem above, then restart the SciStack project to
          continue.
        </div>
      </div>
    </div>
  );
}
