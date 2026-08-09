/**
 * EditTab — palette of draggable function, variable, and constant nodes.
 *
 * Drag an item onto the canvas to place a new node.
 * The drag payload is JSON in the 'application/scistack-node' dataTransfer key:
 *   { nodeType: 'functionNode' | 'variableNode' | 'constantNode', label: string }
 */

import { useEffect, useState, useRef, useCallback } from 'react'
import { callBackend } from '../../api'
import { useBackendMessage } from '../../hooks/useBackendMessage'
import { useScope } from '../../context/ScopeContext'

interface Registry {
  functions: string[]
  variables: string[]
  matlab_functions?: string[]
  matlab_functions_mismatched?: string[]
}

interface PipelineInfo {
  pipeline_id: string
  name: string
}

interface HiddenPipelineInfo {
  pipeline_id: string
  name: string
  is_hypothesis: boolean
}

export default function EditTab() {
  const [registry, setRegistry] = useState<Registry>({ functions: [], variables: [] })
  const [constants, setConstants] = useState<string[]>([])
  const [addingConst, setAddingConst] = useState(false)
  const [constDraft, setConstDraft] = useState('')
  const constInputRef = useRef<HTMLInputElement>(null)

  const [pathInputs, setPathInputs] = useState<string[]>([])
  const [addingPI, setAddingPI] = useState(false)
  const [piDraft, setPiDraft] = useState('')
  const piInputRef = useRef<HTMLInputElement>(null)

  const [addingVar, setAddingVar] = useState(false)
  const [varDraft, setVarDraft] = useState('')
  const [varError, setVarError] = useState('')
  const [varSubmitting, setVarSubmitting] = useState(false)
  const varInputRef = useRef<HTMLInputElement>(null)

  // Nested pipelines: the scopes list + navigation state. Hypothesis-tagged
  // pipelines get their own tab strip (HypothesisTabs) — this list is
  // submodules only, so drag-onto-canvas here always means "place a
  // reusable submodule," never "place a whole hypothesis."
  const { currentScope, jumpTo, renameInPath, bumpGraph, graphVersion } = useScope()
  const [pipelines, setPipelines] = useState<PipelineInfo[]>([])
  const [hypothesisIds, setHypothesisIds] = useState<Set<string>>(new Set())
  const [hiddenPipelines, setHiddenPipelines] = useState<HiddenPipelineInfo[]>([])
  const [showHiddenPipelines, setShowHiddenPipelines] = useState(false)
  const [addingPipe, setAddingPipe] = useState(false)
  const [pipeDraft, setPipeDraft] = useState('')
  const [pipeError, setPipeError] = useState('')
  const [renamingPid, setRenamingPid] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const pipeInputRef = useRef<HTMLInputElement>(null)
  const renameInputRef = useRef<HTMLInputElement>(null)

  function fetchRegistry() {
    callBackend('get_registry')
      .then(d => setRegistry(d as Registry))
      .catch(console.error)
  }

  function fetchPipelines() {
    callBackend('list_pipelines')
      .then(d => setPipelines((d as { pipelines: PipelineInfo[] }).pipelines))
      .catch(console.error)
    callBackend('list_hypotheses')
      .then(d => setHypothesisIds(new Set(
        (d as { hypotheses: Array<{ pipeline_id: string }> }).hypotheses.map(h => h.pipeline_id)
      )))
      .catch(console.error)
  }

  function fetchHiddenPipelines() {
    callBackend('get_hidden_pipelines')
      .then(d => setHiddenPipelines((d as { pipelines: HiddenPipelineInfo[] }).pipelines))
      .catch(console.error)
  }

  const handleRestorePipeline = (pid: string) => {
    callBackend('unhide_pipeline', { pipeline_id: pid })
      .then(() => { setPipeError(''); fetchPipelines(); fetchHiddenPipelines() })
      .catch(err => setPipeError((err as Error).message))
  }

  useEffect(() => {
    fetchRegistry()
    fetchConstants()
    fetchPathInputs()
  }, [])

  // Scope mutations elsewhere (e.g. a use placed on the canvas) bump
  // graphVersion — keep the pipelines list in sync.
  useEffect(() => {
    fetchPipelines()
    fetchHiddenPipelines()
  }, [graphVersion])

  // Re-fetch registry when the backend signals a refresh (e.g. module reload).
  useBackendMessage(useCallback((msg) => {
    if (msg.type === 'dag_updated' || msg.method === 'dag_updated') {
      fetchRegistry()
      fetchPathInputs()
      fetchPipelines()
      fetchHiddenPipelines()
    }
  }, []))

  function fetchConstants() {
    callBackend('get_constants')
      .then(d => setConstants(d as string[]))
      .catch(console.error)
  }

  function fetchPathInputs() {
    callBackend('get_path_inputs')
      .then((items) => {
        const arr = items as Array<{ name: string }>
        setPathInputs(arr.map(i => i.name))
      })
      .catch(err => console.error('[PathInputs] fetch error:', err))
  }

  useEffect(() => {
    if (addingConst) constInputRef.current?.focus()
  }, [addingConst])

  useEffect(() => {
    if (addingPI) piInputRef.current?.focus()
  }, [addingPI])

  useEffect(() => {
    if (addingVar) varInputRef.current?.focus()
  }, [addingVar])

  useEffect(() => {
    if (addingPipe) pipeInputRef.current?.focus()
  }, [addingPipe])

  useEffect(() => {
    if (renamingPid) renameInputRef.current?.focus()
  }, [renamingPid])

  const commitConstDraft = () => {
    const name = constDraft.trim()
    if (name) {
      callBackend('create_constant', { name }).then(fetchConstants)
    }
    setConstDraft('')
    setAddingConst(false)
  }

  const commitVarDraft = () => {
    if (varSubmitting) return
    const name = varDraft.trim()
    if (!name) {
      setVarDraft('')
      setAddingVar(false)
      setVarError('')
      return
    }
    setVarSubmitting(true)
    callBackend('create_variable', { name })
      .then(data => {
        const d = data as { ok?: boolean; error?: string }
        if (d.ok) {
          setVarDraft('')
          setAddingVar(false)
          setVarError('')
        } else {
          setVarError(d.error || 'Failed')
          varInputRef.current?.focus()
        }
      })
      .catch(() => {
        setVarError('Request failed')
        varInputRef.current?.focus()
      })
      .finally(() => setVarSubmitting(false))
  }

  const commitPiDraft = () => {
    const name = piDraft.trim()
    if (name) {
      callBackend('create_path_input', { name })
        .then(() => fetchPathInputs())
        .catch(err => console.error('[PathInputs] create error:', err))
    }
    setPiDraft('')
    setAddingPI(false)
  }

  // Backend 400s (duplicate names, still-used or last-remaining hides)
  // carry a clear message — surface it verbatim under the section.
  const commitPipeDraft = () => {
    const name = pipeDraft.trim()
    if (name) {
      callBackend('create_pipeline', { name })
        .then(() => { setPipeError(''); fetchPipelines() })
        .catch(err => setPipeError((err as Error).message))
    }
    setPipeDraft('')
    setAddingPipe(false)
  }

  const commitRename = () => {
    const pid = renamingPid
    const name = renameDraft.trim()
    setRenamingPid(null)
    setRenameDraft('')
    if (!pid || !name) return
    callBackend('rename_pipeline', { pipeline_id: pid, name })
      .then(() => {
        setPipeError('')
        fetchPipelines()
        renameInPath(pid, name)
        bumpGraph()  // pipelineNode labels on parent canvases change
      })
      .catch(err => setPipeError((err as Error).message))
  }

  const handleDeletePipeline = (pid: string) => {
    callBackend('delete_pipeline', { pipeline_id: pid })
      .then(() => {
        setPipeError('')
        fetchPipelines()
        fetchHiddenPipelines()
        if (pid === currentScope) {
          // Land on whatever pipeline is left, not a hardcoded 'main' —
          // 'main' itself may now be hidden.
          const remaining = pipelines.find(p => p.pipeline_id !== pid)
          if (remaining) jumpTo(remaining.pipeline_id, remaining.name)
        } else {
          bumpGraph()
        }
      })
      .catch(err => setPipeError((err as Error).message))
  }

  const onPipelineDragStart = (e: React.DragEvent, p: PipelineInfo) => {
    e.dataTransfer.setData('application/scistack-pipeline', JSON.stringify(p))
    e.dataTransfer.effectAllowed = 'move'
  }

  const onDragStart = (
    e: React.DragEvent,
    nodeType: 'functionNode' | 'variableNode' | 'constantNode' | 'pathInputNode',
    label: string,
  ) => {
    e.dataTransfer.setData(
      'application/scistack-node',
      JSON.stringify({ nodeType, label }),
    )
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div style={styles.root}>
      <Section
        title="Submodules"
        action={
          <button style={styles.addBtn} onClick={() => setAddingPipe(true)} title="New submodule">
            +
          </button>
        }
      >
        {pipelines.filter(p => !hypothesisIds.has(p.pipeline_id)).map(p => (
          renamingPid === p.pipeline_id ? (
            <input
              key={p.pipeline_id}
              ref={renameInputRef}
              style={styles.draftInput}
              value={renameDraft}
              onChange={e => setRenameDraft(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') commitRename()
                if (e.key === 'Escape') { setRenamingPid(null); setRenameDraft('') }
              }}
              onBlur={commitRename}
            />
          ) : (
            <div
              key={p.pipeline_id}
              draggable
              onDragStart={e => onPipelineDragStart(e, p)}
              onClick={() => jumpTo(p.pipeline_id, p.name)}
              style={{
                ...styles.item,
                borderLeftColor: '#a21caf',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                ...(p.pipeline_id === currentScope ? styles.pipelineCurrent : {}),
              }}
              title={p.pipeline_id === currentScope
                ? 'Current scope'
                : 'Click to open; drag onto the canvas to place as a node'}
            >
              <span style={{ flex: 1 }}>⧉ {p.name}</span>
              {p.pipeline_id !== 'main' && (
                <>
                  <button
                    style={styles.rowBtn}
                    title="Rename pipeline"
                    onClick={e => {
                      e.stopPropagation()
                      setRenamingPid(p.pipeline_id)
                      setRenameDraft(p.name)
                    }}
                  >
                    ✎
                  </button>
                  <button
                    style={styles.rowBtn}
                    title="Delete pipeline"
                    onClick={e => {
                      e.stopPropagation()
                      handleDeletePipeline(p.pipeline_id)
                    }}
                  >
                    ×
                  </button>
                </>
              )}
            </div>
          )
        ))}
        {addingPipe && (
          <input
            ref={pipeInputRef}
            style={styles.draftInput}
            value={pipeDraft}
            placeholder="submodule name…"
            onChange={e => setPipeDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') commitPipeDraft()
              if (e.key === 'Escape') { setPipeDraft(''); setAddingPipe(false) }
            }}
            onBlur={commitPipeDraft}
          />
        )}
        {pipeError && (
          <div style={styles.errorText}>{pipeError}</div>
        )}
        {(() => {
          const hiddenSubmodules = hiddenPipelines.filter(p => !p.is_hypothesis)
          if (hiddenSubmodules.length === 0) return null
          return (
            <div style={styles.hiddenWrap}>
              <button
                style={styles.hiddenToggle}
                onClick={() => setShowHiddenPipelines(v => !v)}
                type="button"
              >
                {showHiddenPipelines
                  ? 'hide'
                  : `${hiddenSubmodules.length} hidden — show`}
              </button>
              {showHiddenPipelines && hiddenSubmodules.map(p => (
                <div key={p.pipeline_id} style={styles.hiddenRow}>
                  <span style={{ flex: 1 }}>{p.name}</span>
                  <button
                    style={styles.rowBtn}
                    onClick={() => handleRestorePipeline(p.pipeline_id)}
                    title="Restore this submodule"
                  >
                    restore
                  </button>
                </div>
              ))}
            </div>
          )
        })()}
      </Section>
      <Section title="Functions">
        {[...registry.functions, ...(registry.matlab_functions ?? [])].map(fn => {
          const mismatch = registry.matlab_functions_mismatched?.includes(fn)
          const displayLabel = mismatch ? `${fn} (function/file name mismatch)` : fn
          return (
            <DragItem
              key={fn}
              label={displayLabel}
              color="#7b68ee"
              onDragStart={e => onDragStart(e, 'functionNode', fn)}
            />
          )
        })}
      </Section>
      <Section
        title="Variables"
        action={
          <button style={styles.addBtn} onClick={() => setAddingVar(true)} title="New variable type">
            +
          </button>
        }
      >
        {registry.variables.map(v => (
          <DragItem
            key={v}
            label={v}
            color="#2a9d8f"
            onDragStart={e => onDragStart(e, 'variableNode', v)}
          />
        ))}
        {addingVar && (
          <>
            <input
              ref={varInputRef}
              style={styles.draftInput}
              value={varDraft}
              placeholder="VariableName…"
              onChange={e => { setVarDraft(e.target.value); setVarError('') }}
              onKeyDown={e => {
                if (e.key === 'Enter') commitVarDraft()
                if (e.key === 'Escape') { setVarDraft(''); setAddingVar(false); setVarError('') }
              }}
              onBlur={commitVarDraft}
            />
            {varError && (
              <div style={styles.errorText}>{varError}</div>
            )}
          </>
        )}
      </Section>
      <Section
        title="Constants"
        action={
          <button style={styles.addBtn} onClick={() => setAddingConst(true)} title="New constant">
            +
          </button>
        }
      >
        {constants.map(c => (
          <DragItem
            key={c}
            label={c}
            color="#2a9d8f"
            onDragStart={e => onDragStart(e, 'constantNode', c)}
          />
        ))}
        {addingConst && (
          <input
            ref={constInputRef}
            style={styles.draftInput}
            value={constDraft}
            placeholder="constant name…"
            onChange={e => setConstDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') commitConstDraft()
              if (e.key === 'Escape') { setConstDraft(''); setAddingConst(false) }
            }}
            onBlur={commitConstDraft}
          />
        )}
      </Section>
      <Section
        title="Path Inputs"
        action={
          <button style={styles.addBtn} onClick={() => setAddingPI(true)} title="New path input">
            +
          </button>
        }
      >
        {pathInputs.map(p => (
          <DragItem
            key={p}
            label={p}
            color="#d97706"
            onDragStart={e => onDragStart(e, 'pathInputNode', p)}
          />
        ))}
        {addingPI && (
          <input
            ref={piInputRef}
            style={styles.draftInput}
            value={piDraft}
            placeholder="param name…"
            onChange={e => setPiDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') commitPiDraft()
              if (e.key === 'Escape') { setPiDraft(''); setAddingPI(false) }
            }}
            onBlur={commitPiDraft}
          />
        )}
      </Section>
    </div>
  )
}

function Section({
  title,
  children,
  action,
}: {
  title: string
  children: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <span style={styles.sectionTitle}>{title}</span>
        {action}
      </div>
      {children}
    </div>
  )
}

function DragItem({
  label,
  color,
  onDragStart,
}: {
  label: string
  color: string
  onDragStart: (e: React.DragEvent) => void
}) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      style={{ ...styles.item, borderLeftColor: color }}
    >
      {label}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    padding: '4px 0',
  },
  section: {
    marginBottom: 8,
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    padding: '6px 12px 4px',
  },
  sectionTitle: {
    flex: 1,
    fontSize: 11,
    fontWeight: 700,
    color: '#666',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  addBtn: {
    background: 'transparent',
    border: 'none',
    color: '#7b68ee',
    fontSize: 18,
    lineHeight: 1,
    cursor: 'pointer',
    padding: '0 2px',
  },
  draftInput: {
    display: 'block',
    width: 'calc(100% - 24px)',
    margin: '2px 12px',
    background: '#1a1a2e',
    border: '1px solid #7b68ee',
    borderRadius: 3,
    color: '#ccc',
    fontSize: 12,
    fontFamily: 'monospace',
    padding: '4px 6px',
    outline: 'none',
    boxSizing: 'border-box',
  },
  item: {
    padding: '5px 12px',
    fontSize: 12,
    fontFamily: 'monospace',
    color: '#ccc',
    borderLeft: '3px solid',
    cursor: 'grab',
    userSelect: 'none',
  },
  errorText: {
    padding: '2px 12px',
    fontSize: 11,
    color: '#f87171',
  },
  pipelineCurrent: {
    background: '#2a2a4a',
    color: '#fff',
  },
  rowBtn: {
    flexShrink: 0,
    background: 'transparent',
    border: 'none',
    color: '#888',
    fontSize: 12,
    lineHeight: 1,
    cursor: 'pointer',
    padding: '0 2px',
  },
  hiddenWrap: {
    marginTop: 4,
  },
  hiddenToggle: {
    background: 'transparent',
    border: 'none',
    color: '#666',
    fontSize: 11,
    cursor: 'pointer',
    padding: '4px 0',
  },
  hiddenRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    fontSize: 11,
    color: '#aaa',
    padding: '2px 0',
  },
}
