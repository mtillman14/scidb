/**
 * Sidebar — right-panel, no tab bar. Shows the Edit palette by default;
 * as soon as a function/constant/variable/path-input/sweep/pipeline node
 * is selected, the palette is replaced by that node's settings panel, and
 * reverts automatically on deselect. There's nothing left to click to
 * switch views — Hypothesis (statement + Research Question) and the old
 * Runs/Project tabs have all moved out (Research Question lives in
 * HypothesisTabs above the canvas; Runs is RunsDock docked on the canvas;
 * Project is the header's Paths popup) — so a manual tab bar had nothing
 * left to arbitrate between.
 *
 * When a function node is selected, the settings panel shows a read-only
 * list of all pipeline variants — the Cartesian product of every constant
 * node's values on the canvas.
 */

import { useMemo } from 'react'
import { useStore } from '@xyflow/react'
import EditTab from './EditTab'
import FunctionSettingsPanel from './FunctionSettingsPanel'
import type { SchemaFilter, RunOptions, WhereFilter } from './FunctionSettingsPanel'
import ConstantSettingsPanel from './ConstantSettingsPanel'
import VariableSettingsPanel from './VariableSettingsPanel'
import PathInputSettingsPanel from './PathInputSettingsPanel'
import SweepSettingsPanel from './SweepSettingsPanel'
import PipelineSettingsPanel from './PipelineSettingsPanel'
import EndpointPanel from './EndpointPanel'
import type { PipelineNodeData } from '../DAG/PipelineNode'
import { useSelectedNode } from '../../context/SelectedNodeContext'
import type { Node } from '@xyflow/react'
import type { ConstantValue } from '../DAG/ConstantNode'

interface FnNodeData {
  label: string
  endpoint_kind?: 'plot' | 'stat'
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

interface PathInputAlternate {
  template: string
  root_folder: string | null
}

interface PathInputNodeData {
  label: string
  template: string
  root_folder: string | null
  alternate_templates: PathInputAlternate[]
}

function isPathInputNode(node: Node | null): node is Node & { data: PathInputNodeData } {
  return node?.type === 'pathInputNode'
}

interface SweepNodeData {
  label: string
  values: number[]
}

function isSweepNode(node: Node | null): node is Node & { data: SweepNodeData } {
  return node?.type === 'sweepNode'
}

function isPipelineNode(node: Node | null): node is Node & { data: PipelineNodeData } {
  return node?.type === 'pipelineNode'
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

  // Subscribe directly to the React Flow store so we re-render when node/edge data changes.
  const nodes = useStore(s => s.nodes)
  const edges = useStore(s => s.edges)

  const hasNodeSelection = isFunctionNode(selectedNode) || isConstantNode(selectedNode) || isVariableNode(selectedNode) || isPathInputNode(selectedNode) || isSweepNode(selectedNode) || isPipelineNode(selectedNode)

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
      <div style={styles.content}>
        {!hasNodeSelection && <EditTab />}
        {isFunctionNode(selectedNode)
          && (selectedNode.data as FnNodeData).endpoint_kind && (
          <EndpointPanel
            fnName={(selectedNode.data as FnNodeData).label}
            kind={(selectedNode.data as FnNodeData).endpoint_kind!}
          />
        )}
        {isFunctionNode(selectedNode) && (
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
        {isConstantNode(selectedNode) && (
          <ConstantSettingsPanel
            id={selectedNode.id}
            label={(selectedNode.data as ConstantNodeData).label}
            values={(selectedNode.data as ConstantNodeData).values}
          />
        )}
        {isVariableNode(selectedNode) && (
          <VariableSettingsPanel
            label={(selectedNode.data as { label: string }).label}
          />
        )}
        {isPathInputNode(selectedNode) && (
          <PathInputSettingsPanel
            id={selectedNode.id}
            label={(selectedNode.data as PathInputNodeData).label}
            template={(selectedNode.data as PathInputNodeData).template}
            root_folder={(selectedNode.data as PathInputNodeData).root_folder}
            alternate_templates={(selectedNode.data as PathInputNodeData).alternate_templates ?? []}
          />
        )}
        {isSweepNode(selectedNode) && (
          <SweepSettingsPanel
            id={selectedNode.id}
            label={(selectedNode.data as SweepNodeData).label}
            values={(selectedNode.data as SweepNodeData).values ?? []}
          />
        )}
        {isPipelineNode(selectedNode) && (
          <PipelineSettingsPanel
            useId={selectedNode.id}
            data={selectedNode.data as PipelineNodeData}
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
  content: {
    flex: 1,
    overflowY: 'auto',
    padding: '8px 0',
  },
}
