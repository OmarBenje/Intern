import { expect, test } from '@playwright/test'

test('disabled queries are idle, clear prior data and ignore an in-flight response', async ({ page }) => {
  let calls = 0
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/query-test/first/', async route => {
    calls++
    await route.fulfill({ json: { name: 'first' } })
  })
  await page.route('**/api/v1/query-test/second/', async route => {
    calls++
    await gate
    await route.fulfill({ json: { name: 'late response' } }).catch(() => {})
  })
  await page.goto('/tests/fixtures/use-api-query.html')
  const state = page.getByLabel('Query state')
  const idle = JSON.stringify({ data: null, error: null, loading: false })
  await expect(state).toHaveText(idle)
  await page.getByRole('button', { name: 'Reload query' }).click()
  await expect(state).toHaveText(idle)
  expect(calls).toBe(0)
  await page.getByRole('button', { name: 'First query' }).click()
  await expect(state).toHaveText(JSON.stringify({ data: { name: 'first' }, error: null, loading: false }))
  await page.getByRole('button', { name: 'Disable query' }).click()
  await expect(state).toHaveText(idle)
  await page.getByRole('button', { name: 'Second query' }).click()
  await expect(state).toHaveText(JSON.stringify({ data: null, error: null, loading: true }))
  await expect.poll(() => calls).toBe(2)
  await page.getByRole('button', { name: 'Disable query' }).click()
  await expect(state).toHaveText(idle)
  release()
  await page.getByRole('button', { name: 'Reload query' }).click()
  await expect(state).toHaveText(idle)
  expect(calls).toBe(2)
})
