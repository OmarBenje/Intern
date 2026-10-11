import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { useApiQuery } from '../../lib/useApiQuery'
import { apiResourceUrl } from '../../lib/api'
import { AuthNotice } from '../../components/auth/AuthControls'
import { Badge, Page, Pages, QueryState } from './shared'
import { recruiterError, recruiterRequest, stages } from './data'
import type { Applicant, Collection } from './data'

export function Applicants() {
  const { id, candidateId } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const selected = candidateId ?? params.get('candidate')
  const filters = new URLSearchParams({ page: params.get('page') ?? '1', min_score: params.get('min_score') ?? '' })
  const query = useApiQuery<Collection<Applicant>>(`/recruiter/${id ? `jobs/${id}/applicants` : 'candidates'}/?${filters}`)
  function close() { if (candidateId) navigate('/recruiter/candidates'); else { const next = new URLSearchParams(params); next.delete('candidate'); setParams(next) } }
  function open(candidate: number) { const next = new URLSearchParams(params); next.set('candidate', String(candidate)); setParams(next) }
  return <Page title="Les talents de demain." description="Faites avancer chaque candidature, de la première rencontre à la décision." action={id && <Link to="/recruiter/jobs" className="dashboard-button">Toutes les offres</Link>}>
    <div className="recruiter-toolbar"><label>Score de matching<select value={params.get('min_score') ?? ''} onChange={e => { const next = new URLSearchParams(params); if (e.target.value) next.set('min_score', e.target.value); else next.delete('min_score'); next.delete('page'); setParams(next) }}><option value="">Tous les candidats</option><option value="85">Au moins 85 %</option><option value="70">Au moins 70 %</option></select></label>{query.data && <span>{query.data.count} candidature{query.data.count > 1 ? 's' : ''}</span>}</div>
    <QueryState {...query} />{query.data && <><div className="recruiter-kanban">{Object.entries(stages).map(([key, label]) => { const items = (query.data?.results ?? []).filter(item => item.stage === key); return <section className="recruiter-column" key={key} aria-label={label}><h2>{label} <Badge>{items.length}</Badge></h2>{items.length ? items.map(item => <button id={`candidate-${item.id}`} className="recruiter-applicant" key={item.id} onClick={() => open(item.id)}><span className="workspace-avatar" aria-hidden="true">{item.profile.full_name.slice(0, 2).toUpperCase()}</span><strong>{item.profile.full_name}</strong><span>{item.profile.headline || item.job_title}</span><Badge>{item.match_score === null ? 'Matching non évalué' : `${item.match_score} % de match`}</Badge></button>) : <p className="recruiter-column-empty">Aucune candidature</p>}</section> })}</div><Pages count={query.data.count} page={query.data.page} onChange={page => { const next = new URLSearchParams(params); next.set('page', String(page)); setParams(next) }} /></>}
    {selected && <CandidateDrawer key={selected} id={selected} close={close} reload={query.reload} />}
  </Page>
}
function CandidateDrawer({ id, close, reload }: { id: string; close: () => void; reload: () => void }) {
  const query = useApiQuery<Applicant>(`/recruiter/candidates/${id}/`)
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const node = dialog.current
    node?.showModal()
    return () => { node?.close(); requestAnimationFrame(() => document.getElementById(`candidate-${id}`)?.focus()) }
  }, [id])
  return <dialog className="recruiter-drawer" ref={dialog} onCancel={event => { event.preventDefault(); close() }} aria-labelledby="candidate-title"><button className="dashboard-button recruiter-close" autoFocus onClick={close}>Fermer</button><h2 id="candidate-title">Fiche candidat</h2><QueryState {...query} />{query.data && <CandidateDetails candidate={query.data} reload={() => { query.reload(); reload() }} />}</dialog>
}
function CandidateDetails({ candidate, reload }: { candidate: Applicant; reload: () => void }) {
  const resumeUrl = candidate.resume_url ? apiResourceUrl(candidate.resume_url) : null
  const [stage, setStage] = useState(candidate.stage)
  const [reason, setReason] = useState(candidate.rejection_reason)
  const [interview, setInterview] = useState(() => candidate.interview_at ? localDateTime(candidate.interview_at) : '')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function save(event: React.FormEvent) {
    event.preventDefault(); setPending(true); setError(null)
    try { await recruiterRequest(`/candidates/${candidate.id}/`, { method: 'PATCH', body: { stage, rejection_reason: reason, interview_at: interview ? new Date(interview).toISOString() : null } }); reload() }
    catch (cause) { setError(recruiterError(cause)) }
    finally { setPending(false) }
  }
  return <><h3>{candidate.profile.full_name}</h3><p>{candidate.profile.headline}</p><Badge>{candidate.match_score === null ? 'Matching non évalué' : `${candidate.match_score} % de match`}</Badge><section className="recruiter-card"><h3>Synthèse IA</h3><p>{candidate.ai_summary || 'Aucune synthèse IA disponible pour cette candidature.'}</p></section><h3>Compétences</h3><p>{candidate.profile.skills.join(' · ') || 'Non renseignées'}</p>{candidate.profile.experiences?.map((item, index) => <section key={`experience-${index}`}><h3>{item.title} · {item.company_name}</h3><p>{item.description}</p></section>)}{candidate.profile.education?.map((item, index) => <section key={`education-${index}`}><h3>{item.degree} · {item.institution}</h3><p>{item.description}</p></section>)}{candidate.profile.projects?.map((item, index) => <section key={`project-${index}`}><h3>{item.title}</h3><p>{item.description}</p></section>)}<a className="dashboard-button" href={`mailto:${encodeURIComponent(candidate.profile.email)}`}>Contacter par e-mail</a><h3>CV transmis</h3>{resumeUrl ? <><iframe title={`CV de ${candidate.profile.full_name}`} src={resumeUrl} className="recruiter-resume" /><a className="dashboard-button" href={`${resumeUrl}?download=1`} download>Télécharger le CV PDF</a></> : <p>Aucun CV transmis.</p>}<form className="recruiter-form" onSubmit={save}><fieldset disabled={pending}><label>Étape de la candidature<select value={stage} onChange={e => setStage(e.target.value)}>{Object.entries(stages).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>{stage === 'rejected' && <label>Motif du refus<textarea required maxLength={5000} value={reason} onChange={e => setReason(e.target.value)} /></label>}<label>Date de l’entretien<input type="datetime-local" value={interview} onChange={e => setInterview(e.target.value)} /></label><p>L’horaire est enregistré dans le suivi. Contactez le candidat pour lui confirmer le rendez-vous.</p></fieldset>{error && <AuthNotice error>{error}</AuthNotice>}<button className="dashboard-button dashboard-button--primary" disabled={pending}>{pending ? 'Enregistrement…' : 'Enregistrer le suivi'}</button></form></>
}
function localDateTime(value: string) { const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
