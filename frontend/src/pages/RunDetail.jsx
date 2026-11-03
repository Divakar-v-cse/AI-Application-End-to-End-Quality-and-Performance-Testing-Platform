import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, reportUrl } from '../api.js'
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
  fmtMs,
  fmtNum,
  fmtPct
} from '../components/ui.jsx'

const FORMATS = [
  { key: 'markdown', label: 'Markdown' },
  { key: 'html', label: 'HTML' },
  { key: 'junit', label: 'JUnit XML' },
  { key: 'csv', label: 'CSV' },
  { key: 'json', label: 'JSON' }
]

export default function RunDetail() {
  const { runKey } = useParams()
  const detail = useFetch(() => api(`/api/runs/${encodeURIComponent(runKey)}`), [runKey])
  const [filter, setFilter] = useState('all')
  const [expanded, setExpanded] = useState('')
  const [recomputing, setRecomputing] = useState(false)
  const [notice, setNotice] = useState('')

  async function reevaluate() {
    setRecomputing(true)
    setNotice('')
    try {
      await api(`/api/quality-gates/evaluate/${encodeURIComponent(runKey)}`, { method: 'POST' })
      detail.reload()
      setNotice('Quality gates recomputed from the persisted results.')
    } catch (err) {
      setNotice(err.message)
    } finally {
      setRecomputing(false)
    }
  }

  if (detail.loading && !detail.data) return <Spinner label="Loading run detail…" />
  if (detail.error) return <ErrorBanner error={detail.error} onRetry={detail.reload} />

  const { run, results = [], gates = [] } = detail.data
  const visible = filter === 'all' ? results : results.filter((row) => row.status === filter || row.suite === filter)
  const blockingFailures = gates.filter((gate) => gate.status === 'failed' && gate.blocking)

  return (
    <>
      <PageHeader
        title={run.run_key}
        subtitle={`Suite ${run.suite} · trigger ${run.trigger} · branch ${run.branch} · ${fmtDate(run.started_at)}`}
        actions={
          <div className="inline">
            <button type="button" className="btn btn-ghost" onClick={detail.reload}>Refresh</button>
            <button type="button" className="btn" onClick={reevaluate} disabled={recomputing} data-testid="reevaluate-gates">
              {recomputing ? 'Recomputing…' : 'Re-evaluate gates'}
            </button>
            <Link className="btn btn-ghost" to="/runs">All runs</Link>
          </div>
        }
      />

      {notice && <div className="banner banner-info"><div>{notice}</div></div>}

      <div className="kpi-grid">
        <Kpi label="Run status" value={<StatusPill status={run.status} />} sub={`${fmtMs(run.duration_ms)} total`} tone={run.status === 'passed' ? 'green' : 'red'} />
        <Kpi label="Total checks" value={fmtNum(run.total)} sub={`${run.skipped} skipped`} />
        <Kpi label="Passed" value={fmtNum(run.passed)} sub={fmtPct(run.total ? (run.passed / run.total) * 100 : 0)} tone="green" />
        <Kpi label="Failed" value={fmtNum(run.failed)} sub={`${blockingFailures.length} blocking gate(s)`} tone={run.failed ? 'red' : 'green'} />
        <Kpi label="Environment" value={run.environment} sub={`source ${run.source}`} />
        <Kpi label="Commit" value={<span className="mono-sm">{run.commit_sha}</span>} sub={run.branch} />
      </div>

      <div className="grid grid-2">
        <Card title="Quality gates" subtitle="Blocking gates must pass before release">
          {gates.length === 0 ? (
            <p className="empty">No gates were evaluated for this run.</p>
          ) : (
            <div className="stack">
              {gates.map((gate) => (
                <div key={gate.gate_key} className={`gate-row ${gate.status === 'failed' ? 'gate-row-fail' : ''}`}>
                  <div>
                    <strong style={{ fontSize: 12.5 }}>{gate.name}</strong>
                    <p className="gate-metric">
                      actual {gate.actual} · {gate.operator} {gate.threshold} {gate.blocking ? '· blocking' : '· advisory'}
                    </p>
                  </div>
                  <StatusPill status={gate.status} />
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Reports" subtitle="Download the run in the format your tooling consumes">
          <div className="stack">
            {FORMATS.map((format) => (
              <a
                key={format.key}
                className="gate-row"
                href={reportUrl(run.run_key, format.key)}
                data-testid={`download-${format.key}`}
                download
              >
                <div>
                  <strong style={{ fontSize: 12.5 }}>{format.label}</strong>
                  <p className="gate-metric">{run.run_key}-report.{format.key === 'junit' ? 'xml' : format.key === 'markdown' ? 'md' : format.key}</p>
                </div>
                <span className="pill pill-blue">Download</span>
              </a>
            ))}
          </div>
          <p className="small dim" style={{ marginTop: 10 }}>
            Report links carry the bearer token as a query parameter so they work from a plain anchor tag.
          </p>
        </Card>
      </div>

      <Card
        title={`Case results · ${visible.length}`}
        subtitle="Failed cases include the assertion message and stack trace"
        padded={false}
        actions={
          <select value={filter} onChange={(e) => setFilter(e.target.value)} data-testid="result-filter">
            <option value="all">All results</option>
            <option value="failed">Failed only</option>
            <option value="passed">Passed only</option>
            <option value="api">API suite</option>
            <option value="ui">UI suite</option>
            <option value="db">DB suite</option>
          </select>
        }
      >
        <DataTable
          rows={visible}
          rowKey={(row) => row.id}
          empty="No results for this filter."
          dense
          columns={[
            {
              key: 'case_key',
              header: 'Case',
              render: (row) => (
                <button
                  type="button"
                  className="mono-sm"
                  style={{ background: 'none', border: 0, color: '#9cc2ff', cursor: 'pointer', padding: 0 }}
                  onClick={() => setExpanded(expanded === row.case_key ? '' : row.case_key)}
                >
                  {row.case_key}
                </button>
              )
            },
            { key: 'name', header: 'Name', render: (row) => <span className="truncate">{row.name}</span> },
            { key: 'suite', header: 'Suite', render: (row) => <span className="pill pill-violet">{row.suite}</span> },
            { key: 'module', header: 'Module', render: (row) => <span className="muted small">{row.module}</span> },
            { key: 'status', header: 'Status', render: (row) => <StatusPill status={row.status} /> },
            { key: 'duration_ms', header: 'Duration', align: 'right', render: (row) => fmtMs(row.duration_ms) },
            {
              key: 'error_message',
              header: 'Message',
              render: (row) =>
                row.error_message ? (
                  <span className="small" style={{ color: '#ff97a0' }}>{row.error_message}</span>
                ) : (
                  <span className="dim small">—</span>
                )
            }
          ]}
        />
        {expanded && (
          <div style={{ padding: '12px 18px' }}>
            {(() => {
              const row = results.find((item) => item.case_key === expanded)
              if (!row) return null
              return (
                <div className="stack">
                  <div className="row-between">
                    <strong className="mono-sm">{row.case_key}</strong>
                    <button type="button" className="btn btn-sm btn-ghost" onClick={() => setExpanded('')}>Close</button>
                  </div>
                  <p className="small muted">{row.name} · {row.module} · {fmtMs(row.duration_ms)}</p>
                  {row.error_message && <div className="banner banner-error"><div>{row.error_message}</div></div>}
                  <pre className="mono-sm" style={{ margin: 0, overflowX: 'auto', background: '#0b1020', padding: 12, borderRadius: 10 }}>
                    {row.stack_trace || 'No stack trace recorded.'}
                  </pre>
                  <p className="small dim">Evidence: {row.evidence || 'none'}</p>
                </div>
              )
            })()}
          </div>
        )}
      </Card>
    </>
  )
}
