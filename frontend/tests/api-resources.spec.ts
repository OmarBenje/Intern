import { expect, test } from '@playwright/test'

test('resource URLs accept the configured and legacy API roots with strict logo validation', async ({ page }) => {
  await page.goto('/')
  const result = await page.evaluate(async () => {
    // Load the same modules as the application through Vite.
    // @ts-expect-error Vite serves these source modules directly in the browser.
    const { API_ROOT, apiResourceUrl } = await import('/src/lib/api.ts')
    // @ts-expect-error Vite serves these source modules directly in the browser.
    const { logoCandidates } = await import('/src/lib/companyLogos.ts')
    return {
      root: API_ROOT,
      configured: apiResourceUrl(`${API_ROOT}/cv/download/`),
      legacy: apiResourceUrl('/api/v1/cv/download/'),
      rejected: ['https://other.example/api/v1/cv/', '//other.example/api/v1/cv/', `${API_ROOT}-other/cv/`].map(apiResourceUrl),
      logos: [API_ROOT, '/api/v1'].map(root => logoCandidates(7, `${root}/companies/7/logo/?v=test`)),
      invalidLogos: [
        `${API_ROOT}/companies/8/logo/?v=test`,
        `${API_ROOT}/companies/7/logo/?v=test&extra=1`,
      ].map(url => logoCandidates(7, url)),
    }
  })
  expect(result.configured).toBe(`${result.root}/cv/download/`)
  expect(result.legacy).toBe(result.configured)
  expect(result.rejected).toEqual([null, null, null])
  expect(result.logos).toEqual([[`${result.root}/companies/7/logo/?v=test`], [`${result.root}/companies/7/logo/?v=test`]])
  expect(result.invalidLogos).toEqual([[], []])
})
