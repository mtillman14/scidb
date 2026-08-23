/**
 * PathInputSettingsPanel — shown in the sidebar when a PathInput node is selected.
 *
 * Read-only: template/root_folder/alternate_templates are source-scanned
 * (see docs/claude/code-discovery-categories.md and the "PathInputs, Sweeps,
 * and Submodules read from source" migration). There is no update_path_input/
 * add_path_input_alternate/remove_path_input_alternate on the backend
 * anymore -- editing a PathInput means editing its `scidb.PathInput(...)`
 * declaration in source and hitting "Refresh Code", same as a function body.
 * This panel used to offer live-editable inputs wired to those since-removed
 * RPCs; they silently no-opped (or errored) on every save, which is why
 * edits looked like they were reverting to the default value.
 */

import { useCallback, useState } from 'react'
import { callBackend } from '../../api'
import { useScope } from '../../context/ScopeContext'

interface PathInputAlternate {
  template: string
  root_folder: string | null
}

interface Props {
  id: string
  label: string
  template: string
  root_folder: string | null
  alternate_templates: PathInputAlternate[]
}

function parseTemplateKeys(template: string): string[] {
  const matches = template.match(/\{(\w+)\}/g)
  if (!matches) return []
  return [...new Set(matches.map(m => m.slice(1, -1)))]
}

export default function PathInputSettingsPanel({ id, label, template, root_folder, alternate_templates }: Props) {
  const { bumpGraph } = useScope()
  const [deepCopyError, setDeepCopyError] = useState('')

  const keys = parseTemplateKeys(template)

  const handleDeepCopy = useCallback(() => {
    callBackend('deep_copy_path_input', { node_id: id })
      .then(() => { setDeepCopyError(''); bumpGraph() })
      .catch(err => setDeepCopyError((err as Error).message))
  }, [id, bumpGraph])

  return (
    <div style={styles.root}>
      <div style={styles.name}>{label}</div>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Path Template</div>
        <div style={styles.value}>{template || '(empty)'}</div>
        <div style={styles.hint}>
          Shared by name — edit the <span style={styles.mono}>scidb.PathInput(...)</span> declaration
          in source, then hit 🔄 Refresh Code.
        </div>
      </section>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Root Folder</div>
        <div style={styles.value}>{root_folder || '(not set)'}</div>
      </section>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Alternate Templates</div>
        <div style={styles.hint}>
          More than one template runs as EachOf(...) — one for_each call per
          alternative, results concatenated.
        </div>

        {alternate_templates.length === 0 ? (
          <div style={styles.empty}>No alternates — single template only.</div>
        ) : (
          alternate_templates.map((alt, i) => (
            <div key={i} style={styles.altRow}>
              <div style={styles.altTemplateText}>{alt.template}</div>
              {alt.root_folder && (
                <div style={styles.altRootText}>root: {alt.root_folder}</div>
              )}
            </div>
          ))
        )}
      </section>

      <section style={styles.section}>
        <button style={styles.deepCopyBtn} onClick={handleDeepCopy} type="button">
          Deep copy (make this placement independent)
        </button>
        {deepCopyError && <div style={styles.errorText}>{deepCopyError}</div>}
      </section>

      {keys.length > 0 && (
        <section style={styles.section}>
          <div style={styles.sectionTitle}>Schema Keys</div>
          <div style={styles.keysRow}>
            {keys.map(k => (
              <span key={k} style={styles.keyPill}>{k}</span>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    padding: '12px',
    color: '#ccc',
    fontSize: 12,
  },
  name: {
    fontFamily: 'monospace',
    fontWeight: 700,
    fontSize: 13,
    color: '#fbbf24',
    marginBottom: 12,
    wordBreak: 'break-all',
  },
  section: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 10,
    fontWeight: 700,
    color: '#666',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  value: {
    display: 'block',
    width: '100%',
    background: '#1a1a2e',
    border: '1px solid #333',
    borderRadius: 3,
    color: '#e5c8a0',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '5px 6px',
    boxSizing: 'border-box',
    wordBreak: 'break-all',
  },
  hint: {
    fontSize: 10,
    color: '#666',
    marginTop: 4,
    lineHeight: 1.4,
  },
  mono: {
    fontFamily: 'monospace',
  },
  deepCopyBtn: {
    width: '100%',
    padding: '5px 0',
    background: 'transparent',
    color: '#fbbf24',
    border: '1px solid #92702a',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 11,
    fontWeight: 600,
  },
  errorText: {
    marginTop: 6,
    fontSize: 11,
    color: '#f87171',
    whiteSpace: 'pre-wrap',
  },
  keysRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 5,
  },
  keyPill: {
    fontSize: 11,
    fontFamily: 'monospace',
    background: '#3d2e1a',
    border: '1px solid #92702a',
    borderRadius: 3,
    padding: '2px 6px',
    color: '#fbbf24',
  },
  empty: {
    color: '#555',
    fontStyle: 'italic',
    fontSize: 11,
    marginTop: 6,
  },
  altRow: {
    marginTop: 6,
    borderBottom: '1px solid #1e1e3a',
    paddingBottom: 4,
  },
  altTemplateText: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#e5c8a0',
    wordBreak: 'break-all',
  },
  altRootText: {
    fontFamily: 'monospace',
    fontSize: 10,
    color: '#8a7a60',
    wordBreak: 'break-all',
  },
}
