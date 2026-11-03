import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { getUser } from '../api.js'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', hint: 'Quality overview', icon: '◈' },
  { to: '/runs', label: 'Test Runs', hint: 'History & execution', icon: '▤' },
  { to: '/metrics', label: 'API Metrics', hint: 'Latency & errors', icon: '◔' },
  { to: '/data-quality', label: 'Data Quality', hint: 'SQL validation', icon: '⌗' },
  { to: '/performance', label: 'Performance', hint: 'Locust load tests', icon: '⚡' },
  { to: '/gates', label: 'Quality Gates', hint: 'CI thresholds', icon: '⛨' },
  { to: '/chatbot', label: 'AI Chatbot', hint: 'Demo under test', icon: '✦' }
]

const TITLES = {
  '/dashboard': 'Quality Dashboard',
  '/runs': 'Test Runs',
  '/metrics': 'API Metrics',
  '/data-quality': 'Data Quality',
  '/performance': 'Performance',
  '/gates': 'Quality Gates',
  '/chatbot': 'AI Chatbot'
}

export default function Layout({ onLogout }) {
  const user = getUser()
  const location = useLocation()
  const active = Object.keys(TITLES).find((path) => location.pathname.startsWith(path))
  const title = active ? TITLES[active] : 'Quality Platform'

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">AQ</span>
          <div>
            <strong>AI Quality</strong>
            <small>E2E &amp; Performance</small>
          </div>
        </div>

        <nav className="nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-item ${isActive ? 'nav-item-active' : ''}`}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              <span className="nav-text">
                <span className="nav-label">{item.label}</span>
                <span className="nav-hint">{item.hint}</span>
              </span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="user-chip">
            <span className="avatar">{(user?.full_name || user?.email || 'QA').slice(0, 2).toUpperCase()}</span>
            <div className="user-meta">
              <strong>{user?.full_name || 'QA Engineer'}</strong>
              <small>{user?.role || 'viewer'}</small>
            </div>
          </div>
          <button type="button" className="btn btn-ghost btn-block" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <span className="topbar-title">{title}</span>
          <span className="topbar-env">
            <span className="dot dot-green" /> local · SQLite
          </span>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
