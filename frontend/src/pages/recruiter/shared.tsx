import type { ReactNode } from 'react'
import './recruiter.css'

export function Badge({ children }: { children: ReactNode }) { return <span className="recruiter-badge">{children}</span> }
export function Page({ title, description, action, children }: { title: string; description: string; action?: ReactNode; children: ReactNode }) {
  return <main id="main-content" className="dashboard-content recruiter-page"><header className="recruiter-heading"><div><p className="recruiter-eyebrow">ESPACE RECRUTEUR</p><h1>{title}</h1><p>{description}</p></div>{action}</header>{children}</main>
}
export function QueryState({ loading, error, reload }: { loading: boolean; error: string | null; reload: () => void }) {
  return error ? <div className="dashboard-error" role="alert">{error} <button className="dashboard-button" onClick={reload}>Réessayer</button></div> : loading ? <p role="status">Chargement…</p> : null
}
export function Pages({ count, page, onChange }: { count: number; page: number; onChange: (page: number) => void }) {
  return count > 20 ? <nav className="recruiter-actions" aria-label="Pagination"><button className="dashboard-button" disabled={page === 1} onClick={() => onChange(page - 1)}>Précédent</button><span>Page {page} sur {Math.ceil(count / 20)}</span><button className="dashboard-button" disabled={page * 20 >= count} onClick={() => onChange(page + 1)}>Suivant</button></nav> : null
}
