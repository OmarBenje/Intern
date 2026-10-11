// Recette locale sur une base fictive neuve, avec Vite et Django réellement lancés.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { chromium } = require('@playwright/test')
const base = process.env.RECETTE_URL || 'http://127.0.0.1:5173'
const adminBase = process.env.RECETTE_ADMIN_URL || 'http://127.0.0.1:8000'
const password = process.env.RECETTE_PASSWORD
if (!password) throw new Error('Définir RECETTE_PASSWORD avec le mot de passe du jeu fictif.')

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const contexts = []
const results = []
const api = path => `${base}/api/v1${path}`

async function context() {
  const value = await browser.newContext({ baseURL: base })
  contexts.push(value)
  return value
}
async function login(page, email, secret = password) {
  await page.goto('/login')
  await page.getByLabel('Adresse e-mail').fill(email)
  await page.getByLabel('Mot de passe', { exact: true }).fill(secret)
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
}
async function csrf(client) {
  const response = await client.get(api('/auth/csrf/'))
  assert.equal(response.status(), 200)
  return (await response.json()).csrf_token
}
async function post(client, path, body) {
  return client.post(api(path), {
    data: body,
    headers: { 'X-CSRFToken': await csrf(client) },
  })
}
async function check(id, label, action) {
  await action()
  results.push(`${id} PASS — ${label}`)
  console.log(results.at(-1))
}

try {
  const anonymous = await context()
  await check('T01', 'session anonyme refusée', async () => {
    assert.equal((await anonymous.request.get(api('/auth/me/'))).status(), 401)
  })
  await check('T02', 'mutation sans CSRF refusée', async () => {
    const response = await anonymous.request.post(api('/auth/login/'), {
      data: { username: 'alice@example.test', password },
    })
    assert.equal(response.status(), 403)
  })
  const registeredEmail = `recette-${Date.now()}@example.test`
  await check('T03', 'inscription en attente, sans session', async () => {
    const response = await post(anonymous.request, '/auth/register/', {
      email: registeredEmail, full_name: 'Personne Exemple', password,
    })
    assert.equal(response.status(), 201)
    assert.equal((await response.json()).status, 'pending')
    assert.equal((await anonymous.request.get(api('/auth/me/'))).status(), 401)
    const inactive = await post(anonymous.request, '/auth/login/', { username: registeredEmail, password })
    assert.equal(inactive.status(), 403)
    assert.equal((await inactive.json()).error.code, 'account_inactive')
  })

  const alice = await context()
  const alicePage = await alice.newPage()
  await check('T04', 'mauvais mot de passe affiché par le client', async () => {
    await login(alicePage, 'alice@example.test', 'mot-de-passe-errone')
    assert.match(alicePage.url(), /\/login$/)
    assert.ok((await alicePage.getByRole('alert').textContent())?.trim())
  })
  await check('T05', 'connexion candidat et tableau de bord réels', async () => {
    await login(alicePage, 'alice@example.test')
    await alicePage.waitForURL(/\/dashboard$/)
    const me = await alice.request.get(api('/auth/me/'))
    assert.equal(me.status(), 200)
    assert.equal((await me.json()).user.role, 'candidate')
  })
  await check('T06', 'catalogue et offre fictive visibles', async () => {
    await alicePage.goto('/stages')
    await alicePage.getByRole('heading', { name: 'Stages en Europe' }).waitFor()
    const response = await alice.request.get(api('/offers/'))
    assert.equal(response.status(), 200)
    assert.ok((await response.json()).count >= 2)
  })

  const bob = await context()
  const bobPage = await bob.newPage()
  await login(bobPage, 'bob@example.test')
  await bobPage.waitForURL(/\/dashboard$/)
  const bobApplications = await (await bob.request.get(api('/applications/'))).json()
  const bobApplicationId = bobApplications.results[0]?.id
  assert.ok(bobApplicationId)
  const bobProfile = await (await bob.request.get(api('/profile/'))).json()
  const bobDocumentId = bobProfile.current_resume_id
  assert.ok(bobDocumentId)
  let aliceOfferIds

  await check('T07', 'dossier candidat propre consultable', async () => {
    const own = await (await alice.request.get(api('/applications/'))).json()
    assert.ok(own.count >= 1)
    aliceOfferIds = new Set(own.results.map(item => item.offer_id))
    assert.equal((await alice.request.get(api(`/applications/${own.results[0].id}/`))).status(), 200)
  })
  await check('T08', 'ID de candidature tierce modifié dans l’URL refusé', async () => {
    assert.equal((await alice.request.get(api(`/applications/${bobApplicationId}/`))).status(), 404)
  })
  await check('T09', 'CV tiers et espace recruteur refusés au candidat', async () => {
    assert.equal((await alice.request.get(api(`/documents/${bobDocumentId}/download/`))).status(), 404)
    assert.equal((await alice.request.get(api('/recruiter/dashboard/'))).status(), 403)
  })
  await check('T10', 'source tierce refusée, candidature sans doublon', async () => {
    const catalogue = await (await alice.request.get(api('/offers/'))).json()
    const offer = catalogue.results.find(item => !aliceOfferIds.has(item.id))
    assert.ok(offer)
    const detail = await (await alice.request.get(api(`/offers/${offer.id}/`))).json()
    const payload = { offer_id: offer.id, source_id: detail.sources[0].id }
    const otherOffer = catalogue.results.find(item => item.id !== offer.id)
    const otherDetail = await (await alice.request.get(api(`/offers/${otherOffer.id}/`))).json()
    const invalid = await post(alice.request, '/applications/', {
      offer_id: offer.id, source_id: otherDetail.sources[0].id,
    })
    assert.equal(invalid.status(), 404)
    const first = await post(alice.request, '/applications/', payload)
    assert.equal(first.status(), 200)
    const second = await post(alice.request, '/applications/', payload)
    assert.equal(second.status(), 200)
    assert.equal((await first.json()).id, (await second.json()).id)
  })

  const recruiterA = await context()
  const recruiterAPage = await recruiterA.newPage()
  await check('T11', 'connexion recruteur et liste de ses offres', async () => {
    await login(recruiterAPage, 'recruteur_a@example.test')
    await recruiterAPage.waitForURL(/\/recruiter\/dashboard$/)
    const jobs = await recruiterA.request.get(api('/recruiter/jobs/'))
    assert.equal(jobs.status(), 200)
    assert.equal((await jobs.json()).count, 1)
  })
  const recruiterB = await context()
  const recruiterBPage = await recruiterB.newPage()
  await login(recruiterBPage, 'recruteur_b@example.test')
  await recruiterBPage.waitForURL(/\/recruiter\/dashboard$/)
  const otherJobs = await (await recruiterB.request.get(api('/recruiter/jobs/'))).json()
  const otherJobId = otherJobs.results[0]?.id
  assert.ok(otherJobId)
  await check('T12', 'ID d’offre d’un autre recruteur refusé', async () => {
    assert.equal((await recruiterA.request.get(api(`/recruiter/jobs/${otherJobId}/`))).status(), 404)
    assert.equal((await recruiterA.request.get(api(`/recruiter/jobs/${otherJobId}/applicants/`))).status(), 404)
  })
  await check('T13', 'administration active le compte en attente', async () => {
    const administrator = await context()
    const page = await administrator.newPage()
    await page.goto(`${adminBase}/admin/`)
    await page.locator('input[name="username"]').fill('admin')
    await page.locator('input[name="password"]').fill(password)
    await page.locator('input[type="submit"]').click()
    await page.waitForURL(`${adminBase}/admin/`)
    await page.goto(`${adminBase}/admin/auth/user/?q=${encodeURIComponent(registeredEmail)}`)
    await page.locator('#result_list tbody tr th a').first().click()
    const active = page.locator('#id_is_active')
    assert.equal(await active.isChecked(), false)
    await active.check()
    await page.locator('input[name="_save"]').click()
    const loginResponse = await post(anonymous.request, '/auth/login/', {
      username: registeredEmail, password,
    })
    assert.equal(loginResponse.status(), 200)
    assert.equal((await anonymous.request.get(api('/auth/me/'))).status(), 200)
  })
  await check('T14', 'candidat non autorisé dans Django Admin', async () => {
    const response = await alice.request.get(`${adminBase}/admin/`, { maxRedirects: 0 })
    assert.equal(response.status(), 302)
  })
  await check('T15', 'déconnexion révoque la session privée', async () => {
    await alicePage.getByRole('button', { name: 'Se déconnecter' }).click()
    await alicePage.waitForURL(/\/login$/)
    assert.equal((await alice.request.get(api('/auth/me/'))).status(), 401)
    assert.equal((await alice.request.get(api('/applications/'))).status(), 401)
  })
  console.log(`Recette navigateur/API : ${results.length} tests réussis.`)
} finally {
  await Promise.all(contexts.map(value => value.close()))
  await browser.close()
}
