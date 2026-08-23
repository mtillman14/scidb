/**
 * SweepSettingsPanel — shown in the sidebar when a Sweep node is selected.
 *
 * Read-only: values are source-scanned (see
 * docs/claude/code-discovery-categories.md and the "PathInputs, Sweeps, and
 * Submodules read from source" migration). There is no update_sweep on the
 * backend anymore -- editing a Sweep means editing its `scidb.Sweep(...)`
 * declaration in source and hitting "Refresh Code", same as a function body.
 * This panel used to offer a live List/Range editor wired to that
 * since-removed RPC; every Save silently failed, which is why edits looked
 * like they were reverting to the default value.
 */

interface Props {
  label: string
  values: number[]
}

export default function SweepSettingsPanel({ label, values }: Props) {
  return (
    <div style={styles.root}>
      <div style={styles.name}>{label}</div>

      <section style={styles.section}>
        <div style={styles.sectionTitle}>Values</div>
        {values.length === 0 ? (
          <div style={styles.empty}>Not configured yet.</div>
        ) : (
          <div style={styles.currentRow}>
            {values.join(', ')}
            <span style={styles.currentCount}> ({values.length})</span>
          </div>
        )}
        {values.length > 1 && (
          <div style={styles.eachOfHint}>
            Runs as EachOf({values.length} values) — one for_each call per value.
          </div>
        )}
      </section>

      <div style={styles.hint}>
        Edit the <span style={styles.mono}>scidb.Sweep(...)</span> declaration in
        source, then hit 🔄 Refresh Code.
      </div>
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
  eachOfHint: {
    fontSize: 10,
    color: '#65a30d',
    marginTop: 4,
  },
  hint: {
    fontSize: 10,
    color: '#666',
    lineHeight: 1.4,
  },
  mono: {
    fontFamily: 'monospace',
  },
}
