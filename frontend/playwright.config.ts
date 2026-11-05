import { defineConfig } from '@playwright/test'

// Local browser QA: starts the Python service and the Vite dev server, then runs
// the specs in ./tests against the real app (frontend proxied to the service).
export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  expect: { timeout: 15000 },
  use: {
    baseURL: 'http://127.0.0.1:5173',
    headless: true,
  },
  webServer: [
    {
      command: './.venv/bin/python -m uvicorn app.main:app --port 8000',
      cwd: '../service',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: true,
      timeout: 30000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: true,
      timeout: 30000,
    },
  ],
})
