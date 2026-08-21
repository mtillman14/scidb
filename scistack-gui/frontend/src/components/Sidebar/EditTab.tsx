/**
 * EditTab — palette of draggable function, variable, constant, path-input,
 * and sweep nodes.
 *
 * Drag an item onto the canvas to place a new node.
 * The drag payload is JSON in the 'application/scistack-node' dataTransfer key:
 *   { nodeType: 'functionNode' | 'variableNode' | 'constantNode' | 'pathInputNode' | 'sweepNode', label: string }
 *
 * The six categories (Submodules, Functions, Variables, Constants, Path
 * Inputs, Sweeps) are shown one at a time behind an icon tab strip rather
 * than stacked — there's a lot of ground to cover in a narrow sidebar.
 * Clicking (not dragging) a list item selects it and opens the info panel
 * docked to the bottom of the sidebar: a read-only signature+docstring for
 * functions, or a free-text notes textarea (persisted server-side, see
 * layout.py's read_notes/write_note) for everything else. The selection
 * lives in SidebarSelectionContext so the canvas (PipelineDAG's
 * onPaneClick) can clear it too.
 */

import { useEffect, useState, useRef, useCallback } from 'react'
import { callBackend } from '../../api'
import { useBackendMessage } from '../../hooks/useBackendMessage'
import { useScope } from '../../context/ScopeContext'
import { useSidebarSelection } from '../../context/SidebarSelectionContext'
import type { SidebarItemKind, SidebarSelectedItem } from '../../context/SidebarSelectionContext'

interface LoadError {
  source: string
  error: string
}

interface Registry {
  functions: string[]
  variables: string[]
  matlab_functions?: string[]
  matlab_functions_mismatched?: string[]
  load_errors?: LoadError[]
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

interface TabDef {
  id: SidebarItemKind
  icon: string
  label: string
}

const TABS: TabDef[] = [
  { id: 'submodule', icon: '⧉', label: 'Submodules' },
  { id: 'function', icon: 'f(x)', label: 'Functions' },
  { id: 'variable', icon: 'x', label: 'Variables' },
  { id: 'constant', icon: 'C', label: 'Constants' },
  { id: 'pathInput', icon: '📁', label: 'Path Inputs' },
  { id: 'sweep', icon: '🧹', label: 'Sweeps' },
]

export default function EditTab() {
  const [activeTab, setActiveTab] = useState<TabDef['id']>('submodule')
  const { selectedItem, setSelectedItem } = useSidebarSelection()

  const selectTab = (tab: TabDef['id']) => {
    setActiveTab(tab)
    setSelectedItem(null)
  }

  const [registry, setRegistry] = useState<Registry>({ functions: [], variables: [] })
  // discoveryError is the request itself failing (network/RPC error) — a
  // real problem, shown here as a banner. registry.load_errors (some
  // module/file failing to import server-side) is NOT shown here: in
  // loose-script/folder-scan mode it's routinely full of framework/example
  // files that were never meant to be pipeline code, so surfacing it as an
  // always-on red banner reads as a process failure when it usually isn't.
  // It's still fully visible, per-module, in 📁 Paths → Discovered Code
  // (components/Sidebar/ProjectConfigPanel.tsx) for when it's worth digging into.
  const [discoveryError, setDiscoveryError] = useState('')
  const [constants, setConstants] = useState<string[]>([])
  const [addingConst, setAddingConst] = useState(false)
  const [constDraft, setConstDraft] = useState('')
  const constInputRef = useRef<HTMLInputElement>(null)

  const [pathInputs, setPathInputs] = useState<string[]>([])
  const [addingPI, setAddingPI] = useState(false)
  const [piDraft, setPiDraft] = useState('')
  const [piError, setPiError] = useState('')
  const [piSubmitting, setPiSubmitting] = useState(false)
  const piInputRef = useRef<HTMLInputElement>(null)

  const [sweeps, setSweeps] = useState<string[]>([])
  const [addingSweep, setAddingSweep] = useState(false)
  const [sweepDraft, setSweepDraft] = useState('')
  const [sweepError, setSweepError] = useState('')
  const [sweepSubmitting, setSweepSubmitting] = useState(false)
  const sweepInputRef = useRef<HTMLInputElement>(null)

  const [addingVar, setAddingVar] = useState(false)
  const [varDraft, setVarDraft] = useState('')
  const [varError, setVarError] = useState('')
  const [varSubmitting, setVarSubmitting] = useState(false)
  const varInputRef = useRef<HTMLInputElement>(null)

  // Manual built-in/library function reference (numpy.mean, a MATLAB
  // builtin, ...) — distinct from auto-discovered functions above.
  const [addingBuiltin, setAddingBuiltin] = useState(false)
  const [builtinLang, setBuiltinLang] = useState<'python' | 'matlab'>('python')
  const [builtinDraft, setBuiltinDraft] = useState('')
  const [builtinError, setBuiltinError] = useState('')
  const [builtinSubmitting, setBuiltinSubmitting] = useState(false)
  const builtinInputRef = useRef<HTMLInputElement>(null)

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

  // Free-text notes (everything except functions) — fetched once, updated
  // locally after each successful save so the textarea doesn't flash.
  const [notes, setNotes] = useState<Record<string, string>>({})
  const fetchNotes = useCallback(() => {
    callBackend('get_notes')
      .then(d => setNotes(d as Record<string, string>))
      .catch(console.error)
  }, [])

  function fetchRegistry() {
    callBackend('get_registry')
      .then(d => { setRegistry(d as Registry); setDiscoveryError('') })
      .catch(err => {
        console.error(err)
        setDiscoveryError(`Failed to load functions/variables: ${(err as Error).message}`)
      })
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
    fetchSweeps()
    fetchNotes()
  }, [fetchNotes])

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
      fetchSweeps()
      fetchPipelines()
      fetchHiddenPipelines()
    }
  }, []))

  function fetchConstants() {
    callBackend('get_constants')
      .then(d => setConstants(d as string[]))
      .catch(err => {
        console.error(err)
        setDiscoveryError(`Failed to load constants: ${(err as Error).message}`)
      })
  }

  function fetchPathInputs() {
    callBackend('get_path_inputs')
      .then((items) => {
        const arr = items as Array<{ name: string }>
        setPathInputs(arr.map(i => i.name))
      })
      .catch(err => {
        console.error('[PathInputs] fetch error:', err)
        setDiscoveryError(`Failed to load path inputs: ${(err as Error).message}`)
      })
  }

  function fetchSweeps() {
    callBackend('get_sweeps')
      .then((items) => {
        const arr = items as Array<{ name: string }>
        setSweeps(arr.map(i => i.name))
      })
      .catch(err => {
        console.error('[Sweeps] fetch error:', err)
        setDiscoveryError(`Failed to load sweeps: ${(err as Error).message}`)
      })
  }

  useEffect(() => {
    if (addingConst) constInputRef.current?.focus()
  }, [addingConst])

  useEffect(() => {
    if (addingPI) piInputRef.current?.focus()
  }, [addingPI])

  useEffect(() => {
    if (addingSweep) sweepInputRef.current?.focus()
  }, [addingSweep])

  useEffect(() => {
    if (addingVar) varInputRef.current?.focus()
  }, [addingVar])

  useEffect(() => {
    if (addingBuiltin) builtinInputRef.current?.focus()
  }, [addingBuiltin])

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

  const commitBuiltinDraft = () => {
    if (builtinSubmitting) return
    const reference = builtinDraft.trim()
    if (!reference) {
      setBuiltinDraft('')
      setAddingBuiltin(false)
      setBuiltinError('')
      return
    }
    setBuiltinSubmitting(true)
    callBackend('create_builtin_function', { language: builtinLang, reference })
      .then(data => {
        const d = data as { ok?: boolean; error?: string }
        if (d.ok) {
          setBuiltinDraft('')
          setAddingBuiltin(false)
          setBuiltinError('')
          fetchRegistry()
        } else {
          setBuiltinError(d.error || 'Failed')
          builtinInputRef.current?.focus()
        }
      })
      .catch(() => {
        setBuiltinError('Request failed')
        builtinInputRef.current?.focus()
      })
      .finally(() => setBuiltinSubmitting(false))
  }

  const commitPiDraft = () => {
    if (piSubmitting) return
    const name = piDraft.trim()
    if (!name) {
      setPiDraft('')
      setAddingPI(false)
      setPiError('')
      return
    }
    setPiSubmitting(true)
    callBackend('create_path_input', { name })
      .then(data => {
        const d = data as { ok?: boolean; error?: string }
        if (d.ok !== false) {
          setPiDraft('')
          setAddingPI(false)
          setPiError('')
          fetchPathInputs()
        } else {
          setPiError(d.error || 'Failed')
          piInputRef.current?.focus()
        }
      })
      .catch(err => {
        setPiError((err as Error).message || 'Request failed')
        piInputRef.current?.focus()
      })
      .finally(() => setPiSubmitting(false))
  }

  const commitSweepDraft = () => {
    if (sweepSubmitting) return
    const name = sweepDraft.trim()
    if (!name) {
      setSweepDraft('')
      setAddingSweep(false)
      setSweepError('')
      return
    }
    setSweepSubmitting(true)
    callBackend('create_sweep', { name })
      .then(data => {
        const d = data as { ok?: boolean; error?: string }
        if (d.ok !== false) {
          setSweepDraft('')
          setAddingSweep(false)
          setSweepError('')
          fetchSweeps()
        } else {
          setSweepError(d.error || 'Failed')
          sweepInputRef.current?.focus()
        }
      })
      .catch(err => {
        setSweepError((err as Error).message || 'Request failed')
        sweepInputRef.current?.focus()
      })
      .finally(() => setSweepSubmitting(false))
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
    nodeType: 'functionNode' | 'variableNode' | 'constantNode' | 'pathInputNode' | 'sweepNode',
    label: string,
  ) => {
    e.dataTransfer.setData(
      'application/scistack-node',
      JSON.stringify({ nodeType, label }),
    )
    e.dataTransfer.effectAllowed = 'move'
  }

  const selectListItem = (kind: SidebarItemKind, name: string, displayLabel?: string) => {
    setSelectedItem({ kind, name, displayLabel })
  }

  return (
    <div style={styles.root}>
      <div style={styles.tabStrip}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            type="button"
            onClick={() => selectTab(tab.id)}
            style={{
              ...styles.tabBtn,
              ...(activeTab === tab.id ? styles.tabBtnActive : {}),
            }}
          >
            <span style={styles.tabIcon}>{tab.icon}</span>
            <span style={styles.tabLabel}>{tab.label}</span>
          </button>
        ))}
      </div>
      <div style={styles.content}>
        {discoveryError && <div style={styles.errorBanner}>{discoveryError}</div>}
        {activeTab === 'submodule' && (
          <Section
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
                  onClick={() => {
                    jumpTo(p.pipeline_id, p.name)
                    selectListItem('submodule', p.pipeline_id, p.name)
                  }}
                  style={{
                    ...styles.item,
                    borderLeftColor: '#a21caf',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    ...(p.pipeline_id === currentScope ? styles.pipelineCurrent : {}),
                    ...(selectedItem?.kind === 'submodule' && selectedItem.name === p.pipeline_id ? styles.itemSelected : {}),
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
        )}
        {activeTab === 'function' && (
          <Section
            action={
              <button
                style={styles.addBtn}
                onClick={() => setAddingBuiltin(true)}
                title="Add a built-in/library function you didn't write yourself (e.g. numpy.mean, or a MATLAB command)"
              >
                +
              </button>
            }
          >
            {[...registry.functions, ...(registry.matlab_functions ?? [])].map(fn => {
              const mismatch = registry.matlab_functions_mismatched?.includes(fn)
              const displayLabel = mismatch ? `${fn} (function/file name mismatch)` : fn
              return (
                <DragItem
                  key={fn}
                  label={displayLabel}
                  color="#7b68ee"
                  selected={selectedItem?.kind === 'function' && selectedItem.name === fn}
                  onDragStart={e => onDragStart(e, 'functionNode', fn)}
                  onClick={() => selectListItem('function', fn)}
                />
              )
            })}
            {addingBuiltin && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ display: 'flex', gap: 4 }}>
                  <select
                    value={builtinLang}
                    onChange={e => {
                      setBuiltinLang(e.target.value as 'python' | 'matlab')
                      setBuiltinError('')
                    }}
                    style={{ fontSize: 12 }}
                  >
                    <option value="python">Python</option>
                    <option value="matlab">MATLAB</option>
                  </select>
                  <input
                    ref={builtinInputRef}
                    style={{ ...styles.draftInput, flex: 1 }}
                    value={builtinDraft}
                    placeholder={builtinLang === 'python' ? 'numpy.mean' : 'mean'}
                    onChange={e => { setBuiltinDraft(e.target.value); setBuiltinError('') }}
                    onKeyDown={e => {
                      if (e.key === 'Enter') commitBuiltinDraft()
                      if (e.key === 'Escape') {
                        setBuiltinDraft('')
                        setAddingBuiltin(false)
                        setBuiltinError('')
                      }
                    }}
                  />
                </div>
                {builtinSubmitting && (
                  <div style={{ ...styles.errorText, color: '#999' }}>
                    {builtinLang === 'matlab' ? 'Validating with MATLAB…' : 'Validating…'}
                  </div>
                )}
                {!builtinSubmitting && builtinError && (
                  <div style={styles.errorText}>{builtinError}</div>
                )}
              </div>
            )}
          </Section>
        )}
        {activeTab === 'variable' && (
          <Section
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
                selected={selectedItem?.kind === 'variable' && selectedItem.name === v}
                onDragStart={e => onDragStart(e, 'variableNode', v)}
                onClick={() => selectListItem('variable', v)}
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
        )}
        {activeTab === 'constant' && (
          <Section
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
                selected={selectedItem?.kind === 'constant' && selectedItem.name === c}
                onDragStart={e => onDragStart(e, 'constantNode', c)}
                onClick={() => selectListItem('constant', c)}
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
        )}
        {activeTab === 'pathInput' && (
          <Section
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
                selected={selectedItem?.kind === 'pathInput' && selectedItem.name === p}
                onDragStart={e => onDragStart(e, 'pathInputNode', p)}
                onClick={() => selectListItem('pathInput', p)}
              />
            ))}
            {addingPI && (
              <>
                <input
                  ref={piInputRef}
                  style={styles.draftInput}
                  value={piDraft}
                  placeholder="param name…"
                  onChange={e => { setPiDraft(e.target.value); setPiError('') }}
                  onKeyDown={e => {
                    if (e.key === 'Enter') commitPiDraft()
                    if (e.key === 'Escape') { setPiDraft(''); setAddingPI(false); setPiError('') }
                  }}
                  onBlur={commitPiDraft}
                />
                {piError && (
                  <div style={styles.errorText}>{piError}</div>
                )}
              </>
            )}
          </Section>
        )}
        {activeTab === 'sweep' && (
          <Section
            action={
              <button style={styles.addBtn} onClick={() => setAddingSweep(true)} title="New parameter sweep">
                +
              </button>
            }
          >
            {sweeps.map(s => (
              <DragItem
                key={s}
                label={s}
                color="#65a30d"
                selected={selectedItem?.kind === 'sweep' && selectedItem.name === s}
                onDragStart={e => onDragStart(e, 'sweepNode', s)}
                onClick={() => selectListItem('sweep', s)}
              />
            ))}
            {addingSweep && (
              <>
                <input
                  ref={sweepInputRef}
                  style={styles.draftInput}
                  value={sweepDraft}
                  placeholder="param name…"
                  onChange={e => { setSweepDraft(e.target.value); setSweepError('') }}
                  onKeyDown={e => {
                    if (e.key === 'Enter') commitSweepDraft()
                    if (e.key === 'Escape') { setSweepDraft(''); setAddingSweep(false); setSweepError('') }
                  }}
                  onBlur={commitSweepDraft}
                />
                {sweepError && (
                  <div style={styles.errorText}>{sweepError}</div>
                )}
              </>
            )}
          </Section>
        )}
      </div>
      {selectedItem && (
        <ItemInfoPanel
          item={selectedItem}
          notes={notes}
          onNoteSaved={(key, text) => setNotes(prev => ({ ...prev, [key]: text }))}
          onClose={() => setSelectedItem(null)}
        />
      )}
    </div>
  )
}

/** Composite key into the notes dict — mirrors layout.py's write_note. */
function noteKey(item: SidebarSelectedItem): string {
  return `${item.kind}:${item.name}`
}

function ItemInfoPanel({
  item,
  notes,
  onNoteSaved,
  onClose,
}: {
  item: SidebarSelectedItem
  notes: Record<string, string>
  onNoteSaved: (key: string, text: string) => void
  onClose: () => void
}) {
  const displayName = item.displayLabel ?? item.name
  const key = noteKey(item)

  return (
    <div style={styles.infoPanel}>
      <div style={styles.infoPanelHeader}>
        <span style={styles.infoPanelTitle}>{displayName}</span>
        <button style={styles.rowBtn} title="Close" onClick={onClose}>×</button>
      </div>
      <div style={styles.infoPanelBody}>
        {item.kind === 'function'
          ? <FunctionDocView fnName={item.name} />
          : <NoteEditor itemKey={key} initialText={notes[key] ?? ''} onSaved={onNoteSaved} />}
      </div>
    </div>
  )
}

interface FunctionDoc {
  ok: boolean
  language?: 'python' | 'matlab'
  signature?: string
  docstring?: string | null
  error?: string
}

function FunctionDocView({ fnName }: { fnName: string }) {
  const [doc, setDoc] = useState<FunctionDoc | null>(null)

  useEffect(() => {
    let cancelled = false
    setDoc(null)
    callBackend('get_function_doc', { name: fnName })
      .then(d => { if (!cancelled) setDoc(d as FunctionDoc) })
      .catch(err => { if (!cancelled) setDoc({ ok: false, error: (err as Error).message }) })
    return () => { cancelled = true }
  }, [fnName])

  if (!doc) return <div style={styles.infoMuted}>Loading…</div>
  if (!doc.ok) return <div style={styles.errorText}>{doc.error}</div>
  return (
    <>
      <div style={styles.signature}>{doc.signature}</div>
      <div style={styles.docstring}>{doc.docstring || <span style={styles.infoMuted}>No docstring available.</span>}</div>
    </>
  )
}

function NoteEditor({
  itemKey,
  initialText,
  onSaved,
}: {
  itemKey: string
  initialText: string
  onSaved: (key: string, text: string) => void
}) {
  const [draft, setDraft] = useState(initialText)

  // Re-sync when a different item (different key) is selected.
  useEffect(() => {
    setDraft(initialText)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemKey])

  const commit = () => {
    if (draft === initialText) return
    callBackend('set_note', { key: itemKey, text: draft })
      .then(() => onSaved(itemKey, draft))
      .catch(console.error)
  }

  return (
    <textarea
      style={styles.noteTextarea}
      value={draft}
      placeholder="Notes…"
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
    />
  )
}

function Section({
  children,
  action,
}: {
  children: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <div style={styles.section}>
      {action && <div style={styles.sectionHeader}>{action}</div>}
      {children}
    </div>
  )
}

function DragItem({
  label,
  color,
  selected,
  onDragStart,
  onClick,
}: {
  label: string
  color: string
  selected?: boolean
  onDragStart: (e: React.DragEvent) => void
  onClick?: () => void
}) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onClick={onClick}
      style={{ ...styles.item, borderLeftColor: color, ...(selected ? styles.itemSelected : {}) }}
    >
      {label}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
  },
  tabStrip: {
    display: 'flex',
    flexShrink: 0,
    borderBottom: '1px solid #333',
  },
  tabBtn: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 2,
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid transparent',
    color: '#888',
    padding: '6px 2px',
    cursor: 'pointer',
  },
  tabBtnActive: {
    color: '#ddd',
    borderBottom: '2px solid #7b68ee',
  },
  tabIcon: {
    fontSize: 14,
    fontFamily: 'monospace',
    lineHeight: 1,
  },
  tabLabel: {
    fontSize: 9,
    textAlign: 'center',
    lineHeight: 1.1,
  },
  content: {
    flex: 1,
    overflowY: 'auto',
    padding: '4px 0',
    minHeight: 0,
  },
  section: {
    marginBottom: 8,
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    padding: '4px 12px',
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
    cursor: 'pointer',
    userSelect: 'none',
  },
  itemSelected: {
    background: '#2a2a4a',
    color: '#fff',
  },
  errorText: {
    padding: '2px 12px',
    fontSize: 11,
    color: '#f87171',
  },
  errorBanner: {
    background: '#442222',
    color: '#ff8888',
    padding: '6px 10px',
    margin: '8px 12px 0',
    borderRadius: 4,
    fontSize: 11,
  },
  errorBannerLine: {
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    marginTop: 2,
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
  infoPanel: {
    flexShrink: 0,
    height: '20%',
    minHeight: 120,
    borderTop: '1px solid #333',
    display: 'flex',
    flexDirection: 'column',
    background: '#181828',
  },
  infoPanelHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '4px 10px',
    borderBottom: '1px solid #2a2a3a',
    flexShrink: 0,
  },
  infoPanelTitle: {
    fontSize: 12,
    fontFamily: 'monospace',
    color: '#ddd',
    fontWeight: 700,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  infoPanelBody: {
    flex: 1,
    overflowY: 'auto',
    padding: '6px 10px',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  infoMuted: {
    fontSize: 11,
    color: '#666',
    fontStyle: 'italic',
  },
  signature: {
    fontSize: 11,
    fontFamily: 'monospace',
    color: '#7b68ee',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  docstring: {
    fontSize: 11,
    color: '#ccc',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
  noteTextarea: {
    flex: 1,
    resize: 'none',
    background: '#1a1a2e',
    border: '1px solid #333',
    borderRadius: 3,
    color: '#ccc',
    fontSize: 11,
    fontFamily: 'inherit',
    padding: '6px 8px',
    outline: 'none',
    boxSizing: 'border-box',
  },
}
