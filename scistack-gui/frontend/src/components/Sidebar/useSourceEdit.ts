/**
 * useSourceEdit — shared submit/error handling for panels that rewrite a
 * declaration in source.
 *
 * Every entity edit goes to the real source file (see
 * docs/claude/entity-editability-model.md), so every edit has failure modes
 * a layout.json write never had: the declaration may live outside the
 * entities file (read-only), or the file may have changed on disk since the
 * GUI read it (stale). Both come back as `{ok: false, reason, ...}` with
 * HTTP 200 — they are expected outcomes carrying structured data, not
 * transport errors.
 *
 * **The failure must be shown, never silently reverted.** Before the
 * update_* endpoints were restored, these panels wired their Save buttons to
 * RPCs that no longer existed; every save quietly no-opped and the field
 * appeared to snap back to its old value, which read as a GUI bug rather
 * than a refused write. That is the specific regression this hook exists to
 * prevent — see SweepSettingsPanel's old docstring.
 */

import { useCallback, useState } from 'react'
import { callBackend } from '../../api'

export interface SourceEditResult {
  ok?: boolean
  error?: string
  reason?: string
  file?: string
  line?: number | null
  unchanged?: boolean
}

export interface SourceEditState {
  /** Fire an edit. Resolves true only when source was actually written. */
  submit: (method: string, params: Record<string, unknown>) => Promise<boolean>
  /** Human-readable failure, or '' — render this, don't swallow it. */
  error: string
  /** Where a read-only declaration lives, for a "declared in foo.py:42" hint. */
  readOnlyAt: { file: string; line: number | null } | null
  saving: boolean
  clearError: () => void
}

export function useSourceEdit(): SourceEditState {
  const [error, setError] = useState('')
  const [readOnlyAt, setReadOnlyAt] = useState<{ file: string; line: number | null } | null>(null)
  const [saving, setSaving] = useState(false)

  const clearError = useCallback(() => {
    setError('')
    setReadOnlyAt(null)
  }, [])

  const submit = useCallback(async (method: string, params: Record<string, unknown>) => {
    setSaving(true)
    setError('')
    setReadOnlyAt(null)
    try {
      const res = (await callBackend(method, params)) as SourceEditResult
      if (res?.ok === false) {
        setError(res.error || 'The edit was refused.')
        if (res.reason === 'read_only' && res.file) {
          setReadOnlyAt({ file: res.file, line: res.line ?? null })
        }
        return false
      }
      return true
    } catch (err) {
      // A genuine transport/server failure, as opposed to a refused write.
      setError((err as Error).message || 'Request failed')
      return false
    } finally {
      setSaving(false)
    }
  }, [])

  return { submit, error, readOnlyAt, saving, clearError }
}

/** `foo.py:42`, or just the path when the line is unknown. */
export function formatLocation(at: { file: string; line: number | null }): string {
  const name = at.file.split('/').pop() || at.file
  return at.line ? `${name}:${at.line}` : name
}
