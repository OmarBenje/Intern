import { useEffect, useState } from 'react'
import { apiRequest } from './api'
import { authError } from '../auth/errors'

/** A query belongs to its URL and attempt; stale responses cannot replace newer data. */
export function useApiQuery<T>(path: `/${string}` | null) {
  const [version, setVersion] = useState(0)
  const [result, setResult] = useState<{ key: string; data: T | null; error: string | null } | null>(null)
  const key = `${path}:${version}`
  useEffect(() => {
    if (!path) return
    const controller = new AbortController()
    apiRequest<T>(path, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setResult({ key, data, error: null }) })
      .catch(cause => { if (!controller.signal.aborted) setResult({ key, data: null, error: authError(cause) }) })
    return () => controller.abort()
  }, [path, key])
  const current = path !== null && result?.key === key ? result : null
  return { data: current?.data ?? null, error: current?.error ?? null, loading: path !== null && !current, reload: () => setVersion(value => value + 1) }
}
