import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { test, expect } from '@playwright/test'

const fixtures = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures')
const subject = path.join(fixtures, 'subject.png')

test('capture wizard runs end-to-end in a real browser', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Ginani VisionFit')).toBeVisible()

  // Consent gate: Continue stays disabled until both boxes are checked.
  const continueBtn = page.getByRole('button', { name: /continue/i })
  await expect(continueBtn).toBeDisabled()
  await page.getByLabel(/consent to my body photos/i).check()
  await page.getByLabel(/understand why captures/i).check()
  await expect(continueBtn).toBeEnabled()
  await continueBtn.click()

  // Height entry.
  await page.getByLabel(/height/i).fill('165')
  await page.getByRole('button', { name: /continue/i }).click()

  // Front and side photographs.
  await page.getByLabel('front image input').setInputFiles(subject)
  await page.getByRole('button', { name: /continue/i }).click()
  await page.getByLabel('side image input').setInputFiles(subject)
  await page.getByRole('button', { name: /continue/i }).click()

  // Run the capture checks: this is a real browser -> service -> browser round trip.
  await page.getByRole('button', { name: /check quality/i }).click()
  await expect(
    page.getByRole('heading', { name: /recapture needed|review needed|quality passed/i }),
  ).toBeVisible()

  // Evidence overlay is rendered on the actual capture in the browser.
  await expect(page.locator('svg[aria-label="front detected evidence"]')).toBeVisible()

  // Slow-turn video step is present.
  await expect(page.getByRole('heading', { name: /slow-turn video/i })).toBeVisible()
})
