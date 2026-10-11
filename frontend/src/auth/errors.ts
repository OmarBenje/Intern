import { ApiError } from '../lib/api'

export function authError(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Une erreur est survenue. Réessayez.'
  if (error.code === 'invalid_credentials') return 'L’adresse e-mail ou le mot de passe est incorrect.'
  if (error.code === 'account_inactive') return 'Votre compte attend la validation du superviseur. Réessayez après son activation.'
  if (error.code === 'invalid_token') return 'Ce lien a expiré ou a déjà été utilisé. Demandez un nouveau lien.'
  if (error.status === 429) return 'Trop de tentatives. Patientez quelques minutes avant de réessayer.'
  if (error.code === 'csrf_failed') return 'La session de sécurité a expiré. Réessayez pour la renouveler.'
  if (error.status === 403) return 'Cette action n’est pas autorisée pour votre compte.'
  if (error.code === 'validation_error') return 'Vérifiez les informations saisies. Le mot de passe doit être suffisamment long, personnel et difficile à deviner.'
  if (error.status >= 500 || error.code === 'invalid_response') return 'Le service est momentanément indisponible. Réessayez dans un instant.'
  return error.message
}
