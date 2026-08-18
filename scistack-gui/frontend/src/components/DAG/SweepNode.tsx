/**
 * SweepNode — a named parameter sweep (list of numbers) in the pipeline.
 *
 * Builds on the Constant node concept (see ConstantNode.tsx): same
 * shared-by-name identity and edge-wiring semantics (`in__{param}`), but
 * the values come from a generated list (direct entry or start/end/step)
 * rather than being staged one at a time. At execution time >1 value
 * becomes EachOf(v1, v2, ...) — see
 * execution_service.build_run_inputs — so a Sweep always runs as one
 * for_each call per value, never a scalar with values silently pooled.
 *
 * Always a source node (feeds into functions); no target handle.
 */

import { Handle, Position } from '@xyflow/react'

export interface SweepNodeData {
  label: string
  values: number[]
}

interface Props {
  data: SweepNodeData
}

function formatPreview(values: number[]): string {
  if (values.length === 0) return 'no values yet'
  if (values.length <= 4) return values.join(', ')
  return `${values.slice(0, 3).join(', ')}, … (${values.length} total)`
}

export default function SweepNode({ data }: Props) {
  return (
    <div style={styles.container}>
      <div style={styles.label}>{data.label}</div>

      <div style={styles.preview}>{formatPreview(data.values)}</div>

      {data.values.length > 0 && (
        <div style={styles.countBadge}>
          {data.values.length} value{data.values.length > 1 ? 's' : ''}
          {data.values.length > 1 ? ' — EachOf' : ''}
        </div>
      )}

      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    background: '#1a2e12',
    border: '2px solid #65a30d',
    borderRadius: 6,
    padding: '6px 12px',
    minWidth: 160,
    fontSize: 13,
    boxShadow: '0 2px 6px rgba(0,0,0,0.10)',
  },
  label: {
    fontWeight: 600,
    color: '#a3e635',
    fontFamily: 'monospace',
    textAlign: 'center',
    marginBottom: 4,
  },
  preview: {
    fontSize: 11,
    color: '#c5e8a0',
    fontFamily: 'monospace',
    wordBreak: 'break-all',
  },
  countBadge: {
    marginTop: 3,
    fontSize: 10,
    fontFamily: 'monospace',
    color: '#a3e635',
    fontWeight: 600,
  },
}
