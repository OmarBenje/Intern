// Recette sur le déploiement réel : lectures, authentification et téléchargement du CV fictif.
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const require = createRequire(new URL('../../frontend/package.json', import.meta.url))
const { chromium } = require('@playwright/test')
const base = process.env.RECETTE_URL || 'http://127.0.0.1:8080'
const password = process.env.RECETTE_PASSWORD
if (!password) throw new Error('Définir RECETTE_PASSWORD avec le mot de passe du jeu fictif.')
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const docs = fileURLToPath(new URL('../docs/', import.meta.url))
const results = []
const apiOrigins = new Set()
const pageErrors = []
const contexts = []

async function session() {
  const context = await browser.newContext({ baseURL: base, viewport: { width: 1440, height: 960 } })
  contexts.push(context)
  context.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/v1/')) apiOrigins.add(url.origin)
  })
  const page = await context.newPage()
  page.on('pageerror', error => pageErrors.push(error.message))
  return { context, page }
}

async function check(label, action) {
  await action()
  results.push(`PASS — ${label}`)
  console.log(results.at(-1))
}

async function login(page, email, target) {
  await page.goto('/login')
  await page.getByLabel('Adresse e-mail').fill(email)
  await page.getByLabel('Mot de passe', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await page.waitForURL(url => url.pathname === target)
}

try {
  const { context, page } = await session()
  await check('proxy, métier et base répondent via /health/ready/', async () => {
    const response = await context.request.get('/health/ready/')
    assert.equal(response.status(), 200)
    assert.equal((await response.json()).status, 'ok')
  })
  await check('session anonyme refusée et mutation sans CSRF refusée', async () => {
    assert.equal((await context.request.get('/api/v1/auth/me/')).status(), 401)
    const response = await context.request.post('/api/v1/auth/login/', { data: { username: 'alice@example.test', password } })
    assert.equal(response.status(), 403)
  })
  await page.goto('/login')
  await page.getByRole('button', { name: 'Se connecter', exact: true }).waitFor()
  await page.screenshot({ path: docs + 'etape9-connexion.png', fullPage: true })
  await check('connexion candidat depuis le client React et session persistante', async () => {
    await login(page, 'alice@example.test', '/dashboard')
    const me = await context.request.get('/api/v1/auth/me/')
    assert.equal(me.status(), 200)
    assert.equal((await me.json()).user.role, 'candidate')
    await page.reload()
    await page.waitForURL(url => url.pathname === '/dashboard')
    await page.getByRole('button', { name: 'Se déconnecter' }).waitFor()
    await page.locator('#main-content[aria-busy="false"]').waitFor()
    await page.locator('.dashboard-table tbody .application-position').first().waitFor()
    await page.screenshot({ path: docs + 'etape9-tableau-de-bord.png', fullPage: true })
  })
  await check('catalogue fictif accessible via Nginx', async () => {
    await page.goto('/stages')
    await page.getByRole('heading', { name: 'Stages en Europe' }).waitFor()
    const response = await context.request.get('/api/v1/offers/')
    assert.equal(response.status(), 200)
    assert.ok((await response.json()).count >= 2)
  })
  await check('CV fictif privé téléchargé par son propriétaire', async () => {
    const profile = await context.request.get('/api/v1/profile/')
    assert.equal(profile.status(), 200)
    const id = (await profile.json()).current_resume_id
    assert.ok(id)
    const pdf = await context.request.get(`/api/v1/documents/${id}/download/`)
    assert.equal(pdf.status(), 200)
    assert.equal((await pdf.body()).subarray(0, 5).toString(), '%PDF-')
  })
  await check('connexion recruteur et tableau de bord réel', async () => {
    const recruiter = await session()
    await login(recruiter.page, 'recruteur_a@example.test', '/recruiter/dashboard')
    const me = await recruiter.context.request.get('/api/v1/auth/me/')
    assert.equal(me.status(), 200)
    assert.equal((await me.json()).user.role, 'recruiter')
    assert.equal((await recruiter.context.request.get('/api/v1/recruiter/dashboard/')).status(), 200)
  })
  await check('administration Django et ses fichiers statiques accessibles', async () => {
    assert.equal((await context.request.get('/admin/login/')).status(), 200)
    const css = await context.request.get('/static/admin/css/base.css')
    assert.equal(css.status(), 200)
    assert.match(css.headers()['content-type'], /text\/css/)
  })
  await check('appels API du navigateur sur la même origine et absence d’erreur JavaScript', async () => {
    assert.deepEqual([...apiOrigins], [new URL(base).origin])
    assert.deepEqual(pageErrors, [])
  })
  results.push(`Navigateur : ${browser.version()}`)
  results.push(`Origine API observée : ${[...apiOrigins].join(', ')}`)
  await writeFile(docs + 'recette-etape9.txt', results.join('\n') + '\n')
} finally {
  for (const context of contexts) await context.close()
  await browser.close()
}
