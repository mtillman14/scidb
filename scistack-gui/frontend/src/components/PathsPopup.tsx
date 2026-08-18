/**
 * PathsPopup — modal opened from the header's small 📁 Paths button.
 *
 * Replaces the old permanent "Project" sidebar tab (renamed per the to-do:
 * a config surface you check occasionally shouldn't eat a slot in the tab
 * bar you look at constantly). Two sections:
 *
 *   - Configured Paths: the resolved [tool.scistack] config (Python
 *     modules/packages + MATLAB functions/variables/addpath) via the new
 *     GET /api/project/paths endpoint — read-only. Editing writes to
 *     pyproject.toml by hand today; a write-back UI is future work (see
 *     .claude/plan-todos-order-26.08.12.md item #3's progress note).
 *   - Discovered Code: the existing ProjectConfigPanel browser, unchanged.
 */

import { useState, useEffect, useCallback } from 'react'
import { callBackend } from '../api'
import ProjectConfigPanel from './Sidebar/ProjectConfigPanel'

interface PathsInfo {
  configured: boolean
  project_root: string
  modules?: string[]
  variable_file?: string | null
  packages?: string[]
  auto_discover?: boolean
  matlab_functions?: string[]
  matlab_variables?: string[]
  matlab_addpath?: string[]
  matlab_variable_dir?: string | null
}

export default function PathsPopup({ onClose }: { onClose: () => void }) {
  const [paths, setPaths] = useState<PathsInfo | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fetchPaths = useCallback(() => {
    callBackend('get_project_paths')
      .then(d => setPaths(d as PathsInfo))
      .catch(err => setError((err as Error).message))
  }, [])

  useEffect(() => { fetchPaths() }, [fetchPaths])

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.dialog} onClick={e => e.stopPropagation()}>
        <div style={styles.header}>
          <span style={styles.title}>Paths</span>
          <button style={styles.closeBtn} onClick={onClose} title="Close" type="button">×</button>
        </div>
        <div style={styles.body}>
          <section style={{ marginBottom: 20 }}>
            <div style={styles.sectionTitle}>Configured Paths</div>
            {error && <div style={styles.errorBanner}>{error}</div>}
            {!paths ? (
              <div style={styles.emptyText}>Loading…</div>
            ) : !paths.configured ? (
              <div style={styles.emptyText}>
                Single-file mode — no [tool.scistack] paths configured.
                Project root: <span style={styles.mono}>{paths.project_root}</span>
              </div>
            ) : (
              <div style={styles.pathsGrid}>
                <PathRow label="Project root" values={[paths.project_root]} />
                <PathRow label="Python modules" values={paths.modules ?? []} />
                <PathRow label="Python packages" values={paths.packages ?? []} />
                <PathRow label="Variable file" values={paths.variable_file ? [paths.variable_file] : []} />
                <PathRow label="MATLAB functions" values={paths.matlab_functions ?? []} />
                <PathRow label="MATLAB variables" values={paths.matlab_variables ?? []} />
                <PathRow label="MATLAB addpath" values={paths.matlab_addpath ?? []} />
                <PathRow label="MATLAB variable dir" values={paths.matlab_variable_dir ? [paths.matlab_variable_dir] : []} />
              </div>
            )}
            <div style={styles.hint}>
              Edit these under <span style={styles.mono}>[tool.scistack]</span> / <span style={styles.mono}>[tool.scistack.matlab]</span> in pyproject.toml (or scistack.toml), then hit Refresh below.
            </div>
          </section>
          <ProjectConfigPanel />
        </div>
      </div>
    </div>
  )
}

function PathRow({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) return null
  return (
    <div style={styles.pathRow}>
      <div style={styles.pathLabel}>{label}</div>
      {values.map((v, i) => (
        <div key={i} style={styles.pathValue}>{v}</div>
      ))}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0, 0, 0, 0.6)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9000,
  },
  dialog: {
    width: 640,
    maxHeight: '80vh',
    display: 'flex',
    flexDirection: 'column',
    background: '#12122a',
    color: '#ccc',
    border: '1px solid #3a3a5a',
    borderRadius: 8,
    boxShadow: '0 10px 40px rgba(0, 0, 0, 0.6)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    padding: '10px 14px',
    borderBottom: '1px solid #2a2a4a',
    flexShrink: 0,
  },
  title: {
    flex: 1,
    fontWeight: 700,
    fontSize: 15,
    color: '#fff',
  },
  closeBtn: {
    background: 'transparent',
    border: 'none',
    color: '#888',
    fontSize: 16,
    cursor: 'pointer',
    padding: '2px 6px',
    lineHeight: 1,
  },
  body: {
    overflowY: 'auto',
    padding: '12px 14px',
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: 700,
    color: '#888',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 8,
  },
  errorBanner: {
    background: '#442222',
    color: '#ff8888',
    padding: '6px 10px',
    borderRadius: 4,
    marginBottom: 8,
    fontSize: 12,
  },
  emptyText: {
    color: '#666',
    fontSize: 12,
    fontStyle: 'italic',
  },
  pathsGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  pathRow: {
    background: '#1a1a2e',
    border: '1px solid #2a2a4a',
    borderRadius: 4,
    padding: '6px 10px',
  },
  pathLabel: {
    fontSize: 10,
    fontWeight: 700,
    color: '#7b68ee',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginBottom: 3,
  },
  pathValue: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#ccc',
    wordBreak: 'break-all',
    padding: '1px 0',
  },
  mono: {
    fontFamily: 'monospace',
  },
  hint: {
    marginTop: 8,
    fontSize: 11,
    color: '#666',
    lineHeight: 1.5,
  },
}
