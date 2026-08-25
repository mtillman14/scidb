import { createContext, useContext, useState } from 'react'

export type SidebarItemKind =
  | 'submodule'
  | 'function'
  | 'variable'
  | 'parameter'
  | 'pathInput'

export interface SidebarSelectedItem {
  kind: SidebarItemKind
  /** Registered name for most kinds; for 'submodule' this is the pipeline_id
   *  (stable across renames — see layout.py's write_note key scheme). */
  name: string
  /** Display label, if different from `name` (submodules only). */
  displayLabel?: string
}

interface SidebarSelectionContextType {
  selectedItem: SidebarSelectedItem | null
  setSelectedItem: (item: SidebarSelectedItem | null) => void
}

const SidebarSelectionContext = createContext<SidebarSelectionContextType>({
  selectedItem: null,
  setSelectedItem: () => {},
})

export function SidebarSelectionProvider({ children }: { children: React.ReactNode }) {
  const [selectedItem, setSelectedItem] = useState<SidebarSelectedItem | null>(null)
  return (
    <SidebarSelectionContext.Provider value={{ selectedItem, setSelectedItem }}>
      {children}
    </SidebarSelectionContext.Provider>
  )
}

export function useSidebarSelection() {
  return useContext(SidebarSelectionContext)
}
