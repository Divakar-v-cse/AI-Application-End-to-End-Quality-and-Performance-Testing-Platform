import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { useFetch } from '../hooks.js'
import {
  Card,
  DataTable,
  ErrorBanner,
  PageHeader,
  Spinner,
  StatusPill,
  fmtDate,
  fmtMs,
  fmtNum
} from '../components/ui.jsx'

const PAGE_SIZE = 12

export default function Runs() {
  const [suite, setSuite] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(0)

  const query = new URLSearchParams()
  if (suite) query.set('suite', suite)
  if (status) query.set('status', status)
  query.set('limit', String(PAGE_SIZE))
  query.set('offset', String(page * PAGE_SIZE))

  const runs = useFetch(() => api(`/api/runs?${query.toString()}`), [suite, status, page])
  const data = runs.data

  function update(setter) {
    return (event) => {
      setter(event.target.value)
      setPage(0)
    }
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <>
      <PageHeader
        title="Test Runs"
        subtitle="Every execution is persisted with per-case results and the quality gates evaluated against it."
        actions={<Link className="btn btn-ghost" to="/dashboard">Back to dashboard</Link>}
      />

      <Card title="Filters" subtitle="Narrow the history by suite or outcome">
        <div className="form-row">
          <div className="field">
            <label htmlFor="suite">Suite</label>
            <select id="suite" value={suite} onChange={update(setSuite)} data-testid="filter-suite">
              <option value="">All suites</option>
              <option value="all">all (full regression)</option>
              <option value="api">api</option>
              <option value="ui">ui</option>
              <option value="db">db</option>
              <option value="perf">perf</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="status">Status</label>
            <select id="status" value={status} onChange={update(setStatus)} data-testid="filter-status">
              <option value="">Any status</option>
              <option value="passed">passed</option>
              <option value="failed">failed</option>
              <option value="running">running</option>
            </select>
          </div>
          <button type="button" className="btn" onClick={runs.reload}>Refresh</button>
        </div>
      </Card>

      <ErrorBanner error={runs.error} onRetry={runs.reload} />

      <Card
        title={`Execution history${data ? ` · ${data.total} run(s)` : ''}`}
        subtitle="Click a run key to inspect case-level results and download reports"
        padded={false}
        actions={
          <div className="inline">
            <button
              type="button"
              className="btn btn-sm"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              Previous
            </button>
            <span className="small muted">Page {page + 1} / {pages}</span>
            <button
              type="button"
              className="btn btn-sm"
              disabled={page + 1 >= pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        }
      >
        {runs.loading && !data ? (
          <div style={{ padding: 18 }}><Spinner label="Loading runs…" /></div>
        ) : (
          <DataTable
            rows={data?.items || []}
            rowKey={(row) => row.run_key}
            empty="No runs match these filters."
            columns={[
              {
                key: 'run_key',
                header: 'Run',
                render: (row) => <Link to={`/runs/${row.run_key}`} className="mono-sm">{row.run_key}</Link>
              },
              { key: 'suite', header: 'Suite', render: (row) => <span className="pill pill-blue">{row.suite}</span> },
              { key: 'status', header: 'Status', render: (row) => <StatusPill status={row.status} /> },
              { key: 'trigger', header: 'Trigger', render: (row) => <span className="muted small">{row.trigger.split(':')[0]}</span> },
              { key: 'commit_sha', header: 'Commit', render: (row) => <span className="mono-sm dim">{row.commit_sha}</span> },
              { key: 'total', header: 'Total', align: 'right', render: (row) => fmtNum(row.total) },
              { key: 'passed', header: 'Passed', align: 'right', render: (row) => fmtNum(row.passed) },
              {
                key: 'failed',
                header: 'Failed',
                align: 'right',
                render: (row) => (
                  <span style={{ color: row.failed ? '#ff97a0' : 'inherit' }}>{fmtNum(row.failed)}</span>
                )
              },
              { key: 'duration_ms', header: 'Duration', align: 'right', render: (row) => fmtMs(row.duration_ms) },
              { key: 'started_at', header: 'Started', render: (row) => fmtDate(row.started_at) }
            ]}
          />
        )}
      </Card>
    </>
  )
}
