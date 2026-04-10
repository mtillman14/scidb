/**
 * ProjectConfigPanel — project-level panel showing discovered exports.
 *
 * Two sections:
 *   - Project Code: modules under src/{project}/ with Variables/Functions/Constants
 *   - Libraries: installed packages from uv.lock that expose scistack exports
 *
 * Triggered by the Refresh button or initially on first render.
 */

import { useState, useEffect, useCallback } from 'react'
import { callBackend } from '../../api'
import AddLibraryDialog from './AddLibraryDialog'

// ---------------------------------------------------------------------------
// Types matching the backend JSON shape
// ---------------------------------------------------------------------------
interface ConstantInfo {
  name: string
  value: string
  description: string
  source_file: string
  source_line: number
}

interface ModuleExports {
  module_name: string
  variables: string[]
  functions: string[]
  constants: ConstantInfo[]
  variable_count: number
  function_count: number
  constant_count: number
}

interface ModuleError {
  module_name: string
  traceback: string
}

interface PackageResult {
  name: string
  modules: ModuleExports[]
  errors: ModuleError[]
  variable_count: number
  function_count: number
  constant_count: number
  is_empty: boolean
}

interface LibrariesResponse {
  libraries: Record<string, PackageResult>
  total_libraries: number
  shown_libraries: number
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function ModuleRow({ mod }: { mod: ModuleExports }) {
  const [open, setOpen] = useState(false)
  const shortName = mod.module_name.split('.').pop() || mod.module_name
  const total = mod.variable_count + mod.function_count + mod.constant_count

  if (total === 0) return null

  return (
    <div style={{ marginBottom: 2 }}>
      <div
        style={styles.moduleHeader}
        onClick={() => setOpen(!open)}
        role="button"
        tabIndex={0}
      >
        <span style={{ marginRight: 6, fontSize: 10 }}>{open ? '\u25BC' : '\u25B6'}</span>
        <span style={{ flex: 1 }}>{shortName}</span>
        <span style={styles.badge}>{total}</span>
      </div>
      {open && (
        <div style={styles.moduleBody}>
          {mod.variables.length > 0 && (
            <div>
              <div style={styles.sectionLabel}>Variables</div>
              {mod.variables.map(v => <div key={v} style={styles.item}>{v}</div>)}
            </div>
          )}
          {mod.functions.length > 0 && (
            <div>
              <div style={styles.sectionLabel}>Functions</div>
              {mod.functions.map(f => <div key={f} style={styles.item}>{f}</div>)}
            </div>
          )}
          {mod.constants.length > 0 && (
            <div>
              <div style={styles.sectionLabel}>Constants</div>
              {mod.constants.map(c => (
                <div key={c.name} style={styles.item} title={c.description || c.value}>
                  {c.name} = {c.value}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ErrorRow({ err }: { err: ModuleError }) {
  const [open, setOpen] = useState(false)
  const shortName = err.module_name.split('.').pop() || err.module_name

  return (
    <div style={{ marginBottom: 2 }}>
      <div
        style={{ ...styles.moduleHeader, color: '#ff6b6b' }}
        onClick={() => setOpen(!open)}
        role="button"
        tabIndex={0}
      >
        <span style={{ marginRight: 6, fontSize: 10 }}>{open ? '\u25BC' : '\u25B6'}</span>
        <span style={{ flex: 1 }}>{shortName}</span>
        <span style={{ ...styles.badge, background: '#552222' }}>error</span>
      </div>
      {open && (
        <pre style={styles.traceback}>{err.traceback}</pre>
      )}
    </div>
  )
}

function PackageSection({ pkg, defaultOpen }: { pkg: PackageResult; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen ?? false)
  const total = pkg.variable_count + pkg.function_count + pkg.constant_count

  return (
    <div style={{ marginBottom: 4 }}>
      <div
        style={styles.packageHeader}
        onClick={() => setOpen(!open)}
        role="button"
        tabIndex={0}
      >
        <span style={{ marginRight: 6, fontSize: 10 }}>{open ? '\u25BC' : '\u25B6'}</span>
        <span style={{ flex: 1, fontWeight: 600 }}>{pkg.name}</span>
        <span style={styles.badge}>{total}</span>
      </div>
      {open && (
        <div style={{ paddingLeft: 12 }}>
          {pkg.modules.map(m => <ModuleRow key={m.module_name} mod={m} />)}
          {pkg.errors.map(e => <ErrorRow key={e.module_name} err={e} />)}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function ProjectConfigPanel() {
  const [projectCode, setProjectCode] = useState<PackageResult | null>(null)
  const [libraries, setLibraries] = useState<Record<string, PackageResult>>({})
  const [totalLibs, setTotalLibs] = useState(0)
  const [shownLibs, setShownLibs] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [addLibOpen, setAddLibOpen] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [code, libs] = await Promise.all([
        callBackend('get_project_code') as Promise<PackageResult>,
        callBackend('get_project_libraries') as Promise<LibrariesResponse>,
      ])
      setProjectCode(code)
      setLibraries(libs.libraries)
      setTotalLibs(libs.total_libraries)
      setShownLibs(libs.shown_libraries)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const handleRefresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      await callBackend('refresh_project')
      await fetchData()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [fetchData])

  // Load on first render.
  useEffect(() => { fetchData() }, [fetchData])

  return (
    <div style={{ padding: '0 12px' }}>
      <div style={styles.header}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>Project</span>
        <button
          onClick={handleRefresh}
          disabled={loading}
          style={styles.refreshBtn}
          title="Re-scan project code and libraries"
        >
          {loading ? 'Scanning...' : 'Refresh'}
        </button>
      </div>

      {error && <div style={styles.errorBanner}>{error}</div>}

      {/* Project Code */}
      <div style={styles.sectionTitle}>Project Code</div>
      {projectCode ? (
        projectCode.is_empty && projectCode.errors.length === 0 ? (
          <div style={styles.emptyText}>
            No Variables, Functions, or Constants found in src/{projectCode.name}/.
          </div>
        ) : (
          <>
            {projectCode.modules.map(m => <ModuleRow key={m.module_name} mod={m} />)}
            {projectCode.errors.map(e => <ErrorRow key={e.module_name} err={e} />)}
          </>
        )
      ) : !loading ? (
        <div style={styles.emptyText}>Not scanned yet.</div>
      ) : null}

      {/* Libraries */}
      <div style={{ ...styles.sectionTitle, marginTop: 16 }}>
        Libraries
        {totalLibs > 0 && (
          <span style={styles.libCount}>
            {shownLibs} of {totalLibs} have exports
          </span>
        )}
        <button
          onClick={() => setAddLibOpen(true)}
          style={{ ...styles.refreshBtn, marginLeft: 'auto' }}
        >
          Add Library
        </button>
      </div>
      <AddLibraryDialog
        open={addLibOpen}
        onClose={() => setAddLibOpen(false)}
        onInstalled={fetchData}
      />
      {Object.keys(libraries).length === 0 && !loading ? (
        <div style={styles.emptyText}>
          No libraries with scistack exports found.
        </div>
      ) : (
        Object.entries(libraries).map(([name, pkg]) => (
          <PackageSection key={name} pkg={pkg} />
        ))
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const styles: Record<string, React.CSSProperties> = {
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
    paddingTop: 4,
  },
  refreshBtn: {
    background: '#2a2a5a',
    color: '#ccc',
    border: '1px solid #3a3a6a',
    borderRadius: 4,
    padding: '4px 10px',
    fontSize: 12,
    cursor: 'pointer',
  },
  errorBanner: {
    background: '#442222',
    color: '#ff8888',
    padding: '6px 10px',
    borderRadius: 4,
    marginBottom: 8,
    fontSize: 12,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: 700,
    color: '#888',
    textTransform: 'uppercase' as const,
    letterSpacing: 1,
    marginBottom: 6,
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  libCount: {
    fontWeight: 400,
    fontSize: 11,
    color: '#666',
    textTransform: 'none' as const,
    letterSpacing: 0,
  },
  packageHeader: {
    display: 'flex',
    alignItems: 'center',
    padding: '4px 6px',
    cursor: 'pointer',
    borderRadius: 4,
    fontSize: 13,
    color: '#ddd',
  },
  moduleHeader: {
    display: 'flex',
    alignItems: 'center',
    padding: '3px 6px',
    cursor: 'pointer',
    borderRadius: 3,
    fontSize: 12,
    color: '#bbb',
  },
  moduleBody: {
    paddingLeft: 20,
    paddingBottom: 4,
  },
  sectionLabel: {
    fontSize: 10,
    fontWeight: 700,
    color: '#666',
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
    marginTop: 4,
    marginBottom: 2,
  },
  item: {
    fontSize: 12,
    color: '#aaa',
    padding: '1px 0',
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  badge: {
    background: '#2a2a5a',
    color: '#888',
    borderRadius: 8,
    padding: '1px 7px',
    fontSize: 10,
    fontWeight: 600,
  },
  traceback: {
    background: '#1a1a2a',
    color: '#cc6666',
    padding: 8,
    borderRadius: 4,
    fontSize: 11,
    overflow: 'auto',
    maxHeight: 200,
    margin: '4px 0',
    whiteSpace: 'pre-wrap' as const,
  },
  emptyText: {
    color: '#666',
    fontSize: 12,
    fontStyle: 'italic',
    padding: '4px 6px',
  },
}
