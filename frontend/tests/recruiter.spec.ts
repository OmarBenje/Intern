import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const company = { full_name: 'Alice Martin', company_name: 'Studio Exemple', siren: '732829320', website_url: 'https://example.test', linkedin_url: '', verification_status: 'verified', email_verified: true }
const user = { id: 10, username: 'recruiter_alice', email: 'alice@example.test', full_name: 'Alice Martin', role: 'recruiter', onboarding_step: 'complete' }
const job = { id: 1, title: 'Stage développement web', department: 'Produit', contract_type: 'internship', location: 'Paris', country_code: 'FR', work_mode: 'hybrid', salary: '1 200 € / mois', description: 'Construire une application React avec notre équipe.', skills: 'React, TypeScript', education: 'Bac +3', languages: 'Français', status: 'active', origin: 'direct', published_at: '2026-10-01T10:00:00Z', applicant_count: 1 }
const applicant = { id: 2, job_id: 1, job_title: job.title, stage: 'new', match_score: null, ai_summary: '', rejection_reason: '', interview_at: null, resume_url: null, profile: { full_name: 'Ada Lovelace', email: 'ada@example.test', headline: 'Développeuse web', skills: ['React', 'TypeScript'] } }
const collection = (results: unknown[]) => ({ results, count: results.length, page: 1, page_size: 20 })
async function session(page: Page, current = user) {
  await page.route('**/api/v1/auth/me/', route => route.fulfill({ json: { user: current } }))
  await page.route('**/api/v1/auth/csrf/', route => route.fulfill({ json: { csrf_token: 'recruiter-csrf' } }))
  await page.route('**/api/v1/recruiter/dashboard/', route => route.fulfill({ json: { company, counts: { active_jobs: 1, applications: 1, average_match: null, views: 12 }, activity: [applicant] } }))
  await page.route('**/api/v1/recruiter/verify/', route => route.fulfill({ json: company }))
  await page.route('**/api/v1/recruiter/jobs/?*', route => route.fulfill({ json: collection([job]) }))
  await page.route('**/api/v1/recruiter/candidates/?*', route => route.fulfill({ json: collection([applicant]) }))
  await page.route('**/api/v1/recruiter/candidates/2/', route => route.fulfill({ json: applicant }))
}

test('role choice precedes every identity field and recruiter registration persists its role', async ({ page }, info) => {
  await page.route('**/api/v1/auth/me/', route => route.fulfill({ status: 401, json: { error: { code: 'authentication_required' } } }))
  await page.route('**/api/v1/auth/csrf/', route => route.fulfill({ json: { csrf_token: 'role-csrf' } }))
  await page.route('**/api/v1/auth/email-availability/', route => route.fulfill({ json: { available: true } }))
  await page.route('**/api/v1/recruiter/verify/', route => route.fulfill({ json: { ...company, verification_status: 'unverified', email_verified: false } }))
  await page.route('**/api/v1/auth/register/', async route => {
    expect(route.request().postDataJSON()).toEqual({ role: 'recruiter', email: 'alice@example.test', full_name: 'Alice Martin', password: 'StrongPassword-987!' })
    expect(route.request().headers()['x-csrftoken']).toBe('role-csrf')
    await route.fulfill({ json: { user: { ...user, onboarding_step: 'verify' } } })
  })
  await page.goto('/register')
  await expect(page.getByLabel('Adresse e-mail')).toHaveCount(0)
  await expect(page.getByLabel('Nom complet')).toHaveCount(0)
  await page.getByRole('radio', { name: /Je suis recruteur/ }).check()
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 900 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath(`role-${width}.png`), fullPage: true })
  }
  await page.getByRole('button', { name: 'Continuer' }).click()
  await page.getByLabel('Adresse e-mail').fill('alice@gmail.com')
  await page.getByRole('button', { name: 'Continuer' }).click()
  await expect(page.getByLabel('Adresse e-mail')).toHaveAccessibleDescription(/professionnelle/)
  await page.getByLabel('Adresse e-mail').fill('alice@example.test')
  await page.getByRole('button', { name: 'Continuer' }).click()
  await page.getByLabel('Nom complet').fill('Alice Martin')
  await page.getByRole('button', { name: 'Continuer' }).click()
  await page.getByLabel('Mot de passe', { exact: true }).fill('StrongPassword-987!')
  await page.getByRole('button', { name: 'Créer mon compte' }).click()
  await expect(page).toHaveURL(/\/recruiter\/verify$/)
  await expect(page.getByRole('heading', { name: 'Vérifiez votre e-mail professionnel' })).toBeVisible()
})

test('recruiter navigation reuses candidate design without fetching candidate dashboard', async ({ page }, info) => {
  await session(page)
  const candidateCalls: string[] = []
  page.on('request', request => { if (request.url().includes('/api/v1/dashboard/')) candidateCalls.push(request.url()) })
  await page.goto('/dashboard')
  await expect(page).toHaveURL(/\/recruiter\/dashboard$/)
  await expect(page.getByRole('heading', { name: 'Bonjour Alice.' })).toBeVisible()
  await expect(page.getByText('Non évalué')).toBeVisible()
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath(`dashboard-${width}.png`), fullPage: true })
  }
  await page.getByRole('link', { name: 'Mes offres', exact: true }).click()
  await expect(page.getByRole('link', { name: job.title })).toBeVisible()
  expect(candidateCalls).toEqual([])
})

test('four-step wizard saves data and handles a publication refusal without losing values', async ({ page }) => {
  await session(page)
  await page.route('**/api/v1/recruiter/jobs/', async route => {
    const body = route.request().postDataJSON()
    expect(body.title).toBe('Stage design')
    expect(body.description).toBe('Concevoir les interfaces de demain.')
    if (body.status === 'active') await route.fulfill({ status: 409, json: { error: { code: 'company_unverified', message: 'La validation de votre entreprise est nécessaire pour publier.' } } })
    else await route.fulfill({ status: 201, json: { ...job, ...body } })
  })
  await page.goto('/recruiter/jobs/new')
  await page.getByLabel('Intitulé du poste').fill('Stage design')
  await page.getByLabel('Ville / localisation').fill('Lyon')
  await page.getByRole('button', { name: 'Continuer' }).click()
  await page.getByLabel('Missions et description').fill('Concevoir les interfaces de demain.')
  await page.getByRole('button', { name: 'Continuer' }).click()
  await page.getByLabel('Niveau d’études attendu').fill('Bac +3')
  await page.getByRole('button', { name: 'Continuer' }).click()
  await expect(page.getByRole('heading', { name: 'Stage design', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Publier l’offre' }).click()
  await expect(page.getByRole('alert')).toContainText('validation de votre entreprise')
  await page.getByRole('button', { name: 'Enregistrer le brouillon' }).click()
  await expect(page).toHaveURL(/\/recruiter\/jobs$/)
})

test('kanban opens accessible candidate drawer, updates stage and restores focus', async ({ page }, info) => {
  await session(page)
  await page.route('**/api/v1/recruiter/candidates/2/', async route => {
    if (route.request().method() === 'PATCH') {
      expect(route.request().postDataJSON().stage).toBe('interview')
      await route.fulfill({ json: { ...applicant, stage: 'interview' } })
    } else await route.fulfill({ json: applicant })
  })
  await page.goto('/recruiter/candidates')
  const card = page.getByRole('button', { name: /Ada Lovelace/ })
  await card.click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByText('Aucune synthèse IA disponible')).toBeVisible()
  await page.getByLabel('Étape de la candidature').selectOption('interview')
  await page.getByRole('button', { name: 'Enregistrer le suivi' }).click()
  await page.screenshot({ path: info.outputPath('candidate-drawer.png'), fullPage: true })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(card).toBeFocused()
})

test('ATS URL is saved with an honest pending state', async ({ page }) => {
  await session(page)
  await page.route('**/api/v1/recruiter/integrations/', async route => {
    if (route.request().method() === 'POST') expect(route.request().postDataJSON()).toEqual({ provider: 'lever', url: 'https://jobs.lever.co/example' })
    await route.fulfill({ json: { results: [] } })
  })
  await page.goto('/recruiter/integrations')
  const card = page.locator('form').filter({ has: page.getByRole('heading', { name: 'Lever', exact: true }) })
  await card.getByLabel('URL Lever').fill('https://jobs.lever.co/example')
  await card.getByRole('button').click()
  await expect(card.getByRole('status')).toContainText('Configuration enregistrée')
  await expect(card.getByText('Activation en attente')).toBeVisible()
})

test('candidate cannot enter recruiter pages', async ({ page }) => {
  await session(page, { ...user, role: 'candidate' })
  await page.route('**/api/v1/dashboard/?*', route => route.fulfill({ json: { full_name: 'Alice', offers: [], counts: {}, results: [], applications: { results: [], count: 0 }, suggestions: [] } }))
  await page.goto('/recruiter/jobs')
  await expect(page).toHaveURL(/\/dashboard$/)
})
