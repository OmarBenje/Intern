import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate } from 'react-router'
import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowLeft02Icon, ArrowRight02Icon, Tick02Icon } from '@hugeicons/core-free-icons'
import { useSession } from '../auth/session-context'
import type { Registration } from '../auth/session-context'
import { authError } from '../auth/errors'
import { ApiError, apiRequest } from '../lib/api'
import { AuthLayout } from '../components/auth/AuthLayout'
import { AuthButton, AuthField, AuthNotice, PasswordField } from '../components/auth/AuthControls'

type FieldErrors = Partial<Record<keyof Registration, string>>
const passwordMessages: Record<string, string> = {
  password_too_short: 'Utilisez au moins 8 caractères.',
  password_too_common: 'Ce mot de passe est trop courant. Choisissez-en un plus original.',
  password_entirely_numeric: 'Le mot de passe ne peut pas contenir uniquement des chiffres.',
  password_too_similar: 'Choisissez un mot de passe différent de vos informations personnelles.',
}
function registrationErrors(cause: unknown): FieldErrors {
  if (!(cause instanceof ApiError) || !cause.details || typeof cause.details !== 'object') return {}
  const details = cause.details as Record<string, unknown>
  const errors: FieldErrors = {}
  for (const field of ['full_name', 'email', 'password'] as const) {
    const entries = details[field] ?? (field === 'password' ? details.password2 ?? details.password1 : undefined)
    if (!Array.isArray(entries) || !entries.length) continue
    errors[field] = entries.map((entry: unknown) => {
      const code = entry && typeof entry === 'object' && 'code' in entry ? String(entry.code) : ''
      if (field === 'password') return passwordMessages[code] ?? 'Vérifiez les règles du mot de passe ci-dessous.'
      return field === 'email' ? code === 'unavailable' ? 'Cette adresse e-mail est déjà utilisée. Connectez-vous ou utilisez une autre adresse.' : 'Saisissez une adresse e-mail valide.' : 'Saisissez votre nom complet.'
    }).filter((value, index, values) => values.indexOf(value) === index).join(' ')
  }
  return errors
}

export function Register() {
  const session = useSession()
  const [values, setValues] = useState<Registration>({ full_name: '', email: '', password: '' })
  const [step, setStep] = useState(0)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fields, setFields] = useState<FieldErrors>({})
  const busy = useRef(false)
  const form = useRef<HTMLFormElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const previousStep = useRef(step)
  useEffect(() => {
    if ((error || Object.keys(fields).length > 0) && !pending) form.current?.querySelector<HTMLElement>('[aria-invalid="true"], [role="alert"]')?.focus()
    else if (previousStep.current !== step) heading.current?.focus()
    previousStep.current = step
  }, [error, fields, pending, step])
  if (session.user) return <Navigate to={session.user.onboarding_step && session.user.onboarding_step !== 'complete' ? `/onboarding/${session.user.onboarding_step}` : '/stages'} replace />
  const update = (field: keyof Registration, value: string) => setValues(previous => ({ ...previous, [field]: value }))
  function back() {
    setError(null); setFields({}); setStep(current => Math.max(0, current - 1))
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy.current || session.loading) return
    if (step === 0) {
      busy.current = true; setPending(true); setError(null); setFields({})
      try {
        const result = await apiRequest<{ available: boolean }>('/auth/email-availability/', { method: 'POST', body: { email: values.email.trim() } })
        if (result.available === false) {
          setFields({ email: 'Cette adresse e-mail est déjà utilisée. Connectez-vous ou utilisez une autre adresse.' })
        } else if (result.available === true) setStep(1)
        else throw new Error('Invalid availability response')
      } catch (cause) {
        const next = registrationErrors(cause)
        setFields(next); setError(next.email ?? authError(cause))
      } finally { busy.current = false; setPending(false) }
      return
    }
    if (step < 2) {
      if (step === 1 && !values.full_name.trim()) {
        setFields({ full_name: 'Saisissez votre nom complet.' }); setError('Indiquez votre nom pour continuer.'); return
      }
      setError(null); setFields({}); setStep(current => current + 1); return
    }
    busy.current = true; setPending(true); setError(null); setFields({})
    try {
      await session.register({ full_name: values.full_name.trim(), email: values.email.trim(), password: values.password })
    } catch (cause) {
      const next = registrationErrors(cause)
      setFields(next)
      if (next.email) setStep(0)
      else if (next.full_name) setStep(1)
      setError(Object.keys(next).length ? 'Votre compte n’a pas été créé. Vérifiez les informations indiquées.'
        : cause instanceof ApiError && cause.status === 409 ? 'La création du compte n’a pas abouti. Essayez de vous connecter ou utilisez une autre adresse e-mail.' : authError(cause))
    } finally { busy.current = false; setPending(false) }
  }
  const titles = [<>Votre prochain<br /><em>chapitre.</em></>, <>Faisons<br /><em>connaissance.</em></>, <>Un espace<br /><em>bien à vous.</em></>]
  return <AuthLayout mode="register">
    <div className="auth-onboarding">
      <div className="auth-registration-nav">
        <span className="auth-kicker">Créer un compte · {step + 1} / 3</span>
        {step > 0 && <button className="auth-previous" type="button" onClick={back} disabled={pending || session.loading}><HugeiconsIcon icon={ArrowLeft02Icon} size={16} strokeWidth={1.5} aria-hidden="true" />Retour</button>}
      </div>
      <ol className="auth-registration-progress" aria-label="Étapes de création du compte">
        {['E-mail', 'Votre nom', 'Mot de passe'].map((label, index) => <li key={label} aria-current={index === step ? 'step' : undefined} data-complete={index < step || undefined}><span className="auth-progress-line" /><span>{index < step && <HugeiconsIcon icon={Tick02Icon} size={14} strokeWidth={2} aria-hidden="true" />}{label}</span></li>)}
      </ol>
      <div key={step} className="auth-stage">
        <header className="auth-heading"><h1 ref={heading} tabIndex={-1}>{titles[step]}</h1></header>
        <form ref={form} className="auth-form" onSubmit={submit} aria-label="Inscription" aria-busy={pending}>
          <fieldset disabled={pending || session.loading}>
            {step === 0 && <AuthField floatingLabel label="Adresse e-mail" name="email" type="email" placeholder="vous@exemple.fr" autoComplete="email" autoCapitalize="none" spellCheck={false} required maxLength={254} value={values.email} onChange={e => update('email', e.target.value)} error={fields.email} />}
            {step === 1 && <AuthField floatingLabel label="Nom complet" name="full_name" placeholder="Prénom Nom" autoComplete="name" required maxLength={240} value={values.full_name} onChange={e => update('full_name', e.target.value)} error={fields.full_name} />}
            {step === 2 && <>
              <input type="hidden" name="username" autoComplete="username" value={values.email} />
              <PasswordField floatingLabel name="password" autoComplete="new-password" required minLength={8} maxLength={4096} hint="8 caractères minimum, pas uniquement des chiffres." value={values.password} onChange={e => update('password', e.target.value)} error={fields.password} />
            </>}
          </fieldset>
          {(error ?? session.error) && <AuthNotice error>{error ?? session.error}</AuthNotice>}
          <AuthButton type="submit" endIcon={<HugeiconsIcon icon={ArrowRight02Icon} size={20} strokeWidth={1.5} />} pending={pending} disabled={session.loading}>{pending ? step === 0 ? 'Vérification de l’adresse…' : 'Création du compte…' : session.loading ? 'Vérification de la session…' : step < 2 ? 'Continuer' : 'Créer mon compte'}</AuthButton>
        </form>
      </div>
    </div>
  </AuthLayout>
}
