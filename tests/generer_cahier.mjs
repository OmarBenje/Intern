import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { chromium } = require('@playwright/test')
const source = new URL('./cahier_de_tests.html', import.meta.url)
const output = fileURLToPath(new URL('./cahier_de_tests.pdf', import.meta.url))
const browser = await chromium.launch({ channel: 'chrome', headless: true })
try {
  const page = await browser.newPage()
  await page.goto(source.href)
  await page.pdf({ path: output, preferCSSPageSize: true, printBackground: true })
  console.log('Cahier PDF généré.')
} finally {
  await browser.close()
}
