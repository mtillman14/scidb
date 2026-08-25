/**
 * ParameterSettingsPanel — shown in the sidebar when a Parameter node is
 * selected. Add, remove and edit its values.
 *
 * Every change here **rewrites the declaration in source** via
 * `update_parameter` — the file is the single source of truth, and the GUI
 * edits it the way an IDE would (docs/claude/entity-editability-model.md).
 * Adding a value is literally adding an argument:
 * `scidb.Parameter(10)` -> `scidb.Parameter(10, 20)`. There is no second
 * kind to convert to, so no conversion prompt (D6).
 *
 * Values that have run but are no longer declared in source stay listed
 * (the DB is the record of what actually ran) and are marked "history" —
 * removing one of those is a no-op against source, so the row has no
 * remove button.
 *
 * A refused write is SHOWN, never silently reverted — see useSourceEdit for
 * why that matters.
 */

import { useState } from 'react'
import type { ParameterValue } from '../DAG/ParameterNode'
import { formatLocation, useSourceEdit } from './useSourceEdit'

interface Props {
  id: string
  label: string
  values: ParameterValue[]
}

/** The values source currently declares, in node order. */
function declaredValues(values: ParameterValue[]): string[] {
  return values.filter(v => v.is_current_source_value).map(v => v.value)
}

/** `"20"` -> 20, `"abc"` -> `"abc"` — the panel's inputs are text, but a
 *  Parameter should hold real numbers so version_keys match a bare literal. */
function coerce(raw: string): number | string | boolean {
  const t = raw.trim()
  if (t === 'true') return true
  if (t === 'false') return false
  if (t !== '' && !Number.isNaN(Number(t))) return Number(t)
  return t
}

export default function ParameterSettingsPanel({ label, values }: Props) {
  const [draft, setDraft] = useState('')
  const { submit, error, readOnlyAt, saving, clearError } = useSourceEdit()

  const declared = declaredValues(values)

  const write = (next: string[]) =>
    submit('update_parameter', { name: label, values: next.map(coerce) })

  const addValue = async () => {
    const v = draft.trim()
    if (!v || declared.includes(v)) {
      setDraft('')
      return
    }
    if (await write([...declared, v])) setDraft('')
  }

  const removeValue = async (value: string) => {
    const next = declared.filter(d => d !== value)
    if (next.length === 0) {
      // Mirrors the backend guard, but locally so the user gets the reason
      // before a round-trip that would refuse it anyway.
      clearError()
      return
    }
    await write(next)
  }

  return (
    <div style={styles.root}>
      <div style={styles.constName}>{label}</div>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>
          Values{declared.length > 1 ? ` — runs ${declared.length}×` : ''}
        </div>

        {values.length === 0 && <div style={styles.empty}>No values yet</div>}

        {values.map((v, i) => {
          const isDeclared = !!v.is_current_source_value
          return (
            <div key={i} style={styles.valueRow}>
              <span style={styles.valuePill}>{v.value}</span>
              {v.record_count > 0 && (
                <span style={styles.recCount}>{v.record_count} rec</span>
              )}
              {!isDeclared && <span style={styles.historyTag}>history</span>}
              {isDeclared && declared.length > 1 && (
                <button
                  style={styles.removeBtn}
                  onClick={() => removeValue(v.value)}
                  disabled={saving}
                  title="Remove from the declaration in source"
                >
                  ×
                </button>
              )}
            </div>
          )
        })}
      </section>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Add value</div>
        <div style={styles.addRow}>
          <input
            style={styles.input}
            placeholder="value…"
            value={draft}
            disabled={saving}
            onChange={e => { setDraft(e.target.value); clearError() }}
            onKeyDown={e => {
              if (e.key === 'Enter') addValue()
              if (e.key === 'Escape') { setDraft(''); clearError() }
            }}
          />
          <button style={styles.addBtn} onClick={addValue} disabled={saving}>
            {saving ? '…' : 'Add'}
          </button>
        </div>
        {declared.length > 1 && (
          <div style={styles.hint}>
            Each value runs as its own for_each call.
          </div>
        )}
      </section>

      {error && (
        <div style={styles.error}>
          {error}
          {readOnlyAt && (
            <div style={styles.errorDetail}>
              Declared in <span style={styles.mono}>{formatLocation(readOnlyAt)}</span> —
              edit it there and hit 🔄 Refresh Code.
            </div>
          )}
        </div>
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
  constName: {
    fontFamily: 'monospace',
    fontWeight: 700,
    fontSize: 13,
    color: '#4ecdc4',
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
  empty: {
    color: '#555',
    fontStyle: 'italic',
    fontSize: 11,
  },
  valueRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
    borderBottom: '1px solid #1e1e3a',
    paddingBottom: 4,
  },
  valuePill: {
    flex: 1,
    background: '#1e3a2f',
    borderRadius: 3,
    padding: '2px 6px',
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#b2ded9',
  },
  recCount: {
    color: '#555',
    fontSize: 10,
    whiteSpace: 'nowrap',
  },
  historyTag: {
    color: '#666',
    fontSize: 9,
    fontStyle: 'italic',
    whiteSpace: 'nowrap',
  },
  removeBtn: {
    background: 'transparent',
    border: 'none',
    color: '#666',
    cursor: 'pointer',
    fontSize: 14,
    padding: '0 2px',
    lineHeight: 1,
  },
  addRow: {
    display: 'flex',
    gap: 6,
  },
  input: {
    flex: 1,
    background: '#1a1a2e',
    border: '1px solid #333',
    borderRadius: 3,
    color: '#ccc',
    fontSize: 11,
    padding: '3px 6px',
    minWidth: 0,
  },
  addBtn: {
    background: '#2a9d8f',
    border: 'none',
    borderRadius: 3,
    color: '#fff',
    fontSize: 11,
    padding: '3px 8px',
    cursor: 'pointer',
    fontWeight: 600,
  },
  hint: {
    marginTop: 5,
    fontSize: 10,
    color: '#666',
  },
  error: {
    background: 'rgba(255, 77, 79, 0.12)',
    border: '1px solid #ff4d4f',
    borderRadius: 4,
    padding: '6px 8px',
    fontSize: 11,
    color: '#ff9a9c',
    whiteSpace: 'pre-wrap',
  },
  errorDetail: {
    marginTop: 4,
    color: '#c98a8b',
  },
  mono: {
    fontFamily: 'monospace',
  },
}
