/**
 * Breadcrumb — the navigation path above the canvas.
 *
 * `main ▸ loading (low_hz=30) ▸ filters` — the crumb is the PATH taken
 * (composition is a DAG, so there is no unique address; decision G3).
 * Crumbs entered through a BOUND use show the binding summary — context
 * for why constants display overridden. Clicking a crumb ascends to it.
 */

import { useScope, bindingSummary } from '../../context/ScopeContext'

export default function Breadcrumb() {
  const { breadcrumb, ascendTo } = useScope()

  // At the root with no path taken there is nothing to navigate — hide the
  // bar so the root canvas looks exactly like the pre-nesting GUI.
  if (breadcrumb.length === 1) return null

  return (
    <div style={styles.bar}>
      {breadcrumb.map((crumb, i) => {
        const isLast = i === breadcrumb.length - 1
        const binding = bindingSummary(crumb.binding)
        return (
          <span key={`${crumb.pipeline_id}-${i}`} style={styles.crumbWrap}>
            {i > 0 && <span style={styles.separator}>▸</span>}
            <button
              style={isLast ? styles.crumbCurrent : styles.crumb}
              onClick={() => !isLast && ascendTo(i)}
              disabled={isLast}
              type="button"
              title={isLast ? 'Current scope' : `Go back to ${crumb.name}`}
            >
              {crumb.name}
              {binding && <span style={styles.binding}> ({binding})</span>}
            </button>
          </span>
        )
      })}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  bar: {
    display: 'flex',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 2,
    padding: '4px 12px',
    background: '#12122a',
    borderBottom: '1px solid #2a2a4a',
    flexShrink: 0,
    minHeight: 28,
    boxSizing: 'border-box',
  },
  crumbWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: 2,
  },
  separator: {
    color: '#555',
    fontSize: 11,
    padding: '0 4px',
  },
  crumb: {
    background: 'transparent',
    border: 'none',
    color: '#9a8ff0',
    fontSize: 12,
    fontFamily: 'monospace',
    cursor: 'pointer',
    padding: '2px 4px',
    borderRadius: 3,
  },
  crumbCurrent: {
    background: '#2a2a4a',
    border: 'none',
    color: '#fff',
    fontSize: 12,
    fontFamily: 'monospace',
    fontWeight: 600,
    cursor: 'default',
    padding: '2px 6px',
    borderRadius: 3,
  },
  binding: {
    color: '#d8b4fe',
    fontWeight: 400,
    fontSize: 11,
  },
}
