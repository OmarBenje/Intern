import { ApiError, apiRequest } from '../../lib/api'
import { authError } from '../../auth/errors'

export type Company = { full_name: string; company_name: string; siren: string; website_url: string; linkedin_url: string; verification_status: 'unverified' | 'pending' | 'verified' | 'rejected'; email_verified: boolean }
export type Job = { id: number; title: string; department: string; contract_type: string; location: string; country_code: string; work_mode: string; salary: string; description: string; skills: string; education: string; languages: string; status: string; origin: string; published_at: string | null; applicant_count: number }
export type Applicant = { id: number; job_id: number; job_title: string; stage: string; match_score: number | null; ai_summary: string; rejection_reason: string; interview_at: string | null; resume_url: string | null; profile: { full_name: string; email: string; headline?: string; skills?: string[]; experiences?: { title: string; company_name: string; description: string }[]; education?: { institution: string; degree: string; description: string }[]; projects?: { title: string; description: string }[] } }
export type Collection<T> = { results: T[]; count: number; page: number; page_size: number }
export const statuses: Record<string, string> = { draft: 'Brouillon', active: 'Active', paused: 'Suspendue', archived: 'Archivée', unverified: 'À compléter', pending: 'En cours de validation', verified: 'Vérifiée', rejected: 'À corriger' }
export const contracts: Record<string, string> = { internship: 'Stage', apprenticeship: 'Alternance', employment: 'CDI' }
export const stages: Record<string, string> = { new: 'Nouveaux', recommended: 'Recommandés IA', review: 'En revue', interview: 'Entretien', accepted: 'Acceptés', rejected: 'Refusés' }
export function recruiterError(error: unknown) {
  if (!(error instanceof ApiError)) return 'Une erreur est survenue. Réessayez.'
  if (error.code === 'validation_error') {
    const details = error.details && typeof error.details === 'object' ? Object.values(error.details).flat().filter(value => typeof value === 'string') : []
    return details.length ? details.join(' ') : 'Vérifiez les informations saisies.'
  }
  if (['network_error', 'request_failed', 'csrf_failed'].includes(error.code) || error.status >= 500 || error.status === 429) return authError(error)
  return error.message
}
export const recruiterRequest = <T,>(path: `/${string}`, options?: Parameters<typeof apiRequest>[1]) => apiRequest<T>(`/recruiter${path}`, options)
