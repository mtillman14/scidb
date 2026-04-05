/**
 * PathInputSettingsPanel — shown in the sidebar when a PathInput node is selected.
 *
 * Editable fields for path template and root folder.  Changes update the
 * React Flow node data (so the canvas reflects edits live) and persist to
 * the backend via PUT /api/path-inputs/{name}.
 */

import { useState, useEffect, useRef } from 'react'
import { useReactFlow } from '@xyflow/react'
import { callBackend } from '../../api'

interface Props {
  id: string
  label: string
  template: string
  root_folder: string | null
}

function parseTemplateKeys(template: string): string[] {
  const matches = template.match(/\{(\w+)\}/g)
  if (!matches) return []
  return [...new Set(matches.map(m => m.slice(1, -1)))]
}

export default function PathInputSettingsPanel({ id, label, template, root_folder }: Props) {
  const { setNodes } = useReactFlow()
  const [draftTemplate, setDraftTemplate] = useState(template)
  const [draftRoot, setDraftRoot] = useState(root_folder ?? '')
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync drafts when a different node is selected.
  useEffect(() => {
    setDraftTemplate(template)
    setDraftRoot(root_folder ?? '')
  }, [id, template, root_folder])

  const persist = (newTemplate: string, newRoot: string) => {
    const rootVal = newRoot.trim() || null

    // Update React Flow node data so the canvas reflects changes immediately.
    setNodes(nds => nds.map(n =>
      n.id === id
        ? { ...n, data: { ...n.data, template: newTemplate, root_folder: rootVal } }
        : n
    ))

    // Debounced save to backend.
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      callBackend('update_path_input', { name: label, template: newTemplate, root_folder: rootVal })
        .catch(err => console.error('[PathInputSettings] save error:', err))
    }, 400)
  }

  const onTemplateChange = (val: string) => {
    setDraftTemplate(val)
    persist(val, draftRoot)
  }

  const onRootChange = (val: string) => {
    setDraftRoot(val)
    persist(draftTemplate, val)
  }

  const keys = parseTemplateKeys(draftTemplate)

  return (
    <div style={styles.root}>
      <div style={styles.name}>{label}</div>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Path Template</div>
        <input
          style={styles.input}
          value={draftTemplate}
          placeholder="{subject}/trial_{trial}.mat"
          onChange={e => onTemplateChange(e.target.value)}
        />
      </section>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Root Folder</div>
        <input
          style={styles.input}
          value={draftRoot}
          placeholder="/data (optional)"
          onChange={e => onRootChange(e.target.value)}
        />
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
  input: {
    display: 'block',
    width: '100%',
    background: '#1a1a2e',
    border: '1px solid #444',
    borderRadius: 3,
    color: '#e5c8a0',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '5px 6px',
    outline: 'none',
    boxSizing: 'border-box',
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
}
