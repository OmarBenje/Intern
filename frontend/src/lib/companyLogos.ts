// Optional CDN access uses only a publishable key, never a secret API key.
import { apiResourceUrl } from './api'
export const logoDevKey = (import.meta.env.VITE_LOGO_DEV_PUBLISHABLE_KEY ?? '').trim()
export const logoDevEnabled = logoDevKey.startsWith('pk_')

const platforms = ['linkedin.com', 'licdn.com', 'welcometothejungle.com', 'indeed.com', 'glassdoor.com', 'greenhouse.io', 'ashbyhq.com', 'lever.co', 'myworkdayjobs.com', 'smartrecruiters.com', 'recruitee.com']

export function logoCandidates(id: number, localUrl?: string | null, domain?: string | null) {
  const candidates: string[] = []
  if (localUrl && new RegExp(`^/api/v1/companies/${id}/logo/\\?v=[a-zA-Z0-9_-]{1,128}$`).test(localUrl)) {
    const url = apiResourceUrl(localUrl)
    if (url) candidates.push(url)
  }
  const host = domain?.toLowerCase()
  if (logoDevEnabled && host && host.length <= 253 && /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/.test(host) && !platforms.some(p => host === p || host.endsWith(`.${p}`))) {
    const query = new URLSearchParams({ token: logoDevKey, format: 'png', size: '128', theme: 'light', fallback: '404' })
    candidates.push(`https://img.logo.dev/${host}?${query}`)
  }
  return candidates
}
