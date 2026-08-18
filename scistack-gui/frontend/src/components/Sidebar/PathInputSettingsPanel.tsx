/**
 * PathInputSettingsPanel — shown in the sidebar when a PathInput node is selected.
 *
 * Editable fields for path template and root folder.  Changes update the
 * React Flow node data (so the canvas reflects edits live) and persist to
 * the backend on Enter or blur.  Escape reverts to the last saved value.
 *
 * Alternate templates (below the primary) are the PathInput analog of a
 * Constant node's multiple staged values: >1 template under one name runs
 * as EachOf(PathInput(...), PathInput(...), ...) at execution time (see
 * execution_service.build_run_inputs). Same add/remove-row pattern as
 * ConstantSettingsPanel's variant list, one row per alternate.
 */

import { useRef, useEffect, useState, useCallback } from 'react'
import { useReactFlow } from '@xyflow/react'
import { callBackend } from '../../api'
import { useCommittedInput } from '../../hooks/useCommittedInput'
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
  const { setNodes } = useReactFlow()
  const { bumpGraph } = useScope()
  const [deepCopyError, setDeepCopyError] = useState('')
  const [altTemplateDraft, setAltTemplateDraft] = useState('')
  const [altRootDraft, setAltRootDraft] = useState('')
  const [altError, setAltError] = useState('')

  // Refs so each field's callbacks can read the other field's latest draft
  // without stale-closure issues.
  const latestTemplate = useRef(template)
  const latestRoot = useRef(root_folder ?? '')

  useEffect(() => {
    latestTemplate.current = template
    latestRoot.current = root_folder ?? ''
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  const updateCanvas = (newTemplate: string, newRoot: string) => {
    const rootVal = newRoot.trim() || null
    setNodes(nds => nds.map(n =>
      n.id === id
        ? { ...n, data: { ...n.data, template: newTemplate, root_folder: rootVal } }
        : n
    ))
  }

  const saveToBackend = (newTemplate: string, newRoot: string) => {
    const rootVal = newRoot.trim() || null
    callBackend('update_path_input', { name: label, template: newTemplate, root_folder: rootVal })
      .catch(err => console.error('[PathInputSettings] save error:', err))
  }

  const templateInput = useCommittedInput({
    initialValue: template,
    resetKey: id,
    onLiveChange: val => { latestTemplate.current = val; updateCanvas(val, latestRoot.current) },
    onSave: val => saveToBackend(val, latestRoot.current),
  })

  const rootInput = useCommittedInput({
    initialValue: root_folder ?? '',
    resetKey: id,
    onLiveChange: val => { latestRoot.current = val; updateCanvas(latestTemplate.current, val) },
    onSave: val => saveToBackend(latestTemplate.current, val),
  })

  const keys = parseTemplateKeys(templateInput.value)

  const handleDeepCopy = useCallback(() => {
    callBackend('deep_copy_path_input', { node_id: id })
      .then(() => { setDeepCopyError(''); bumpGraph() })
      .catch(err => setDeepCopyError((err as Error).message))
  }, [id, bumpGraph])

  const addAlternate = useCallback(() => {
    const t = altTemplateDraft.trim()
    if (!t) return
    const rootVal = altRootDraft.trim() || null
    callBackend('add_path_input_alternate', { name: label, template: t, root_folder: rootVal })
      .then(() => {
        setAltError('')
        setNodes(nds => nds.map(n =>
          n.id === id
            ? { ...n, data: { ...n.data, alternate_templates: [...alternate_templates, { template: t, root_folder: rootVal }] } }
            : n
        ))
        setAltTemplateDraft('')
        setAltRootDraft('')
      })
      .catch(err => setAltError((err as Error).message))
  }, [id, label, altTemplateDraft, altRootDraft, alternate_templates, setNodes])

  const removeAlternate = useCallback((index: number) => {
    callBackend('remove_path_input_alternate', { name: label, index })
      .then(() => {
        setNodes(nds => nds.map(n =>
          n.id === id
            ? { ...n, data: { ...n.data, alternate_templates: alternate_templates.filter((_, i) => i !== index) } }
            : n
        ))
      })
      .catch(err => setAltError((err as Error).message))
  }, [id, label, alternate_templates, setNodes])

  return (
    <div style={styles.root}>
      <div style={styles.name}>{label}</div>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Path Template</div>
        <input
          style={styles.input}
          placeholder="{subject}/trial_{trial}.mat"
          {...templateInput}
        />
        <div style={styles.hint}>
          Shared by name — editing this changes every placement of "{label}".
        </div>
      </section>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Root Folder</div>
        <input
          style={styles.input}
          placeholder="/data (optional)"
          {...rootInput}
        />
      </section>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Alternate Templates</div>
        <div style={styles.hint}>
          More than one template runs as EachOf(...) — one for_each call per
          alternative, results concatenated.
        </div>

        {alternate_templates.length === 0 && (
          <div style={styles.empty}>No alternates — single template only.</div>
        )}

        {alternate_templates.map((alt, i) => (
          <div key={i} style={styles.altRow}>
            <div style={styles.altRowText}>
              <div style={styles.altTemplateText}>{alt.template}</div>
              {alt.root_folder && (
                <div style={styles.altRootText}>root: {alt.root_folder}</div>
              )}
            </div>
            <button style={styles.removeBtn} onClick={() => removeAlternate(i)} title="Remove" type="button">
              ×
            </button>
          </div>
        ))}

        <div style={styles.addAltForm}>
          <input
            style={styles.input}
            placeholder="{subject}/alt_template.csv"
            value={altTemplateDraft}
            onChange={e => setAltTemplateDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') addAlternate() }}
          />
          <input
            style={styles.input}
            placeholder="root folder (optional)"
            value={altRootDraft}
            onChange={e => setAltRootDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') addAlternate() }}
          />
          <button style={styles.addAltBtn} onClick={addAlternate} type="button">
            + Add alternate
          </button>
        </div>
        {altError && <div style={styles.errorText}>{altError}</div>}
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
  hint: {
    fontSize: 10,
    color: '#666',
    marginTop: 4,
    lineHeight: 1.4,
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
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    marginTop: 6,
    borderBottom: '1px solid #1e1e3a',
    paddingBottom: 4,
  },
  altRowText: {
    flex: 1,
    minWidth: 0,
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
  removeBtn: {
    flexShrink: 0,
    background: 'transparent',
    border: 'none',
    color: '#666',
    cursor: 'pointer',
    fontSize: 14,
    padding: '0 2px',
    lineHeight: 1,
  },
  addAltForm: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    marginTop: 8,
  },
  addAltBtn: {
    background: '#92702a',
    border: 'none',
    borderRadius: 3,
    color: '#fff',
    fontSize: 11,
    padding: '4px 8px',
    cursor: 'pointer',
    fontWeight: 600,
  },
}
