/**
 * AddLibraryDialog — modal for browsing tapped indexes and installing libraries.
 *
 * Flow:
 *   1. User opens dialog (from the Project tab's Libraries section)
 *   2. Select a tapped index from the dropdown
 *   3. Search for packages by name
 *   4. Pick a version (default: latest)
 *   5. Click Install → calls POST /api/project/libraries → closes on success
 *   6. On failure: show uv's error verbatim
 */

import { useState, useEffect, useCallback } from 'react'
import { callBackend } from '../../api'

interface IndexInfo {
  name: string
  url: string
  exists_locally: boolean
}

interface PackageInfo {
  name: string
  description: string
  versions: string[]
  index_url: string
}

interface Props {
  open: boolean
  onClose: () => void
  onInstalled: () => void
}

export default function AddLibraryDialog({ open, onClose, onInstalled }: Props) {
  const [indexes, setIndexes] = useState<IndexInfo[]>([])
  const [selectedIndex, setSelectedIndex] = useState('')
  const [query, setQuery] = useState('')
  const [packages, setPackages] = useState<PackageInfo[]>([])
  const [selectedPkg, setSelectedPkg] = useState<PackageInfo | null>(null)
  const [version, setVersion] = useState('')
  const [installing, setInstalling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searching, setSearching] = useState(false)

  // Load indexes on open.
  useEffect(() => {
    if (!open) return
    ;(async () => {
      const res = await callBackend('get_indexes') as { indexes: IndexInfo[] }
      setIndexes(res.indexes)
      if (res.indexes.length > 0 && !selectedIndex) {
        setSelectedIndex(res.indexes[0].name)
      }
    })()
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  // Search when query or index changes (debounced).
  useEffect(() => {
    if (!open || !selectedIndex) return
    const timer = setTimeout(async () => {
      setSearching(true)
      try {
        const res = await callBackend('search_index_packages', {
          name: selectedIndex,
          q: query,
        }) as { packages: PackageInfo[]; error?: string }
        if (res.error) {
          setError(res.error)
          setPackages([])
        } else {
          setPackages(res.packages)
          setError(null)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [open, selectedIndex, query])

  const handleInstall = useCallback(async () => {
    if (!selectedPkg) return
    setInstalling(true)
    setError(null)
    try {
      const res = await callBackend('add_library', {
        name: selectedPkg.name,
        version: version || undefined,
        index: selectedPkg.index_url || undefined,
      }) as { ok: boolean; error?: string }
      if (res.ok) {
        onInstalled()
        onClose()
      } else {
        setError(res.error || 'Install failed.')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setInstalling(false)
    }
  }, [selectedPkg, version, onInstalled, onClose])

  if (!open) return null

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.dialog} onClick={e => e.stopPropagation()}>
        <div style={styles.title}>Add Library</div>

        {/* Index selector */}
        <label style={styles.label}>Index</label>
        {indexes.length === 0 ? (
          <div style={styles.hint}>
            No tapped indexes configured. Add one in ~/.scistack/config.toml.
          </div>
        ) : (
          <select
            style={styles.select}
            value={selectedIndex}
            onChange={e => { setSelectedIndex(e.target.value); setPackages([]); setSelectedPkg(null) }}
          >
            {indexes.map(idx => (
              <option key={idx.name} value={idx.name}>
                {idx.name} {!idx.exists_locally ? '(not cloned)' : ''}
              </option>
            ))}
          </select>
        )}

        {/* Search */}
        <label style={styles.label}>Search</label>
        <input
          style={styles.input}
          placeholder="Package name..."
          value={query}
          onChange={e => { setQuery(e.target.value); setSelectedPkg(null) }}
        />

        {/* Results */}
        <div style={styles.resultsList}>
          {searching && <div style={styles.hint}>Searching...</div>}
          {!searching && packages.length === 0 && query && (
            <div style={styles.hint}>No packages found.</div>
          )}
          {packages.map(pkg => (
            <div
              key={pkg.name}
              style={{
                ...styles.resultRow,
                background: selectedPkg?.name === pkg.name ? '#2a2a6a' : 'transparent',
              }}
              onClick={() => {
                setSelectedPkg(pkg)
                setVersion(pkg.versions.length > 0 ? pkg.versions[0] : '')
              }}
            >
              <div style={{ fontWeight: 600 }}>{pkg.name}</div>
              {pkg.description && <div style={{ fontSize: 11, color: '#888' }}>{pkg.description}</div>}
            </div>
          ))}
        </div>

        {/* Version picker */}
        {selectedPkg && (
          <>
            <label style={styles.label}>Version</label>
            {selectedPkg.versions.length > 0 ? (
              <select
                style={styles.select}
                value={version}
                onChange={e => setVersion(e.target.value)}
              >
                {selectedPkg.versions.map(v => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            ) : (
              <input
                style={styles.input}
                placeholder="latest"
                value={version}
                onChange={e => setVersion(e.target.value)}
              />
            )}
          </>
        )}

        {/* Error */}
        {error && <pre style={styles.error}>{error}</pre>}

        {/* Actions */}
        <div style={styles.actions}>
          <button style={styles.cancelBtn} onClick={onClose}>Cancel</button>
          <button
            style={styles.installBtn}
            disabled={!selectedPkg || installing}
            onClick={handleInstall}
          >
            {installing ? 'Installing...' : 'Install'}
          </button>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed',
    top: 0, left: 0, right: 0, bottom: 0,
    background: 'rgba(0,0,0,0.6)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  },
  dialog: {
    background: '#1a1a2e',
    border: '1px solid #3a3a6a',
    borderRadius: 8,
    padding: 20,
    width: 420,
    maxHeight: '80vh',
    overflow: 'auto',
    color: '#ddd',
  },
  title: {
    fontSize: 16,
    fontWeight: 700,
    marginBottom: 12,
  },
  label: {
    display: 'block',
    fontSize: 11,
    fontWeight: 700,
    color: '#888',
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
    marginTop: 10,
    marginBottom: 4,
  },
  select: {
    width: '100%',
    background: '#12122a',
    color: '#ddd',
    border: '1px solid #3a3a6a',
    borderRadius: 4,
    padding: '6px 8px',
    fontSize: 13,
  },
  input: {
    width: '100%',
    background: '#12122a',
    color: '#ddd',
    border: '1px solid #3a3a6a',
    borderRadius: 4,
    padding: '6px 8px',
    fontSize: 13,
    boxSizing: 'border-box' as const,
  },
  resultsList: {
    maxHeight: 200,
    overflow: 'auto',
    marginTop: 8,
    border: '1px solid #2a2a4a',
    borderRadius: 4,
    minHeight: 60,
  },
  resultRow: {
    padding: '6px 10px',
    cursor: 'pointer',
    borderBottom: '1px solid #2a2a4a',
    fontSize: 13,
  },
  hint: {
    color: '#666',
    fontSize: 12,
    fontStyle: 'italic',
    padding: '8px 10px',
  },
  error: {
    background: '#442222',
    color: '#ff8888',
    padding: 8,
    borderRadius: 4,
    marginTop: 8,
    fontSize: 11,
    maxHeight: 120,
    overflow: 'auto',
    whiteSpace: 'pre-wrap' as const,
  },
  actions: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 16,
  },
  cancelBtn: {
    background: 'transparent',
    color: '#888',
    border: '1px solid #3a3a6a',
    borderRadius: 4,
    padding: '6px 16px',
    fontSize: 13,
    cursor: 'pointer',
  },
  installBtn: {
    background: '#7b68ee',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    padding: '6px 16px',
    fontSize: 13,
    cursor: 'pointer',
    fontWeight: 600,
  },
}
