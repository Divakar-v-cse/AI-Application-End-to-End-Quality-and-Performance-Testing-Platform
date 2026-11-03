const BASE = import.meta.env.VITE_API_BASE ?? ''
export const TOKEN_KEY = 'aqp.token'
export const USER_KEY = 'aqp.user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}

export function saveSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

function describeError(status, payload) {
  if (payload && typeof payload.detail === 'string') return payload.detail
  if (payload && Array.isArray(payload.detail)) {
    const first = payload.detail[0]
    if (first?.loc) return `${first.loc.slice(1).join('.')}: ${first.msg}`
    return JSON.stringify(payload.detail)
  }
  return `Request failed with HTTP ${status}`
}

export async function api(path, { method = 'GET', body, auth = true } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (auth && token) headers.Authorization = `Bearer ${token}`

  let response
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body)
    })
  } catch (err) {
    throw new Error(`Cannot reach the API at ${BASE || window.location.origin}. Is the backend running? (${err.message})`)
  }

  const text = await response.text()
  let payload = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = { detail: text.slice(0, 400) }
    }
  }

  // A 401 on an authenticated call means the session is gone. A 401 from a
  // public call (the login form) is a credential error and must be shown as
  // the server described it.
  if (response.status === 401 && auth) {
    clearSession()
    window.dispatchEvent(new Event('aqp:unauthorized'))
    throw new Error('Your session expired. Sign in again.')
  }
  if (!response.ok) throw new Error(describeError(response.status, payload))
  return payload
}

export function reportUrl(runKey, fmt) {
  const token = encodeURIComponent(getToken())
  return `${BASE}/api/reports/${encodeURIComponent(runKey)}/${fmt}?token=${token}`
}
