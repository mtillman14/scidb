/**
 * ParameterNode — a named parameter in the pipeline: one or more values.
 *
 * One `scidb.Parameter` class, one node type (D6, see
 * docs/claude/entity-editability-model.md): adding a value is adding an
 * argument, so a node never changes type or id under the user.
 *
 * Replaces the former ConstantNode + SweepNode. The merge went in the
 * constant node's direction because it was already the richer widget: the
 * old sweep node had no per-value checkboxes, no `src` badge and no
 * DB-history rows, and now inherits all three.
 *
 * Shows the name and a checkboxed list of the distinct values it has taken
 * across pipeline runs, plus whatever source currently declares. Checked
 * values are "selected" for downstream runs; unchecking persists as a
 * hidden value and never deletes data (see
 * pipeline_store.hide_constant_value, and execution_service's filtering,
 * which excludes unchecked values from multi-value fan-outs too).
 *
 * State management: checked state lives inside each value object in the
 * node's `data`, seeded from the backend on every graph fetch
 * (build_parameter_nodes). Toggling updates local state immediately
 * (useReactFlow().setNodes -- same pattern as VariableNode) and fires the
 * hide/unhide call in the background; a `dag_updated` broadcast from that
 * call re-fetches the graph and reconciles if the optimistic update and
 * persisted state ever disagree.
 *
 * Always a source node (feeds into functions); no target handle.
 */

import { useCallback } from 'react'
import { Handle, Position, useReactFlow } from '@xyflow/react'
import { callBackend } from '../../api'

export interface ParameterValue {
  value: string
  record_count: number
  checked: boolean
  is_current_source_value?: boolean
}

export interface ParameterNodeData {
  label: string
  values: ParameterValue[]
}

interface Props {
  id: string
  data: ParameterNodeData
}

export default function ParameterNode({ id, data }: Props) {
  const { setNodes } = useReactFlow()

  const toggleValue = useCallback((index: number) => {
    const target = data.values[index]
    if (!target) return
    const nextChecked = !target.checked
    setNodes(nds => nds.map(node => {
      if (node.id !== id) return node
      const values = (node.data.values as ParameterValue[]).map((v, i) =>
        i === index ? { ...v, checked: nextChecked } : v
      )
      return { ...node, data: { ...node.data, values } }
    }))
    const method = nextChecked ? 'unhide_parameter_value' : 'hide_parameter_value'
    callBackend(method, { name: data.label, value: target.value }).catch(console.error)
  }, [id, data.label, data.values, setNodes])

  const showCheckboxes = data.values.length > 1
  // A Parameter whose source declares several values fans out at execution
  // time -- one for_each call per value, via EachOf (see
  // execution_service.build_run_inputs).
  const sourceValueCount = data.values.filter(v => v.is_current_source_value).length

  return (
    <div style={styles.container}>
      <Handle type="source" position={Position.Right} />
      <div style={styles.label}>{data.label}</div>

      {data.values.length > 0 && (
        <div style={styles.listbox}>
          {data.values.map((v, i) => {
            const rowLabel = `${v.value} · ${v.record_count} rec${v.record_count !== 1 ? 's' : ''}`
            return (
              <label key={i} style={showCheckboxes ? styles.valueRow : styles.valueRowNoCheck}>
                {showCheckboxes && (
                  <input
                    type="checkbox"
                    checked={v.checked}
                    onChange={() => toggleValue(i)}
                    style={styles.checkbox}
                  />
                )}
                <span style={!showCheckboxes || v.checked ? styles.valueLabel : styles.valueLabelUnchecked}>
                  {rowLabel}
                </span>
                {v.is_current_source_value && (
                  <span style={styles.sourceBadge} title="Current value in source code">
                    src
                  </span>
                )}
              </label>
            )
          })}
        </div>
      )}

      {sourceValueCount > 1 && (
        <div style={styles.countBadge}>
          {sourceValueCount} values — EachOf
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    background: '#1e3a2f',
    border: '2px solid #2a9d8f',
    borderRadius: 6,
    padding: '6px 12px',
    minWidth: 140,
    fontSize: 13,
    boxShadow: '0 2px 6px rgba(0,0,0,0.10)',
  },
  label: {
    fontWeight: 600,
    color: '#4ecdc4',
    fontFamily: 'monospace',
    textAlign: 'center',
    marginBottom: 4,
  },
  listbox: {
    display: 'flex',
    flexDirection: 'column',
    gap: 3,
    maxHeight: 90,
    overflowY: 'auto',
  },
  valueRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 5,
    cursor: 'pointer',
    userSelect: 'none',
  },
  valueRowNoCheck: {
    display: 'flex',
    alignItems: 'center',
    userSelect: 'none',
  },
  checkbox: {
    margin: 0,
    cursor: 'pointer',
    accentColor: '#2a9d8f',
    flexShrink: 0,
  },
  valueLabel: {
    fontSize: 11,
    color: '#b2ded9',
    fontFamily: 'monospace',
  },
  valueLabelUnchecked: {
    fontSize: 11,
    color: '#555',
    fontFamily: 'monospace',
    textDecoration: 'line-through',
  },
  sourceBadge: {
    fontSize: 8,
    fontWeight: 700,
    color: '#1e3a2f',
    background: '#4ecdc4',
    borderRadius: 3,
    padding: '1px 3px',
    marginLeft: 4,
    letterSpacing: 0.3,
    flexShrink: 0,
  },
  countBadge: {
    marginTop: 3,
    fontSize: 10,
    fontFamily: 'monospace',
    color: '#4ecdc4',
    fontWeight: 600,
  },
}
