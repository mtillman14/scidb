/**
 * SweepSettingsPanel — shown in the sidebar when a Sweep node is selected.
 *
 * Two ways to build the value list:
 *   - List: type/paste numbers directly ("1, 2, 5, 10").
 *   - Range: start + end + either a step size or a target number of
 *     steps — the classic "sweep a parameter" shape the to-do asked for.
 * Both modes show a live preview before saving. Saving always sends the
 * final, already-computed flat list to the backend (see
 * layout.write_sweep) — range generation is entirely a frontend concern;
 * the backend only ever stores and EachOf(...)-wraps plain numbers.
 */

import { useState, useMemo, useCallback, useEffect } from 'react'
import { useReactFlow } from '@xyflow/react'
import { callBackend } from '../../api'

interface Props {
  id: string
  label: string
  values: number[]
}

type Mode = 'list' | 'range'
type RangeKind = 'step' | 'count'

function parseListDraft(text: string): number[] {
  return text
    .split(/[,\s]+/)
    .map(s => s.trim())
    .filter(s => s.length > 0)
    .map(Number)
    .filter(n => !Number.isNaN(n))
}

/** Round away float noise (0.1 + 0.2 -> 0.30000000000000004) without
 * clobbering intentionally precise values — 10 significant decimals is
 * far past anything a sweep step size would legitimately need. */
function clean(n: number): number {
  return Math.round(n * 1e10) / 1e10
}

function generateRange(start: number, end: number, third: number, kind: RangeKind): number[] {
  if (Number.isNaN(start) || Number.isNaN(end) || Number.isNaN(third)) return []
  if (kind === 'count') {
    const count = Math.floor(third)
    if (count < 1) return []
    if (count === 1) return [clean(start)]
    const step = (end - start) / (count - 1)
    return Array.from({ length: count }, (_, i) => clean(start + i * step))
  }
  // step-size mode
  const step = third
  if (step === 0) return start === end ? [clean(start)] : []
  const count = Math.floor((end - start) / step + 1e-9) + 1
  if (count < 1) return []
  return Array.from({ length: count }, (_, i) => clean(start + i * step))
}

export default function SweepSettingsPanel({ id, label, values }: Props) {
  const { setNodes } = useReactFlow()
  const [mode, setMode] = useState<Mode>('list')
  const [listDraft, setListDraft] = useState(values.join(', '))
  const [start, setStart] = useState('0')
  const [end, setEnd] = useState('10')
  const [third, setThird] = useState('1')
  const [rangeKind, setRangeKind] = useState<RangeKind>('step')
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  // Re-seed the list draft whenever a different Sweep is shown (switching
  // selection) — matches PathInputSettingsPanel's resetKey pattern.
  useEffect(() => {
    setListDraft(values.join(', '))
  }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  const previewValues = useMemo(() => {
    if (mode === 'list') return parseListDraft(listDraft)
    return generateRange(Number(start), Number(end), Number(third), rangeKind)
  }, [mode, listDraft, start, end, third, rangeKind])

  const handleSave = useCallback(() => {
    if (previewValues.length === 0) {
      setError('No values to save — check your input.')
      return
    }
    callBackend('update_sweep', { name: label, values: previewValues })
      .then(() => {
        setError('')
        setSaved(true)
        setTimeout(() => setSaved(false), 1500)
        setNodes(nds => nds.map(n =>
          n.id === id ? { ...n, data: { ...n.data, values: previewValues } } : n
        ))
      })
      .catch(err => setError((err as Error).message))
  }, [id, label, previewValues, setNodes])

  return (
    <div style={styles.root}>
      <div style={styles.name}>{label}</div>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Current Values</div>
        {values.length === 0 ? (
          <div style={styles.empty}>Not configured yet.</div>
        ) : (
          <div style={styles.currentRow}>
            {values.join(', ')}
            <span style={styles.currentCount}> ({values.length})</span>
          </div>
        )}
      </section>

      <section style={styles.section}>
        <div style={styles.modeRow}>
          <button
            style={mode === 'list' ? styles.modeBtnActive : styles.modeBtn}
            onClick={() => setMode('list')}
            type="button"
          >
            List
          </button>
          <button
            style={mode === 'range' ? styles.modeBtnActive : styles.modeBtn}
            onClick={() => setMode('range')}
            type="button"
          >
            Range
          </button>
        </div>

        {mode === 'list' ? (
          <>
            <div style={styles.sectionTitle}>Values</div>
            <input
              style={styles.input}
              placeholder="1, 2, 5, 10"
              value={listDraft}
              onChange={e => setListDraft(e.target.value)}
            />
            <div style={styles.hint}>Comma- or space-separated numbers.</div>
          </>
        ) : (
          <>
            <div style={styles.rangeGrid}>
              <label style={styles.rangeField}>
                <span style={styles.rangeLabel}>Start</span>
                <input
                  style={styles.input}
                  type="number"
                  value={start}
                  onChange={e => setStart(e.target.value)}
                />
              </label>
              <label style={styles.rangeField}>
                <span style={styles.rangeLabel}>End</span>
                <input
                  style={styles.input}
                  type="number"
                  value={end}
                  onChange={e => setEnd(e.target.value)}
                />
              </label>
              <label style={styles.rangeField}>
                <span style={styles.rangeLabel}>
                  {rangeKind === 'step' ? 'Step size' : 'Number of steps'}
                </span>
                <input
                  style={styles.input}
                  type="number"
                  value={third}
                  onChange={e => setThird(e.target.value)}
                />
              </label>
            </div>
            <div style={styles.rangeKindRow}>
              <button
                style={rangeKind === 'step' ? styles.modeBtnActive : styles.modeBtn}
                onClick={() => setRangeKind('step')}
                type="button"
              >
                By step size
              </button>
              <button
                style={rangeKind === 'count' ? styles.modeBtnActive : styles.modeBtn}
                onClick={() => setRangeKind('count')}
                type="button"
              >
                By # of steps
              </button>
            </div>
          </>
        )}

        <div style={styles.previewSection}>
          <div style={styles.sectionTitle}>Preview</div>
          <div style={styles.previewText}>
            {previewValues.length === 0
              ? 'No values — check your input.'
              : previewValues.length <= 8
              ? previewValues.join(', ')
              : `${previewValues.slice(0, 6).join(', ')}, … (${previewValues.length} total)`}
          </div>
          {previewValues.length > 1 && (
            <div style={styles.eachOfHint}>
              Runs as EachOf({previewValues.length} values) — one for_each
              call per value.
            </div>
          )}
        </div>

        <button style={styles.saveBtn} onClick={handleSave} type="button">
          {saved ? 'Saved ✓' : 'Save'}
        </button>
        {error && <div style={styles.errorText}>{error}</div>}
      </section>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    padding: '12px',
    color: '#ccc',
    fontSize: 12,
  },
  name: {
    fontFamily: 'monospace',
    fontWeight: 700,
    fontSize: 13,
    color: '#a3e635',
    marginBottom: 12,
    wordBreak: 'break-all',
  },
  section: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontSize: 10,
    fontWeight: 700,
    color: '#666',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  empty: {
    color: '#555',
    fontStyle: 'italic',
    fontSize: 11,
  },
  currentRow: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#c5e8a0',
    wordBreak: 'break-all',
    background: '#1a2e12',
    border: '1px solid #365314',
    borderRadius: 3,
    padding: '5px 6px',
  },
  currentCount: {
    color: '#65a30d',
  },
  modeRow: {
    display: 'flex',
    gap: 4,
    marginBottom: 10,
  },
  modeBtn: {
    flex: 1,
    padding: '5px 0',
    background: 'transparent',
    color: '#888',
    border: '1px solid #333',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 11,
    fontWeight: 600,
  },
  modeBtnActive: {
    flex: 1,
    padding: '5px 0',
    background: '#365314',
    color: '#a3e635',
    border: '1px solid #65a30d',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 11,
    fontWeight: 600,
  },
  input: {
    display: 'block',
    width: '100%',
    background: '#1a1a2e',
    border: '1px solid #444',
    borderRadius: 3,
    color: '#c5e8a0',
    fontSize: 11,
    fontFamily: 'monospace',
    padding: '5px 6px',
    outline: 'none',
    boxSizing: 'border-box',
  },
  hint: {
    fontSize: 10,
    color: '#666',
    marginTop: 4,
    lineHeight: 1.4,
  },
  rangeGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr 1fr',
    gap: 6,
    marginBottom: 8,
  },
  rangeField: {
    display: 'flex',
    flexDirection: 'column',
    gap: 3,
  },
  rangeLabel: {
    fontSize: 9,
    color: '#666',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  rangeKindRow: {
    display: 'flex',
    gap: 4,
  },
  previewSection: {
    marginTop: 12,
  },
  previewText: {
    fontFamily: 'monospace',
    fontSize: 11,
    color: '#e5e5e5',
    background: '#12122a',
    border: '1px solid #333',
    borderRadius: 3,
    padding: '5px 6px',
    wordBreak: 'break-all',
  },
  eachOfHint: {
    fontSize: 10,
    color: '#65a30d',
    marginTop: 4,
  },
  saveBtn: {
    width: '100%',
    marginTop: 10,
    padding: '6px 0',
    background: '#65a30d',
    color: '#0d1a05',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 11,
    fontWeight: 700,
  },
  errorText: {
    marginTop: 6,
    fontSize: 11,
    color: '#f87171',
    whiteSpace: 'pre-wrap',
  },
}
