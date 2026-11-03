import { useState } from 'react'
import { api } from '../api.js'
import { useFetch } from '../hooks.js'
import {
  Card,
  DataTable,
  ErrorBanner,
  Kpi,
  PageHeader,
  Spinner,
  StatusPill,
  fmtDate,
  fmtNum,
  fmtPct
} from '../components/ui.jsx'

export default function DataQuality() {
  const checks = useFetch(() => api('/api/data-quality/checks'))
  const history = useFetch(() => api('/api/data-quality/history?limit=10'))
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')

  async function runChecks() {
    setBusy(true)
    setNotice('')
    try {
      const result = await api('/api/data-quality/run', { method: 'POST' })
      setNotice(
        `${result.run.run_key}: ${result.items.length - result.failed}/${result.items.length} SQL checks passed.`
      )
      checks.reload()
      history.reload()
    } catch (err) {
      setNotice(err.message)
    } finally {
      setBusy(false)
    }
  }

  const data = checks.data
  const summary = data?.summary
  const items = data?.items || []

  return (
    <>
      <PageHeader
        title="Data Quality"
        subtitle="SQL validation rules for missing records, duplicates, nulls, domain values, referential integrity and AI evaluation integrity."
        actions={
          <button type="button" className="btn btn-primary" onClick={runChecks} disabled={busy} data-testid="run-db-checks">
            {busy ? 'Validating…' : 'Run SQL validation'}
          </button>
        }
      />

      {notice && <div className="banner banner-info"><div>{notice}</div></div>}
      <ErrorBanner error={checks.error} onRetry={checks.reload} />

      <div className="kpi-grid">
        <Kpi label="Checks executed" value={fmtNum(summary?.total || 0)} sub={summary?.run_key || '—'} />
        <Kpi label="Passed" value={fmtNum(summary?.passed || 0)} tone="green" />
        <Kpi
          label="Failed"
          value={fmtNum(summary?.failed || 0)}
          tone={summary?.failed ? 'red' : 'green'}
          sub={fmtPct(summary?.total ? (summary.passed / summary.total) * 100 : 0)}
        />
        <Kpi label="Rows scanned" value={fmtNum(summary?.rows_scanned || 0)} sub="across all tables" />
        <Kpi
          label="Severity mix"
          value={
            Object.keys(summary?.severity_counts || {}).length
              ? Object.entries(summary.severity_counts).map(([key, value]) => `${value} ${key}`).join(' · ')
              : 'clean'
          }
          tone={Object.keys(summary?.severity_counts || {}).length ? 'amber' : 'green'}
        />
        <Kpi label="Checked at" value={<span className="small">{fmtDate(summary?.checked_at)}</span>} />
      </div>

      <Card
        title="Validation rules"
        subtitle="Each rule returns offending rows; a passing check returns zero rows"
        padded={false}
      >
        {checks.loading && !data ? (
          <div style={{ padding: 18 }}><Spinner label="Running validation report…" /></div>
        ) : (
          <DataTable
            rows={items}
            rowKey={(row) => row.check_key}
            empty="No validation results yet — run the SQL suite."
            columns={[
              { key: 'check_key', header: 'Check', render: (row) => <span className="mono-sm">{row.check_key}</span> },
              { key: 'name', header: 'Rule', render: (row) => <span className="truncate">{row.name}</span> },
              { key: 'table_name', header: 'Table', render: (row) => <span className="mono-sm dim">{row.table_name}</span> },
              {
                key: 'severity',
                header: 'Severity',
                render: (row) => (
                  <span className={`pill ${row.severity === 'critical' ? 'pill-red' : row.severity === 'high' ? 'pill-amber' : 'pill-grey'}`}>
                    {row.severity}
                  </span>
                )
              },
              { key: 'status', header: 'Status', render: (row) => <StatusPill status={row.status} /> },
              {
                key: 'failing_rows',
                header: 'Offending',
                align: 'right',
                render: (row) => (
                  <span style={{ color: row.failing_rows ? '#ff97a0' : 'inherit' }}>{fmtNum(row.failing_rows)}</span>
                )
              },
              { key: 'total_rows', header: 'Scanned', align: 'right', render: (row) => fmtNum(row.total_rows) },
              {
                key: 'query',
                header: 'SQL',
                render: (row) => (
                  <code className="mono-sm dim truncate" title={row.query}>{row.query}</code>
                )
              }
            ]}
          />
        )}
      </Card>

      <div className="grid grid-2">
        <Card title="Rule catalogue" subtitle="The SQL each check executes against SQLite">
          <div className="stack" style={{ maxHeight: 360, overflowY: 'auto' }}>
            {items.map((row) => (
              <div key={`sql-${row.check_key}`} className="stack" style={{ gap: 4 }}>
                <div className="row-between">
                  <strong className="mono-sm">{row.check_key}</strong>
                  <StatusPill status={row.status} />
                </div>
                <pre className="mono-sm" style={{ margin: 0, whiteSpace: 'pre-wrap', background: '#0b1020', padding: 10, borderRadius: 9 }}>
                  {row.query}
                </pre>
              </div>
            ))}
            {!items.length && <p className="empty">No rules executed yet.</p>}
          </div>
        </Card>

        <Card title="Validation history" subtitle="Pass rate per SQL validation run" padded={false}>
          <DataTable
            rows={history.data?.items || []}
            rowKey={(row) => row.run_key}
            empty="No history."
            dense
            columns={[
              { key: 'run_key', header: 'Run', render: (row) => <span className="mono-sm">{row.run_key}</span> },
              { key: 'checks', header: 'Checks', align: 'right', render: (row) => fmtNum(row.checks) },
              {
                key: 'failed',
                header: 'Failed',
                align: 'right',
                render: (row) => <span style={{ color: row.failed ? '#ff97a0' : 'inherit' }}>{fmtNum(row.failed)}</span>
              },
              { key: 'pass_rate', header: 'Pass rate', align: 'right', render: (row) => fmtPct(row.pass_rate) },
              { key: 'checked_at', header: 'Checked', render: (row) => fmtDate(row.checked_at) }
            ]}
          />
        </Card>
      </div>
    </>
  )
}
