/**
 * HypothesisPanel — sidebar tab for the CURRENT hypothesis's documentation:
 * research question, hypothesis statement, and evidence for/against.
 *
 * Keyed off the breadcrumb's ROOT (not `currentScope`) so it stays visible
 * and correct while the user has descended into one of the hypothesis's
 * submodules — matches HypothesisTabs' "which tab is active" logic.
 *
 * Follows PipelineSettingsPanel's pattern: re-seed on scope change, save
 * via callBackend, status.ok/status.error display.
 */

import { useState, useEffect, useCallback } from 'react'
import { callBackend } from '../../api'
import { useScope } from '../../context/ScopeContext'
import type { HypothesisInfo } from '../HypothesisTabs'

export default function HypothesisPanel() {
  const { breadcrumb, graphVersion } = useScope()
  const rootPipelineId = breadcrumb[0].pipeline_id
  const [hyp, setHyp] = useState<HypothesisInfo | null>(null)
  const [questionDraft, setQuestionDraft] = useState('')
  const [statementDraft, setStatementDraft] = useState('')
  const [evidenceForDraft, setEvidenceForDraft] = useState('')
  const [evidenceAgainstDraft, setEvidenceAgainstDraft] = useState('')
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null)

  const fetchHypothesis = useCallback(() => {
    callBackend('list_hypotheses')
      .then(d => {
        const found = (d as { hypotheses: HypothesisInfo[] }).hypotheses
          .find(h => h.pipeline_id === rootPipelineId)
        setHyp(found ?? null)
      })
      .catch(console.error)
  }, [rootPipelineId])

  useEffect(() => { fetchHypothesis() }, [fetchHypothesis, graphVersion])

  // Re-seed the free-text drafts whenever a different hypothesis is shown.
  useEffect(() => {
    setQuestionDraft(hyp?.research_question ?? '')
    setStatementDraft(hyp?.hypothesis_statement ?? '')
  }, [hyp?.pipeline_id]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = useCallback((patch: Partial<HypothesisInfo>) => {
    if (!hyp) return
    callBackend('update_hypothesis', { pipeline_id: hyp.pipeline_id, ...patch })
      .then(() => { setStatus({ ok: true, text: 'Saved.' }); fetchHypothesis() })
      .catch(err => setStatus({ ok: false, text: (err as Error).message }))
  }, [hyp, fetchHypothesis])

  if (!hyp) {
    return (
      <div style={styles.root}>
        <div style={styles.empty}>
          This isn't a hypothesis pipeline (it's a submodule) — no
          research-question documentation to show here.
        </div>
      </div>
    )
  }

  const addEvidence = (
    field: 'evidence_for' | 'evidence_against',
    draft: string,
    clearDraft: () => void,
  ) => {
    const text = draft.trim()
    if (!text) return
    save({ [field]: [...hyp[field], text] })
    clearDraft()
  }

  const removeEvidence = (field: 'evidence_for' | 'evidence_against', index: number) => {
    save({ [field]: hyp[field].filter((_, i) => i !== index) })
  }

  return (
    <div style={styles.root}>
      <div style={styles.title}>{hyp.name}</div>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Research Question</div>
        <textarea
          style={styles.textarea}
          placeholder="What are we trying to find out?"
          value={questionDraft}
          onChange={e => setQuestionDraft(e.target.value)}
          onBlur={() => save({ research_question: questionDraft })}
        />
      </section>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Hypothesis</div>
        <textarea
          style={styles.textarea}
          placeholder="What do we expect, and why?"
          value={statementDraft}
          onChange={e => setStatementDraft(e.target.value)}
          onBlur={() => save({ hypothesis_statement: statementDraft })}
        />
      </section>

      <EvidenceList
        title="Evidence For"
        color="#4ade80"
        items={hyp.evidence_for}
        draft={evidenceForDraft}
        setDraft={setEvidenceForDraft}
        onAdd={() => addEvidence('evidence_for', evidenceForDraft, () => setEvidenceForDraft(''))}
        onRemove={i => removeEvidence('evidence_for', i)}
      />

      <EvidenceList
        title="Evidence Against"
        color="#f87171"
        items={hyp.evidence_against}
        draft={evidenceAgainstDraft}
        setDraft={setEvidenceAgainstDraft}
        onAdd={() => addEvidence('evidence_against', evidenceAgainstDraft, () => setEvidenceAgainstDraft(''))}
        onRemove={i => removeEvidence('evidence_against', i)}
      />

      {status && (
        <div style={status.ok ? styles.statusOk : styles.statusError}>{status.text}</div>
      )}
    </div>
  )
}

function EvidenceList({
  title,
  color,
  items,
  draft,
  setDraft,
  onAdd,
  onRemove,
}: {
  title: string
  color: string
  items: string[]
  draft: string
  setDraft: (v: string) => void
  onAdd: () => void
  onRemove: (index: number) => void
}) {
  return (
    <section style={styles.section}>
      <div style={{ ...styles.sectionTitle, color }}>{title}</div>
      {items.map((item, i) => (
        <div key={i} style={styles.evidenceRow}>
          <span style={styles.evidenceText}>{item}</span>
          <button style={styles.removeBtn} onClick={() => onRemove(i)} title="Remove" type="button">
            ×
          </button>
        </div>
      ))}
      <div style={styles.evidenceAddRow}>
        <input
          style={styles.evidenceInput}
          value={draft}
          placeholder="add a note…"
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') onAdd() }}
        />
        <button style={styles.addBtn} onClick={onAdd} title="Add" type="button">+</button>
      </div>
    </section>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    padding: '12px',
    color: '#ccc',
    fontSize: 12,
  },
  empty: {
    color: '#666',
    fontSize: 12,
    lineHeight: 1.5,
  },
  title: {
    fontFamily: 'monospace',
    fontWeight: 700,
    fontSize: 13,
    color: '#fff',
    marginBottom: 12,
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
  textarea: {
    display: 'block',
    width: '100%',
    minHeight: 56,
    resize: 'vertical',
    background: '#1a1a2e',
    border: '1px solid #444',
    borderRadius: 3,
    color: '#ccc',
    fontSize: 12,
    fontFamily: 'inherit',
    padding: '6px 8px',
    outline: 'none',
    boxSizing: 'border-box',
  },
  evidenceRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    marginBottom: 4,
    background: '#1a1a2e',
    borderRadius: 3,
    padding: '4px 6px',
  },
  evidenceText: {
    flex: 1,
    fontSize: 11,
    lineHeight: 1.4,
    wordBreak: 'break-word',
  },
  evidenceAddRow: {
    display: 'flex',
    gap: 4,
    marginTop: 4,
  },
  evidenceInput: {
    flex: 1,
    minWidth: 0,
    background: '#1a1a2e',
    border: '1px solid #2a2a4a',
    borderRadius: 3,
    color: '#ccc',
    fontSize: 11,
    fontFamily: 'inherit',
    padding: '4px 6px',
    outline: 'none',
  },
  addBtn: {
    flexShrink: 0,
    background: 'transparent',
    border: 'none',
    color: '#7b68ee',
    fontSize: 16,
    lineHeight: 1,
    cursor: 'pointer',
    padding: '0 4px',
  },
  removeBtn: {
    flexShrink: 0,
    background: 'transparent',
    border: 'none',
    color: '#888',
    fontSize: 13,
    lineHeight: 1,
    cursor: 'pointer',
    padding: '0 2px',
  },
  statusOk: {
    marginTop: 6,
    fontSize: 11,
    color: '#6be16b',
  },
  statusError: {
    marginTop: 6,
    fontSize: 11,
    color: '#f87171',
    whiteSpace: 'pre-wrap',
  },
}
