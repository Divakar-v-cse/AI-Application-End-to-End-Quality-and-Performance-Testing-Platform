import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts'
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
  fmtMs,
  fmtNum,
  fmtPct
} from '../components/ui.jsx'

const SUITE_OPTIONS = [
  { value: 'all', label: 'Full regression (API + UI + DB)' },
  { value: 'api', label: 'API suite only' },
  { value: 'db', label: 'Data validation suite' },
  { value: 'perf', label: 'Performance summary' },
  { value: 'ui', label: 'UI suite (Playwright)' }
]

const BAR_COLORS = ['#4f8cff', '#2ecc8f', '#ffb547', '#a78bfa', '#ff5f6d', '#38bdf8']

export default function Dashboard() {
  const summary = useFetch(() => api('/api/dashboard/summary'))
  const trend = useFetch(() => api('/api/dashboard/trend?days=14'))
  const gates = useFetch(() => api('/api/quality-gates'))

  const [suite, setSuite] = useState('all')
  const [running, setRunning] = useState(false)
  const [outcome, setOutcome] = useState(null)
  const [runError, setRunError] = useState('')

  async function execute() {
    setRunning(true)
    setRunError('')
    setOutcome(null)
    try {
      const detail = await api('/api/runs', {
        method: 'POST',
        body: { suite, trigger: 'dashboard', branch: 'main', commit_sha: 'local' }
      })
      setOutcome(detail)
      summary.reload()
      trend.reload()
      gates.reload()
    } catch (err) {
      setRunError(err.message)
    } finally {
      setRunning(false)
    }
  }

  const s = summary.data
  const trendData = (trend.data || []).map((point) => ({
    ...point,
    label: point.date?.slice(5)
  }))

  return (
    <>
      <PageHeader
        title="Quality Dashboard"
        subtitle="Live view of automated test outcomes, API latency, browser load time, load-test behaviour and data-integrity checks."
        actions={
          <div className="inline">
            <select value={suite} onChange={(e) => setSuite(e.target.value)} data-testid="run-suite">
              {SUITE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-primary"
              onClick={execute}
              disabled={running}
              data-testid="run-suite-button"
            >
              {running ? 'Executing…' : 'Run quality suite'}
            </button>
          </div>
        }
      />

      {runError && (
        <div className="banner banner-error" role="alert">
          <div>
            <strong>Execution failed.</strong>
            <p>{runError}</p>
          </div>
        </div>
      )}

      {outcome && (
        <div className={`banner ${outcome.run.status === 'passed' ? 'banner-ok' : 'banner-warn'}`} data-testid="run-outcome">
          <div>
            <strong>
              {outcome.run.run_key} · {outcome.run.status.toUpperCase()}
            </strong>
            <p>
              {outcome.run.passed}/{outcome.run.total} passed · {outcome.run.failed} failed ·{' '}
              {fmtMs(outcome.run.duration_ms)} · {outcome.gates.filter((g) => g.status === 'failed').length} gate(s) failing —{' '}
              <Link to={`/runs/${outcome.run.run_key}`}>open run detail</Link>
            </p>
          </div>
        </div>
      )}

      <ErrorBanner error={summary.error} onRetry={summary.reload} />

      {summary.loading && !s ? (
        <Spinner label="Loading quality metrics…" />
      ) : (
        s && (
          <>
            <div className="kpi-grid">
              <Kpi
                label="Total automated tests"
                value={fmtNum(s.total_tests)}
                sub={`${fmtNum(s.suites?.api?.total || 0)} API · ${fmtNum(s.suites?.ui?.total || 0)} UI · ${fmtNum(s.suites?.db?.total || 0)} DB`}
              />
              <Kpi label="Passed" value={fmtNum(s.passed)} sub={`${fmtPct(s.pass_rate)} pass rate`} tone="green" />
              <Kpi label="Failed" value={fmtNum(s.failed)} sub={`${fmtNum(s.skipped)} skipped`} tone={s.failed ? 'red' : 'green'} />
              <Kpi label="API p95 latency" value={fmtMs(s.p95_api_ms)} sub={`avg ${fmtMs(s.avg_api_ms)}`} tone="violet" />
              <Kpi
                label="Avg page load"
                value={fmtMs(s.avg_page_load_ms)}
                sub="budget 3,000 ms"
                tone={s.avg_page_load_ms > 3000 ? 'red' : 'default'}
              />
              <Kpi
                label="Load error rate"
                value={fmtPct(s.load_error_rate)}
                sub={`${fmtNum(s.load_rps)} req/s throughput`}
                tone={s.load_error_rate > 1 ? 'red' : 'green'}
              />
              <Kpi
                label="Data validation failures"
                value={fmtNum(s.data_failures)}
                sub={`${fmtNum(s.data_checks)} SQL checks`}
                tone={s.data_failures ? 'red' : 'green'}
              />
              <Kpi
                label="Active gate failures"
                value={fmtNum(s.active_gates_failed)}
                sub={s.latest_run ? `latest ${s.latest_run.run_key}` : 'no runs yet'}
                tone={s.active_gates_failed ? 'amber' : 'green'}
              />
            </div>

            <div className="grid grid-2">
              <Card title="Execution trend" subtitle="14-day pass rate and failing checks">
                {trend.loading ? (
                  <Spinner />
                ) : (
                  <div className="chart-box">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={trendData} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
                        <defs>
                          <linearGradient id="passFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#2ecc8f" stopOpacity={0.45} />
                            <stop offset="100%" stopColor="#2ecc8f" stopOpacity={0.02} />
                          </linearGradient>
                          <linearGradient id="failFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#ff5f6d" stopOpacity={0.35} />
                            <stop offset="100%" stopColor="#ff5f6d" stopOpacity={0.02} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="label" tickLine={false} axisLine={false} />
                        <YAxis domain={[0, 100]} tickLine={false} axisLine={false} />
                        <Tooltip
                          formatter={(value, name) => (name === 'pass_rate' ? [`${value}%`, 'Pass rate'] : [value, name])}
                        />
                        <Area type="monotone" dataKey="pass_rate" stroke="#2ecc8f" strokeWidth={2} fill="url(#passFill)" />
                        <Area type="monotone" dataKey="failed" stroke="#ff5f6d" strokeWidth={1.5} fill="url(#failFill)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
                <div className="legend" style={{ marginTop: 6 }}>
                  <span><i style={{ background: '#2ecc8f' }} /> Pass rate %</span>
                  <span><i style={{ background: '#ff5f6d' }} /> Failed checks</span>
                </div>
              </Card>

              <Card title="API latency by endpoint" subtitle="Average and p95 response time">
                {s.endpoint_latency?.length ? (
                  <div className="chart-box">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={s.endpoint_latency.slice(0, 7)} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis
                          dataKey="endpoint"
                          tickLine={false}
                          axisLine={false}
                          interval={0}
                          tickFormatter={(value) => value.replace('/api/', '').slice(0, 11)}
                        />
                        <YAxis tickLine={false} axisLine={false} />
                        <Tooltip formatter={(value) => [`${value} ms`]} />
                        <Bar dataKey="avg_ms" name="avg" radius={[4, 4, 0, 0]} fill="#4f8cff" />
                        <Bar dataKey="p95_ms" name="p95" radius={[4, 4, 0, 0]} fill="#a78bfa" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <p className="empty">No API telemetry recorded yet.</p>
                )}
                <div className="legend" style={{ marginTop: 6 }}>
                  <span><i style={{ background: '#4f8cff' }} /> Average</span>
                  <span><i style={{ background: '#a78bfa' }} /> p95</span>
                </div>
              </Card>
            </div>

            <div className="grid grid-2">
              <Card title="Page load & data integrity" subtitle="Average browser load time vs failing SQL checks">
                {trendData.length ? (
                  <div className="chart-box">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={trendData} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="label" tickLine={false} axisLine={false} />
                        <YAxis yAxisId="left" tickLine={false} axisLine={false} />
                        <YAxis yAxisId="right" orientation="right" tickLine={false} axisLine={false} allowDecimals={false} />
                        <Tooltip formatter={(value) => [value]} />
                        <Line yAxisId="left" type="monotone" dataKey="page_load_ms" name="page load ms" stroke="#ffb547" strokeWidth={2} dot={false} />
                        <Line yAxisId="right" type="monotone" dataKey="data_failures" name="data failures" stroke="#ff5f6d" strokeWidth={2} dot={{ r: 2 }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <p className="empty">No historical data.</p>
                )}
                <div className="legend" style={{ marginTop: 6 }}>
                  <span><i style={{ background: '#ffb547' }} /> Page load (ms)</span>
                  <span><i style={{ background: '#ff5f6d' }} /> Data failures</span>
                </div>
              </Card>

              <Card
                title="Suite breakdown"
                subtitle="Pass rate per suite in the latest execution"
                actions={<Link className="btn btn-sm btn-ghost" to="/gates">Quality gates</Link>}
              >
                {s.suites && (
                  <div className="chart-box" style={{ height: 200 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        layout="vertical"
                        data={Object.entries(s.suites).map(([key, value]) => ({
                          suite: key.toUpperCase(),
                          pass_rate: value.pass_rate,
                          total: value.total
                        }))}
                        margin={{ top: 4, right: 24, bottom: 4, left: 8 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                        <XAxis type="number" domain={[0, 100]} tickLine={false} axisLine={false} />
                        <YAxis type="category" dataKey="suite" tickLine={false} axisLine={false} width={44} />
                        <Tooltip formatter={(value) => [`${value}%`, 'pass rate']} />
                        <Bar dataKey="pass_rate" radius={[0, 5, 5, 0]} barSize={18}>
                          {Object.keys(s.suites).map((key, index) => (
                            <Cell key={key} fill={s.suites[key].pass_rate >= 95 ? '#2ecc8f' : '#ffb547'} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
                <div className="grid grid-3" style={{ marginTop: 10 }}>
                  {Object.entries(s.suites || {}).map(([key, value]) => (
                    <div key={key} className="gate-row">
                      <div>
                        <strong style={{ fontSize: 12 }}>{key.toUpperCase()}</strong>
                        <p className="gate-metric">{value.passed}/{value.total} · avg {fmtMs(value.avg_ms)}</p>
                      </div>
                      <span className={`pill ${value.failed ? 'pill-red' : 'pill-green'}`}>{fmtPct(value.pass_rate, 0)}</span>
                    </div>
                  ))}
                </div>
              </Card>
            </div>

            <Card
              title="Recent executions"
              subtitle="Newest first — click a run key for results, gates and report downloads"
              actions={<Link className="btn btn-sm btn-ghost" to="/runs">All runs</Link>}
              padded={false}
            >
              <DataTable
                rows={s.recent_runs || []}
                rowKey={(row) => row.run_key}
                columns={[
                  {
                    key: 'run_key',
                    header: 'Run',
                    render: (row) => <Link to={`/runs/${row.run_key}`} className="mono-sm">{row.run_key}</Link>
                  },
                  { key: 'suite', header: 'Suite', render: (row) => <span className="pill pill-blue">{row.suite}</span> },
                  { key: 'status', header: 'Status', render: (row) => <StatusPill status={row.status} /> },
                  { key: 'trigger', header: 'Trigger', render: (row) => <span className="muted small">{row.trigger.split(':')[0]}</span> },
                  { key: 'total', header: 'Tests', align: 'right', render: (row) => fmtNum(row.total) },
                  { key: 'failed', header: 'Failed', align: 'right', render: (row) => fmtNum(row.failed) },
                  { key: 'duration_ms', header: 'Duration', align: 'right', render: (row) => fmtMs(row.duration_ms) },
                  { key: 'started_at', header: 'Started', render: (row) => fmtDate(row.started_at) }
                ]}
              />
            </Card>
          </>
        )
      )}
    </>
  )
}
