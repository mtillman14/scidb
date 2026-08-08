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

import { useState, useCallback, useRef, useEffect } from 'react'
import { Handle, Position } from '@xyflow/react'
import { callBackend } from '../../api'
import { usePlanRun } from '../../context/PlanRunContext'
import { useScope, bindingSummary, type BindingSpec } from '../../context/ScopeContext'

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
  const { bumpGraph } = useScope()
  const [duplicating, setDuplicating] = useState(false)
  const [draftName, setDraftName] = useState('')
  const [error, setError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (duplicating) inputRef.current?.focus()
  }, [duplicating])

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

  const commitDuplicate = useCallback(() => {
    const name = draftName.trim()
    if (!name) {
      setDuplicating(false)
      return
    }
    callBackend('duplicate_pipeline', { pipeline_id: data.child_pipeline_id, name })
      .then(() => {
        setError('')
        setDuplicating(false)
        setDraftName('')
        bumpGraph()
      })
      .catch(err => setError((err as Error).message))
  }, [draftName, data.child_pipeline_id, bumpGraph])

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

      <div style={styles.buttonRow}>
        <button style={styles.button} onClick={handleRun} type="button">
          ▶ Run
        </button>
        <button
          style={styles.button}
          onClick={e => { e.stopPropagation(); setDuplicating(true) }}
          type="button"
          title="Fork this submodule's own nodes into a new, independent pipeline"
        >
          ⎘ Duplicate
        </button>
      </div>
      {duplicating && (
        <div style={styles.duplicateForm} onClick={e => e.stopPropagation()}>
          <input
            ref={inputRef}
            style={styles.duplicateInput}
            value={draftName}
            placeholder="new pipeline name…"
            onChange={e => { setDraftName(e.target.value); setError('') }}
            onKeyDown={e => {
              if (e.key === 'Enter') commitDuplicate()
              if (e.key === 'Escape') { setDuplicating(false); setDraftName(''); setError('') }
            }}
            onBlur={commitDuplicate}
          />
          {error && <div style={styles.duplicateError}>{error}</div>}
        </div>
      )}

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
  buttonRow: {
    display: 'flex',
    gap: 4,
  },
  duplicateForm: {
    marginTop: 4,
  },
  duplicateInput: {
    display: 'block',
    width: '100%',
    background: '#fff',
    border: '1px solid #a21caf',
    borderRadius: 3,
    color: '#701a75',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '3px 6px',
    outline: 'none',
    boxSizing: 'border-box',
  },
  duplicateError: {
    marginTop: 2,
    fontSize: 10,
    color: '#dc2626',
    whiteSpace: 'pre-wrap',
  },
  button: {
    flex: 1,
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
