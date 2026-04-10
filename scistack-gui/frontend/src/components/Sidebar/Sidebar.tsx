/**
 * Sidebar — right-panel with tabs.
 *
 * Tabs:
 *   - Runs: collapsible per-run log sections, most recent first.
 *   - Edit: palette of draggable function and variable nodes.
 *   - Node: settings panel for the selected function or constant node (auto-activates on selection).
 *
 * When a function node is selected, the Node tab shows a read-only list of all
 * pipeline variants — the Cartesian product of every constant node's values on the canvas.
 */

import { useState, useEffect, useMemo } from 'react'
import { useStore } from '@xyflow/react'
import RunsTab from './RunsTab'
import EditTab from './EditTab'
import FunctionSettingsPanel from './FunctionSettingsPanel'
import type { SchemaFilter, RunOptions, WhereFilter } from './FunctionSettingsPanel'
import ConstantSettingsPanel from './ConstantSettingsPanel'
import VariableSettingsPanel from './VariableSettingsPanel'
import PathInputSettingsPanel from './PathInputSettingsPanel'
import ProjectConfigPanel from './ProjectConfigPanel'
import { useSelectedNode } from '../../context/SelectedNodeContext'
import type { Node } from '@xyflow/react'
import type { ConstantValue } from '../DAG/ConstantNode'

const BASE_TABS = ['Runs', 'Edit', 'Project'] as const
type BaseTab = typeof BASE_TABS[number]
type Tab = BaseTab | 'Node'

interface FnNodeData {
  label: string
  schemaFilter?: SchemaFilter | null
  schemaLevel?: string[] | null
  whereFilters?: WhereFilter[]
  runOptions?: RunOptions
}

interface ConstantNodeData {
  label: string
  values: ConstantValue[]
}

function isFunctionNode(node: Node | null): node is Node & { data: FnNodeData } {
  return node?.type === 'functionNode'
}

function isConstantNode(node: Node | null): node is Node & { data: ConstantNodeData } {
  return node?.type === 'constantNode'
}

function isVariableNode(node: Node | null): node is Node & { data: { label: string } } {
  return node?.type === 'variableNode'
}

interface PathInputNodeData {
  label: string
  template: string
  root_folder: string | null
}

function isPathInputNode(node: Node | null): node is Node & { data: PathInputNodeData } {
  return node?.type === 'pathInputNode'
}

/** Compute the Cartesian product of value arrays. */
function cartesian(arrays: string[][]): string[][] {
  if (arrays.length === 0) return []
  return arrays.reduce<string[][]>(
    (acc, arr) => acc.flatMap(row => arr.map(v => [...row, v])),
    [[]]
  )
}

export default function Sidebar() {
  const { selectedNode } = useSelectedNode()
  const [activeTab, setActiveTab] = useState<Tab>('Runs')

  // Subscribe directly to the React Flow store so we re-render when node/edge data changes.
  const nodes = useStore(s => s.nodes)
  const edges = useStore(s => s.edges)

  // Auto-switch to Node tab when a function, constant, or variable node is selected; revert when deselected.
  useEffect(() => {
    if (isFunctionNode(selectedNode) || isConstantNode(selectedNode) || isVariableNode(selectedNode) || isPathInputNode(selectedNode)) {
      setActiveTab('Node')
    } else if (activeTab === 'Node') {
      setActiveTab('Runs')
    }
  }, [selectedNode])  // eslint-disable-line react-hooks/exhaustive-deps

  const hasNodeTab = isFunctionNode(selectedNode) || isConstantNode(selectedNode) || isVariableNode(selectedNode) || isPathInputNode(selectedNode)
  const tabs: Tab[] = hasNodeTab ? ['Runs', 'Edit', 'Node'] : ['Runs', 'Edit']

  // Compute variant combinations from constant nodes and multi-wired variable inputs
  // connected to the selected function node.
  // Re-derived whenever nodes or edges change (value edits, new connections, etc.).
  const { constantNames, inputTypeNames, variants } = useMemo(() => {
    const empty = { constantNames: [] as string[], inputTypeNames: [] as string[], variants: [] as Record<string, string>[] }
    if (!isFunctionNode(selectedNode)) return empty

    // BFS upstream: walk edges in reverse to find all ancestor node IDs.
    const visited = new Set<string>()
    const queue = [selectedNode.id]
    while (queue.length > 0) {
      const current = queue.shift()!
      for (const e of edges) {
        if (e.target === current && !visited.has(e.source)) {
          visited.add(e.source)
          queue.push(e.source)
        }
      }
    }

    // Constant variant axes
    const constantNodes = nodes.filter(
      n => n.type === 'constantNode' && visited.has(n.id)
    ) as Array<Node & { data: ConstantNodeData }>

    const cNames = constantNodes.map(n => n.data.label)
    const cValueLists = constantNodes.map(n =>
      (n.data.values ?? []).map((v: ConstantValue) => v.value)
    )

    // Multi-variable input axes: find in__ handles with >1 variable source
    const inputHandleTypes: Record<string, string[]> = {}
    for (const e of edges) {
      if (e.target !== selectedNode.id) continue
      const th = e.targetHandle ?? ''
      if (!th.startsWith('in__')) continue
      const sourceNode = nodes.find(n => n.id === e.source)
      if (!sourceNode || sourceNode.type !== 'variableNode') continue
      const param = th.replace('in__', '')
      const label = (sourceNode.data as { label: string }).label
      if (!inputHandleTypes[param]) inputHandleTypes[param] = []
      if (!inputHandleTypes[param].includes(label)) {
        inputHandleTypes[param].push(label)
      }
    }

    // Only include params with >1 type as variant axes
    const itNames: string[] = []
    const itValueLists: string[][] = []
    for (const [param, types] of Object.entries(inputHandleTypes)) {
      if (types.length > 1) {
        itNames.push(param)
        itValueLists.push(types)
      }
    }

    const allNames = [...cNames, ...itNames]
    const allValueLists = [...cValueLists, ...itValueLists]

    if (allNames.length === 0) return empty
    if (allValueLists.some(vals => vals.length === 0)) {
      return { constantNames: cNames, inputTypeNames: itNames, variants: [] }
    }

    const combos = cartesian(allValueLists)
    const variantRows = combos.map(combo =>
      Object.fromEntries(allNames.map((name, i) => [name, combo[i]]))
    )

    return { constantNames: cNames, inputTypeNames: itNames, variants: variantRows }
  }, [nodes, edges, selectedNode])

  return (
    <div style={styles.root}>
      <div style={styles.tabBar}>
        {tabs.map(tab => (
          <button
            key={tab}
            style={activeTab === tab ? styles.tabActive : styles.tab}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>
      <div style={styles.content}>
        {activeTab === 'Runs' && <RunsTab />}
        {activeTab === 'Edit' && <EditTab />}
        {activeTab === 'Project' && <ProjectConfigPanel />}
        {activeTab === 'Node' && isFunctionNode(selectedNode) && (
          <FunctionSettingsPanel
            id={selectedNode.id}
            label={(selectedNode.data as FnNodeData).label}
            variants={variants}
            constantNames={constantNames}
            inputTypeNames={inputTypeNames}
            schemaFilter={(selectedNode.data as FnNodeData).schemaFilter ?? null}
            schemaLevel={(selectedNode.data as FnNodeData).schemaLevel ?? null}
            whereFilters={(selectedNode.data as FnNodeData).whereFilters ?? []}
            runOptions={(selectedNode.data as FnNodeData).runOptions ?? { dry_run: false, save: true, distribute: false, as_table: false }}
          />
        )}
        {activeTab === 'Node' && isConstantNode(selectedNode) && (
          <ConstantSettingsPanel
            id={selectedNode.id}
            label={(selectedNode.data as ConstantNodeData).label}
            values={(selectedNode.data as ConstantNodeData).values}
          />
        )}
        {activeTab === 'Node' && isVariableNode(selectedNode) && (
          <VariableSettingsPanel
            label={(selectedNode.data as { label: string }).label}
          />
        )}
        {activeTab === 'Node' && isPathInputNode(selectedNode) && (
          <PathInputSettingsPanel
            id={selectedNode.id}
            label={(selectedNode.data as PathInputNodeData).label}
            template={(selectedNode.data as PathInputNodeData).template}
            root_folder={(selectedNode.data as PathInputNodeData).root_folder}
          />
        )}
      </div>
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
  tabBar: {
    display: 'flex',
    flexShrink: 0,
    borderBottom: '1px solid #2a2a4a',
    background: '#12122a',
  },
  tab: {
    padding: '8px 16px',
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid transparent',
    color: '#888',
    fontSize: 13,
    cursor: 'pointer',
    fontWeight: 500,
  },
  tabActive: {
    padding: '8px 16px',
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid #7b68ee',
    color: '#fff',
    fontSize: 13,
    cursor: 'pointer',
    fontWeight: 600,
  },
  content: {
    flex: 1,
    overflowY: 'auto',
    padding: '8px 0',
  },
}
