import { beforeEach, describe, expect, it, vi } from 'vitest'

const token = vi.fn()

vi.unmock('./auth-client')
vi.mock('@neondatabase/auth', () => ({
  createAuthClient: () => ({ token }),
}))
vi.mock('@neondatabase/auth/react/adapters', () => ({
  BetterAuthReactAdapter: () => ({}),
}))

describe('bearerToken', () => {
  beforeEach(() => {
    vi.resetModules()
    token.mockReset().mockResolvedValue({ data: { token: 'jwt' }, error: null })
  })

  it('uses the normal Neon token cache by default', async () => {
    const { bearerToken } = await import('./auth-client')
    expect(await bearerToken()).toBe('jwt')
    expect(token).toHaveBeenCalledWith(undefined)
  })

  it('bypasses both client and cookie caches when refreshing an expired JWT', async () => {
    const { bearerToken } = await import('./auth-client')
    expect(await bearerToken(true)).toBe('jwt')
    expect(token).toHaveBeenCalledWith({
      query: { disableCookieCache: 'true' },
      fetchOptions: { headers: { 'X-Force-Fetch': 'true' } },
    })
  })
})
