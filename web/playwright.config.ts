import { resolve } from 'node:path'
import { defineConfig, devices } from '@playwright/test'

const reportDir = resolve(process.env.EDGEVISION_E2E_REPORT_DIR ?? 'playwright-report')
const outputDir = resolve(process.env.EDGEVISION_E2E_OUTPUT_DIR ?? 'test-results')
const discoveryOnly = process.argv.includes('--list')

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  outputDir,
  reporter: [[resolve('e2e/safe-reporter.ts'), { reportDir, discoveryOnly }]],
  use: {
    baseURL: process.env.EDGEVISION_E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
    reducedMotion: 'reduce',
    locale: 'zh-CN',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
