import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

async function backend(page: Page, authenticated = false) {
  const commands: { path: string; data: Record<string, string>; csrf: string | undefined }[] = []
  let signedIn = authenticated
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path.endsWith('/csrf/')) return route.fulfill({ json: { csrf_token: 'before-login' } })
    if (path.endsWith('/me/')) return route.fulfill(signedIn
      ? { json: { user: { id: 1, username: 'ada', email: 'ada@example.test' } } }
      : { status: 401, json: { error: { code: 'not_authenticated' } } })
    if (request.method() === 'GET') return route.fulfill({ json: { offers: [], applications: { results: [], count: 0, page: 1, page_size: 8 }, counts: { applications: 0, needs_input: 0 }, full_name: 'Ada' } })
    commands.push({ path, data: request.postDataJSON(), csrf: request.headers()['x-csrftoken'] })
    if (path.endsWith('/login/')) {
      signedIn = true
      return route.fulfill({ json: { user: { id: 1, username: 'ada', email: 'ada@example.test' }, csrf_token: 'after-login' } })
    }
    if (path.endsWith('/logout/')) signedIn = false
    return route.fulfill({ json: { ok: true } })
  })
  return commands
}

async function fillLogin(page: Page) {
  await expect(page.getByRole('button', { name: 'Se connecter', exact: true })).toBeEnabled()
  await page.getByLabel('Adresse e-mail').fill('ada@example.test')
  await page.getByLabel('Mot de passe', { exact: true }).fill('test-password-only')
}

test('desktop: editorial spread, password visibility and CSRF login/logout', async ({ page }, testInfo) => {
  const commands = await backend(page)
  await page.goto('/login')
  await fillLogin(page)
  await expect(page.locator('.auth-visual img')).toBeVisible()
  await expect(page.locator('.auth-image-slot')).toHaveCount(0)
  await expect(page.locator('.auth-visual img')).toHaveJSProperty('naturalWidth', 1086)
  const viewport = page.viewportSize()!
  await expect(page.locator('.auth-layout')).toHaveCSS('min-height', `${viewport.height}px`)
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight && document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  const visual = await page.locator('.auth-visual').boundingBox()
  const form = await page.locator('.auth-panel').boundingBox()
  expect(visual!.x + visual!.width).toBeLessThanOrEqual(form!.x)
  await expect(page).toHaveTitle('Connexion — Intern')
  await page.getByRole('button', { name: 'Afficher le mot de passe' }).click()
  await expect(page.getByLabel('Mot de passe', { exact: true })).toHaveAttribute('type', 'text')
  await page.getByRole('button', { name: 'Masquer le mot de passe' }).click()
  await page.screenshot({ path: testInfo.outputPath('login-desktop.png'), fullPage: true })
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  expect(commands[0]).toEqual({ path: '/api/v1/auth/login/', data: { username: 'ada@example.test', password: 'test-password-only' }, csrf: 'before-login' })
  await page.getByRole('button', { name: 'Se déconnecter' }).click()
  await expect(page).toHaveURL(/\/login$/)
  expect(commands[1].csrf).toBe('after-login')
})

test('private deep link returns to its section after login', async ({ page }) => {
  await backend(page)
  await page.goto('/candidatures')
  await expect(page).toHaveURL(/\/login$/)
  await fillLogin(page)
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await expect(page).toHaveURL(/\/candidatures$/)
})

test('existing session bypasses login', async ({ page }) => {
  await backend(page, true)
  await page.goto('/login')
  await expect(page).toHaveURL(/\/dashboard$/)
})

test('invalid fields show inline feedback without native tooltips and recover on correction', async ({ page }, info) => {
  const commands = await backend(page)
  await page.goto('/login')
  const email = page.getByLabel('Adresse e-mail')
  const password = page.getByLabel('Mot de passe', { exact: true })
  const submit = page.getByRole('button', { name: 'Se connecter', exact: true })
  await expect(submit).toBeEnabled()
  await email.evaluate(input => {
    input.addEventListener('invalid', event => {
      queueMicrotask(() => { input.setAttribute('data-native-tooltip-suppressed', String(event.defaultPrevented)) })
    })
  })
  await submit.click()
  await expect(email).toBeFocused()
  await expect(email).toHaveAccessibleDescription('Renseignez ce champ.')
  await expect(email).toHaveAttribute('data-native-tooltip-suppressed', 'true')
  await expect(password).toHaveAccessibleDescription('Renseignez ce champ.')
  await expect(email).toHaveCSS('outline-style', 'none')
  expect(commands).toHaveLength(0)
  await email.fill('invalid-address')
  await password.fill('test-password-only')
  await password.press('Enter')
  await expect(email).toBeFocused()
  await expect(email).toHaveAccessibleDescription('Saisissez une adresse e-mail valide.')
  await page.screenshot({ path: info.outputPath('login-inline-error.png'), fullPage: true })
  expect(commands).toHaveLength(0)
  await email.fill('ada@example.test')
  await expect(email).not.toHaveAttribute('aria-invalid', 'true')
  await expect(page.locator('.auth-field-error')).toHaveCount(0)
  await email.press('Enter')
  await expect(page).toHaveURL(/\/dashboard$/)
  expect(commands.filter(command => command.path.endsWith('/login/'))).toHaveLength(1)
})

test('invalid credentials remain on form with accessible error and no automatic retry', async ({ page }) => {
  await backend(page)
  let calls = 0
  await page.route('**/api/v1/auth/login/', async route => {
    calls++
    await route.fulfill({ status: 401, json: { error: { code: 'invalid_credentials', message: 'Invalid credentials.' } } })
  })
  await page.goto('/login'); await fillLogin(page)
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('incorrect')
  await expect(page.getByLabel('Adresse e-mail')).toHaveAttribute('aria-invalid', 'true')
  await expect(page).toHaveURL(/\/login$/)
  expect(calls).toBe(1)
})

test('inactive account explains the pending validation', async ({ page }) => {
  await backend(page)
  await page.route('**/api/v1/auth/login/', route => route.fulfill({ status: 403, json: { error: { code: 'account_inactive' } } }))
  await page.goto('/login'); await fillLogin(page)
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('validation du superviseur')
  await expect(page).toHaveURL(/\/login$/)
})

test('pending login blocks repeated submissions', async ({ page }, info) => {
  await backend(page)
  let calls = 0
  let finish: () => void = () => {}
  const pending = new Promise<void>(resolve => { finish = resolve })
  await page.route('**/api/v1/auth/login/', async route => {
    calls++; await pending
    await route.fulfill({ json: { user: { id: 1, username: 'ada', email: 'ada@example.test' }, csrf_token: 'rotated' } })
  })
  await page.goto('/login'); await fillLogin(page)
  const button = page.getByRole('button', { name: 'Se connecter', exact: true })
  await button.screenshot({ path: info.outputPath('login-button.png') })
  const before = await button.boundingBox()
  await button.click()
  const loading = page.getByRole('button', { name: 'Connexion en cours…' })
  await expect(loading).toBeDisabled()
  await expect(loading).toHaveAttribute('aria-busy', 'true')
  await expect(loading).toHaveCSS('opacity', '1')
  await loading.screenshot({ path: info.outputPath('login-button-loading.png') })
  const during = await loading.boundingBox()
  expect(during!.width).toBe(before!.width)
  expect(during!.height).toBe(before!.height)
  await page.locator('form').evaluate(form => { form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })) })
  finish()
  await expect(page).toHaveURL(/\/dashboard$/)
  expect(calls).toBe(1)
})

test('HTML outage and rate limit have useful errors', async ({ page }) => {
  await backend(page)
  await page.route('**/api/v1/auth/login/', route => route.fulfill({ status: 502, contentType: 'text/html', body: '<h1>Bad gateway</h1>' }))
  await page.goto('/login'); await fillLogin(page)
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('momentanément indisponible')
  await page.route('**/api/v1/auth/login/', route => route.fulfill({ status: 429, json: { error: { code: 'rate_limited' } } }))
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Trop de tentatives')
})

test('reset request does not reveal whether account exists', async ({ page }) => {
  const commands = await backend(page)
  await page.goto('/login')
  await page.getByRole('link', { name: 'Mot de passe oublié ?' }).click()
  await expect(page).toHaveURL(/\/reset-password$/)
  await expect(page.getByRole('form', { name: 'Réinitialisation du mot de passe' })).toBeVisible()
  await page.getByRole('form', { name: 'Réinitialisation du mot de passe' }).getByLabel('Adresse e-mail').fill('ada@example.test')
  await page.getByRole('button', { name: 'Recevoir un lien' }).click()
  await expect(page.getByRole('status')).toContainText('Si un compte correspond')
  expect(commands[0].data).toEqual({ email: 'ada@example.test' })
  expect(commands[0].csrf).toBe('before-login')
})

test('reset confirmation validates match, sends token and removes it from URL', async ({ page }) => {
  const commands = await backend(page)
  await page.goto('/reset-password?uid=test-uid&token=test-token')
  await page.getByLabel('Nouveau mot de passe', { exact: true }).fill('new-test-password')
  await page.getByLabel('Confirmer le mot de passe', { exact: true }).fill('different-password')
  await page.getByRole('button', { name: 'Enregistrer le mot de passe' }).click()
  await expect(page.getByRole('alert')).toContainText('ne correspondent pas')
  expect(commands).toHaveLength(0)
  await page.getByLabel('Confirmer le mot de passe', { exact: true }).fill('new-test-password')
  await page.getByRole('button', { name: 'Enregistrer le mot de passe' }).click()
  await expect(page.getByRole('status')).toContainText('maintenant vous connecter')
  await expect(page).toHaveURL(/\/reset-password$/)
  expect(commands[0].data).toEqual({ uid: 'test-uid', token: 'test-token', new_password: 'new-test-password' })
})

test('mobile: no overflow, labelled fields and visible keyboard focus', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await backend(page)
  await page.goto('/login')
  await expect(page.getByRole('button', { name: 'Se connecter', exact: true })).toBeEnabled()
  await expect(page.locator('.auth-visual')).toBeHidden()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByLabel('Adresse e-mail').focus()
  await page.keyboard.press('Tab')
  await expect(page.getByLabel('Mot de passe', { exact: true })).toBeFocused()
  await expect(page.getByLabel('Mot de passe', { exact: true })).toHaveCSS('outline-style', 'none')
  await expect(page.locator('.auth-password-field .auth-field-rule')).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 0)')
  await page.screenshot({ path: testInfo.outputPath('login-mobile.png'), fullPage: true })
})

test('floating labels remain readable after editing, clearing and browser-restored values', async ({ page }, info) => {
  await backend(page)
  await page.goto('/login')
  const email = page.getByLabel('Adresse e-mail')
  const label = page.locator('.auth-field--floating label').first()
  const labelAboveValue = () => email.evaluate(input => {
    const field = input.getBoundingClientRect()
    const label = input.nextElementSibling!.getBoundingClientRect()
    return label.bottom <= field.top + parseFloat(getComputedStyle(input).paddingTop)
  })
  await expect(label).toBeVisible()
  await email.click()
  await expect.poll(labelAboveValue).toBe(true)
  await email.fill('ada@example.test')
  await page.getByRole('heading', { level: 1 }).click()
  await expect.poll(labelAboveValue).toBe(true)
  await email.fill('')
  await page.getByRole('heading', { level: 1 }).click()
  await expect.poll(labelAboveValue).toBe(false)
  // Browser restoration can change an input's DOM value without a React input event.
  await email.evaluate(input => { (input as HTMLInputElement).value = 'restored@example.test' })
  await expect.poll(labelAboveValue).toBe(true)
  await page.screenshot({ path: info.outputPath('login-restored-value.png'), fullPage: true })
  await email.focus()
  await page.keyboard.press('Tab')
  const password = page.getByLabel('Mot de passe', { exact: true })
  await expect(password).toBeFocused()
  await password.fill('Test-only-482!')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: 'Afficher le mot de passe' })).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(password).toHaveAttribute('type', 'text')
  await expect(password).toHaveValue('Test-only-482!')
  await expect(page.locator('.auth-password-eye-off')).toHaveCSS('opacity', '1')
  await expect(page.locator('.auth-password-eye-off')).toHaveCSS('transition-duration', '0s')
})

test('malformed success does not pretend login succeeded', async ({ page }) => {
  await backend(page)
  await page.route('**/api/v1/auth/login/', route => route.fulfill({ json: { unexpected: true } }))
  await page.goto('/login'); await fillLogin(page)
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('momentanément indisponible')
  await expect(page).toHaveURL(/\/login$/)
})

test('CSRF rejection allows a manual fresh attempt without replaying login automatically', async ({ page }) => {
  await backend(page)
  let attempts = 0, tokens = 0
  await page.route('**/api/v1/auth/csrf/', route => { tokens++; return route.fulfill({ json: { csrf_token: `csrf-${tokens}` } }) })
  await page.route('**/api/v1/auth/login/', async route => {
    attempts++
    if (attempts === 1) return route.fulfill({ status: 403, json: { error: { code: 'csrf_failed' } } })
    expect(route.request().headers()['x-csrftoken']).toBe('csrf-2')
    await route.fulfill({ json: { user: { id: 1, username: 'ada', email: 'ada@example.test' }, csrf_token: 'rotated' } })
  })
  await page.goto('/login'); await fillLogin(page)
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('sécurité a expiré')
  expect(attempts).toBe(1)
  await page.getByRole('button', { name: 'Se connecter', exact: true }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  expect(attempts).toBe(2)
})
