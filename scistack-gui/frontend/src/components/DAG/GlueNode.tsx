/**
 * GlueNode — free-form user code that reshapes an input in memory, between a
 * variable and the function consuming it.
 *
 * A glue node is a FunctionNode *variant*, not a different kind of thing: the
 * same `in__{param}` / `out__` handle contract, so edge resolution needs no
 * new branch on either side. What it deliberately does not have:
 *
 *   - **no Run button.** A glue node is transient by construction. It runs
 *     only as part of a consuming function's run, so a standalone run would
 *     produce nothing — and the backend refuses one with a clear message
 *     rather than reporting a successful run that did nothing.
 *   - **no state badge.** There is no saved output for green or red to
 *     describe. A glue node feeding nothing renders inert, never red.
 *
 * See docs/claude/free-code-glue-nodes.md §5.
 */

import { useCallback, useEffect } from 'react'
import { Handle, Position, useUpdateNodeInternals } from '@xyflow/react'

interface GlueNodeData {
  label: string
  input_params?: Record<string, string>  // param_name → wired variable type
  /** D4: apply per schema key (post-slice) instead of to the whole table. */
  per_schema_key?: boolean
  /** 'matlab' for a .m glue node. Glue runs in the language of the run. */
  language?: string
}

interface Props {
  id: string
  data: GlueNodeData
}

export default function GlueNode({ id, data }: Props) {
  const updateNodeInternals = useUpdateNodeInternals()

  const inputParams = data.input_params ?? {}
  const leftHandles = Object.entries(inputParams).map(([param, type]) => ({
    id: `in__${param}`,
    label: param,
    title: type ? `${param}: ${type}` : param,
  }))

  // Same remeasure dance as FunctionNode: a node dropped on the canvas
  // changes its handle set once the signature resolves, and every handle's
  // computed `top` depends on the total count.
  const handleKey = leftHandles.map(h => h.id).join('|')
  useEffect(() => {
    updateNodeInternals(id)
  }, [id, handleKey])  // eslint-disable-line react-hooks/exhaustive-deps

  const handleStyle = useCallback((
    index: number,
    total: number,
    side: 'left' | 'right',
  ): React.CSSProperties => ({
    top: `${((index + 1) / (total + 1)) * 100}%`,
    transform: `translate(${side === 'left' ? '-50%' : '50%'}, -50%)`,
  }), [])

  return (
    <div style={styles.container}>
      {leftHandles.length > 0
        ? leftHandles.map((h, i) => (
            <Handle
              key={h.id}
              id={h.id}
              type="target"
              position={Position.Left}
              style={handleStyle(i, leftHandles.length, 'left')}
              title={h.title}
            />
          ))
        : <Handle type="target" position={Position.Left} />
      }

      <div style={styles.label} title={data.label}>
        <span style={styles.icon} aria-hidden>⟿</span>
        {data.label}
      </div>

      <div style={styles.subtitle}>
        {data.language === 'matlab' ? 'MATLAB glue' : 'glue'}
        {data.per_schema_key ? ' · per schema key' : ''}
      </div>

      {leftHandles.length === 0 && (
        <div style={styles.hint}>Wire a variable into this node</div>
      )}

      <Handle type="source" position={Position.Right} id="out__" />
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    // Deliberately quieter than a function node: dashed and desaturated, so
    // a canvas reads at a glance as "these are the real steps, and these are
    // the joins between them".
    background: '#fafafa',
    border: '2px dashed #9ca3af',
    borderRadius: 6,
    padding: '6px 10px',
    minWidth: 140,
    fontSize: 12,
    boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
  },
  label: {
    fontWeight: 600,
    color: '#374151',
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  icon: {
    color: '#6b7280',
    fontSize: 14,
    lineHeight: 1,
  },
  subtitle: {
    color: '#6b7280',
    fontSize: 10,
    marginTop: 2,
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  hint: {
    marginTop: 4,
    color: '#9ca3af',
    fontSize: 10,
    fontStyle: 'italic',
  },
}
