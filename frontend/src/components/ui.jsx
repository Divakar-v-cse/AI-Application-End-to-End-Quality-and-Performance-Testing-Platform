const STATUS_LABELS = {
  passed: 'Passed',
  failed: 'Failed',
  error: 'Error',
  skipped: 'Skipped',
  running: 'Running',
  not_applicable: 'N/A',
  review: 'Review',
  blocked: 'Blocked'
}

const STATUS_TONES = {
  passed: 'green',
  failed: 'red',
  error: 'red',
  skipped: 'grey',
  running: 'amber',
  not_applicable: 'grey',
  review: 'amber'
}

export function StatusPill({ status }) {
  const key = String(status || 'skipped').toLowerCase()
  return (
    <span className={`pill pill-${STATUS_TONES[key] || 'grey'}`}>
      <span className="pill-dot" />
      {STATUS_LABELS[key] || status}
    </span>
  )
}

export function Card({ title, subtitle, actions, children, className = '', padded = true }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      <div className={padded ? 'card-body' : ''}>{children}</div>
    </section>
  )
}

export function Kpi({ label, value, sub, tone = 'default' }) {
  return (
    <div className={`kpi kpi-${tone}`}>
      <p className="kpi-label">{label}</p>
      <p className="kpi-value">{value}</p>
      {sub && <p className="kpi-sub">{sub}</p>}
    </div>
  )
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  )
}

export function Spinner({ label = 'Loading…' }) {
  return (
    <div className="loading">
      <span className="spinner" />
      <span>{label}</span>
    </div>
  )
}

export function ErrorBanner({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="banner banner-error" role="alert">
      <div>
        <strong>Could not load this view.</strong>
        <p>{error}</p>
      </div>
      {onRetry && (
        <button type="button" className="btn btn-ghost" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

export function Empty({ children = 'No data yet.' }) {
  return <p className="empty">{children}</p>
}

export function DataTable({ columns, rows, rowKey, empty = 'No rows.', dense = false }) {
  if (!rows || rows.length === 0) return <Empty>{empty}</Empty>
  return (
    <div className="table-wrap">
      <table className={`table ${dense ? 'table-dense' : ''}`}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} className={col.align === 'right' ? 'right' : ''}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey ? rowKey(row) : index}>
              {columns.map((col) => (
                <td key={col.key} className={col.align === 'right' ? 'right' : ''}>
                  {col.render ? col.render(row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function fmtMs(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  if (n >= 1000) return `${(n / 1000).toFixed(2)} s`
  return `${n.toFixed(n < 10 ? 1 : 0)} ms`
}

export function fmtPct(value, digits = 1) {
  if (value === null || value === undefined) return '—'
  return `${Number(value).toFixed(digits)}%`
}

export function fmtNum(value) {
  if (value === null || value === undefined) return '—'
  return Number(value).toLocaleString()
}

export function fmtDate(value) {
  if (!value) return '—'
  const d = new Date(value.endsWith?.('Z') ? value : `${value}Z`)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}
