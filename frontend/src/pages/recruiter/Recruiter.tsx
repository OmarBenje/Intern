import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { useSession } from '../../auth/session-context'
import { useApiQuery } from '../../lib/useApiQuery'
import { AuthButton, AuthField, AuthNotice } from '../../components/auth/AuthControls'
import { Badge, Page, QueryState } from './shared'
import { recruiterRequest, recruiterError, statuses } from './data'
import type { Company, Applicant } from './data'

export function RecruiterDashboard() {
  const { user } = useSession()
  const query = useApiQuery<{ company: Company; counts: { active_jobs: number; applications: number; average_match: number | null; views: number }; activity: Applicant[] }>('/recruiter/dashboard/')
  const data = query.data
  return <Page title={`Bonjour ${user?.full_name?.split(' ')[0] || 'à vous'}.`} description="Vos offres, vos candidatures et les rencontres à venir." action={<Link className="dashboard-button dashboard-button--primary" to="/recruiter/jobs/new">+ Créer une offre</Link>}>
    <QueryState {...query} />
    {data && <>
      {data.company.verification_status !== 'verified' && <div className="recruiter-notice"><Badge>{statuses[data.company.verification_status]}</Badge><span>Votre entreprise doit être validée avant la publication des offres.</span><Link to="/recruiter/verify">Voir mon entreprise</Link></div>}
      <div className="recruiter-metrics">{[['Offres actives', data.counts.active_jobs], ['Candidatures reçues', data.counts.applications], ['Matching IA moyen', data.counts.average_match === null ? '—' : `${Math.round(data.counts.average_match)} %`], ['Vues des annonces', data.counts.views]].map(([label, value]) => <section className="recruiter-card" key={label}><p>{label}</p><strong className="recruiter-metric">{value}</strong></section>)}</div>
      <section className="recruiter-card"><h2>Dernières candidatures</h2>{data.activity.length ? data.activity.map(item => <Link className="recruiter-activity" key={item.id} to={`/recruiter/candidates/${item.id}`}><span><strong>{item.profile.full_name}</strong><small>{item.job_title}</small></span><Badge>{item.match_score === null ? 'Non évalué' : `${item.match_score} % de match`}</Badge></Link>) : <div className="recruiter-empty"><h3>Les belles rencontres commencent ici.</h3><p>Préparez votre première offre. Les candidatures reçues apparaîtront dans cet espace.</p><Link to="/recruiter/jobs/new">Créer ma première offre →</Link></div>}</section>
      <div className="recruiter-grid"><Link className="recruiter-card recruiter-shortcut" to="/recruiter/jobs"><h2>Vos opportunités</h2><p>Créez, modifiez et suivez vos offres.</p><span>Gérer mes offres →</span></Link><Link className="recruiter-card recruiter-shortcut" to="/recruiter/integrations"><h2>Votre ATS, au même endroit.</h2><p>Préparez la connexion de vos outils de recrutement.</p><span>Découvrir les intégrations →</span></Link></div>
    </>}
  </Page>
}

export function CompanyVerification() {
  const query = useApiQuery<Company>('/recruiter/verify/')
  return <Page title="Faisons connaissance." description="Quelques informations pour créer votre espace entreprise."><QueryState {...query} />{query.data && <VerificationForm key={`${query.data.email_verified}-${query.data.verification_status}`} company={query.data} reload={query.reload} />}</Page>
}
function VerificationForm({ company, reload }: { company: Company; reload: () => void }) {
  const session = useSession()
  const navigate = useNavigate()
  const [values, setValues] = useState({ company_name: company.company_name, siren: company.siren, website_url: company.website_url, linkedin_url: company.linkedin_url })
  const [code, setCode] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  async function sendCode() {
    setPending(true); setError(null)
    try { await recruiterRequest('/verify/send-code/', { method: 'POST', body: {} }); setMessage('Un code valable 10 minutes a été envoyé à votre adresse professionnelle.') }
    catch (cause) { setError(recruiterError(cause)) }
    finally { setPending(false) }
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); setPending(true); setError(null)
    try {
      if (!company.email_verified) { await recruiterRequest('/verify/code/', { method: 'POST', body: { code } }); reload() }
      else { await recruiterRequest('/verify/', { method: 'POST', body: values }); await session.refresh(); navigate('/recruiter/dashboard') }
    } catch (cause) { setError(recruiterError(cause)) }
    finally { setPending(false) }
  }
  const submitted = ['pending', 'verified'].includes(company.verification_status)
  return <section className="recruiter-card recruiter-form-card"><ol className="recruiter-steps"><li aria-current={!company.email_verified ? 'step' : undefined}>01 · E-mail professionnel</li><li aria-current={company.email_verified && !submitted ? 'step' : undefined}>02 · Votre entreprise</li><li aria-current={submitted ? 'step' : undefined}>03 · Vérification</li></ol>
    {submitted ? <><Badge>{statuses[company.verification_status]}</Badge><h2>{company.company_name}</h2><p>{company.verification_status === 'pending' ? 'Votre compte est en cours de validation par notre équipe. Vous pouvez déjà préparer vos offres.' : 'Votre entreprise est vérifiée. Vous pouvez publier vos offres.'}</p><p>SIREN : {company.siren}</p><Link className="dashboard-button" to="/recruiter/dashboard">Accéder à mon espace</Link></> : <form className="recruiter-form" onSubmit={submit}>
      {company.verification_status === 'rejected' && <AuthNotice error>Les informations de votre entreprise doivent être corrigées avant un nouvel examen.</AuthNotice>}
      <fieldset disabled={pending}>{!company.email_verified ? <><h2>Vérifiez votre e-mail professionnel</h2><p>{session.user?.email}</p><button className="dashboard-button" type="button" onClick={sendCode}>Envoyer un code</button><AuthField label="Code à 6 chiffres" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={e => setCode(e.target.value)} /></> : <><h2>Votre entreprise</h2>{(['company_name', 'siren', 'website_url', 'linkedin_url'] as const).map(key => <AuthField key={key} label={{ company_name: 'Nom de l’entreprise', siren: 'Numéro SIREN', website_url: 'Site web de l’entreprise (HTTPS)', linkedin_url: 'Page LinkedIn (facultatif)' }[key]} name={key} required={key !== 'linkedin_url'} type={key.includes('url') ? 'url' : 'text'} pattern={key === 'siren' ? '[0-9]{9}' : undefined} maxLength={key === 'siren' ? 9 : key === 'company_name' ? 240 : 2048} value={values[key]} onChange={e => setValues({ ...values, [key]: e.target.value })} />)}</>}</fieldset>
      {message && <AuthNotice>{message}</AuthNotice>}{error && <AuthNotice error>{error}</AuthNotice>}<AuthButton type="submit" pending={pending}>{company.email_verified ? 'Soumettre mon entreprise' : 'Valider mon e-mail'}</AuthButton>
    </form>}
  </section>
}

const providers = [['greenhouse', 'Greenhouse'], ['lever', 'Lever'], ['workday', 'Workday'], ['ashby', 'Ashby'], ['smartrecruiters', 'SmartRecruiters'], ['wttj', 'Welcome to the Jungle'], ['feed', 'Flux XML / JSON']]
type Integration = { provider: string; url: string; status: string }
export function ATSIntegrations() {
  const query = useApiQuery<{ results: Integration[] }>('/recruiter/integrations/')
  return <Page title="Vos outils, réunis." description="Renseignez le portail carrière ou le flux de votre entreprise pour préparer son intégration."><QueryState {...query} /><p className="recruiter-notice">La connexion et la synchronisation nécessitent une activation par l’équipe Intern. Enregistrer une URL ne lance pas d’import.</p>{query.data && <div className="recruiter-grid">{providers.map(([key, name]) => <IntegrationCard key={key} provider={key} name={name} integration={query.data?.results.find(item => item.provider === key)} />)}</div>}</Page>
}
function IntegrationCard({ provider, name, integration }: { provider: string; name: string; integration?: Integration }) {
  const [url, setUrl] = useState(integration?.url ?? '')
  const [saved, setSaved] = useState(!!integration)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function submit(event: FormEvent) {
    event.preventDefault(); setPending(true); setError(null)
    try { await recruiterRequest('/integrations/', { method: 'POST', body: { provider, url } }); setSaved(true) }
    catch (cause) { setError(recruiterError(cause)) }
    finally { setPending(false) }
  }
  return <form className="recruiter-card recruiter-form" onSubmit={submit}><div className="recruiter-heading"><h2>{name}</h2><Badge>{saved ? 'Activation en attente' : 'Non connecté'}</Badge></div><AuthField label={`URL ${name}`} type="url" required maxLength={2048} value={url} onChange={e => { setUrl(e.target.value); setSaved(false) }} placeholder="https://…" disabled={pending} />{error && <AuthNotice error>{error}</AuthNotice>}<button className="dashboard-button" disabled={pending}>{pending ? 'Enregistrement…' : 'Enregistrer la configuration'}</button>{saved && <p role="status">Configuration enregistrée. Synchronisation non activée.</p>}</form>
}
