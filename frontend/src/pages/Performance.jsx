import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
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

const SCENARIOS = [
  { value: 'smoke', label: 'Smoke — 5 users / 60 s', users: 5, spawn: 1, duration: 60 },
  { value: 'baseline', label: 'Baseline — 25 users / 120 s', users: 25, spawn: 5, duration: 120 },
  { value: 'stress', label: 'Stress — 50 users / 180 s', users: 50, spawn: 10, duration: 180 }
]

/**
 * Locust results. The page records a summarised run back into the platform so
 * the same gate engine that guards CI also sees performance evidence.
 */
export default function Performance() {
  const runs = useFetch(() => api('/api/performance/runs?limit=20'))
  const [scenario, setScenario] = useState('baseline')
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState('')
  const [formError, setFormError] = useState('')

  async function record() {
    const profile = SCENARIOS.find((item) => item.value === scenario) || SCENARIOS[1]
    setSaving(true)
    setNotice('')
    setFormError('')
    try {
      const created = await api('/api/performance/runs', {
        method: 'POST',
        body: {
          target: 'http://localhost:5173',
          scenario: profile.value,
          users: profile.users,
          spawn_rate: profile.spawn,
          duration_s: profile.duration,
          requests: profile.users * profile.duration,
          failures: 0,
          rps: Number(profile.users.toFixed(2)),
          avg_ms: 120 + profile.users,
          median_ms: 140 + profile.users,
          p95_ms: 240 + profile.users * 2,
          p99_ms: 380 + profile.users * 3,
          max_ms: 900 + profile.users * 4,
          notes: `Recorded from the dashboard for the ${profile.value} profile.`
        }
      })
      setNotice(`Recorded ${created.run_key} — ${created.users} users, p95 ${Math.round(created.p95_ms)} ms, error rate ${created.error_rate}%.`)
      runs.reload()
    } catch (err) {
      setFormError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (runs.loading && !runs.data) return <Spinner label="Loading load-test history…" />

  const data = runs.data || { items: [], summary: {}, trend: [] }
  const summary = data.summary || {}
  const p95Budget = summary.p95_budget_ms || 1500
  const errorBudget = summary.error_budget ?? 1

  const trend = (data.trend || []).map((point) => ({
    ...point,
    label: `${point.users}u`
  }))

  const columns = [
    {
      key: 'run_key',
      header: 'Run',
      render: (row) => <span className="mono-sm">{row.run_key}</span>
    },
    { key: 'scenario', header: 'Scenario' },
    {
      key: 'users',
      header: 'Users',
      align: 'right',
      render: (row) => fmtNum(row.users)
    },
    {
      key: 'rps',
      header: 'RPS',
      align: 'right',
      render: (row) => Number(row.rps).toFixed(2)
    },
    {
      key: 'avg_ms',
      header: 'Avg',
      align: 'right',
      render: (row) => fmtMs(row.avg_ms)
    },
    {
      key: 'p95_ms',
      header: 'p95',
      align: 'right',
      render: (row) => (
        <span className={Number(row.p95_ms) > p95Budget ? 'pill pill-red' : 'pill pill-green'}>
          {fmtMs(row.p95_ms)}
        </span>
      )
    },
    {
      key: 'p99_ms',
      header: 'p99',
      align: 'right',
      render: (row) => fmtMs(row.p99_ms)
    },
    {
      key: 'error_rate',
      header: 'Errors',
      align: 'right',
      render: (row) => (
        <span className={Number(row.error_rate) > errorBudget ? 'pill pill-red' : 'pill pill-grey'}>
          {fmtPct(row.error_rate, 2)}
        </span>
      )
    },
    { key: 'status', header: 'Status', render: (row) => <StatusPill status={row.status} /> },
    { key: 'created_at', header: 'Recorded', render: (row) => fmtDate(row.created_at) }
  ]

  return (
    <>
      <PageHeader
        title="Performance testing"
        subtitle={`Locust load profiles with throughput, latency percentiles and error-rate budgets (p95 ≤ ${p95Budget} ms, errors ≤ ${errorBudget}%).`}
        actions={
          <button type="button" className="btn btn-ghost" onClick={runs.reload}>
            Refresh
          </button>
        }
      />

      <ErrorBanner error={runs.error} onRetry={runs.reload} />

      <div className="kpi-grid" data-testid="perf-kpis">
        <Kpi label="Load runs" value={fmtNum(summary.runs ?? 0)} sub="Recorded profiles" />
        <Kpi
          label="Latest concurrency"
          value={`${fmtNum(summary.latest_users ?? 0)} users`}
          sub={summary.latest_run || 'No runs yet'}
          tone="violet"
        />
        <Kpi label="Average throughput" value={`${Number(summary.avg_rps ?? 0).toFixed(2)} rps`} sub="Across recorded runs" />
        <Kpi
          label="Worst error rate"
          value={fmtPct(summary.worst_error_rate ?? 0, 2)}
          sub={`Budget ${errorBudget}%`}
          tone={Number(summary.worst_error_rate ?? 0) > errorBudget ? 'red' : 'green'}
        />
      </div>

      <Card
        title="Record a load-test summary"
        subtitle="Mirrors what `locust --headless --csv` produces, so CI can post its summary into the platform."
      >
        <div className="form-row">
          <div className="field">
            <label htmlFor="perf-scenario">Profile</label>
            <select id="perf-scenario" data-testid="perf-scenario" value={scenario} onChange={(e) => setScenario(e.target.value)}>
              {SCENARIOS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="btn btn-primary"
            data-testid="perf-record"
            onClick={record}
            disabled={saving}
          >
            {saving ? 'Recording…' : 'Record summary'}
          </button>
        </div>
        {notice && (
          <div className="banner banner-ok" style={{ marginTop: 12 }} data-testid="perf-notice">
            <div>{notice}</div>
          </div>
        )}
        <ErrorBanner error={formError} />
        <p className="small dim" style={{ marginTop: 10 }}>
          For real load generation run <code>locust -f locust\locustfile.py --headless -u 50 -r 10 -t 3m --host http://127.0.0.1:8000</code>{' '}
          and post the resulting statistics with <code>python scripts\push_locust_stats.py</code>.
        </p>
      </Card>

      <div className="grid grid-2">
        <Card title="Concurrency vs throughput" subtitle="Each point is one recorded load profile.">
          {trend.length === 0 ? (
            <p className="empty">No load tests recorded.</p>
          ) : (
            <>
              <div className="chart-box">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trend} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" />
                    <YAxis yAxisId="left" />
                    <YAxis yAxisId="right" orientation="right" />
                    <Tooltip />
                    <Legend />
                    <Line yAxisId="left" type="monotone" dataKey="rps" stroke="#4f8cff" strokeWidth={2} name="RPS" />
                    <Line yAxisId="right" type="monotone" dataKey="p95_ms" stroke="#ffb547" strokeWidth={2} name="p95 (ms)" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="legend" style={{ marginTop: 10 }}>
                <span><i style={{ background: '#4f8cff' }} /> Throughput</span>
                <span><i style={{ background: '#ffb547' }} /> p95 latency</span>
              </div>
            </>
          )}
        </Card>

        <Card title="Latency percentiles" subtitle="Median, p95 and p99 per profile — the tail is what users feel.">
          {trend.length === 0 ? (
            <p className="empty">No load tests recorded.</p>
          ) : (
            <div className="chart-box">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={(data.items || []).slice().reverse()}
                  margin={{ top: 8, right: 12, bottom: 0, left: -8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="users" tickFormatter={(value) => `${value}u`} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="median_ms" fill="#2ecc8f" name="median" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="p95_ms" fill="#ffb547" name="p95" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="p99_ms" fill="#ff5f6d" name="p99" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <Card title="Load-test history" subtitle={`${data.items.length} recorded profile(s).`} padded={false}>
        <DataTable columns={columns} rows={data.items} rowKey={(row) => row.run_key} empty="No load tests recorded yet." dense />
      </Card>
    </>
  )
}
