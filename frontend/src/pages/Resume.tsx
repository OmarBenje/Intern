import { toast } from 'sonner'
import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowRight02Icon, Download04Icon, File02Icon, FileSyncIcon, Tick02Icon, Upload04Icon } from '@hugeicons/core-free-icons'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { ApiError, apiRequest, apiUrl } from '../lib/api'
import { AuthButton, AuthNotice } from '../components/auth/AuthControls'
import './Resume.css'
import { useSession } from '../auth/session-context'
import { OnboardingProgress } from '../components/onboarding/OnboardingParts'
import { useOnboardingReveals, useOnboardingStepMotion } from '../components/onboarding/onboarding-motion'

type Profile = { current_resume_id?: number | null }
type Document = { id: number; original_name: string; byte_size?: number; created_at?: string }
const MAX_BYTES = 10 * 1024 * 1024
function message(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'invalid_pdf') return 'Ce PDF est illisible, protégé ou contient du contenu actif. Exportez une nouvelle version PDF puis réessayez.'
    if (error.status === 413) return 'Votre PDF dépasse la limite de 10 Mo.'
    if (error.status === 401) return 'Votre session a expiré. Reconnectez-vous pour ajouter votre CV.'
    if (error.code === 'storage_unavailable') return 'Le stockage est temporairement indisponible. Réessayez dans un instant.'
  }
  return 'L’enregistrement n’a pas pu être confirmé. Réessayez avant de continuer.'
}

export function Resume({ onboarding = false, embedded = false, onSaved }: { onboarding?: boolean; embedded?: boolean; onSaved?: () => void }) {
  const Container = embedded ? 'div' : 'main'
  const navigate = useNavigate()
  const session = useSession()
  const [replacing, setReplacing] = useState(false)
  const [currentDocument, setCurrentDocument] = useState<Document | null>(null)
  const [currentId, setCurrentId] = useState<number | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [uploaded, setUploaded] = useState<Document | null>(null)
  const [loading, setLoading] = useState(true)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [version, setVersion] = useState(0)
  const busy = useRef(false)
  const input = useRef<HTMLInputElement>(null)
  const replaceButton = useRef<HTMLButtonElement>(null)
  const previousReplacing = useRef(false)
  const card = useOnboardingStepMotion(1, !loading)
  useOnboardingReveals(card, `${replacing}|${currentId}`, !loading)
  useEffect(() => {
    if (replacing) input.current?.focus()
    else if (previousReplacing.current) replaceButton.current?.focus()
    previousReplacing.current = replacing
  }, [replacing])
  useEffect(() => {
    const controller = new AbortController()
    apiRequest<Profile>('/profile/', { signal: controller.signal })
      .then(profile => { if (!controller.signal.aborted) { setCurrentId(profile.current_resume_id ?? null); setLoading(false) } })
      .catch(cause => { if (!controller.signal.aborted) { setError(message(cause)); setLoading(false) } })
    return () => controller.abort()
  }, [version])

  useEffect(() => {
    if (!embedded || !currentId) return
    const controller = new AbortController()
    async function loadDocument() {
      for (let page = 1; !controller.signal.aborted; page++) {
        const data = await apiRequest<{ results: Document[]; count: number; page_size: number }>(`/documents/?page=${page}&page_size=100`, { signal: controller.signal })
        const match = data.results.find(document => document.id === currentId)
        if (match) { if (!controller.signal.aborted) setCurrentDocument(match); break }
        if (!data.results.length || page * data.page_size >= data.count) break
      }
    }
    void loadDocument().catch(() => { /* Download remains available without metadata. */ })
    return () => controller.abort()
  }, [embedded, currentId])

  function select(files: File[]) {
    if (busy.current || loading) return
    setError(null); setUploaded(null); setFile(null)
    if (files.length !== 1) { setError('Choisissez un seul CV au format PDF.'); return }
    const next = files[0]
    if (!/\.pdf$/i.test(next.name) || (next.type && next.type !== 'application/pdf')) { setError('Choisissez un fichier PDF.'); return }
    if (!next.size || next.size > MAX_BYTES) { setError('Choisissez un PDF non vide de 10 Mo maximum.'); return }
    setFile(next)
  }
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy.current) return
    if (!file && !(onboarding && currentId && !replacing)) return
    busy.current = true; setPending(true); setError(null)
    try {
      if (!file) {
        await session.refresh()
        navigate('/onboarding/address', { replace: true })
        return
      }
      let document = uploaded
      if (!document) {
        const body = new FormData()
        body.append('kind', 'resume'); body.append('file', file)
        document = await apiRequest<Document>('/documents/', { method: 'POST', body, timeoutMs: 120000 })
        setUploaded(document)
      }
      const profile = await apiRequest<Profile>('/profile/resume/', { method: 'PUT', body: { document_id: document.id }, timeoutMs: 120000 })
      setCurrentId(profile.current_resume_id ?? document.id)
      toast.success('Votre CV a été enregistré.'); setReplacing(false); setFile(null); setUploaded(null)
      onSaved?.()
      if (input.current) input.current.value = ''
      if (onboarding) { await session.refresh(); navigate('/onboarding/address', { replace: true }) }
    } catch (cause) { setError(message(cause)) }
    finally { busy.current = false; setPending(false) }
  }
  return <Container id={embedded ? undefined : "main-content"} className={`resume-page resume-polished${embedded ? " resume-embedded" : ""}`}>
    <div ref={card} className={`resume-card${onboarding ? ' onboarding-card' : ''}`}>
      {onboarding && <OnboardingProgress step={1} pending={pending} />}
      {!onboarding && !embedded && <aside className="resume-help"><p className="eyebrow">Votre profil candidat</p><h2>Tout commence <br />avec votre CV.</h2><p>Un seul document pour garder votre parcours à portée de main.</p><div className="resume-help-details"><p><strong>Vous gardez la main</strong><br />Remplacez-le quand votre parcours évolue.</p></div></aside>}
      <section className="resume-form-panel">
        {!onboarding && !embedded && <p className="eyebrow">Curriculum vitæ</p>}{!embedded && <><h1 tabIndex={-1}>{currentId && !replacing ? 'Votre CV est prêt.' : currentId ? 'Remplacez votre CV.' : 'Ajoutez votre CV.'}</h1>{(!onboarding || replacing) && <p className="intro">{currentId && !replacing ? 'Vous pouvez passer à la suite ou choisir une autre version.' : currentId ? 'Votre CV actuel reste enregistré jusqu’à la validation du nouveau.' : 'Déposez votre PDF. Vous pourrez le remplacer à tout moment.'}</p>}</>}
        {loading ? <AuthNotice>Chargement de votre profil…</AuthNotice> : <>
          <form onSubmit={submit} className="resume-form" aria-busy={pending}>
            {currentId && !replacing ? <div className="resume-saved-card" data-onboarding-reveal="saved-cv">
              <div className="resume-file-icon"><HugeiconsIcon icon={File02Icon} size={32} strokeWidth={1.5} aria-hidden="true" /></div>
              <div className="resume-file-info"><strong>{currentDocument?.id === currentId ? currentDocument.original_name : 'Votre CV actuel'}</strong><span>Document PDF{currentDocument?.id === currentId && currentDocument.byte_size ? ` · ${Math.max(1, Math.round(currentDocument.byte_size / 1024))} Ko` : ''}</span></div>
              <span className="resume-saved-status"><HugeiconsIcon icon={Tick02Icon} size={16} strokeWidth={2} aria-hidden="true" /> Enregistré</span>
              <div className="resume-file-tools"><a aria-label="Télécharger mon CV actuel" href={apiUrl(`/documents/${currentId}/download/`)}><HugeiconsIcon icon={Download04Icon} size={20} strokeWidth={1.5} aria-hidden="true" />Télécharger</a><button ref={replaceButton} type="button" onClick={() => { setReplacing(true) }}><HugeiconsIcon icon={FileSyncIcon} size={20} strokeWidth={1.5} aria-hidden="true" />Remplacer</button></div>
            </div> : <div data-onboarding-reveal="upload-cv" className={`resume-drop${file ? ' resume-drop--selected' : ''}${dragging ? ' resume-drop--active' : ''}`} onDragOver={event => { event.preventDefault(); if (!pending) setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); select(Array.from(event.dataTransfer.files)) }}>
              <span className="resume-upload-icon" aria-hidden="true"><HugeiconsIcon className="resume-upload-idle" icon={Upload04Icon} size={32} strokeWidth={1.5} /><HugeiconsIcon className="resume-upload-ready" icon={Tick02Icon} size={32} strokeWidth={1.5} /></span>
              <label htmlFor="resume-file">{file ? file.name : <>Déposez votre PDF ici ou <span className="resume-browse">choisissez un fichier</span></>}</label>
              <input ref={input} id="resume-file" type="file" accept=".pdf,application/pdf" disabled={pending} aria-describedby="resume-hint" onChange={event => { if (event.target.files?.length) select(Array.from(event.target.files)) }} />
              <small id="resume-hint">{file ? `${Math.max(1, Math.round(file.size / 1024))} Ko · prêt à enregistrer` : 'CV · PDF uniquement · 10 Mo maximum'}</small>
            </div>}
            {replacing && !pending && <button type="button" className="resume-cancel" onClick={() => { setReplacing(false); setFile(null); setUploaded(null); setError(null) }}>Garder mon CV actuel</button>}
            {error && <AuthNotice error>{error}</AuthNotice>}
            {(onboarding || file || replacing || !currentId) && <div className="resume-footer"><div className="resume-actions"><AuthButton type="submit" pending={pending} disabled={!file && !(onboarding && currentId && !replacing)}>{pending ? uploaded ? 'Enregistrement…' : 'Envoi de votre CV…' : uploaded ? 'Réessayer l’association du CV' : onboarding ? currentId && !replacing ? 'Continuer' : 'Enregistrer et continuer' : 'Enregistrer mon CV'}{!pending && onboarding && <HugeiconsIcon icon={ArrowRight02Icon} size={20} strokeWidth={2} aria-hidden="true" />}</AuthButton></div></div>}
          </form>
        </>}
        {!loading && error && !file && <button type="button" className="auth-previous" onClick={() => { setError(null); setLoading(true); setVersion(v => v + 1) }}>Recharger mon profil</button>}
      </section>
    </div>
  </Container>
}
