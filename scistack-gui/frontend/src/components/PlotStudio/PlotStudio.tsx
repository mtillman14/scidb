/**
 * Plot Studio — interactive plotting for a scidb variable.
 *
 * The panel is deliberately thin. It renders whatever `plot_describe` and
 * `plot_capabilities` return and sends back a spec; every decision about which
 * plot kinds are legal, what the defaults are, and how data is reduced lives in
 * scistackplot (CLAUDE.md NOTE 3). Adding a plot kind or a role should require
 * no change here beyond a label.
 *
 * The controls replace the four mutually-dependent checkbox groups of the
 * original R/Shiny app with one rule: every factor carries exactly one role.
 * That is a single <select> per factor, and the invariant is enforced by the
 * backend rather than by widgets updating each other's options.
 *
 * See docs/claude/plotting-library-design.md.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-cartesian-dist-min'
import { callBackend, isVSCodeMode } from '../../api'

const Plot = createPlotlyComponent(Plotly)

type Role = 'iterate' | 'x' | 'color' | 'facet' | 'aggregate' | 'free'

const ROLE_OPTIONS: { value: Role; label: string; hint: string }[] = [
  { value: 'x', label: 'X axis', hint: 'Position along the x axis' },
  { value: 'color', label: 'Color', hint: 'One coloured series per level' },
  { value: 'facet', label: 'Facet', hint: 'One subplot per level — arrange them under Layout' },
  { value: 'iterate', label: 'Separate figures', hint: 'One whole figure per level' },
  { value: 'aggregate', label: 'Average over', hint: 'Collapse this factor to its mean' },
  { value: 'free', label: 'Replicates', hint: 'Keep as repeated observations' },
]

const KIND_LABELS: Record<string, string> = {
  scatter: 'Scatter',
  strip: 'Strip (jittered)',
  line: 'Lines',
  box: 'Box',
  violin: 'Violin',
  bar: 'Bar + error',
  band: 'Mean + error band',
  heatmap: 'Heatmap',
}

interface FactorInfo {
  name: string
  display: string
  levels: (string | number)[]
  level_count: number
  is_variant: boolean
  /** Levels are the measure's own struct/dict fields, not a condition. */
  is_field: boolean
}

interface TableInfo {
  factors: FactorInfo[]
  measures: { name: string; shape: string }[]
  row_count: number
}

interface KindInfo {
  kind: string
  available: boolean
  reason: string | null
}

interface Capabilities {
  shape: string
  has_replicates: boolean
  default: string
  available: string[]
  kinds: KindInfo[]
}

type MatchOp = 'starts_with' | 'ends_with' | 'contains' | 'not_contains' | 'equals' | 'regex'

const MATCH_OPS: { value: MatchOp; label: string }[] = [
  { value: 'starts_with', label: 'starts with' },
  { value: 'ends_with', label: 'ends with' },
  { value: 'contains', label: 'contains' },
  { value: 'not_contains', label: 'does not contain' },
  { value: 'equals', label: 'is exactly' },
  { value: 'regex', label: 'matches regex' },
]

interface Matcher {
  op: MatchOp
  value: string
  label?: string | null
}

interface FacetOptions {
  /** Grid size. null/absent means "compute me from the other one and the panel count". */
  n_rows?: number | null
  n_cols?: number | null
  /** One entry per row / column slot; a blank value is an unset slot. */
  rows?: Matcher[]
  cols?: Matcher[]
  share_x?: boolean
  share_y?: boolean
}

/**
 * What the backend actually laid out, echoed back on every figure.
 *
 * The panel never computes a grid itself: `rows`/`cols` here are the EFFECTIVE
 * numbers (so setting one of them visibly fills in the other), and
 * `layout_notes` carries anything the layout had to do that the rules did not
 * ask for — a panel spilled out of a claimed cell, a grid grown to fit.
 */
interface GridMeta {
  rows?: number
  cols?: number
  panels?: number
  layout_notes?: string[]
}

interface Spec {
  measures: string[]
  roles: Record<string, Role>
  kind: string
  aggregate?: { statistic: string; error: string }
  facet?: FacetOptions
  variant_policy?: string
  /* Set by the source when it can say which rows are current — a scidb
     variable whose function was edited holds records from both the old and the
     new code. Kept in the spec even while the policy is not 'pin', so toggling
     back restores it. */
  pinned_variant?: Record<string, unknown>
  style?: Record<string, unknown>
}

interface DescribeResponse {
  catalog: { measures: { name: string; shape: string; plottable: boolean }[] }
  variable: string | null
  eligible?: boolean
  reason?: string | null
  table?: TableInfo
  spec?: Spec
  capabilities?: Capabilities
  joinable_with?: string[]
}

interface FigurePayload {
  key: Record<string, unknown>
  label: string
  figure: { data: unknown[]; layout: Record<string, unknown> }
  row_count: number
  downsampled_from: number | null
}

interface Props {
  /** Variable type (scidb) or column name (CSV). Empty picks the default. */
  variable: string
  /** Set to plot a CSV file instead of the project database. */
  csvPath?: string
  /**
   * True when this IS the whole webview (its own VS Code tab) rather than a
   * modal over the DAG: no backdrop, no rounded card, no close button — the
   * tab's own chrome does that.
   */
  embedded?: boolean
  onClose: () => void
}

export default function PlotStudio({ variable, csvPath, embedded = false, onClose }: Props) {
  // Threaded into every call: the backend picks CsvSource or ScidbSource from
  // it, and nothing else about the panel changes (one DataSource protocol).
  const sourceParams = useMemo(
    () => (csvPath ? { csv_path: csvPath } : {}),
    [csvPath]
  )
  const [describe, setDescribe] = useState<DescribeResponse | null>(null)
  const [spec, setSpec] = useState<Spec | null>(null)
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [figures, setFigures] = useState<FigurePayload[]>([])
  const [specError, setSpecError] = useState('')
  const [loadError, setLoadError] = useState('')
  const [busy, setBusy] = useState(false)
  const [code, setCode] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  // Reclaiming space happens at two levels: hiding the controls rail inside
  // the panel, and asking VS Code to enlarge the tab the webview lives in.
  const [controlsHidden, setControlsHidden] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const [canvasHeight, setCanvasHeight] = useState(0)
  const observerRef = useRef<ResizeObserver | null>(null)

  // A CSV has no variable type; name the file instead.
  const title = describe?.variable ?? variable ?? (csvPath ? csvPath.split('/').pop() ?? 'CSV' : '')

  // Plotly needs a definite pixel height, so measure the canvas rather than
  // hardcoding one: a maximized panel should give the figure the extra space.
  //
  // A callback ref, NOT a mount effect: on mount this component renders the
  // "Loading…" branch, which has no canvas, so an effect keyed on [] observed
  // nothing and left the height at 0 — the figure then sat at its 320px floor
  // in a full-height pane.
  const canvasRef = useCallback((node: HTMLDivElement | null) => {
    observerRef.current?.disconnect()
    if (!node || typeof ResizeObserver === 'undefined') return
    setCanvasHeight(node.getBoundingClientRect().height)
    const observer = new ResizeObserver(entries => {
      setCanvasHeight(entries[0].contentRect.height)
    })
    observer.observe(node)
    observerRef.current = observer
  }, [])

  useEffect(() => () => observerRef.current?.disconnect(), [])

  // --- open ---------------------------------------------------------------
  useEffect(() => {
    let cancelled = false
    setDescribe(null)
    setSpec(null)
    setFigures([])
    setLoadError('')
    callBackend('plot_describe', { variable: variable || undefined, ...sourceParams })
      .then(raw => {
        if (cancelled) return
        const response = raw as DescribeResponse
        setDescribe(response)
        if (response.spec) setSpec(response.spec)
        if (response.capabilities) setCapabilities(response.capabilities)
      })
      .catch(err => !cancelled && setLoadError((err as Error).message))
    return () => { cancelled = true }
  }, [variable, sourceParams])

  // --- resolve on every spec change (debounced) ---------------------------
  const timer = useRef<number | null>(null)
  useEffect(() => {
    if (!spec) return
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      setBusy(true)
      Promise.all([
        callBackend('plot_resolve', { spec, ...sourceParams }),
        callBackend('plot_capabilities', { spec, ...sourceParams }).catch(() => null),
      ])
        .then(([resolved, caps]) => {
          const result = resolved as { ok: boolean; error: string | null; figures: FigurePayload[] }
          setSpecError(result.ok ? '' : (result.error ?? 'Could not resolve this plot.'))
          setFigures(result.figures ?? [])
          if (caps) setCapabilities(caps as Capabilities)
        })
        .catch(err => setSpecError((err as Error).message))
        .finally(() => setBusy(false))
    }, 180)
    return () => { if (timer.current) window.clearTimeout(timer.current) }
  }, [spec, sourceParams])

  // --- spec edits ---------------------------------------------------------
  const setRole = useCallback((factor: string, role: Role) => {
    setSpec(prev => (prev ? { ...prev, roles: { ...prev.roles, [factor]: role } } : prev))
  }, [])

  const setKind = useCallback((kind: string) => {
    setSpec(prev => (prev ? { ...prev, kind } : prev))
  }, [])

  const setAggregate = useCallback((patch: { statistic?: string; error?: string }) => {
    setSpec(prev => prev && ({
      ...prev,
      aggregate: { statistic: 'mean', error: 'sd', ...(prev.aggregate ?? {}), ...patch },
    }))
  }, [])

  const setFacet = useCallback((patch: Partial<FacetOptions>) => {
    setSpec(prev => (prev ? { ...prev, facet: { ...(prev.facet ?? {}), ...patch } } : prev))
  }, [])

  /**
   * Edit the rule in one grid slot, padding the array out to reach it.
   *
   * The slots ARE the grid — there is no add/remove, because the number of rows
   * and columns is the thing the user set. A slot left blank claims nothing and
   * takes whatever is left over, in order (scistackplot's Matcher.is_blank).
   */
  const setRuleAt = useCallback(
    (axis: 'rows' | 'cols', index: number, patch: Partial<Matcher>) => {
      setSpec(prev => {
        if (!prev) return prev
        const rules = [...(prev.facet?.[axis] ?? [])]
        while (rules.length <= index) rules.push({ op: 'contains', value: '' })
        rules[index] = { ...rules[index], ...patch }
        return { ...prev, facet: { ...(prev.facet ?? {}), [axis]: rules } }
      })
    },
    []
  )

  const setVariantPolicy = useCallback((policy: string) => {
    setSpec(prev => (prev ? { ...prev, variant_policy: policy } : prev))
  }, [])

  const factors = describe?.table?.factors ?? []
  const hasVariants = useMemo(() => factors.some(f => f.is_variant), [factors])
  // 'pin' is only a legal policy when something was handed to us to pin on —
  // validate() refuses PIN with an empty pinned_variant.
  const canPin = Boolean(
    spec?.pinned_variant && Object.keys(spec.pinned_variant).length > 0
  )
  const summarizing = spec?.kind === 'bar' || spec?.kind === 'band'
  const faceted = Object.values(spec?.roles ?? {}).includes('facet')

  // The grid the backend actually built. Read back rather than recomputed: the
  // "set one, the other follows" arithmetic is grid_shape_for's, in
  // scistackplot, and a second copy of it here would be the thing that drifts.
  const gridMeta = (figures[0]?.figure?.layout?.meta ?? {}) as GridMeta
  const effRows = Math.max(1, gridMeta.rows ?? 1)
  const effCols = Math.max(1, gridMeta.cols ?? 1)
  const layoutNotes = gridMeta.layout_notes ?? []

  // --- export -------------------------------------------------------------
  const handleExport = useCallback(() => {
    if (!spec) return
    setNotice('')
    callBackend('plot_export', { spec, ...sourceParams })
      .then(raw => setCode((raw as { source: string }).source))
      .catch(err => setNotice(`Export failed: ${(err as Error).message}`))
  }, [spec, sourceParams])

  const handleSave = useCallback(async () => {
    if (!spec) return
    setNotice('')
    const defaultName = `${title || 'figure'}.png`.replace(/[^\w.-]+/g, '_')
    try {
      let path: string | null = null
      if (isVSCodeMode) {
        const picked = await callBackend('pick_save_path', { defaultName })
        path = (picked as { path: string | null }).path
        if (!path) return  // dialog cancelled
      } else {
        path = window.prompt('Save the figure as:', defaultName)
        if (!path) return
      }
      setNotice('Rendering at full resolution…')
      const result = (await callBackend('plot_save_figure', { spec, path, ...sourceParams })) as {
        ok: boolean
        error: string | null
        files: string[]
      }
      if (!result.ok) setNotice(`Could not save: ${result.error}`)
      else setNotice(`Saved ${result.files.join(', ')}`)
    } catch (err) {
      setNotice(`Could not save: ${(err as Error).message}`)
    }
  }, [spec, sourceParams, title])

  const handleAddToPipeline = useCallback(() => {
    if (!spec) return
    setNotice('Writing endpoint…')
    callBackend('plot_add_to_pipeline', { spec })
      .then(raw => {
        const result = raw as { ok?: boolean; error?: string; function_name?: string; file?: string }
        if (result.error) setNotice(`Could not add: ${result.error}`)
        else setNotice(`Added ${result.function_name} to ${result.file}. Wire it up on the canvas.`)
      })
      .catch(err => setNotice(`Could not add: ${(err as Error).message}`))
  }, [spec])

  // --- render -------------------------------------------------------------
  if (loadError) {
    return (
      <Shell variable={title} onClose={onClose} embedded={embedded}>
        <div style={styles.error}>Could not open the plot panel: {loadError}</div>
      </Shell>
    )
  }
  if (!describe) {
    return (
      <Shell variable={title} onClose={onClose} embedded={embedded}>
        <div style={styles.note}>Loading…</div>
      </Shell>
    )
  }
  if (describe.eligible === false) {
    // The empty state the design doc insists on: say why, never draw blank axes.
    return (
      <Shell variable={title} onClose={onClose} embedded={embedded}>
        <div style={styles.note}>{describe.reason}</div>
      </Shell>
    )
  }

  const gridRows = (figures[0]?.figure?.layout?.meta as { rows?: number } | undefined)?.rows ?? 1
  const available = figures.length > 1
    ? Math.round(canvasHeight / 2) - 28
    : canvasHeight - 16
  // Fill the pane, but never squeeze a tall facet grid: each row needs room for
  // its own tick labels and the next row's title.
  const figureHeight = Math.max(320, gridRows * 240, available)

  return (
    <Shell
      variable={title}
      onClose={onClose}
      embedded={embedded}
      panelRef={panelRef}
      controlsHidden={controlsHidden}
      onToggleControls={() => setControlsHidden(v => !v)}
    >
      <div style={styles.body}>
        <div
          style={{
            ...styles.controls,
            ...(controlsHidden ? styles.controlsHidden : null),
          }}
        >
          <Section title="Measure">
            <div style={styles.readonlyValue}>
              {variable}
              <span style={styles.shapeTag}>{capabilities?.shape}</span>
            </div>
          </Section>

          <Section title="Factors">
            <div style={styles.hint}>Each factor does exactly one thing.</div>
            {factors.map(factor => (
              <label key={factor.name} style={styles.factorRow}>
                <span style={styles.factorName}>
                  {factor.display}
                  {factor.is_variant && <span style={styles.variantTag} title="A pipeline variant, not a replicate">variant</span>}
                  {factor.is_field && <span style={styles.fieldTag} title="The fields of this struct/dict variable — one subplot each by default">fields</span>}
                  <span style={styles.levelCount}>{factor.level_count}</span>
                </span>
                <select
                  value={spec?.roles?.[factor.name] ?? 'free'}
                  onChange={e => setRole(factor.name, e.target.value as Role)}
                  style={styles.select}
                >
                  {ROLE_OPTIONS.map(option => (
                    <option key={option.value} value={option.value} title={option.hint}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </Section>

          <Section title="Plot type">
            {(capabilities?.kinds ?? []).map(info => (
              <label
                key={info.kind}
                style={{ ...styles.kindRow, opacity: info.available ? 1 : 0.45 }}
                title={info.reason ?? ''}
              >
                <input
                  type="radio"
                  name="plot-kind"
                  checked={spec?.kind === info.kind}
                  disabled={!info.available}
                  onChange={() => setKind(info.kind)}
                  style={{ marginRight: 6 }}
                />
                {KIND_LABELS[info.kind] ?? info.kind}
              </label>
            ))}
          </Section>

          {faceted && (
            <Section title="Layout">
              <div style={styles.hint}>
                Set rows or columns — the other follows from the number of
                subplots. Then name what belongs in each one; blank takes
                whatever is left, in order.
              </div>
              <div style={styles.gridSizeRow}>
                <GridSizeInput
                  label="N rows"
                  value={spec?.facet?.n_rows ?? null}
                  effective={effRows}
                  onChange={n => setFacet({ n_rows: n })}
                />
                <GridSizeInput
                  label="N columns"
                  value={spec?.facet?.n_cols ?? null}
                  effective={effCols}
                  onChange={n => setFacet({ n_cols: n })}
                />
              </div>

              <RuleSlots
                title="Rows"
                count={effRows}
                rules={spec?.facet?.rows ?? []}
                onEdit={(i, patch) => setRuleAt('rows', i, patch)}
              />
              <RuleSlots
                title="Columns"
                count={effCols}
                rules={spec?.facet?.cols ?? []}
                onEdit={(i, patch) => setRuleAt('cols', i, patch)}
              />

              {/* Never let the layout quietly disobey a rule: if a subplot had
                  to move, or the grid had to grow, say which and why. */}
              {layoutNotes.map((note, index) => (
                <div key={index} style={styles.layoutNote}>{note}</div>
              ))}
            </Section>
          )}

          {summarizing && (
            <Section title="Summary">
              <label style={styles.factorRow}>
                <span style={styles.factorName}>Centre</span>
                <select
                  value={spec?.aggregate?.statistic ?? 'mean'}
                  onChange={e => setAggregate({ statistic: e.target.value })}
                  style={styles.select}
                >
                  <option value="mean">Mean</option>
                  <option value="median">Median</option>
                </select>
              </label>
              <label style={styles.factorRow}>
                <span style={styles.factorName}>Spread</span>
                <select
                  value={spec?.aggregate?.error ?? 'sd'}
                  onChange={e => setAggregate({ error: e.target.value })}
                  style={styles.select}
                >
                  <option value="sd">SD</option>
                  <option value="sem">SEM</option>
                  <option value="ci95">95% CI</option>
                  <option value="iqr">IQR</option>
                  <option value="none">None</option>
                </select>
              </label>
            </Section>
          )}

          {hasVariants && (
            <Section title="Variants">
              <div style={styles.hint}>
                Levels here are different pipeline variants, not repeated measurements.
              </div>
              {canPin && spec?.variant_policy === 'pin' && (
                /* Never let a pin hide data silently — that is the whole bug
                   this stage exists to fix. Say what is being left out and how
                   to get it back. */
                <div style={styles.pinNote}>
                  Showing only the newest code version at each schema location.
                  Older versions are still stored — switch to “Keep separate” to
                  plot them alongside.
                </div>
              )}
              <select
                value={spec?.variant_policy ?? 'facet'}
                onChange={e => setVariantPolicy(e.target.value)}
                style={styles.select}
              >
                {/* Only offered when the source supplied something to pin;
                    PIN without a pinned_variant is refused by validate. */}
                {canPin && <option value="pin">Show only the current code version</option>}
                <option value="facet">Keep separate (assign a role)</option>
                <option value="pool">Pool them (average across variants)</option>
              </select>
            </Section>
          )}

          <div style={{ ...styles.actions, flexWrap: 'wrap' }}>
            <button
              type="button"
              style={styles.button}
              onClick={handleSave}
              title="Render with matplotlib at full resolution — the same figure the pipeline would produce"
            >
              Save image
            </button>
            <button type="button" style={styles.button} onClick={handleExport}>
              Export code
            </button>
            <button type="button" style={styles.primaryButton} onClick={handleAddToPipeline}>
              Add to pipeline
            </button>
          </div>
          {notice && <div style={styles.notice}>{notice}</div>}
        </div>

        <div style={styles.canvas} ref={canvasRef}>
          {specError && <div style={styles.specError}>{specError}</div>}
          {busy && <div style={styles.note}>Resolving…</div>}
          {!specError && figures.length === 0 && !busy && (
            <div style={styles.note}>Nothing to plot with these settings.</div>
          )}
          {figures.map((figure, index) => (
            <div
              key={figure.label || index}
              style={{
                ...styles.figureBlock,
                ...(figures.length === 1 ? { height: '100%' } : null),
              }}
            >
              {figure.label && <div style={styles.figureLabel}>{figure.label}</div>}
              {figure.downsampled_from && (
                <div style={styles.downsampleNote}>
                  Showing a reduced view of {figure.downsampled_from.toLocaleString()} points —
                  the exported figure uses every point.
                </div>
              )}
              <Plot
                data={figure.figure.data}
                layout={{
                  ...figure.figure.layout,
                  autosize: true,
                  height: figureHeight,
                  paper_bgcolor: 'transparent',
                  plot_bgcolor: 'transparent',
                  font: { color: '#ccc', size: 11 },
                }}
                config={{
                  displaylogo: false,
                  responsive: true,
                  // A webview cannot download; "Save image" does it server-side.
                  modeBarButtonsToRemove: isVSCodeMode ? ['toImage'] : [],
                }}
                style={{ width: '100%' }}
                useResizeHandler
              />
            </div>
          ))}
        </div>
      </div>

      {code !== null && (
        <div style={styles.codeOverlay} onClick={() => setCode(null)}>
          <pre style={styles.code} onClick={e => e.stopPropagation()}>{code}</pre>
        </div>
      )}
    </Shell>
  )
}

interface ShellProps {
  variable: string
  onClose: () => void
  embedded?: boolean
  children: React.ReactNode
  panelRef?: React.RefObject<HTMLDivElement>
  controlsHidden?: boolean
  onToggleControls?: () => void
}

function Shell({
  variable,
  onClose,
  embedded,
  children,
  panelRef,
  controlsHidden,
  onToggleControls,
}: ShellProps) {
  return (
    // No overlay click-to-close: a stray click on the backdrop while dragging a
    // plotly selection would throw the panel away mid-exploration.
    <div style={embedded ? styles.embeddedRoot : styles.overlay}>
      <div ref={panelRef} style={embedded ? styles.embeddedPanel : styles.panel}>
        <div style={styles.header}>
          {/* The toggle sits over the rail it collapses, so the control is
              where the thing it controls is. */}
          <div style={styles.headerLeft}>
            {onToggleControls && (
              <button
                type="button"
                style={styles.headerButton}
                onClick={onToggleControls}
                title="Give the figure the controls' width"
              >
                {controlsHidden ? '❯ Controls' : '❮ Controls'}
              </button>
            )}
            <span style={styles.title}>Plot — {variable}</span>
          </div>
          <div style={styles.headerActions}>
            {!embedded && (
              <button type="button" style={styles.close} onClick={onClose}>✕</button>
            )}
          </div>
        </div>
        {children}
      </div>
    </div>
  )
}

interface GridSizeInputProps {
  label: string
  /** What the user pinned, or null when this dimension is computed. */
  value: number | null
  /** What the backend laid out — shown as a placeholder while unpinned. */
  effective: number
  onChange: (value: number | null) => void
}

/**
 * One dimension of the facet grid.
 *
 * An empty box is not "1", it is "you decide": the backend computes it from the
 * other dimension and the subplot count, and the result shows through as the
 * placeholder. That is what makes "I set 2 columns" answer "so, 3 rows".
 */
function GridSizeInput({ label, value, effective, onChange }: GridSizeInputProps) {
  return (
    <label style={styles.gridSizeField}>
      <span style={styles.gridSizeLabel}>{label}</span>
      <input
        type="number"
        min={1}
        value={value ?? ''}
        placeholder={String(effective)}
        onChange={e => onChange(e.target.value ? Number(e.target.value) : null)}
        title={value === null ? `Computed: ${effective}. Type a number to pin it.` : 'Clear to compute automatically'}
        style={{
          ...styles.select,
          width: 56,
          ...(value === null ? styles.gridSizeAuto : null),
        }}
      />
    </label>
  )
}

interface RuleSlotsProps {
  title: string
  /** Number of slots = the grid dimension. Comes from the rendered layout. */
  count: number
  rules: Matcher[]
  onEdit: (index: number, patch: Partial<Matcher>) => void
}

/**
 * One axis of the facet grid, one editor per slot.
 *
 * Fixed length, not a list with +/- buttons: the grid already has a known
 * number of rows and columns, so a rule is a property OF row 2, not an extra
 * row. Each slot claims the panels whose name it matches; a blank slot takes
 * whatever is left over, in order, and anything matching no slot at all lands
 * in a trailing "other" row/column rather than disappearing.
 */
function RuleSlots({ title, count, rules, onEdit }: RuleSlotsProps) {
  const singular = title.replace(/s$/, '')
  return (
    <div style={styles.ruleList}>
      <div style={styles.ruleTitle}>{title}</div>
      {Array.from({ length: count }, (_, index) => {
        const rule = rules[index] ?? { op: 'contains' as MatchOp, value: '' }
        return (
          <div key={index} style={styles.ruleRow}>
            <span style={styles.slotIndex}>{singular} {index + 1}</span>
            <select
              value={rule.op}
              onChange={e => onEdit(index, { op: e.target.value as MatchOp })}
              style={{ ...styles.select, flex: '0 0 88px' }}
            >
              {MATCH_OPS.map(op => (
                <option key={op.value} value={op.value}>{op.label}</option>
              ))}
            </select>
            <input
              value={rule.value}
              onChange={e => onEdit(index, { value: e.target.value })}
              placeholder="anything"
              style={{ ...styles.select, flex: 1, minWidth: 0 }}
            />
          </div>
        )
      })}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={styles.section}>
      <div style={styles.sectionTitle}>{title}</div>
      {children}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
  },
  // Own-tab mode: fill the webview exactly, no card, no backdrop.
  embeddedRoot: { position: 'absolute', inset: 0, background: '#16162a' },
  embeddedPanel: {
    width: '100%', height: '100%', background: '#16162a',
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  panel: {
    width: '96vw', height: '94vh', background: '#16162a',
    border: '1px solid #3a3a5a', borderRadius: 8,
    display: 'flex', flexDirection: 'column', overflow: 'hidden',
  },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '8px 12px', borderBottom: '1px solid #2a2a4a', background: '#1a1a2e',
  },
  title: { color: '#eee', fontSize: 13, fontWeight: 600 },
  close: {
    background: 'transparent', border: 'none', color: '#888',
    cursor: 'pointer', fontSize: 14,
  },
  body: { display: 'flex', flex: 1, minHeight: 0 },
  controls: {
    width: 260, padding: 12, borderRight: '1px solid #2a2a4a',
    overflowY: 'auto', flexShrink: 0,
  },
  // Collapsed rather than unmounted: the control state survives the toggle.
  controlsHidden: {
    width: 0, padding: 0, borderRight: 'none', overflow: 'hidden',
  },
  headerActions: { display: 'flex', alignItems: 'center', gap: 6 },
  headerLeft: { display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 },
  ruleList: { marginTop: 6 },
  ruleTitle: { fontSize: 10, color: '#999', marginBottom: 3 },
  ruleRow: { display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 },
  slotIndex: { fontSize: 10, color: '#888', flex: '0 0 52px' },
  gridSizeRow: { display: 'flex', gap: 8, marginBottom: 4 },
  gridSizeField: { display: 'flex', alignItems: 'center', gap: 4 },
  gridSizeLabel: { fontSize: 11, color: '#bbb' },
  // An unpinned dimension reads as derived, not as something the user typed.
  gridSizeAuto: { color: '#8a8aa8', fontStyle: 'italic' },
  layoutNote: {
    fontSize: 10, color: '#e0b050', marginTop: 6, lineHeight: 1.4,
  },
  headerButton: {
    background: '#22223a', color: '#ccc', border: '1px solid #3a3a5a',
    borderRadius: 4, cursor: 'pointer', fontSize: 11, padding: '2px 8px',
  },
  canvas: { flex: 1, padding: 12, overflowY: 'auto' },
  section: { marginBottom: 16 },
  sectionTitle: {
    fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.6,
    color: '#7b68ee', marginBottom: 6, fontWeight: 700,
  },
  hint: { fontSize: 10, color: '#777', marginBottom: 6, fontStyle: 'italic' },
  pinNote: {
    fontSize: 10, lineHeight: 1.45, color: '#d9c48f', marginBottom: 6,
    padding: '5px 7px', background: '#221c0c', borderLeft: '2px solid #d9b45f',
  },
  factorRow: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    gap: 6, marginBottom: 5,
  },
  factorName: {
    fontSize: 11, fontFamily: 'monospace', color: '#ccc',
    display: 'flex', alignItems: 'center', gap: 4, minWidth: 0,
  },
  levelCount: {
    fontSize: 9, color: '#666', background: '#22223a',
    borderRadius: 8, padding: '0 5px',
  },
  variantTag: {
    fontSize: 8, color: '#fbbf24', border: '1px solid #6b5a1a',
    borderRadius: 3, padding: '0 3px', textTransform: 'uppercase',
  },
  fieldTag: {
    fontSize: 8, color: '#67e8f9', border: '1px solid #1a5a6b',
    borderRadius: 3, padding: '0 3px', textTransform: 'uppercase',
  },
  shapeTag: { fontSize: 9, color: '#67e8f9', marginLeft: 6 },
  readonlyValue: { fontSize: 12, fontFamily: 'monospace', color: '#eee' },
  select: {
    background: '#22223a', color: '#ddd', border: '1px solid #3a3a5a',
    borderRadius: 4, fontSize: 11, padding: '2px 4px', maxWidth: 130,
  },
  kindRow: {
    display: 'flex', alignItems: 'center', fontSize: 11,
    color: '#ccc', marginBottom: 3, cursor: 'pointer',
  },
  actions: { display: 'flex', gap: 6, marginTop: 8 },
  button: {
    flex: 1, padding: '5px 8px', background: '#22223a', color: '#ccc',
    border: '1px solid #3a3a5a', borderRadius: 4, cursor: 'pointer', fontSize: 11,
  },
  primaryButton: {
    flex: 1, padding: '5px 8px', background: '#7b68ee', color: '#fff',
    border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 11, fontWeight: 600,
  },
  notice: { fontSize: 10, color: '#67e8f9', marginTop: 6 },
  note: { fontSize: 12, color: '#777', fontStyle: 'italic', padding: 8 },
  error: { fontSize: 12, color: '#f87171', padding: 12 },
  specError: {
    fontSize: 11, color: '#fbbf24', background: '#2a2416',
    border: '1px solid #6b5a1a', borderRadius: 4, padding: 8, marginBottom: 8,
  },
  figureBlock: { marginBottom: 14 },
  figureLabel: {
    fontSize: 11, fontFamily: 'monospace', color: '#aaa', marginBottom: 2,
  },
  downsampleNote: { fontSize: 10, color: '#fbbf24', marginBottom: 4 },
  codeOverlay: {
    position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.75)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40,
  },
  code: {
    background: '#0e0e1a', color: '#ddd', border: '1px solid #3a3a5a',
    borderRadius: 6, padding: 16, fontSize: 11, fontFamily: 'monospace',
    maxHeight: '80%', maxWidth: '80%', overflow: 'auto', whiteSpace: 'pre',
  },
}
