import { useEffect } from 'react'
import { HugeiconsIcon } from '@hugeicons/react'
import { Logout01Icon } from '@hugeicons/core-free-icons'
import { Link, Outlet, useLocation, useSearchParams } from 'react-router'
import { useSession } from '../../auth/session-context'
import { useApiQuery } from '../../lib/useApiQuery'
import type { DashboardData } from './data'
import './dashboard.css'
import './workspace.css'
import { logoDevEnabled } from '../../lib/companyLogos'

const navigation = [
  { path: '/dashboard', label: 'Tableau de bord' },
  { path: '/stages', label: 'Explorer les offres' },
  { path: '/candidatures', label: 'Candidatures', count: 'applications' },
  { path: '/a-valider', label: 'À valider', count: 'needs_input' },
  { path: '/tracker', label: 'Suivi' },
  { path: '/profil', label: 'Profil' },
  { path: '/engine', label: 'Moteur' },
] as const

export function Workspace({ logout, loggingOut, logoutError }: { logout: () => void; loggingOut: boolean; logoutError: string | null }) {
  const { user } = useSession()
  const { pathname } = useLocation()
  const [params] = useSearchParams()
  const query = params.get('q') ?? ''
  const filter = pathname === '/a-valider' ? 'needs_input' : params.get('filter') ?? 'all'
  const page = params.get('page') ?? '1'
  const title = navigation.find(item => item.path === pathname)?.label ?? (pathname.startsWith('/companies/') ? 'Découvrir l’entreprise' : pathname.startsWith('/offers/') ? 'Détail de l’offre' : pathname.startsWith('/applications/') ? 'Votre candidature' : 'Votre espace')
  useEffect(() => { document.title = `${title} — Intern` }, [title])
  const searchParams = new URLSearchParams({ q: query, filter, page, page_size: '8' })
  const { data, error, loading, reload } = useApiQuery<DashboardData>(`/dashboard/?${searchParams}`)
  const name = data?.full_name || user?.email || user?.username || 'Mon compte'
  const initials = name.includes('@') ? name.slice(0, 2) : name.split(/\s+/).slice(0, 2).map(part => part[0]).join('')
  return <div className={`workspace${pathname === '/stages' ? ' workspace--catalogue' : ''}`}><div className="workspace-frame">
    <header className="workspace-navbar">
      <Link to="/dashboard" className="workspace-brand" aria-label="Intern, accueil">intern<span>.</span></Link>
      <nav aria-label="Navigation principale">
        {navigation.map(item => {
          const active = pathname === item.path
            || (item.path === '/stages' && (pathname.startsWith('/offers/') || pathname.startsWith('/companies/')))
            || (item.path === '/candidatures' && pathname.startsWith('/applications/'))
          return <Link key={item.path} to={item.path} aria-current={active ? 'page' : undefined} className={`workspace-nav-link${active ? ' is-active' : ''}`}>
            <span>{item.label}</span>
            {'count' in item && !!data?.counts[item.count] && <span className="workspace-count">{data.counts[item.count]}</span>}
          </Link>
        })}
      </nav>
      <div className="workspace-navbar-account">
        <div className="workspace-account"><Link to="/profil" className="workspace-account-link" aria-label={`Mon profil : ${name}`}><span className="workspace-avatar" aria-hidden="true">{initials.toUpperCase()}</span><span className="workspace-account-name">{name}<small>Espace candidat</small></span></Link><button type="button" className="workspace-icon-button" onClick={logout} disabled={loggingOut} aria-label={loggingOut ? 'Déconnexion…' : 'Se déconnecter'}><HugeiconsIcon icon={Logout01Icon} size={18} strokeWidth={1.5} aria-hidden="true" /></button></div>
        {logoDevEnabled && <a className="workspace-logo-credit" href="https://www.logo.dev" target="_blank" rel="noopener">Logos fournis par Logo.dev</a>}
        {logoutError && <p className="workspace-error" role="alert">{logoutError}</p>}
      </div>
    </header>
    <div className="workspace-main">
      <Outlet context={{ data, loading, error, reload }} />
    </div>
  </div></div>
}
