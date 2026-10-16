// Screenshots from the real local API and database. No intercepted API responses.
import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const base = process.env.CAPTURES_URL || 'http://127.0.0.1:5173'
const adminBase = process.env.CAPTURES_ADMIN_URL || 'http://127.0.0.1:8000'
const password = process.env.CAPTURES_PASSWORD || 'Intern-Demo-2026!'
const directory = fileURLToPath(new URL('../captures/ecrans/', import.meta.url))
await mkdir(directory, { recursive: true })
const browser = await chromium.launch({ headless: true, ...(process.env.CAPTURES_BROWSER ? { channel: process.env.CAPTURES_BROWSER } : {}) })
const refresh = process.argv.includes('--refresh')
const rows = refresh ? JSON.parse(await readFile(`${directory}/manifest.json`, 'utf8')).screens.filter(row => Number.parseInt(row.filename) <= 15) : []
const contexts = []
const failures = []
async function saveManifest(complete = false) {
  await writeFile(`${directory}/manifest.json`, JSON.stringify({ complete, base, adminBase, backend: 'Django + PostgreSQL réels', api_interception: false, viewport: { width: 1440, height: 1000 }, screens: rows }, null, 2) + '\n')
}
async function pageFor(user) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, baseURL: base, locale: 'fr-FR' })
  contexts.push(context)
  const page = await context.newPage()
  page.on('pageerror', error => failures.push(error.message))
  if (user) {
    const csrf = await context.request.get(`${base}/api/v1/auth/csrf/`)
    assert.equal(csrf.status(), 200)
    const { csrf_token } = await csrf.json()
    const response = await context.request.post(`${base}/api/v1/auth/login/`, {
      data: { username: `${user}@example.test`, password }, headers: { 'X-CSRFToken': csrf_token },
    })
    assert.equal(response.status(), 200, `Connexion réelle de ${user}`)
  }
  return page
}
async function shot(page, filename, label, path) {
  if (path) {
    await page.goto(path)
    assert.equal(new URL(page.url()).pathname, new URL(path, base).pathname, `Écran attendu : ${path}`)
  }
  if (new URL(page.url()).pathname.startsWith('/admin/')) await page.locator('#content').waitFor()
  else await page.getByRole('heading').first().waitFor()
  await page.waitForLoadState('networkidle')
  await page.waitForFunction(() => [...document.querySelectorAll('[aria-busy="true"], [class*="skeleton"], [role="status"]')].every(node => {
    if (!node.getClientRects().length) return true
    if (node.getAttribute('aria-busy') === 'true' || node.className.includes('skeleton')) return false
    return !/^(Chargement|Vérification de la session|Lecture de la couverture)/.test(node.textContent.trim())
  }))
  if (path) assert.equal(new URL(page.url()).pathname, new URL(path, base).pathname, `Écran après chargement : ${path}`)
  const modal = await page.getByRole('dialog').count()
  if (modal) await page.setViewportSize({ width: 1440, height: 1800 })
  await page.evaluate(() => document.fonts.ready)
  if (await page.locator('iframe').count()) await page.waitForTimeout(2500)
  await page.screenshot({ path: `${directory}/${filename}.png`, fullPage: true, animations: 'disabled' })
  rows.push({ label, filename: `${filename}.png`, url: page.url(), captured_at: new Date().toISOString(), viewport: page.viewportSize() })
  if (modal) await page.setViewportSize({ width: 1440, height: 1000 })
  await saveManifest()
  console.log(`CAPTURE ${filename} — ${label}`)
}
async function json(page, path) {
  const response = await page.request.get(`${base}/api/v1${path}`, { maxRetries: 3 })
  assert.equal(response.status(), 200, path)
  return response.json()
}
try {
  if (!refresh) {
  const publicPage = await pageFor()
  await shot(publicPage, '01-connexion', 'Connexion', '/login')
  await publicPage.getByLabel('Adresse e-mail').fill('alice@example.test')
  await publicPage.getByLabel('Mot de passe', { exact: true }).fill('mot-de-passe-incorrect')
  await publicPage.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await publicPage.getByRole('alert').waitFor()
  await shot(publicPage, '02-connexion-erreur', 'Connexion : mot de passe incorrect')
  await publicPage.getByLabel('Mot de passe', { exact: true }).fill(password)
  await publicPage.getByLabel('Adresse e-mail').fill('attente@example.test')
  await publicPage.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await publicPage.getByRole('alert').waitFor()
  await shot(publicPage, '03-compte-inactif', 'Connexion : compte en attente')
  await shot(publicPage, '04-mot-de-passe-oublie', 'Demande de réinitialisation', '/reset-password')
  await shot(publicPage, '05-nouveau-mot-de-passe', 'Formulaire de nouveau mot de passe (jeton fictif, sans envoi)', '/reset-password?uid=demo&token=demo')
  async function register(role, offset) {
    const roleLabel = role === 'candidate' ? 'candidat' : 'recruteur'
    await publicPage.goto(role === 'recruiter' ? '/recruiter/signup' : '/register')
    await shot(publicPage, `${offset}-inscription-${role}-role`, `Inscription ${roleLabel} : choix du rôle`)
    await publicPage.getByRole('button', { name: 'Continuer', exact: true }).click()
    await shot(publicPage, `${offset + 1}-inscription-${role}-email`, `Inscription ${roleLabel} : e-mail`)
    await publicPage.getByLabel('Adresse e-mail').fill(`capture-${role}-${Date.now()}@example.test`)
    await publicPage.getByRole('button', { name: 'Continuer', exact: true }).click()
    await publicPage.getByLabel('Nom complet').waitFor()
    await shot(publicPage, `${offset + 2}-inscription-${role}-nom`, `Inscription ${roleLabel} : nom`)
    await publicPage.getByLabel('Nom complet').fill('Personne Démonstration')
    await publicPage.getByRole('button', { name: 'Continuer', exact: true }).click()
    await publicPage.getByLabel('Mot de passe', { exact: true }).waitFor()
    await shot(publicPage, `${offset + 3}-inscription-${role}-mot-de-passe`, `Inscription ${roleLabel} : mot de passe`)
    await publicPage.getByLabel('Mot de passe', { exact: true }).fill(password)
    await publicPage.getByRole('button', { name: 'Créer mon compte', exact: true }).click()
    await publicPage.getByRole('heading', { name: 'Votre demande est enregistrée.' }).waitFor()
    await shot(publicPage, `${offset + 4}-inscription-${role}-attente`, `Inscription ${roleLabel} : confirmation en attente`)
  }
  await register('candidate', 6)
  await register('recruiter', 11)
  }
  const alice = await pageFor('alice')
  for (const [id, label, path] of [
    ['16-tableau-de-bord', 'Tableau de bord candidat', '/dashboard'],
    ['17-catalogue-stages', 'Catalogue des stages', '/stages'],
    ['18-candidatures', 'Candidatures du candidat', '/candidatures'],
    ['19-a-valider', 'Candidatures à valider', '/a-valider'],
    ['20-tracker', 'Suivi des candidatures', '/tracker'],
    ['21-profil', 'Profil et CV candidat', '/profil'],
    ['22-moteur', 'Moteur de candidatures', '/engine'],
    ['23-onboarding-cv', 'Configuration : CV', '/onboarding/resume'],
    ['24-onboarding-adresse', 'Configuration : adresse', '/onboarding/address'],
    ['25-onboarding-eligibilite', 'Configuration : droit au travail', '/onboarding/work-eligibility'],
    ['26-page-introuvable', 'Page introuvable', '/page-inconnue'],
  ]) await shot(alice, id, label, path)
  const offers = (await json(alice, '/offers/')).results
  assert.ok(offers.length, 'Catalogue fictif non vide')
  const offer = offers[0]
  await shot(alice, '27-detail-stage', 'Détail d’un stage', `/offers/${offer.id}`)
  const detail = await json(alice, `/offers/${offer.id}/`)
  const companyId = typeof detail.company === 'object' ? detail.company.id : detail.company_id || detail.company
  assert.ok(companyId, 'Entreprise de l’offre')
  await shot(alice, '28-entreprise', 'Page entreprise', `/companies/${companyId}`)
  const applications = (await json(alice, '/applications/')).results
  assert.ok(applications.length)
  await shot(alice, '29-detail-candidature', 'Détail d’une candidature', `/applications/${applications[0].id}`)
  const empty = await pageFor('vide')
  await shot(empty, '30-candidatures-vides', 'Candidat sans candidature', '/candidatures')
  const recruiter = await pageFor('recruteur_a')
  for (const [id, label, path] of [
    ['31-recruteur-tableau-de-bord', 'Tableau de bord recruteur', '/recruiter/dashboard'],
    ['32-recruteur-offres', 'Offres du recruteur', '/recruiter/jobs'],
    ['33-recruteur-candidats', 'Candidatures reçues', '/recruiter/candidates'],
    ['34-recruteur-entreprise', 'Entreprise vérifiée', '/recruiter/verify'],
    ['35-recruteur-integrations', 'Intégrations ATS', '/recruiter/integrations'],
    ['36-recruteur-nouvelle-offre', 'Nouvelle offre : informations générales', '/recruiter/jobs/new'],
  ]) await shot(recruiter, id, label, path)
  const jobs = (await json(recruiter, '/recruiter/jobs/')).results
  assert.ok(jobs.length)
  await shot(recruiter, '37-recruteur-modifier-offre', 'Modifier une offre : informations générales', `/recruiter/jobs/${jobs[0].id}/edit`)
  await recruiter.getByRole('button', { name: 'Continuer', exact: true }).click()
  await shot(recruiter, '38-recruteur-missions', 'Offre : missions et compétences')
  await recruiter.getByRole('button', { name: 'Continuer', exact: true }).click()
  await shot(recruiter, '39-recruteur-matching', 'Offre : critères de matching')
  await recruiter.getByRole('button', { name: 'Continuer', exact: true }).click()
  await shot(recruiter, '40-recruteur-apercu', 'Offre : aperçu avant publication (sans publier)')
  await shot(recruiter, '41-recruteur-candidatures-offre', 'Candidatures reçues pour une offre', `/recruiter/jobs/${jobs[0].id}/applicants`)
  const candidates = (await json(recruiter, '/recruiter/candidates/')).results
  assert.ok(candidates.length)
  await shot(recruiter, '42-recruteur-fiche-candidat', 'Fiche du candidat reçu', `/recruiter/candidates/${candidates[0].id}`)
  const unverified = await pageFor('recruteur_non_verifie')
  await shot(unverified, '43-recruteur-verification', 'Vérification professionnelle requise', '/recruiter/verify')
  const admin = await pageFor()
  await admin.goto(`${adminBase}/admin/`)
  await shot(admin, '44-administration-connexion', 'Connexion Django Admin')
  await admin.locator('input[name="username"]').fill('admin')
  await admin.locator('input[name="password"]').fill(password)
  await admin.locator('input[type="submit"]').click()
  await admin.waitForURL(`${adminBase}/admin/`)
  await shot(admin, '45-administration-accueil', 'Accueil administration')
  await shot(admin, '46-administration-utilisateurs', 'Administration : utilisateurs', `${adminBase}/admin/auth/user/`)
  const userLink = admin.locator('#result_list tbody tr th a').first()
  await userLink.click()
  await shot(admin, '47-administration-utilisateur', 'Administration : détail et activation d’un utilisateur')
  await shot(admin, '48-administration-offres', 'Administration : offres', `${adminBase}/admin/jobboard/offer/`)
  await admin.locator('#result_list tbody tr th a').first().click()
  await shot(admin, '49-administration-offre', 'Administration : détail d’une offre')
  assert.equal(rows.length, 49, 'Tous les écrans attendus sont capturés')
  assert.deepEqual(failures, [], 'Aucune erreur JavaScript')
  await saveManifest(true)
  const table = rows.map(row => `| ${row.label} | [${row.filename}](ecrans/${row.filename}) |`).join('\n')
  await writeFile(fileURLToPath(new URL('../captures/README.md', import.meta.url)), `# Captures des écrans principaux\n\n${rows.length} captures réelles dans Chromium, sur React/Vite, Django et PostgreSQL\nlancés en local. Aucune réponse API interceptée ou simulée. Données fictives.\nRésolution : 1440 × 1000 par défaut, 1440 × 1800 pour la fiche candidat\nouverte dans une fenêtre modale. Capture de toute la hauteur de chaque page.\n\n| Écran | Capture |\n| --- | --- |\n${table}\n\nLe [manifeste](ecrans/manifest.json) conserve les URL et les dates de capture.\nLe formulaire de nouveau mot de passe utilise un jeton fictif : il montre le\nrendu, sans prétendre vérifier un lien de réinitialisation valide. Les\nassistants de création/modification sont capturés sans publication.\n\nReproduction depuis Intern : suivre [EXECUTION.md, étape 5](../../EXECUTION.md#étape-5--couche-présentation),\npuis lancer \`node frontend/scripts/capturer_ecrans.mjs\`. Le script crée\ndeux comptes fictifs en attente ; ne pas l’utiliser sur une base personnelle.\n\nLes quatre fichiers historiques à la racine de ce dossier (connexion.png,\ninscription-attente.png, profil-candidat.png, espace-recruteur.png) proviennent\nde tests avec API contrôlée. Ils ne font pas partie de la série réelle ci-dessus.\nLa conformité au prototype Figma reste à comparer écran par écran.\n`)
  console.log(`${rows.length} captures réelles terminées.`)
} finally {
  await Promise.all(contexts.map(context => context.close()))
  await browser.close()
}
