/**
 * PipelineDAG — the main React Flow canvas.
 *
 * Fetches GET /api/pipeline for the CURRENT SCOPE (nested pipelines: the
 * canvas shows one pipeline_id at a time, root 'main' by default), applies
 * dagre layout, and renders the interactive pipeline graph.
 *
 * React Flow concepts used here:
 *   - ReactFlow component: the canvas itself
 *   - useNodesState / useEdgesState: React state hooks that React Flow provides
 *     for tracking the node/edge arrays (including position changes from dragging)
 *   - nodeTypes: maps the "type" string from our backend data to a React component
 *   - Background / Controls / Panel: built-in UI chrome from React Flow
 */

import { useEffect, useCallback, useRef, useState } from 'react'
import {
  ReactFlow,
  addEdge,
  useNodesState,
  useEdgesState,
  useReactFlow,
  Background,
  Controls,
  Panel,
  type Node,
  type Edge,
  type EdgeChange,
  type Connection,
  type OnSelectionChangeParams,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import VariableNode from './VariableNode'
import FunctionNode from './FunctionNode'
import ConstantNode from './ConstantNode'
import PathInputNode from './PathInputNode'
import SweepNode from './SweepNode'
import PipelineNode, { type PipelineNodeData } from './PipelineNode'
import RunsDock from '../RunsDock'
import { applyDagreLayout } from '../../layout'
import { callBackend } from '../../api'
import { useBackendMessage } from '../../hooks/useBackendMessage'
import { useSelectedNode } from '../../context/SelectedNodeContext'
import { useScope } from '../../context/ScopeContext'
import { usePlanRun } from '../../context/PlanRunContext'
import { useClipboard } from '../../context/ClipboardContext'

// Tell React Flow which React component to render for each node "type" string.
// These match the "type" field we set in GET /api/pipeline.
const nodeTypes = {
  variableNode: VariableNode,
  functionNode: FunctionNode,
  constantNode: ConstantNode,
  pathInputNode: PathInputNode,
  sweepNode: SweepNode,
  pipelineNode: PipelineNode,
}

interface ContextMenuState {
  x: number
  y: number
  nodeType: 'functionNode' | 'variableNode'
  fnLabel?: string
  varType?: string
  // Which single direction this variable node's type plays in the
  // current scope's interface — a type produced by a function inside the
  // scope is ALWAYS classified as an output there (document_interface's
  // inputs = consumed - produced), never an input, even if it's also
  // consumed further downstream as an intermediate; a type only ever
  // consumed (never produced) is a pure input. Only one direction is
  // ever real for a given type in a given scope, so only one toggle is
  // offered — never both.
  portDirection?: 'input' | 'output'
}

interface HiddenPorts {
  input: string[]
  output: string[]
}

interface HiddenEdge {
  edge_id: string
  source: string
  target: string
  source_handle: string | null
  target_handle: string | null
}

export default function PipelineDAG() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChangeBase] = useEdgesState<Edge>([])
  const { screenToFlowPosition, fitView } = useReactFlow()
  const { selectedNode, setSelectedNode } = useSelectedNode()
  const { currentScope, breadcrumb, descend, graphVersion, bumpGraph } = useScope()
  const { requestPlan } = usePlanRun()
  const { clipboard, setClipboard } = useClipboard()
  const isFirstLoad = useRef(true)
  // Last mouse position over the canvas (screen coords) — Cmd/Ctrl+V has
  // no drop point of its own, so it pastes wherever the cursor currently
  // is, same idea as the existing drag-and-drop's screenToFlowPosition use.
  const lastMousePosRef = useRef({ x: 0, y: 0 })
  // The scope the on-screen nodes belong to — on a scope switch, on-screen
  // positions must NOT carry over to the new canvas.
  const loadedScope = useRef<string | null>(null)
  // Nodes dropped onto the canvas, keyed by id, waiting for React Flow to
  // measure their rendered size so the DROP POINT can be re-centered under
  // the node (dropped nodes start pinned by their top-left corner, since
  // their eventual width/height isn't known until they've rendered once).
  const pendingCenterRef = useRef<Map<string, { x: number; y: number }>>(new Map())
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)
  const [runFinalized, setRunFinalized] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [extractDraft, setExtractDraft] = useState<{ open: boolean; name: string; error: string }>(
    { open: false, name: '', error: '' }
  )
  const [hiddenEdges, setHiddenEdges] = useState<HiddenEdge[]>([])
  const [showHiddenEdges, setShowHiddenEdges] = useState(false)
  const [hiddenPorts, setHiddenPorts] = useState<HiddenPorts>({ input: [], output: [] })

  const fetchPipeline = useCallback(async () => {
    // Fetch pipeline first — _build_graph has a side effect (graduate_manual_node)
    // that writes to layout.json. Layout must be read AFTER that write, otherwise
    // savedPositions will have stale keys and dagre will recalculate positions.
    const data = await callBackend('get_pipeline', { pipeline_id: currentScope }) as { nodes: Node[]; edges: Edge[] }
    const layoutData = await callBackend('get_layout', { pipeline_id: currentScope }) as Record<string, unknown>
    const savedPositions =
      (layoutData.positions ?? layoutData) as Record<string, { x: number; y: number }>  // handle both new and legacy format

    // Initialise all constant values as checked (selected for running).
    const initialised = data.nodes.map((node: Node) => {
      if (node.type !== 'constantNode') return node
      return {
        ...node,
        data: {
          ...node.data,
          values: ((node.data as { values?: unknown[] }).values ?? []).map(
            (v: unknown) => ({ ...(v as object), checked: true })
          ),
        },
      }
    })

    const scopeChanged = loadedScope.current !== currentScope
    loadedScope.current = currentScope

    // On refreshes, use current on-screen positions so nodes never jump.
    // Only fall back to saved/dagre positions for nodes not already on screen.
    // On a SCOPE SWITCH the previous nodes belong to another canvas, so
    // saved/dagre positions win unconditionally.
    setNodes(prev => {
      const currentPositions: Record<string, { x: number; y: number }> = {}
      if (!scopeChanged) {
        for (const n of prev) {
          currentPositions[n.id] = n.position
        }
      }
      const merged = { ...savedPositions, ...currentPositions }
      return applyDagreLayout(initialised, data.edges, merged)
    })
    setEdges(data.edges)

    // Fit the viewport on the very first load and on every scope switch.
    if (isFirstLoad.current || scopeChanged) {
      isFirstLoad.current = false
      // Small delay so React Flow has rendered the nodes before fitting.
      setTimeout(() => fitView({ padding: 0.2 }), 50)
    }

    // Hidden edges are scoped per pipeline (a delete in one hypothesis
    // never hides another hypothesis's independent placement of the same
    // shared wiring) — refreshed alongside the graph so the restore-panel
    // count stays live for the currently open scope.
    callBackend('get_hidden_edges', { pipeline_id: currentScope }).then(res => {
      setHiddenEdges((res as { edges: HiddenEdge[] }).edges)
    })

    // This scope's own hidden ports (to-do #9) — right-click a variable
    // node's Show/Hide label needs current state. Scoped to currentScope
    // like hidden edges: a hide made in one subpipeline never affects
    // another's independent interface.
    callBackend('get_hidden_ports', { pipeline_id: currentScope }).then(res => {
      setHiddenPorts(res as HiddenPorts)
    })
  }, [setNodes, setEdges, fitView, currentScope])

  useEffect(() => {
    fetchPipeline()
  }, [fetchPipeline, graphVersion])

  // Refresh DAG whenever the backend signals that data changed.
  useBackendMessage(useCallback((msg) => {
    if (msg.type === 'dag_updated' || msg.method === 'dag_updated') fetchPipeline()
  }, [fetchPipeline]))

  // Re-center nodes queued by onDrop once React Flow has measured their
  // rendered size (fit-content width/height isn't known until then).
  useEffect(() => {
    if (pendingCenterRef.current.size === 0) return
    for (const [id, center] of pendingCenterRef.current) {
      const node = nodes.find(n => n.id === id)
      const { width, height } = node?.measured ?? {}
      if (!width || !height) continue
      pendingCenterRef.current.delete(id)
      const newX = center.x - width / 2
      const newY = center.y - height / 2
      setNodes(prev => prev.map(n => n.id === id ? { ...n, position: { x: newX, y: newY } } : n))
      callBackend('put_layout', { node_id: id, x: newX, y: newY, pipeline_id: currentScope })
    }
  }, [nodes, setNodes, currentScope])

  // Keep selectedNode data fresh after DAG refreshes.
  useEffect(() => {
    if (!selectedNode) return
    const updated = nodes.find(n => n.id === selectedNode.id)
    if (updated && updated !== selectedNode) setSelectedNode(updated)
    else if (!updated) setSelectedNode(null)
  }, [nodes])  // eslint-disable-line react-hooks/exhaustive-deps

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    setContextMenu(null)
    if (node.type === 'functionNode' || node.type === 'constantNode' || node.type === 'variableNode' || node.type === 'pathInputNode' || node.type === 'sweepNode' || node.type === 'pipelineNode') {
      setSelectedNode(node)
    } else {
      setSelectedNode(null)
    }
  }, [setSelectedNode])

  const onPaneClick = useCallback(() => {
    setSelectedNode(null)
    setContextMenu(null)
  }, [setSelectedNode])

  // Box-select (shift+drag, react-flow's default) tracked here so a
  // multi-node selection can offer "extract to submodule" — the app never
  // read node.selected before this.
  const onSelectionChange = useCallback(({ nodes: selected }: OnSelectionChangeParams) => {
    setSelectedIds(selected.map(n => n.id))
  }, [])

  // Copy/paste (to-do #5) — the clipboard holds a REFERENCE (source scope
  // + node ids), not a data snapshot, so paste always resolves against
  // live current config/wiring (see scope_service.paste_nodes). Works
  // within one scope (paste again = a second copy) and BETWEEN scopes
  // (copy here, switch hypothesis tabs, paste there) with no special
  // casing — target is just whatever currentScope is at paste time.
  const handleCopy = useCallback(() => {
    if (selectedIds.length === 0) return
    setClipboard({ sourcePipelineId: currentScope, nodeIds: selectedIds })
  }, [selectedIds, currentScope, setClipboard])

  const handlePaste = useCallback(() => {
    if (!clipboard) return
    const position = screenToFlowPosition(lastMousePosRef.current)
    callBackend('paste_nodes', {
      pipeline_id: currentScope,
      source_pipeline_id: clipboard.sourcePipelineId,
      node_ids: clipboard.nodeIds,
      x: position.x,
      y: position.y,
    })
      .then(res => {
        const { node_id_map } = res as { node_id_map: Record<string, string> }
        setSelectedIds(Object.values(node_id_map))
        setClipboard(null)  // one paste consumes the clipboard — the Paste button disappears
        bumpGraph()
      })
      .catch(err => window.alert(`Could not paste: ${(err as Error).message}`))
  }, [clipboard, currentScope, screenToFlowPosition, bumpGraph, setClipboard])

  // Cmd/Ctrl+C / Cmd/Ctrl+V, ignored while typing in a text field (so
  // editing a node's name/value keeps using the browser's native copy).
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return
      const tag = (document.activeElement as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (document.activeElement as HTMLElement | null)?.isContentEditable) return
      if (e.key === 'c' && selectedIds.length > 0) {
        e.preventDefault()
        handleCopy()
      } else if (e.key === 'v' && clipboard) {
        e.preventDefault()
        handlePaste()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedIds, clipboard, handleCopy, handlePaste])

  const handleExtract = useCallback(() => {
    const name = extractDraft.name.trim()
    if (!name) return
    callBackend('extract_to_submodule', {
      pipeline_id: currentScope,
      node_ids: selectedIds,
      name,
    })
      .then(() => {
        setExtractDraft({ open: false, name: '', error: '' })
        setSelectedIds([])
        bumpGraph()
      })
      .catch(err => setExtractDraft(d => ({ ...d, error: (err as Error).message })))
  }, [extractDraft.name, selectedIds, currentScope, bumpGraph])

  const handleRestoreEdge = useCallback((edgeId: string) => {
    callBackend('unhide_edge', { edge_id: edgeId, pipeline_id: currentScope })
      .then(() => bumpGraph())
      .catch(err => window.alert(`Could not restore edge: ${(err as Error).message}`))
  }, [bumpGraph, currentScope])

  // Short label for a node id in the restore list — strip prefixes/hashes
  // rather than showing the raw fn__{fn}__{wiring_id} form.
  const shortNodeLabel = useCallback((nodeId: string) => {
    const bare = nodeId.split('::')[0]
    const m = /^(var|const|pathInput)__(.+)$/.exec(bare)
    if (m) return m[2]
    const fm = /^fn__(.+)__[0-9a-f]{16}$/.exec(bare)
    if (fm) return fm[1]
    return bare
  }, [])

  // Double-click a pipeline node → descend into the child scope (push the
  // navigation crumb; the crumb carries the binding so the breadcrumb can
  // show why constants display overridden).
  const onNodeDoubleClick = useCallback((_: unknown, node: Node) => {
    if (node.type !== 'pipelineNode') return
    const data = node.data as unknown as PipelineNodeData
    descend({
      use_id: node.id,
      pipeline_id: data.child_pipeline_id,
      name: data.label,
      binding: data.binding,
    })
  }, [descend])

  // Right-click a function node → "Run until here" (pull execution, R2).
  // Right-click a variable node, OUTSIDE root scope → "Show/Hide outside
  // pipeline" (to-do #9) — root is never itself a pipeline node anywhere,
  // so hiding its ports would be a no-op.
  const onNodeContextMenu = useCallback((e: React.MouseEvent, node: Node) => {
    if (node.type !== 'functionNode' && node.type !== 'variableNode') return
    if (node.type === 'variableNode' && currentScope === 'main') return
    e.preventDefault()
    // Menu coordinates are relative to the canvas wrapper (position: relative).
    const bounds = wrapperRef.current?.getBoundingClientRect()
    const base = { x: e.clientX - (bounds?.left ?? 0), y: e.clientY - (bounds?.top ?? 0) }
    if (node.type === 'functionNode') {
      setContextMenu({ ...base, nodeType: 'functionNode', fnLabel: (node.data as { label: string }).label })
    } else {
      // Classify from THIS scope's own edges (already scope-filtered by
      // the backend, so any edge touching this node id is in-scope): an
      // edge INTO the variable node means something here produces it
      // (output); an edge OUT means something here consumes it (input).
      // Produced wins over consumed — see ContextMenuState.portDirection.
      const isProduced = edges.some(ed => ed.target === node.id)
      const isConsumed = edges.some(ed => ed.source === node.id)
      const portDirection = isProduced ? 'output' : isConsumed ? 'input' : undefined
      if (!portDirection) return  // isolated node — nothing to hide/show
      setContextMenu({
        ...base,
        nodeType: 'variableNode',
        varType: (node.data as { label: string }).label,
        portDirection,
      })
    }
  }, [currentScope, edges])

  const handleRunUntilHere = useCallback(() => {
    if (!contextMenu?.fnLabel) return
    requestPlan({
      pipeline_id: currentScope,
      mode: 'until',
      target: contextMenu.fnLabel,
      label: `${breadcrumb[breadcrumb.length - 1].name} until ${contextMenu.fnLabel}`,
    })
    setContextMenu(null)
  }, [contextMenu, currentScope, breadcrumb, requestPlan])

  // Toggle one direction's port for the right-clicked variable type — the
  // internal node itself is never hidden, only its outward-facing dot on
  // THIS scope's interface (see domain.scope_filter.document_interface).
  const handleTogglePort = useCallback((direction: 'input' | 'output') => {
    const varType = contextMenu?.varType
    if (!varType) return
    const isHidden = hiddenPorts[direction].includes(varType)
    callBackend(isHidden ? 'unhide_port' : 'hide_port', {
      pipeline_id: currentScope,
      direction,
      var_type: varType,
    })
      .then(() => {
        setContextMenu(null)
        setHiddenPorts(prev => ({
          ...prev,
          [direction]: isHidden
            ? prev[direction].filter(t => t !== varType)
            : [...prev[direction], varType],
        }))
        bumpGraph()
      })
      .catch(err => window.alert(`Could not update port visibility: ${(err as Error).message}`))
  }, [contextMenu, hiddenPorts, currentScope, bumpGraph])

  const handleRunEndpoints = useCallback(() => {
    requestPlan({
      pipeline_id: currentScope,
      mode: 'endpoints',
      finalized: runFinalized,
      label: `${breadcrumb[breadcrumb.length - 1].name} endpoints`,
    })
  }, [currentScope, breadcrumb, requestPlan, runFinalized])

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()

    // Pipeline dragged from the sidebar → place a pipeline USE in this scope.
    const rawPipeline = e.dataTransfer.getData('application/scistack-pipeline')
    if (rawPipeline) {
      const { pipeline_id, name } = JSON.parse(rawPipeline) as { pipeline_id: string; name: string }
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY })
      callBackend('add_pipeline_use', {
        parent_pipeline_id: currentScope,
        child_pipeline_id: pipeline_id,
        binding: null,
        x: position.x,
        y: position.y,
      })
        .then(res => {
          const { use_id } = res as { use_id: string }
          pendingCenterRef.current.set(use_id, position)
          bumpGraph()
        })
        .catch(err => window.alert(`Could not place pipeline '${name}': ${(err as Error).message}`))
      return
    }

    const raw = e.dataTransfer.getData('application/scistack-node')
    if (!raw) return
    const { nodeType, label } = JSON.parse(raw) as { nodeType: string; label: string }

    const position = screenToFlowPosition({ x: e.clientX, y: e.clientY })
    const prefix = nodeType === 'functionNode' ? 'fn' : nodeType === 'constantNode' ? 'const' : nodeType === 'pathInputNode' ? 'pathInput' : nodeType === 'sweepNode' ? 'sweep' : 'var'
    const nodeId = `${prefix}__${label}__${Math.random().toString(36).slice(2, 8)}`
    pendingCenterRef.current.set(nodeId, position)

    const buildFnData = async () => {
      if (nodeType !== 'functionNode') return { run_state: 'red' as const }
      try {
        const info = await callBackend('get_function_params', { name: label }) as {
          params: string[]
          output_names?: string[]
          language?: string
          endpoint_kind?: 'plot' | 'stat' | null
        }
        const input_params: Record<string, string> = {}
        for (const p of info.params) input_params[p] = ''
        const output_types = info.output_names ?? []
        const extra: Record<string, unknown> = {}
        if (info.language === 'matlab') extra.language = 'matlab'
        // Endpoint badge/Show button must appear on the freshly dropped
        // node, before any run creates DB history.
        if (info.endpoint_kind) extra.endpoint_kind = info.endpoint_kind
        return { input_params, output_types, constant_params: [] as string[], run_state: 'red' as const, ...extra }
      } catch {
        return { run_state: 'red' as const }
      }
    }

    buildFnData().then(fnExtra => {
      setNodes(prev => {
        // put_layout broadcasts dag_updated, so the refetched graph may
        // already contain this node — never append a duplicate id.
        if (prev.some(n => n.id === nodeId)) return prev
        const newNode: Node = {
          id: nodeId,
          type: nodeType,
          position,
          data: {
            label,
            ...(nodeType === 'variableNode' ? { total_records: 0, run_state: 'red' } : {}),
            ...(nodeType === 'functionNode' ? fnExtra : {}),
            ...(nodeType === 'constantNode' ? { values: [] } : {}),
            ...(nodeType === 'pathInputNode' ? { template: '', root_folder: null, alternate_templates: [] } : {}),
            ...(nodeType === 'sweepNode' ? { values: [] } : {}),
          },
        }
        return [...prev, newNode]
      })
    })

    // Persist so it survives a DAG refresh — created IN the current scope.
    callBackend('put_layout', { node_id: nodeId, x: position.x, y: position.y, node_type: nodeType, label, pipeline_id: currentScope })
  }, [screenToFlowPosition, setNodes, currentScope, bumpGraph])

  const onNodeDragStop = useCallback((_: unknown, node: Node) => {
    callBackend('put_layout', { node_id: node.id, x: node.position.x, y: node.position.y, pipeline_id: currentScope })
  }, [currentScope])

  const onNodesDelete = useCallback((deleted: Node[]) => {
    for (const node of deleted) {
      if (node.type === 'pipelineNode') {
        // Pipeline nodes are use edges — removing one deletes the use row
        // (and its layout positions) but never the child pipeline itself.
        callBackend('remove_pipeline_use', { use_id: node.id })
          .catch(err => {
            window.alert(`Could not remove pipeline node: ${(err as Error).message}`)
            bumpGraph()  // restore the node — the delete did not happen
          })
      } else {
        callBackend('delete_layout', { node_id: node.id })
      }
    }
  }, [bumpGraph])

  // Would connecting source -> target close a cycle in the graph currently
  // on screen (DB-derived + manual edges)? BFS forward from target — if
  // source is reachable, target already leads back to source.
  const wouldCreateCycle = useCallback((source: string, target: string) => {
    if (source === target) return true
    const adjacency = new Map<string, string[]>()
    for (const e of edges) {
      if (!e.source || !e.target) continue
      if (!adjacency.has(e.source)) adjacency.set(e.source, [])
      adjacency.get(e.source)!.push(e.target)
    }
    const seen = new Set([target])
    const queue = [target]
    while (queue.length) {
      const current = queue.shift() as string
      if (current === source) return true
      for (const next of adjacency.get(current) ?? []) {
        if (!seen.has(next)) {
          seen.add(next)
          queue.push(next)
        }
      }
    }
    return false
  }, [edges])

  // Instant client-side guard — rejects the drag before onConnect fires, no
  // backend round trip. The backend re-checks authoritatively (defense in
  // depth) since it also knows about edges outside the current scope view.
  const isValidConnection = useCallback((connection: Connection | Edge) => {
    const { source, target } = connection
    if (!source || !target) return false
    if (wouldCreateCycle(source, target)) {
      console.warn('[PipelineDAG] rejected connection that would create a cycle', { source, target })
      return false
    }
    return true
  }, [wouldCreateCycle])

  const onConnect = useCallback((connection: Connection) => {
    const edgeId = `manual__${Math.random().toString(36).slice(2, 8)}`
    const edge: Edge = {
      ...connection,
      id: edgeId,
      data: { manual: true },
    }
    setEdges(prev => addEdge(edge, prev))
    callBackend('put_edge', {
      edge_id: edgeId,
      source: connection.source,
      target: connection.target,
      source_handle: connection.sourceHandle ?? null,
      target_handle: connection.targetHandle ?? null,
    }).catch(err => {
      window.alert(`Could not create connection: ${(err as Error).message}`)
      setEdges(prev => prev.filter(e => e.id !== edgeId))
    })
  }, [setEdges])

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    for (const change of changes) {
      if (change.type !== 'remove') continue
      // Manual edges hard-delete; DB-derived edges are hidden (never
      // deleted — build_edges excludes them on every rebuild until
      // reconnected or restored). Backend decides which based on the id
      // prefix; the frontend just forwards the removed edge's endpoints so
      // a hidden DB-derived edge can be labeled in the restore panel.
      const removed = edges.find(e => e.id === change.id)
      callBackend('delete_edge', {
        edge_id: change.id,
        source: removed?.source,
        target: removed?.target,
        source_handle: removed?.sourceHandle ?? null,
        target_handle: removed?.targetHandle ?? null,
      }).catch(err => {
        window.alert(`Could not delete edge: ${(err as Error).message}`)
        bumpGraph()  // restore the edge — the delete did not happen
      })
    }
    onEdgesChangeBase(changes)
  }, [onEdgesChangeBase, edges, bumpGraph])

  return (
    <div
      ref={wrapperRef}
      style={{ width: '100%', height: '100%', position: 'relative' }}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onMouseMove={e => { lastMousePosRef.current = { x: e.clientX, y: e.clientY } }}
    >
      {/* React Flow's default selected-edge color (--xy-edge-stroke-selected-default:
          #555) is a dark gray meant for a light canvas — on this app's dark navy
          background it's nearly invisible, so a click-to-select gives no visible
          feedback. Override with a bright, on-brand highlight + thicker stroke;
          deselecting (clicking the pane, or Escape) removes the .selected class
          automatically, so the highlight already disappears for free. */}
      <style>{`
        .react-flow__edge-path {
          stroke: #6b6b8f;
        }
        .react-flow__edge:hover .react-flow__edge-path {
          stroke: #9d92f5;
        }
        .react-flow__edge.selected .react-flow__edge-path {
          stroke: #a78bfa;
          stroke-width: 3;
          filter: drop-shadow(0 0 4px rgba(167, 139, 250, 0.6));
        }
      `}</style>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={onNodeDragStop}
        onNodesDelete={onNodesDelete}
        onConnect={onConnect}
        isValidConnection={isValidConnection}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        onNodeContextMenu={onNodeContextMenu}
        onPaneClick={onPaneClick}
        onSelectionChange={onSelectionChange}
        nodeTypes={nodeTypes}
      >
        <Background />
        <Controls />
        {(selectedIds.length > 0 || clipboard) && (
          <Panel position="top-right">
            <div style={styles.clipboardPanel}>
              {selectedIds.length > 0 && (
                <button style={styles.clipboardBtn} onClick={handleCopy} type="button" title="Cmd/Ctrl+C">
                  ⧉ Copy {selectedIds.length}
                </button>
              )}
              {clipboard && (
                <button style={styles.clipboardBtn} onClick={handlePaste} type="button" title="Cmd/Ctrl+V — pastes at the cursor">
                  📋 Paste {clipboard.nodeIds.length}
                </button>
              )}
            </div>
          </Panel>
        )}
        {selectedIds.length > 1 && (
          <Panel position="top-left">
            <div style={styles.extractPanel}>
              {!extractDraft.open ? (
                <button
                  style={styles.extractBtn}
                  onClick={() => setExtractDraft({ open: true, name: '', error: '' })}
                  type="button"
                >
                  ⧉ Extract {selectedIds.length} nodes to submodule
                </button>
              ) : (
                <div style={styles.extractForm}>
                  <input
                    style={styles.extractInput}
                    autoFocus
                    value={extractDraft.name}
                    placeholder="submodule name…"
                    onChange={e => setExtractDraft(d => ({ ...d, name: e.target.value, error: '' }))}
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleExtract()
                      if (e.key === 'Escape') setExtractDraft({ open: false, name: '', error: '' })
                    }}
                  />
                  <button style={styles.extractBtn} onClick={handleExtract} type="button">
                    Extract
                  </button>
                </div>
              )}
              {extractDraft.error && <div style={styles.extractError}>{extractDraft.error}</div>}
            </div>
          </Panel>
        )}
        <Panel position="bottom-left">
          <RunsDock />
        </Panel>
        {hiddenEdges.length > 0 && (
          <Panel position="bottom-left">
            <div style={styles.hiddenEdgesPanel}>
              <button
                style={styles.hiddenEdgesToggle}
                onClick={() => setShowHiddenEdges(v => !v)}
                type="button"
              >
                {showHiddenEdges ? 'hide' : `${hiddenEdges.length} hidden edge${hiddenEdges.length === 1 ? '' : 's'} — show`}
              </button>
              {showHiddenEdges && (
                <div style={styles.hiddenEdgesList}>
                  {hiddenEdges.map(he => (
                    <div key={he.edge_id} style={styles.hiddenEdgeRow}>
                      <span style={styles.hiddenEdgeText}>
                        {shortNodeLabel(he.source)} → {shortNodeLabel(he.target)}
                      </span>
                      <button
                        style={styles.hiddenEdgeRestoreBtn}
                        onClick={() => handleRestoreEdge(he.edge_id)}
                        type="button"
                        title="Restore this edge (also unhides — recomputes state fresh from the database)"
                      >
                        restore
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Panel>
        )}
        <Panel position="top-right">
          <div style={styles.runPanel}>
            <label style={styles.finalizedToggle} title="Draft runs preview endpoints without DB writes; finalized runs stamp and record them.">
              <input
                type="checkbox"
                checked={runFinalized}
                onChange={e => setRunFinalized(e.target.checked)}
                style={{ margin: 0 }}
              />
              finalized
            </label>
            <button
              style={styles.runEndpointsBtn}
              onClick={handleRunEndpoints}
              type="button"
              title="Plan-preview and run every endpoint in this scope (nested pipelines included)"
            >
              ▶ Run endpoints
            </button>
          </div>
        </Panel>
      </ReactFlow>
      {contextMenu && contextMenu.nodeType === 'functionNode' && (
        <div style={{ ...styles.contextMenu, left: contextMenu.x, top: contextMenu.y }}>
          <button style={styles.contextMenuItem} onClick={handleRunUntilHere} type="button">
            ▶ Run until here
          </button>
        </div>
      )}
      {contextMenu && contextMenu.nodeType === 'variableNode' && (() => {
        const varType = contextMenu.varType ?? ''
        const direction = contextMenu.portDirection
        if (!varType || !direction) return null
        return (
          <div style={{ ...styles.contextMenu, left: contextMenu.x, top: contextMenu.y }}>
            <button style={styles.contextMenuItem} onClick={() => handleTogglePort(direction)} type="button">
              {hiddenPorts[direction].includes(varType)
                ? `◎ Show as ${direction} port`
                : `⊘ Hide as ${direction} port`}
            </button>
          </div>
        )
      })()}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  runPanel: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '4px 8px',
    background: '#1a1a2e',
    border: '1px solid #3a3a5a',
    borderRadius: 6,
  },
  finalizedToggle: {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    color: '#ccc',
    fontSize: 11,
    cursor: 'pointer',
    userSelect: 'none',
  },
  runEndpointsBtn: {
    padding: '4px 10px',
    background: '#7b68ee',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: 12,
  },
  extractPanel: {
    padding: '4px 8px',
    background: '#1a1a2e',
    border: '1px solid #a21caf',
    borderRadius: 6,
    userSelect: 'none',
  },
  hiddenEdgesPanel: {
    padding: '4px 8px',
    background: '#1a1a2e',
    border: '1px solid #dc2626',
    borderRadius: 6,
  },
  hiddenEdgesToggle: {
    padding: '3px 8px',
    background: 'transparent',
    color: '#f87171',
    border: 'none',
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: 11,
  },
  hiddenEdgesList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 3,
    marginTop: 4,
    maxHeight: 140,
    overflowY: 'auto',
  },
  hiddenEdgeRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  hiddenEdgeText: {
    fontSize: 10,
    fontFamily: 'monospace',
    color: '#ccc',
    whiteSpace: 'nowrap',
  },
  hiddenEdgeRestoreBtn: {
    padding: '2px 6px',
    background: '#374151',
    color: '#fff',
    border: 'none',
    borderRadius: 3,
    cursor: 'pointer',
    fontSize: 10,
    flexShrink: 0,
  },
  clipboardPanel: {
    display: 'flex',
    gap: 4,
    padding: '4px 8px',
    background: '#1a1a2e',
    border: '1px solid #2563eb',
    borderRadius: 6,
    // This floating panel sits on top of the canvas, unlike React Flow's
    // own pane (which disables text selection so shift-drag box-select
    // works cleanly) — without this, a shift-drag gesture starting on or
    // crossing the panel also drags out a native browser text selection
    // alongside React Flow's own selection rectangle.
    userSelect: 'none',
  },
  clipboardBtn: {
    padding: '4px 10px',
    background: '#2563eb',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: 12,
    whiteSpace: 'nowrap',
  },
  extractForm: {
    display: 'flex',
    gap: 4,
  },
  extractInput: {
    background: '#0f0f1e',
    border: '1px solid #a21caf',
    borderRadius: 3,
    color: '#ccc',
    fontSize: 12,
    fontFamily: 'monospace',
    padding: '4px 6px',
    outline: 'none',
  },
  extractBtn: {
    padding: '4px 10px',
    background: '#a21caf',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: 12,
    whiteSpace: 'nowrap',
  },
  extractError: {
    marginTop: 4,
    fontSize: 11,
    color: '#f87171',
    maxWidth: 240,
    whiteSpace: 'pre-wrap',
  },
  contextMenu: {
    position: 'absolute',
    zIndex: 1000,
    background: '#1a1a2e',
    border: '1px solid #3a3a5a',
    borderRadius: 4,
    boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
    overflow: 'hidden',
  },
  contextMenuItem: {
    display: 'block',
    width: '100%',
    padding: '6px 14px',
    background: 'transparent',
    color: '#eee',
    border: 'none',
    fontSize: 12,
    textAlign: 'left',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
}
