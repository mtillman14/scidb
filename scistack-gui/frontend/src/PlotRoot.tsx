/**
 * PlotRoot — the Plot Studio as a whole webview, rather than a modal.
 *
 * The extension hosts this in its own editor tab (see extension/src/plotPanel.ts)
 * so the pipeline canvas stays visible beside it. The initial target arrives in
 * the injected `window.__SCISTACK_VIEW__`; later ones arrive as
 * `open_plot_studio` notifications, because the tab is REUSED when you plot a
 * second variable rather than piling up tabs.
 */

import { useEffect, useState } from 'react'
import PlotStudio from './components/PlotStudio/PlotStudio'
import { addNotificationHandler } from './api'

export interface PlotViewConfig {
  view: 'plot'
  variable: string | null
  csvPath: string | null
}

interface Target {
  variable: string
  csvPath?: string
}

export default function PlotRoot({ initial }: { initial: PlotViewConfig }) {
  const [target, setTarget] = useState<Target>({
    variable: initial.variable ?? '',
    csvPath: initial.csvPath ?? undefined,
  })

  useEffect(() => {
    return addNotificationHandler(msg => {
      if (msg.method !== 'open_plot_studio') return
      const params = (msg.params ?? {}) as { variable?: string; csv_path?: string }
      setTarget({
        variable: params.variable ?? '',
        csvPath: params.csv_path ?? undefined,
      })
    })
  }, [])

  return (
    <PlotStudio
      // Remount on retarget: a new variable means a new spec, new capabilities
      // and new factors, and carrying the old ones over shows a stale panel
      // for one render.
      key={`${target.csvPath ?? ''}:${target.variable}`}
      variable={target.variable}
      csvPath={target.csvPath}
      embedded
      onClose={() => undefined}
    />
  )
}
