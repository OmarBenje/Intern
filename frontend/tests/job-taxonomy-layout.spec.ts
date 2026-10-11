import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import type { JobTaxonomy } from '../src/components/offers/JobTaxonomyPicker'
import { prepareDashboard } from './fixtures/dashboard'

// The complete vocabulary exercises long labels and a genuinely scrollable list.
// Counts are fixed so this layout check does not depend on a running database.
const vocabulary = JSON.parse(readFileSync(new URL('../../metier/app/jobboard/data/job-taxonomy-v1.json', import.meta.url), 'utf8')) as JobTaxonomy
const taxonomy = { ...vocabulary, domains: vocabulary.domains.map((domain, index) => ({ ...domain, count: 298 - index * 11, subdomains: domain.subdomains.map((sub, index) => ({ ...sub, count: index + 1 })) })) }

for (const view of [
  { name: 'desktop', width: 1280, height: 900, theme: 'light' },
  { name: 'dark', width: 1280, height: 900, theme: 'dark' },
  { name: 'mobile', width: 320, height: 740, theme: 'light' },
  { name: 'short', width: 800, height: 520, theme: 'light' },
]) {
  test(`long taxonomy keeps search and actions visible on ${view.name}`, async ({ page }, info) => {
    await page.setViewportSize(view)
    await prepareDashboard(page)
    await page.route('**/api/v1/taxonomy/**', route => route.fulfill({ json: taxonomy }))
    await page.goto(`/stages?domains=${taxonomy.domains.map(domain => domain.slug).join(',')}`)
    await page.evaluate(theme => { document.documentElement.className = theme }, view.theme)
    await page.getByRole('button', { name: 'Domaines et métiers', exact: true }).click()
    const dialog = page.getByRole('dialog')
    const search = dialog.getByRole('searchbox')
    await expect(search).toBeFocused()
    const list = dialog.locator('.job-taxonomy-groups')
    expect(await list.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true)
    await list.evaluate(element => { element.scrollTop = element.scrollHeight })
    for (const control of [search, dialog.getByRole('button', { name: 'Voir les offres' })]) {
      const box = await control.boundingBox()
      expect(box!.y).toBeGreaterThanOrEqual(0)
      expect(box!.y + box!.height).toBeLessThanOrEqual(view.height)
    }
    expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
    await list.evaluate(element => { element.scrollTop = 0 })
    await dialog.locator('summary').first().click()
    await dialog.getByRole('searchbox').blur()
    await dialog.screenshot({ animations: 'disabled', path: info.outputPath(`taxonomy-${view.name}.png`) })
    await dialog.getByRole('button', { name: `Retirer la sélection : ${taxonomy.domains[0].name}`, exact: true }).click()
    await expect(dialog.getByRole('status')).toHaveText(`${taxonomy.domains.length - 1} sélections`)
    await expect(dialog.locator('details').first()).not.toHaveAttribute('data-selected', 'true')
    await dialog.getByRole('button', { name: 'Effacer la sélection' }).click()
    await expect(dialog.getByRole('status')).toHaveText('Tous les domaines')
    await expect(dialog.locator('.job-taxonomy-selections')).toHaveCount(0)
    await dialog.locator('summary').first().click()
    await dialog.screenshot({ animations: 'disabled', path: info.outputPath(`taxonomy-${view.name}-default.png`) })
    await dialog.getByRole('button', { name: 'Annuler', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Domaines et métiers', exact: true })).toContainText(`${taxonomy.domains.length} sélections`)
  })
}
