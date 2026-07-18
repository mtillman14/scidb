/**
 * PipelineNode — a nested pipeline placed on a parent canvas.
 *
 * The React Flow node id IS the use_id (decision G1: the same child placed
 * twice is two nodes with different use_ids; the binding lives on the use).
 *
 * data comes from GET /api/pipeline:
 *   { label, child_pipeline_id, binding, inputs, outputs }
 * inputs/outputs are variable-type name lists — the node's connection ports
 * (rendered like a function node's handles). A non-empty binding renders as
 * a compact badge. Double-click (handled at canvas level) descends into the
 * child scope; the ▶ Run button plan-previews mode=all on the CHILD
 * pipeline (per-step run_until of a child is not available descend-less).
 */

import { Handle, Position } from '@xyflow/react'
import { usePlanRun } from '../../context/PlanRunContext'
import { bindingSummary, type BindingSpec } from '../../context/ScopeContext'

export interface PipelineNodeData {
  label: string
  child_pipeline_id: string
  binding: BindingSpec | null
  inputs: string[]
  outputs: string[]
}

interface Props {
  id: string
  data: PipelineNodeData
}

export default function PipelineNode({ data }: Props) {
  const { requestPlan } = usePlanRun()

  const badge = bindingSummary(data.binding)

  const handleStyle = (index: number, total: number): React.CSSProperties => ({
    top: `${((index + 1) / (total + 1)) * 100}%`,
    transform: 'translateY(-50%)',
  })

  const handleRun = (e: React.MouseEvent) => {
    e.stopPropagation()
    requestPlan({
      pipeline_id: data.child_pipeline_id,
      mode: 'all',
      label: data.label,
    })
  }

  return (
    <div style={styles.container} title="Double-click to open this pipeline">
      {data.inputs.length > 0
        ? data.inputs.map((name, i) => (
            <Handle
              key={name}
              id={`in__${name}`}
              type="target"
              position={Position.Left}
              style={handleStyle(i, data.inputs.length)}
              title={name}
            />
          ))
        : <Handle type="target" position={Position.Left} />
      }

      <div style={styles.kind}>⧉ pipeline</div>
      <div style={styles.label}>{data.label}</div>
      {badge && (
        <div style={styles.badge} title={badge}>{badge}</div>
      )}

      <button style={styles.button} onClick={handleRun} type="button">
        ▶ Run
      </button>

      {data.outputs.length > 0
        ? data.outputs.map((name, i) => (
            <Handle
              key={name}
              id={`out__${name}`}
              type="source"
              position={Position.Right}
              style={handleStyle(i, data.outputs.length)}
              title={name}
            />
          ))
        : <Handle type="source" position={Position.Right} />
      }
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    background: '#fdf4ff',
    border: '2px double #a21caf',
    borderRadius: 8,
    padding: '8px 12px',
    minWidth: 180,
    fontSize: 13,
    boxShadow: '0 2px 6px rgba(0,0,0,0.12)',
  },
  kind: {
    fontSize: 10,
    fontWeight: 700,
    color: '#a21caf',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    textAlign: 'center',
  },
  label: {
    fontWeight: 600,
    color: '#701a75',
    fontFamily: 'monospace',
    marginBottom: 4,
    textAlign: 'center',
  },
  badge: {
    display: 'block',
    margin: '0 auto 6px',
    padding: '1px 8px',
    maxWidth: 220,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    background: '#f5d0fe',
    color: '#701a75',
    border: '1px solid #d946ef',
    borderRadius: 10,
    fontSize: 10,
    fontFamily: 'monospace',
    textAlign: 'center',
    width: 'fit-content',
  },
  button: {
    width: '100%',
    padding: '4px 0',
    background: '#a21caf',
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: 12,
  },
}
