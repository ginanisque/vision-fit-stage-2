import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// Unit tests must never contact the configured Neon Auth service.
vi.mock('../lib/auth-client', () => ({
  bearerToken: vi.fn().mockResolvedValue('test-bearer-token'),
  authClient: {
    signIn: { email: vi.fn() }, signUp: { email: vi.fn() }, signOut: vi.fn(),
  },
}))

// Auto-cleanup needs a global afterEach; provide it explicitly since vitest globals are off.
afterEach(() => {
  cleanup()
})

// jsdom does not implement object URLs; stub them for previews.
if (typeof URL.createObjectURL !== 'function') {
  URL.createObjectURL = () => 'blob:mock-url'
  URL.revokeObjectURL = () => undefined
}

