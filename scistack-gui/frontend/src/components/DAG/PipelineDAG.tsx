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
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import VariableNode from './VariableNode'
import FunctionNode from './FunctionNode'
import ConstantNode from './ConstantNode'
import PathInputNode from './PathInputNode'
import PipelineNode, { type PipelineNodeData } from './PipelineNode'
import { applyDagreLayout } from '../../layout'
import { callBackend } from '../../api'
import { useBackendMessage } from '../../hooks/useBackendMessage'
import { useSelectedNode } from '../../context/SelectedNodeContext'
import { useScope } from '../../context/ScopeContext'
import { usePlanRun } from '../../context/PlanRunContext'

// Tell React Flow which React component to render for each node "type" string.
// These match the "type" field we set in GET /api/pipeline.
const nodeTypes = {
  variableNode: VariableNode,
  functionNode: FunctionNode,
  constantNode: ConstantNode,
  pathInputNode: PathInputNode,
  pipelineNode: PipelineNode,
}

interface ContextMenuState {
  x: number
  y: number
  fnLabel: string
}

export default function PipelineDAG() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChangeBase] = useEdgesState<Edge>([])
  const { screenToFlowPosition, fitView } = useReactFlow()
  const { selectedNode, setSelectedNode } = useSelectedNode()
  const { currentScope, breadcrumb, descend, graphVersion, bumpGraph } = useScope()
  const { requestPlan } = usePlanRun()
  const isFirstLoad = useRef(true)
  // The scope the on-screen nodes belong to — on a scope switch, on-screen
  // positions must NOT carry over to the new canvas.
  const loadedScope = useRef<string | null>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)
  const [runFinalized, setRunFinalized] = useState(false)

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
  }, [setNodes, setEdges, fitView, currentScope])

  useEffect(() => {
    fetchPipeline()
  }, [fetchPipeline, graphVersion])

  // Refresh DAG whenever the backend signals that data changed.
  useBackendMessage(useCallback((msg) => {
    if (msg.type === 'dag_updated' || msg.method === 'dag_updated') fetchPipeline()
  }, [fetchPipeline]))

  // Keep selectedNode data fresh after DAG refreshes.
  useEffect(() => {
    if (!selectedNode) return
    const updated = nodes.find(n => n.id === selectedNode.id)
    if (updated && updated !== selectedNode) setSelectedNode(updated)
    else if (!updated) setSelectedNode(null)
  }, [nodes])  // eslint-disable-line react-hooks/exhaustive-deps

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    setContextMenu(null)
    if (node.type === 'functionNode' || node.type === 'constantNode' || node.type === 'variableNode' || node.type === 'pathInputNode' || node.type === 'pipelineNode') {
      setSelectedNode(node)
    } else {
      setSelectedNode(null)
    }
  }, [setSelectedNode])

  const onPaneClick = useCallback(() => {
    setSelectedNode(null)
    setContextMenu(null)
  }, [setSelectedNode])

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
  const onNodeContextMenu = useCallback((e: React.MouseEvent, node: Node) => {
    if (node.type !== 'functionNode') return
    e.preventDefault()
    // Menu coordinates are relative to the canvas wrapper (position: relative).
    const bounds = wrapperRef.current?.getBoundingClientRect()
    setContextMenu({
      x: e.clientX - (bounds?.left ?? 0),
      y: e.clientY - (bounds?.top ?? 0),
      fnLabel: (node.data as { label: string }).label,
    })
  }, [])

  const handleRunUntilHere = useCallback(() => {
    if (!contextMenu) return
    requestPlan({
      pipeline_id: currentScope,
      mode: 'until',
      target: contextMenu.fnLabel,
      label: `${breadcrumb[breadcrumb.length - 1].name} until ${contextMenu.fnLabel}`,
    })
    setContextMenu(null)
  }, [contextMenu, currentScope, breadcrumb, requestPlan])

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
        .then(() => bumpGraph())
        .catch(err => window.alert(`Could not place pipeline '${name}': ${(err as Error).message}`))
      return
    }

    const raw = e.dataTransfer.getData('application/scistack-node')
    if (!raw) return
    const { nodeType, label } = JSON.parse(raw) as { nodeType: string; label: string }

    const position = screenToFlowPosition({ x: e.clientX, y: e.clientY })
    const prefix = nodeType === 'functionNode' ? 'fn' : nodeType === 'constantNode' ? 'const' : nodeType === 'pathInputNode' ? 'pathInput' : 'var'
    const nodeId = `${prefix}__${label}__${Math.random().toString(36).slice(2, 8)}`

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
            ...(nodeType === 'pathInputNode' ? { template: '', root_folder: null } : {}),
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
    })
  }, [setEdges])

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    for (const change of changes) {
      if (change.type === 'remove' && change.id.startsWith('manual__')) {
        callBackend('delete_edge', { edge_id: change.id })
      }
    }
    // DB-derived edges represent real data — block removal so they don't
    // flicker away and reappear on the next pipeline refresh.
    onEdgesChangeBase(changes.filter(c => c.type !== 'remove' || c.id.startsWith('manual__')))
  }, [onEdgesChangeBase])

  return (
    <div
      ref={wrapperRef}
      style={{ width: '100%', height: '100%', position: 'relative' }}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={onNodeDragStop}
        onNodesDelete={onNodesDelete}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        onNodeContextMenu={onNodeContextMenu}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
      >
        <Background />
        <Controls />
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
      {contextMenu && (
        <div style={{ ...styles.contextMenu, left: contextMenu.x, top: contextMenu.y }}>
          <button style={styles.contextMenuItem} onClick={handleRunUntilHere} type="button">
            ▶ Run until here
          </button>
        </div>
      )}
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
