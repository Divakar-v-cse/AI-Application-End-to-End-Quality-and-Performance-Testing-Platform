import { useState } from 'react'
import { api, saveSession } from '../api.js'

const DEMO_EMAIL = 'qa@example.com'
const DEMO_PASSWORD = 'Passw0rd!'

export default function Login() {
  const [email, setEmail] = useState(DEMO_EMAIL)
  const [password, setPassword] = useState(DEMO_PASSWORD)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    setError('')

    if (!email.trim()) {
      setError('Email is required.')
      return
    }
    if (!/.+@.+\..+/.test(email.trim())) {
      setError('Enter a valid email address.')
      return
    }
    if (!password) {
      setError('Password is required.')
      return
    }

    setBusy(true)
    try {
      const session = await api('/api/auth/login', {
        method: 'POST',
        body: { email: email.trim(), password },
        auth: false
      })
      saveSession(session.access_token, session.user)
      window.dispatchEvent(new Event('aqp:login'))
    } catch (err) {
      setError(err.message || 'Sign in failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit} noValidate>
        <div className="inline" style={{ gap: 11 }}>
          <span className="brand-mark">AQ</span>
          <div>
            <h1>AI Quality Platform</h1>
            <p className="sub">End-to-end &amp; performance testing console</p>
          </div>
        </div>

        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            data-testid="login-email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="qa@example.com"
          />
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            data-testid="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />
        </div>

        {error && (
          <p className="login-error" role="alert" data-testid="login-error">
            {error}
          </p>
        )}

        <button
          type="submit"
          className="btn btn-primary btn-block"
          data-testid="login-submit"
          disabled={busy}
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>

        <div className="demo-creds">
          <strong>Demo credentials</strong>
          <span>{DEMO_EMAIL} / {DEMO_PASSWORD}</span>
        </div>
      </form>
    </div>
  )
}
