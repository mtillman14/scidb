/**
 * HypothesisTabs — top-level tab strip, one tab per hypothesis pipeline.
 *
 * A hypothesis is not a separate structure — it's a pipeline (see
 * ScopeContext/pipeline_store.py's nested-pipeline scopes) tagged with
 * research-question/evidence metadata. 'main' is simply the default
 * hypothesis, a sibling to every other one, not a special scratch scope.
 *
 * Switching tabs is exactly ScopeContext's existing `jumpTo` (resets the
 * breadcrumb to that pipeline's root) — no new navigation state needed.
 * A tab reads as "current" whenever the breadcrumb's ROOT is that
 * hypothesis, so it stays highlighted while the user has descended into
 * one of its submodules.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { callBackend } from '../api'
import { useBackendMessage } from '../hooks/useBackendMessage'
import { useScope } from '../context/ScopeContext'

export interface HypothesisInfo {
  pipeline_id: string
  name: string
  research_question: string
  hypothesis_statement: string
  evidence_for: string[]
  evidence_against: string[]
}

export default function HypothesisTabs() {
  const { breadcrumb, jumpTo, renameInPath, bumpGraph } = useScope()
  const [hypotheses, setHypotheses] = useState<HypothesisInfo[]>([])
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const [renamingPid, setRenamingPid] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [duplicatingPid, setDuplicatingPid] = useState<string | null>(null)
  const [duplicateDraft, setDuplicateDraft] = useState('')
  const addInputRef = useRef<HTMLInputElement>(null)
  const renameInputRef = useRef<HTMLInputElement>(null)
  const duplicateInputRef = useRef<HTMLInputElement>(null)

  const fetchHypotheses = useCallback(() => {
    callBackend('list_hypotheses')
      .then(d => setHypotheses((d as { hypotheses: HypothesisInfo[] }).hypotheses))
      .catch(console.error)
  }, [])

  useEffect(() => { fetchHypotheses() }, [fetchHypotheses])

  useBackendMessage(useCallback((msg) => {
    if (msg.type === 'dag_updated' || msg.method === 'dag_updated') fetchHypotheses()
  }, [fetchHypotheses]))

  useEffect(() => {
    if (adding) addInputRef.current?.focus()
  }, [adding])

  useEffect(() => {
    if (renamingPid) renameInputRef.current?.focus()
  }, [renamingPid])

  useEffect(() => {
    if (duplicatingPid) duplicateInputRef.current?.focus()
  }, [duplicatingPid])

  const commitDraft = () => {
    const name = draft.trim()
    if (name) {
      callBackend('create_hypothesis', { name })
        .then((d) => {
          setError('')
          fetchHypotheses()
          const r = d as { pipeline_id: string; name: string }
          jumpTo(r.pipeline_id, r.name)
        })
        .catch(err => setError((err as Error).message))
    }
    setDraft('')
    setAdding(false)
  }

  const commitRename = () => {
    const pid = renamingPid
    const name = renameDraft.trim()
    setRenamingPid(null)
    setRenameDraft('')
    if (!pid || !name) return
    callBackend('rename_pipeline', { pipeline_id: pid, name })
      .then(() => {
        setError('')
        fetchHypotheses()
        renameInPath(pid, name)
        bumpGraph()
      })
      .catch(err => setError((err as Error).message))
  }

  const commitDuplicate = () => {
    const pid = duplicatingPid
    const name = duplicateDraft.trim()
    setDuplicatingPid(null)
    setDuplicateDraft('')
    if (!pid || !name) return
    callBackend('duplicate_hypothesis', { pipeline_id: pid, name })
      .then((d) => {
        setError('')
        fetchHypotheses()
        const r = d as { pipeline_id: string }
        jumpTo(r.pipeline_id, name)
      })
      .catch(err => setError((err as Error).message))
  }

  const handleDelete = (pid: string) => {
    callBackend('delete_hypothesis', { pipeline_id: pid })
      .then(() => {
        setError('')
        fetchHypotheses()
        if (pid === rootPipelineId) jumpTo('main', 'main')
        else bumpGraph()
      })
      .catch(err => setError((err as Error).message))
  }

  // A tab reads as "current" whenever the breadcrumb's root is that
  // hypothesis — stays highlighted while descended into a submodule.
  const rootPipelineId = breadcrumb[0].pipeline_id

  return (
    <div style={styles.root}>
      {hypotheses.map(h => (
        renamingPid === h.pipeline_id ? (
          <input
            key={h.pipeline_id}
            ref={renameInputRef}
            style={styles.renameInput}
            value={renameDraft}
            onChange={e => setRenameDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') commitRename()
              if (e.key === 'Escape') { setRenamingPid(null); setRenameDraft('') }
            }}
            onBlur={commitRename}
          />
        ) : duplicatingPid === h.pipeline_id ? (
          <input
            key={h.pipeline_id}
            ref={duplicateInputRef}
            style={styles.renameInput}
            value={duplicateDraft}
            placeholder={`${h.name} copy…`}
            onChange={e => setDuplicateDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') commitDuplicate()
              if (e.key === 'Escape') { setDuplicatingPid(null); setDuplicateDraft('') }
            }}
            onBlur={commitDuplicate}
          />
        ) : (
          <div
            key={h.pipeline_id}
            style={h.pipeline_id === rootPipelineId ? styles.tabActive : styles.tab}
            title={h.research_question || h.name}
          >
            <span onClick={() => jumpTo(h.pipeline_id, h.name)} style={styles.tabLabel}>
              {h.name}
            </span>
            <span style={styles.tabActions}>
              <button
                style={styles.rowBtn}
                title="Duplicate this hypothesis into a new tab (e.g. gait symmetry -> gait speed)"
                onClick={() => { setDuplicatingPid(h.pipeline_id); setDuplicateDraft(`${h.name} copy`) }}
              >
                ⎘
              </button>
              {h.pipeline_id !== 'main' && (
                <>
                  <button
                    style={styles.rowBtn}
                    title="Rename hypothesis"
                    onClick={() => { setRenamingPid(h.pipeline_id); setRenameDraft(h.name) }}
                  >
                    ✎
                  </button>
                  <button
                    style={styles.rowBtn}
                    title="Delete hypothesis"
                    onClick={() => handleDelete(h.pipeline_id)}
                  >
                    ×
                  </button>
                </>
              )}
            </span>
          </div>
        )
      ))}
      {adding ? (
        <input
          ref={addInputRef}
          style={styles.renameInput}
          value={draft}
          placeholder="hypothesis name…"
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') commitDraft()
            if (e.key === 'Escape') { setDraft(''); setAdding(false) }
          }}
          onBlur={commitDraft}
        />
      ) : (
        <button style={styles.addTab} onClick={() => setAdding(true)} title="New hypothesis">
          + new hypothesis
        </button>
      )}
      {error && <span style={styles.errorText}>{error}</span>}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    display: 'flex',
    alignItems: 'center',
    gap: 2,
    padding: '0 12px',
    background: '#15152e',
    borderBottom: '1px solid #2a2a4a',
    flexShrink: 0,
    overflowX: 'auto',
  },
  tab: {
    display: 'flex',
    alignItems: 'center',
    padding: '0 4px 0 14px',
    borderBottom: '2px solid transparent',
    color: '#888',
    fontSize: 13,
    fontWeight: 500,
    whiteSpace: 'nowrap',
  },
  tabActive: {
    display: 'flex',
    alignItems: 'center',
    padding: '0 4px 0 14px',
    borderBottom: '2px solid #7b68ee',
    color: '#fff',
    fontSize: 13,
    fontWeight: 600,
    whiteSpace: 'nowrap',
  },
  tabLabel: {
    padding: '8px 6px 8px 0',
    cursor: 'pointer',
  },
  tabActions: {
    display: 'flex',
    alignItems: 'center',
  },
  addTab: {
    padding: '8px 10px',
    background: 'transparent',
    border: 'none',
    color: '#666',
    fontSize: 12,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  renameInput: {
    background: '#1a1a2e',
    border: '1px solid #7b68ee',
    borderRadius: 3,
    color: '#ccc',
    fontSize: 12,
    fontFamily: 'monospace',
    padding: '4px 6px',
    outline: 'none',
    margin: '4px 0',
  },
  errorText: {
    fontSize: 11,
    color: '#f87171',
    marginLeft: 8,
  },
  rowBtn: {
    flexShrink: 0,
    background: 'transparent',
    border: 'none',
    color: '#888',
    fontSize: 12,
    lineHeight: 1,
    cursor: 'pointer',
    padding: '4px 2px',
  },
}
