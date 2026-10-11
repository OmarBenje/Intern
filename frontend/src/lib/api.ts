export const API_ROOT = (import.meta.env.VITE_API_ROOT || '/api/v1').replace(/\/$/, '')
export function apiUrl(path: `/${string}`) { return `${API_ROOT}${path}` }
export function apiResourceUrl(path: string): string | null {
  const prefix = [API_ROOT, '/api/v1'].find(root => path.startsWith(`${root}/`))
  return prefix === undefined ? null : apiUrl(path.slice(prefix.length) as `/${string}`)
}
let csrfToken: string | null = null

export class ApiError extends Error {
  status: number
  code: string
  details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

export function clearCsrfToken() { csrfToken = null }

async function jsonResponse(response: Response): Promise<unknown> {
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 403) clearCsrfToken()
    const error = data && typeof data === 'object' && 'error' in data ? data.error : null
    const fields = error && typeof error === 'object' ? error as Record<string, unknown> : {}
    throw new ApiError(response.status,
      typeof fields.code === 'string' ? fields.code : 'request_failed',
      typeof fields.message === 'string' ? fields.message : 'Le serveur est temporairement indisponible.',
      fields.details)
  }
  if (!data || typeof data !== 'object') {
    throw new ApiError(response.status, 'invalid_response', 'La réponse du serveur est illisible.')
  }
  return data
}

async function send(path: `/${string}`, options: RequestInit, timeoutMs = 20000): Promise<Response> {
  try {
    return await fetch(apiUrl(path), {
      ...options,
      signal: options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(timeoutMs)]) : AbortSignal.timeout(timeoutMs),
      credentials: 'same-origin', mode: 'same-origin', cache: 'no-store', redirect: 'error',
    })
  } catch (error) {
    if (options.signal?.aborted) throw error
    throw new ApiError(0, 'network_error', 'Impossible de joindre le serveur. Vérifiez votre connexion puis réessayez.')
  }
}

export async function refreshCsrfToken(signal?: AbortSignal): Promise<string> {
  const data = await jsonResponse(await send('/auth/csrf/', { signal }))
  if (!('csrf_token' in (data as object)) || typeof (data as Record<string, unknown>).csrf_token !== 'string') {
    throw new ApiError(0, 'csrf_unavailable', 'Impossible de sécuriser la connexion. Réessayez.')
  }
  csrfToken = (data as { csrf_token: string }).csrf_token
  return csrfToken
}

export async function apiRequest<T>(
  path: `/${string}`,
  options: { method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'; body?: unknown; signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<T> {
  const method = options.method ?? 'GET'
  const headers = new Headers({ Accept: 'application/json' })
  if (method !== 'GET') headers.set('X-CSRFToken', csrfToken ?? await refreshCsrfToken(options.signal))
  const body = options.body instanceof FormData ? options.body
    : options.body === undefined ? undefined : JSON.stringify(options.body)
  if (typeof body === 'string') headers.set('Content-Type', 'application/json')
  const response = await send(path, { method, headers, body, signal: options.signal }, options.timeoutMs)
  if (response.status === 204) return undefined as T
  const data = await jsonResponse(response)
  if ('csrf_token' in (data as object) && typeof (data as Record<string, unknown>).csrf_token === 'string') {
    csrfToken = (data as { csrf_token: string }).csrf_token
  }
  return data as T
}
