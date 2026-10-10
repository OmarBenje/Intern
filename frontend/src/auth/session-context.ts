import { createContext, useContext } from 'react'

export type User = { id: number; username: string; email: string; full_name?: string; role?: 'candidate' | 'recruiter'; onboarding_step?: 'verify' | 'resume' | 'address' | 'work-eligibility' | 'complete' }
export type Registration = { full_name: string; email: string; password: string; role?: 'candidate' | 'recruiter' }
export type Session = { user: User | null; loading: boolean; error: string | null }
type SessionContextValue = Session & {
  login: (username: string, password: string) => Promise<void>
  register: (details: Registration) => Promise<void>
  logout: () => Promise<void>
  reload: () => void
  refresh: () => Promise<void>
}
export const SessionContext = createContext<SessionContextValue | null>(null)

export function useSession() {
  const context = useContext(SessionContext)
  if (!context) throw new Error('SessionProvider manquant')
  return context
}
