/**
 * ClipboardContext — the copy/paste "clipboard" for canvas nodes (to-do
 * #5), shared across scope navigation so copying on one hypothesis's
 * canvas and pasting on another's works.
 *
 * Holds only a REFERENCE (source scope + node ids), not a snapshot of the
 * nodes' data — paste always resolves against live current config/wiring
 * (see scope_service.paste_nodes), same as duplicate_pipeline already
 * does for a whole scope.
 */

import { createContext, useContext, useState } from 'react'

export interface ClipboardSelection {
  sourcePipelineId: string
  nodeIds: string[]
}

interface ClipboardContextType {
  clipboard: ClipboardSelection | null
  setClipboard: (selection: ClipboardSelection | null) => void
}

const ClipboardContext = createContext<ClipboardContextType>({
  clipboard: null,
  setClipboard: () => {},
})

export function ClipboardProvider({ children }: { children: React.ReactNode }) {
  const [clipboard, setClipboard] = useState<ClipboardSelection | null>(null)
  return (
    <ClipboardContext.Provider value={{ clipboard, setClipboard }}>
      {children}
    </ClipboardContext.Provider>
  )
}

export function useClipboard() {
  return useContext(ClipboardContext)
}
