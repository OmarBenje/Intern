import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError, apiRequest, clearCsrfToken } from '../lib/api'

import { SessionContext } from './session-context'
import type { User, Session, Registration } from './session-context'
import { authError } from './errors'

function checkedUser(data: { user: User }): User {
  const user = data.user
  if (!user || typeof user.id !== 'number' || typeof user.username !== 'string' || typeof user.email !== 'string') {
    throw new ApiError(200, 'invalid_response', 'La réponse du serveur est illisible.')
  }
  return user
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session>({ user: null, loading: true, error: null })
  const [version, setVersion] = useState(0)
  const operation = useRef(false)
  const generation = useRef(0)
  useEffect(() => {
    const controller = new AbortController()
    apiRequest<{ user: User }>('/auth/me/', { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setSession({ user: checkedUser(data), loading: false, error: null }) })
      .catch((error) => {
        if (!controller.signal.aborted) setSession({ user: null, loading: false,
          error: error instanceof ApiError && error.status === 401 ? null : authError(error) })
      })
    return () => controller.abort()
  }, [version])

  async function login(username: string, password: string) {
    if (operation.current || session.loading) throw new Error('Session occupée')
    operation.current = true
    generation.current++
    try {
      clearCsrfToken()
      const data = await apiRequest<{ user: User }>('/auth/login/', { method: 'POST', body: { username, password } })
      const user = checkedUser(data)
      setSession({ user, loading: false, error: null })
    } finally { operation.current = false }
  }
  async function register(details: Registration) {
    if (operation.current || session.loading) throw new Error('Session occupée')
    operation.current = true
    generation.current++
    try {
      clearCsrfToken()
      const data = await apiRequest<{ status: string }>('/auth/register/', { method: 'POST', body: details })
      if (data.status !== 'pending') throw new ApiError(201, 'invalid_response', 'La réponse du serveur est illisible.')
      setSession({ user: null, loading: false, error: null })
    } finally { operation.current = false }
  }
  async function logout() {
    if (operation.current) return
    operation.current = true
    generation.current++
    try {
      try { await apiRequest('/auth/logout/', { method: 'POST', body: {} }) }
      catch (error) { if (!(error instanceof ApiError && error.status === 401)) throw error }
      clearCsrfToken()
      setSession({ user: null, loading: false, error: null })
    } finally { operation.current = false }
  }
  async function refresh() {
    if (operation.current) throw new Error('Session occupée')
    const current = ++generation.current
    try {
      const data = await apiRequest<{ user: User }>('/auth/me/')
      if (current !== generation.current) throw new Error('Session modifiée')
      setSession({ user: checkedUser(data), loading: false, error: null })
    } catch (error) {
      if (current === generation.current && error instanceof ApiError && error.status === 401) {
        setSession({ user: null, loading: false, error: null })
      }
      throw error
    }
  }
  return <SessionContext value={{ ...session, login, register, logout, refresh, reload: () => { generation.current++; setSession({ user: null, loading: true, error: null }); setVersion(v => v + 1) } }}>{children}</SessionContext>
}
