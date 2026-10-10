import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { useApiQuery } from '../../lib/useApiQuery'
import { AuthField, AuthNotice } from '../../components/auth/AuthControls'
import { Badge, Page, Pages, QueryState } from './shared'
import { contracts, recruiterError, recruiterRequest, statuses } from './data'
import type { Collection, Job } from './data'

export function RecruiterJobs() {
  const [params, setParams] = useSearchParams()
  const query = useApiQuery<Collection<Job>>(`/recruiter/jobs/?${params}`)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  function filter(key: string, value: string) { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); next.delete('page'); setParams(next, { replace: true }) }
  async function action(job: Job, status: string) {
    setPending(true); setError(null)
    try { await recruiterRequest(`/jobs/${job.id}/${status === 'duplicate' ? 'duplicate/' : ''}`, { method: status === 'duplicate' ? 'POST' : 'PATCH', body: status === 'duplicate' ? {} : { status } }); query.reload() }
    catch (cause) { setError(recruiterError(cause)) }
    finally { setPending(false) }
  }
  return <Page title="Vos prochaines rencontres." description="Toutes vos offres et leur progression, en un seul endroit." action={<Link className="dashboard-button dashboard-button--primary" to="/recruiter/jobs/new">+ Créer une offre</Link>}>
    <div className="recruiter-toolbar"><label>Rechercher<input type="search" placeholder="Intitulé du poste…" value={params.get('q') ?? ''} onChange={e => filter('q', e.target.value)} /></label><label>Statut<select value={params.get('status') ?? ''} onChange={e => filter('status', e.target.value)}><option value="">Tous les statuts</option>{['active', 'draft', 'paused', 'archived'].map(value => <option key={value} value={value}>{statuses[value]}</option>)}</select></label><label>Contrat<select value={params.get('contract_type') ?? ''} onChange={e => filter('contract_type', e.target.value)}><option value="">Tous les contrats</option>{Object.entries(contracts).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Localisation<input value={params.get('location') ?? ''} placeholder="Ville…" onChange={e => filter('location', e.target.value)} /></label><label>Origine<select value={params.get('origin') ?? ''} onChange={e => filter('origin', e.target.value)}><option value="">Toutes les origines</option><option value="direct">Direct</option><option value="greenhouse">Greenhouse</option><option value="lever">Lever</option></select></label></div>
    <QueryState {...query} />{error && <AuthNotice error>{error}</AuthNotice>}
    {query.data && <>{query.data.results.length ? <div className="recruiter-table-wrap"><table className="recruiter-table"><thead><tr><th>Poste</th><th>Statut</th><th>Origine</th><th>Candidatures</th><th>Publication</th><th>Actions</th></tr></thead><tbody>{query.data.results.map(job => <tr key={job.id}><td><Link to={`/recruiter/jobs/${job.id}/edit`}><strong>{job.title}</strong></Link><small>{[job.department, contracts[job.contract_type], job.location].filter(Boolean).join(' · ')}</small></td><td><Badge>{statuses[job.status]}</Badge></td><td><Badge>{job.origin === 'direct' ? 'Direct' : `ATS · ${job.origin}`}</Badge></td><td><Link to={`/recruiter/jobs/${job.id}/applicants`}>{job.applicant_count} candidat{job.applicant_count > 1 ? 's' : ''}</Link></td><td>{job.published_at ? new Date(job.published_at).toLocaleDateString('fr-FR') : '—'}</td><td><div className="recruiter-actions"><Link className="dashboard-button" to={`/recruiter/jobs/${job.id}/edit`}>Éditer</Link><button className="dashboard-button" disabled={pending} onClick={() => action(job, 'duplicate')}>Dupliquer</button>{job.status === 'active' && <button className="dashboard-button" disabled={pending} onClick={() => action(job, 'paused')}>Suspendre</button>}{job.status !== 'archived' && <button className="dashboard-button" disabled={pending} onClick={() => action(job, 'archived')}>Archiver</button>}</div></td></tr>)}</tbody></table></div> : <section className="recruiter-card recruiter-empty"><h2>{params.size ? 'Aucune offre ne correspond.' : 'Votre première offre vous attend.'}</h2><p>{params.size ? 'Essayez d’autres filtres.' : 'Décrivez le poste et les talents que vous souhaitez rencontrer.'}</p><Link to="/recruiter/jobs/new">Créer une offre →</Link></section>}<Pages count={query.data.count} page={query.data.page} onChange={page => { const next = new URLSearchParams(params); next.set('page', String(page)); setParams(next) }} /></>}
  </Page>
}

type JobValues = Pick<Job, 'title' | 'department' | 'contract_type' | 'location' | 'country_code' | 'work_mode' | 'salary' | 'description' | 'skills' | 'education' | 'languages'>
const empty: JobValues = { title: '', department: '', contract_type: 'internship', location: '', country_code: 'FR', work_mode: 'onsite', salary: '', description: '', skills: '', education: '', languages: '' }
export function JobWizard() {
  const { id } = useParams()
  const query = useApiQuery<Job>(id ? `/recruiter/jobs/${id}/` : null)
  return <Page title={id ? 'Affinons votre offre.' : 'Une nouvelle opportunité.'} description="Quatre étapes pour donner envie aux bons talents de vous rejoindre.">{id && <QueryState {...query} />}{(!id || query.data) && <Wizard key={id ?? 'new'} job={query.data} />}</Page>
}
function Wizard({ job }: { job: Job | null }) {
  const navigate = useNavigate()
  const [values, setValues] = useState<JobValues>(() => job ? Object.fromEntries(Object.keys(empty).map(key => [key, job[key as keyof JobValues]])) as JobValues : empty)
  const [step, setStep] = useState(0)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const busy = useRef(false)
  const title = useRef<HTMLHeadingElement>(null)
  const labels = ['Informations générales', 'Missions & compétences', 'Critères de matching', 'Aperçu & publication']
  const change = (key: keyof JobValues, value: string) => setValues(previous => ({ ...previous, [key]: value }))
  async function save(status: string) {
    if (busy.current) return
    busy.current = true; setPending(true); setError(null)
    try { await recruiterRequest(job ? `/jobs/${job.id}/` : '/jobs/', { method: job ? 'PATCH' : 'POST', body: { ...values, status } }); navigate('/recruiter/jobs') }
    catch (cause) { setError(recruiterError(cause)) }
    finally { busy.current = false; setPending(false) }
  }
  function next(event: FormEvent) { event.preventDefault(); if (step < 3) { setStep(step + 1); setTimeout(() => title.current?.focus(), 0) } else void save('active') }
  const input = (key: keyof JobValues, label: string, required = false, maxLength = 160) => <AuthField label={label} name={key} required={required} maxLength={maxLength} value={values[key]} onChange={e => change(key, e.target.value)} />
  return <section className="recruiter-card recruiter-form-card"><ol className="recruiter-steps">{labels.map((label, index) => <li key={label} aria-current={step === index ? 'step' : undefined}>{index + 1} · {label}</li>)}</ol><h2 tabIndex={-1} ref={title}>{labels[step]}</h2><form className="recruiter-form" onSubmit={next}><fieldset disabled={pending}>
    {step === 0 && <div className="recruiter-grid">{input('title', 'Intitulé du poste', true, 300)}{input('department', 'Département')}<label>Type de contrat<select value={values.contract_type} onChange={e => change('contract_type', e.target.value)}>{Object.entries(contracts).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>{input('salary', 'Gratification / salaire')}{input('location', 'Ville / localisation', true, 240)}<label>Pays (code ISO)<input required pattern="[A-Z]{2}" maxLength={2} value={values.country_code} onChange={e => change('country_code', e.target.value.toUpperCase())} /></label><label>Mode de travail<select value={values.work_mode} onChange={e => change('work_mode', e.target.value)}><option value="onsite">Présentiel</option><option value="hybrid">Hybride</option><option value="remote">Télétravail</option></select></label></div>}
    {step === 1 && <><label>Missions et description<textarea required rows={10} maxLength={50000} value={values.description} onChange={e => change('description', e.target.value)} placeholder="Présentez l’équipe, les missions et ce que le candidat pourra apprendre…" /></label><label>Compétences techniques et humaines<textarea rows={4} maxLength={5000} value={values.skills} onChange={e => change('skills', e.target.value)} placeholder="Python, esprit d’équipe, autonomie…" /></label></>}
    {step === 2 && <>{input('education', 'Niveau d’études attendu')}{input('languages', 'Langues requises', false, 240)}<label>Technologies et compétences clés<textarea rows={4} maxLength={5000} value={values.skills} onChange={e => change('skills', e.target.value)} /></label><p className="recruiter-notice">Ces critères seront conservés pour l’évaluation des candidatures. Les scores et synthèses IA apparaîtront lorsqu’une évaluation sera disponible.</p></>}
    {step === 3 && <article className="recruiter-preview"><Badge>{contracts[values.contract_type]}</Badge><h2>{values.title}</h2><p>{values.department} · {values.location}, {values.country_code}</p><p>{values.salary}</p><h3>Vos missions</h3><p className="recruiter-prose">{values.description}</p><h3>Le profil recherché</h3><p className="recruiter-prose">{values.skills}</p><p>{values.education} · {values.languages}</p><p className="recruiter-notice">La publication nécessite une entreprise vérifiée. Le catalogue candidat affiche actuellement les stages confirmés en Europe.</p></article>}
    </fieldset>{error && <AuthNotice error>{error}</AuthNotice>}<div className="recruiter-actions">{step > 0 && <button type="button" className="dashboard-button" disabled={pending} onClick={() => setStep(step - 1)}>Retour</button>}<button type="button" className="dashboard-button" disabled={pending || !values.title.trim()} onClick={() => save('draft')}>Enregistrer le brouillon</button><button className="dashboard-button dashboard-button--primary" disabled={pending}>{pending ? 'Enregistrement…' : step === 3 ? 'Publier l’offre' : 'Continuer'}</button></div></form></section>
}
