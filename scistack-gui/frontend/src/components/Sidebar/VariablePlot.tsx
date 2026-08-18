/**
 * VariablePlot — default, no-code plotting for scalar/1D-numeric variables
 * (to-do #4), rendered inside VariableSettingsPanel below the Records
 * table.
 *
 * Fetches GET /api/variables/{name}/plot-data (raw, unaggregated points —
 * see api/variables.py::get_variable_plot_data) and does all grouping/
 * averaging CLIENT-SIDE so toggling which schema keys stay "kept" (vs.
 * averaged over) is instant, no round trip per toggle.
 *
 * One checkbox per schema key: checked = kept as a distinct axis/group
 * (default = every key checked, i.e. "every trial"); unchecked = averaged
 * over. Any combination is valid — "average over all trials" is just the
 * trial checkbox unchecked, "average over all trials and subjects" is
 * trial+subject unchecked, etc. — a strict generalization of the to-do's
 * named examples, not three hardcoded presets.
 */

import { useEffect, useMemo, useState } from 'react'
import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-basic-dist-min'
import { callBackend } from '../../api'

const Plot = createPlotlyComponent(Plotly)

interface PlotPoint {
  value: number | number[]
  [schemaKey: string]: unknown
}

interface PlotDataResponse {
  eligible: boolean
  reason: string | null
  kind: 'scalar' | '1d' | null
  schema_keys: string[]
  points: PlotPoint[]
}

interface Props {
  label: string
}

interface Group {
  label: string
  count: number
  scalarValues: number[]
  arrayValues: number[][]
}

function mean(values: number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length
}

function elementwiseMean(arrays: number[][]): number[] | null {
  const len = arrays[0].length
  if (!arrays.every(a => a.length === len)) return null
  const out = new Array(len).fill(0)
  for (const arr of arrays) {
    for (let i = 0; i < len; i++) out[i] += arr[i]
  }
  return out.map(v => v / arrays.length)
}

function groupPoints(points: PlotPoint[], keptKeys: string[]): Group[] {
  const byKey = new Map<string, Group>()
  for (const point of points) {
    const label = keptKeys.length === 0
      ? '(all)'
      : keptKeys.map(k => `${k}=${point[k] ?? '—'}`).join(', ')
    let group = byKey.get(label)
    if (!group) {
      group = { label, count: 0, scalarValues: [], arrayValues: [] }
      byKey.set(label, group)
    }
    group.count += 1
    if (Array.isArray(point.value)) group.arrayValues.push(point.value)
    else group.scalarValues.push(point.value)
  }
  return [...byKey.values()]
}

export default function VariablePlot({ label }: Props) {
  const [data, setData] = useState<PlotDataResponse | null>(null)
  const [error, setError] = useState('')
  const [keptKeys, setKeptKeys] = useState<Set<string>>(new Set())

  useEffect(() => {
    setData(null)
    setError('')
    callBackend('get_variable_plot_data', { name: label })
      .then(d => {
        const resp = d as PlotDataResponse
        setData(resp)
        setKeptKeys(new Set(resp.schema_keys))  // default: every key kept ("every trial")
      })
      .catch(err => setError((err as Error).message))
  }, [label])

  const groups = useMemo(() => {
    if (!data || !data.eligible) return []
    return groupPoints(data.points, data.schema_keys.filter(k => keptKeys.has(k)))
  }, [data, keptKeys])

  const mismatched = useMemo(
    () => groups.filter(g => g.arrayValues.length > 0 && elementwiseMean(g.arrayValues) === null),
    [groups]
  )

  if (error) return <div style={styles.note}>Could not load plot data: {error}</div>
  if (!data) return <div style={styles.note}>Loading plot…</div>
  if (!data.eligible) {
    return (
      <div style={styles.note}>
        Not plottable ({data.reason ?? 'not scalar/1D numeric'}) — see Records above.
      </div>
    )
  }
  if (data.points.length === 0) {
    return <div style={styles.note}>No records to plot yet.</div>
  }

  const toggleKey = (key: string) => {
    setKeptKeys(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const plotGroups = groups.filter(g => g.arrayValues.length === 0 || elementwiseMean(g.arrayValues) !== null)

  const traces: unknown[] = data.kind === 'scalar'
    ? [{
        type: 'scatter',
        mode: 'markers',
        x: plotGroups.map((_, i) => i),
        y: plotGroups.map(g => mean(g.scalarValues)),
        text: plotGroups.map(g => `${g.label}<br>n=${g.count}<br>value=${mean(g.scalarValues).toFixed(4)}`),
        hoverinfo: 'text',
        marker: { size: 10, color: '#67e8f9' },
      }]
    : plotGroups.map(g => {
        const y = elementwiseMean(g.arrayValues) ?? []
        return {
          type: 'scatter',
          mode: 'lines',
          name: g.label,
          x: y.map((_, i) => i),
          y,
          text: y.map((v, i) => `${g.label}<br>n=${g.count}<br>index=${i}<br>value=${v.toFixed(4)}`),
          hoverinfo: 'text',
        }
      })

  const layout = {
    autosize: true,
    height: 260,
    margin: { l: 44, r: 12, t: 8, b: data.kind === 'scalar' ? 60 : 32 },
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { color: '#ccc', size: 10 },
    showlegend: data.kind === '1d' && plotGroups.length > 1,
    legend: { font: { size: 9 } },
    xaxis: data.kind === 'scalar'
      ? {
          tickvals: plotGroups.map((_, i) => i),
          ticktext: plotGroups.map(g => g.label || '(all)'),
          tickangle: -40,
          gridcolor: '#2a2a4a',
        }
      : { title: { text: 'index', font: { size: 10 } }, gridcolor: '#2a2a4a' },
    yaxis: { title: { text: 'value', font: { size: 10 } }, gridcolor: '#2a2a4a' },
  }

  return (
    <div style={styles.root}>
      <div style={styles.keysRow}>
        {data.schema_keys.map(k => (
          <label key={k} style={styles.keyLabel} title="Checked = kept as a distinct group; unchecked = averaged over">
            <input
              type="checkbox"
              checked={keptKeys.has(k)}
              onChange={() => toggleKey(k)}
              style={{ marginRight: 3 }}
            />
            {k}
          </label>
        ))}
      </div>
      {mismatched.length > 0 && (
        <div style={styles.warning}>
          ⚠ {mismatched.length} group(s) skipped — mismatched array lengths
          within the group (can't average arrays of different sizes).
        </div>
      )}
      {plotGroups.length === 0
        ? <div style={styles.note}>Nothing to plot for this schema level.</div>
        : (
          <Plot
            data={traces}
            layout={layout}
            config={{ displaylogo: false, responsive: true }}
            style={{ width: '100%' }}
            useResizeHandler
          />
        )
      }
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  root: {
    marginTop: 4,
  },
  keysRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 6,
  },
  keyLabel: {
    display: 'flex',
    alignItems: 'center',
    fontSize: 11,
    fontFamily: 'monospace',
    color: '#aaa',
    cursor: 'pointer',
  },
  note: {
    fontSize: 11,
    color: '#666',
    fontStyle: 'italic',
    padding: '4px 0',
  },
  warning: {
    fontSize: 10,
    color: '#fbbf24',
    marginBottom: 4,
  },
}
