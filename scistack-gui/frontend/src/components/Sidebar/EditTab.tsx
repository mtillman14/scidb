/**
 * EditTab — palette of draggable function, variable, and constant nodes.
 *
 * Drag an item onto the canvas to place a new node.
 * The drag payload is JSON in the 'application/scistack-node' dataTransfer key:
 *   { nodeType: 'functionNode' | 'variableNode' | 'constantNode', label: string }
 */

import { useEffect, useState, useRef, useCallback } from 'react'
import { useWebSocket } from '../../hooks/useWebSocket'

interface Registry {
  functions: string[]
  variables: string[]
}

export default function EditTab() {
  const [registry, setRegistry] = useState<Registry>({ functions: [], variables: [] })
  const [constants, setConstants] = useState<string[]>([])
  const [addingConst, setAddingConst] = useState(false)
  const [constDraft, setConstDraft] = useState('')
  const constInputRef = useRef<HTMLInputElement>(null)

  const [pathInputs, setPathInputs] = useState<string[]>([])
  const [addingPI, setAddingPI] = useState(false)
  const [piDraft, setPiDraft] = useState('')
  const piInputRef = useRef<HTMLInputElement>(null)

  const [addingVar, setAddingVar] = useState(false)
  const [varDraft, setVarDraft] = useState('')
  const [varError, setVarError] = useState('')
  const [varSubmitting, setVarSubmitting] = useState(false)
  const varInputRef = useRef<HTMLInputElement>(null)

  function fetchRegistry() {
    fetch('/api/registry')
      .then(r => r.json())
      .then(setRegistry)
      .catch(console.error)
  }

  useEffect(() => {
    fetchRegistry()
    fetchConstants()
    fetchPathInputs()
  }, [])

  // Re-fetch registry when the backend signals a refresh (e.g. module reload).
  useWebSocket(useCallback((msg) => {
    if (msg.type === 'dag_updated') {
      fetchRegistry()
      fetchPathInputs()
    }
  }, []))

  function fetchConstants() {
    fetch('/api/constants')
      .then(r => r.json())
      .then(setConstants)
      .catch(console.error)
  }

  function fetchPathInputs() {
    fetch('/api/path-inputs')
      .then(r => {
        console.log('[PathInputs] GET status:', r.status)
        return r.json()
      })
      .then((items: Array<{ name: string }>) => {
        console.log('[PathInputs] fetched:', items)
        setPathInputs(items.map(i => i.name))
      })
      .catch(err => console.error('[PathInputs] fetch error:', err))
  }

  useEffect(() => {
    if (addingConst) constInputRef.current?.focus()
  }, [addingConst])

  useEffect(() => {
    if (addingPI) piInputRef.current?.focus()
  }, [addingPI])

  useEffect(() => {
    if (addingVar) varInputRef.current?.focus()
  }, [addingVar])

  const commitConstDraft = () => {
    const name = constDraft.trim()
    if (name) {
      fetch('/api/constants', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      }).then(fetchConstants)
    }
    setConstDraft('')
    setAddingConst(false)
  }

  const commitVarDraft = () => {
    if (varSubmitting) return
    const name = varDraft.trim()
    if (!name) {
      setVarDraft('')
      setAddingVar(false)
      setVarError('')
      return
    }
    setVarSubmitting(true)
    fetch('/api/variables/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          setVarDraft('')
          setAddingVar(false)
          setVarError('')
        } else {
          setVarError(data.error || 'Failed')
          varInputRef.current?.focus()
        }
      })
      .catch(() => {
        setVarError('Request failed')
        varInputRef.current?.focus()
      })
      .finally(() => setVarSubmitting(false))
  }

  const commitPiDraft = () => {
    const name = piDraft.trim()
    console.log('[PathInputs] commitPiDraft called, name:', JSON.stringify(name))
    if (name) {
      fetch('/api/path-inputs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
        .then(r => {
          console.log('[PathInputs] POST status:', r.status)
          return r.json()
        })
        .then(data => {
          console.log('[PathInputs] POST response:', data)
          fetchPathInputs()
        })
        .catch(err => console.error('[PathInputs] POST error:', err))
    }
    setPiDraft('')
    setAddingPI(false)
  }

  const onDragStart = (
    e: React.DragEvent,
    nodeType: 'functionNode' | 'variableNode' | 'constantNode' | 'pathInputNode',
    label: string,
  ) => {
    e.dataTransfer.setData(
      'application/scistack-node',
      JSON.stringify({ nodeType, label }),
    )
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div style={styles.root}>
      <Section title="Functions">
        {registry.functions.map(fn => (
          <DragItem
            key={fn}
            label={fn}
            color="#7b68ee"
            onDragStart={e => onDragStart(e, 'functionNode', fn)}
          />
        ))}
      </Section>
      <Section
        title="Variables"
        action={
          <button style={styles.addBtn} onClick={() => setAddingVar(true)} title="New variable type">
            +
          </button>
        }
      >
        {registry.variables.map(v => (
          <DragItem
            key={v}
            label={v}
            color="#2a9d8f"
            onDragStart={e => onDragStart(e, 'variableNode', v)}
          />
        ))}
        {addingVar && (
          <>
            <input
              ref={varInputRef}
              style={styles.draftInput}
              value={varDraft}
              placeholder="VariableName…"
              onChange={e => { setVarDraft(e.target.value); setVarError('') }}
              onKeyDown={e => {
                if (e.key === 'Enter') commitVarDraft()
                if (e.key === 'Escape') { setVarDraft(''); setAddingVar(false); setVarError('') }
              }}
              onBlur={commitVarDraft}
            />
            {varError && (
              <div style={styles.errorText}>{varError}</div>
            )}
          </>
        )}
      </Section>
      <Section
        title="Constants"
        action={
          <button style={styles.addBtn} onClick={() => setAddingConst(true)} title="New constant">
            +
          </button>
        }
      >
        {constants.map(c => (
          <DragItem
            key={c}
            label={c}
            color="#2a9d8f"
            onDragStart={e => onDragStart(e, 'constantNode', c)}
          />
        ))}
        {addingConst && (
          <input
            ref={constInputRef}
            style={styles.draftInput}
            value={constDraft}
            placeholder="constant name…"
            onChange={e => setConstDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') commitConstDraft()
              if (e.key === 'Escape') { setConstDraft(''); setAddingConst(false) }
            }}
            onBlur={commitConstDraft}
          />
        )}
      </Section>
      <Section
        title="Path Inputs"
        action={
          <button style={styles.addBtn} onClick={() => setAddingPI(true)} title="New path input">
            +
          </button>
        }
      >
        {pathInputs.map(p => (
          <DragItem
            key={p}
            label={p}
            color="#d97706"
            onDragStart={e => onDragStart(e, 'pathInputNode', p)}
          />
        ))}
        {addingPI && (
          <input
            ref={piInputRef}
            style={styles.draftInput}
            value={piDraft}
            placeholder="param name…"
            onChange={e => setPiDraft(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') commitPiDraft()
              if (e.key === 'Escape') { setPiDraft(''); setAddingPI(false) }
            }}
            onBlur={commitPiDraft}
          />
        )}
      </Section>
    </div>
  )
}

function Section({
  title,
  children,
  action,
}: {
  title: string
  children: React.ReactNode
  action?: React.ReactNode
}) {
  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <span style={styles.sectionTitle}>{title}</span>
        {action}
      </div>
      {children}
    </div>
  )
}

function DragItem({
  label,
  color,
  onDragStart,
}: {
  label: string
  color: string
  onDragStart: (e: React.DragEvent) => void
}) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      style={{ ...styles.item, borderLeftColor: color }}
    >
      {label}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    padding: '4px 0',
  },
  section: {
    marginBottom: 8,
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    padding: '6px 12px 4px',
  },
  sectionTitle: {
    flex: 1,
    fontSize: 11,
    fontWeight: 700,
    color: '#666',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  addBtn: {
    background: 'transparent',
    border: 'none',
    color: '#7b68ee',
    fontSize: 18,
    lineHeight: 1,
    cursor: 'pointer',
    padding: '0 2px',
  },
  draftInput: {
    display: 'block',
    width: 'calc(100% - 24px)',
    margin: '2px 12px',
    background: '#1a1a2e',
    border: '1px solid #7b68ee',
    borderRadius: 3,
    color: '#ccc',
    fontSize: 12,
    fontFamily: 'monospace',
    padding: '4px 6px',
    outline: 'none',
    boxSizing: 'border-box',
  },
  item: {
    padding: '5px 12px',
    fontSize: 12,
    fontFamily: 'monospace',
    color: '#ccc',
    borderLeft: '3px solid',
    cursor: 'grab',
    userSelect: 'none',
  },
  errorText: {
    padding: '2px 12px',
    fontSize: 11,
    color: '#f87171',
  },
}
