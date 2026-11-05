import { useState } from 'react'
import type { AuthSession } from '../types'
import { login, signUp } from '../lib/api'

interface Props {
  onAuthenticated: (session: AuthSession) => void
  onCancel: () => void
}

export function LoginPanel({ onAuthenticated, onCancel }: Props) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>('sign-in')
  const [name, setName] = useState('')

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onAuthenticated(mode === 'sign-in' ? await login(email, password) : await signUp(name, email, password))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="step login-panel" aria-labelledby="login-title">
      <h1 id="login-title">{mode === 'sign-in' ? 'Sign in' : 'Create account'}</h1>
      <p className="muted">Your account role determines whether measurement administration is available.</p>
      <form onSubmit={submit}>
        {mode === 'sign-up' && <label className="stacked-field">Name<input value={name} onChange={(e) => setName(e.target.value)} required /></label>}
        <label className="stacked-field">Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label className="stacked-field">Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="actions">
          <button className="primary" type="submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'sign-in' ? 'Sign in' : 'Create account'}</button>
          <button className="secondary" type="button" onClick={onCancel}>Cancel</button>
        </div>
        <button className="text-button" type="button" onClick={() => setMode(mode === 'sign-in' ? 'sign-up' : 'sign-in')}>
          {mode === 'sign-in' ? 'New customer? Create an account' : 'Already have an account? Sign in'}
        </button>
      </form>
    </section>
  )
}
