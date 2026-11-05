import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Local development proxies /api to the Python quality service on :8000.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '')
  const localApiUrl = env.VISIONFIT_LOCAL_API_URL || 'http://127.0.0.1:8000'
  return {
  plugins: [react()],
  define: {
    'import.meta.env.VITE_NEON_AUTH_URL': JSON.stringify(env.VITE_NEON_AUTH_URL || env.NEON_AUTH_BASE_URL || ''),
  },
  server: {
    proxy: {
      '/api': localApiUrl,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Playwright specs live under tests/ and use a real browser, not Vitest.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
  }
})
