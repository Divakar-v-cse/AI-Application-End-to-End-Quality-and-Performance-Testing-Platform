import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
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
  fmtDate,
  fmtMs,
  fmtNum,
  fmtPct
} from '../components/ui.jsx'

export default function ApiMetrics() {
  const [days, setDays] = useState(7)
  const apiUsage = useFetch(() => api(`/api/metrics/api?days=${days}&limit=300`), [days])
  const pages = useFetch(() => api(`/api/metrics/pages?days=${days}`), [days])

  const summary = apiUsage.data?.summary
  const pageSummary = pages.data?.summary
  const endpoints = apiUsage.data?.by_endpoint || []
  const pageRows = pages.data?.by_page || []

  const series = (apiUsage.data?.items || [])
    .slice()
    .reverse()
    .map((row, index) => ({ index, ms: row.response_time_ms, endpoint: row.endpoint }))

  return (
    <>
      <PageHeader
        title="API Metrics"
        subtitle="Response-time telemetry captured from every executed API check and ingested run."
        actions={
          <div className="inline">
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} data-testid="metrics-window">
              <option value={1}>Last 24 hours</option>
              <option value={7}>Last 7 days</option>
              <option value={14}>Last 14 days</option>
              <option value={30}>Last 30 days</option>
            </select>
            <button type="button" className="btn" onClick={() => { apiUsage.reload(); pages.reload() }}>Refresh</button>
          </div>
        }
      />

      <ErrorBanner error={apiUsage.error} onRetry={apiUsage.reload} />

      <div className="kpi-grid">
        <Kpi label="API calls sampled" value={fmtNum(summary?.calls || 0)} sub={`window ${days}d`} />
        <Kpi label="Average" value={fmtMs(summary?.avg_ms)} sub="all endpoints" />
        <Kpi label="p95" value={fmtMs(summary?.p95_ms)} sub="budget 800 ms" tone={(summary?.p95_ms || 0) > 800 ? 'red' : 'green'} />
        <Kpi label="p99" value={fmtMs(summary?.p99_ms)} />
        <Kpi label="Max" value={fmtMs(summary?.max_ms)} tone="amber" />
        <Kpi label="Error rate" value={fmtPct(summary?.error_rate)} tone={(summary?.error_rate || 0) > 1 ? 'red' : 'green'} />
      </div>

      <div className="grid grid-2">
        <Card title="Latency per endpoint" subtitle="Average and p95 in milliseconds">
          {apiUsage.loading && !endpoints.length ? (
            <Spinner />
          ) : endpoints.length ? (
            <div className="chart-box">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={endpoints.slice(0, 8)} margin={{ top: 8, right: 10, bottom: 0, left: -14 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="endpoint"
                    tickLine={false}
                    axisLine={false}
                    interval={0}
                    tickFormatter={(value) => value.replace('/api/', '').slice(0, 12)}
                  />
                  <YAxis tickLine={false} axisLine={false} />
                  <Tooltip formatter={(value) => [`${value} ms`]} />
                  <Bar dataKey="avg_ms" name="avg" fill="#4f8cff" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="p95_ms" name="p95" fill="#a78bfa" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="empty">No API samples in this window.</p>
          )}
          <div className="legend" style={{ marginTop: 6 }}>
            <span><i style={{ background: '#4f8cff' }} /> Average</span>
            <span><i style={{ background: '#a78bfa' }} /> p95</span>
          </div>
        </Card>

        <Card title="Sample sequence" subtitle="Every recorded call, in order">
          {series.length ? (
            <div className="chart-box">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={series} margin={{ top: 8, right: 10, bottom: 0, left: -14 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="index" tickLine={false} axisLine={false} />
                  <YAxis tickLine={false} axisLine={false} />
                  <Tooltip
                    formatter={(value) => [`${value} ms`, 'response']}
                    labelFormatter={(value) => `sample #${value}`}
                  />
                  <Line type="monotone" dataKey="ms" stroke="#2ecc8f" strokeWidth={1.6} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="empty">No samples.</p>
          )}
        </Card>
      </div>

      <Card
        title="Endpoint table"
        subtitle="Total volume and worst-case latency per route"
        padded={false}
      >
        <DataTable
          rows={endpoints}
          rowKey={(row) => row.endpoint}
          empty="No endpoint telemetry."
          columns={[
            { key: 'endpoint', header: 'Endpoint', render: (row) => <span className="mono-sm">{row.endpoint}</span> },
            { key: 'calls', header: 'Calls', align: 'right', render: (row) => fmtNum(row.calls) },
            { key: 'avg_ms', header: 'Avg', align: 'right', render: (row) => fmtMs(row.avg_ms) },
            { key: 'p95_ms', header: 'p95', align: 'right', render: (row) => fmtMs(row.p95_ms) },
            {
              key: 'budget',
              header: 'Budget',
              align: 'right',
              render: (row) => (
                <span className={`pill ${row.p95_ms <= 800 ? 'pill-green' : 'pill-red'}`}>
                  {row.p95_ms <= 800 ? 'within' : 'over'}
                </span>
              )
            }
          ]}
        />
      </Card>

      <div className="grid grid-2">
        <Card title="Browser page load" subtitle="Average load time per page">
          {pageRows.length ? (
            <div className="chart-box" style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={pageRows} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="page" width={96} tickLine={false} axisLine={false} />
                  <Tooltip formatter={(value) => [`${value} ms`, 'avg load']} />
                  <Bar dataKey="avg_ms" fill="#ffb547" radius={[0, 5, 5, 0]} barSize={14} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="empty">No page metrics ingested yet.</p>
          )}
        </Card>

        <Card title="Page budget" subtitle="3,000 ms average budget, measured by Playwright">
          <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)' }}>
            <Kpi label="Samples" value={fmtNum(pageSummary?.samples || 0)} sub={`${pageSummary?.window_days || days}d window`} />
            <Kpi label="Average" value={fmtMs(pageSummary?.avg_ms)} />
            <Kpi label="p95" value={fmtMs(pageSummary?.p95_ms)} tone="violet" />
            <Kpi
              label="Slowest"
              value={fmtMs(pageSummary?.slowest_ms)}
              tone={(pageSummary?.slowest_ms || 0) > (pageSummary?.budget_ms || 3000) ? 'red' : 'green'}
            />
          </div>
          <p className="small dim" style={{ marginTop: 12 }}>
            Page timings are pushed by Playwright through <code>POST /api/ingest/page-metrics</code> or recorded by the
            platform when the UI runner is enabled.
          </p>
        </Card>
      </div>

      <Card title="Raw samples" subtitle="Newest API measurements" padded={false}>
        <DataTable
          rows={(apiUsage.data?.items || []).slice(0, 40)}
          rowKey={(row) => row.id}
          dense
          empty="No samples."
          columns={[
            { key: 'endpoint', header: 'Endpoint', render: (row) => <span className="mono-sm">{row.endpoint}</span> },
            { key: 'method', header: 'Method', render: (row) => <span className="pill pill-grey">{row.method}</span> },
            {
              key: 'status_code',
              header: 'Status',
              render: (row) => (
                <span className={`pill ${row.status_code < 400 ? 'pill-green' : 'pill-red'}`}>{row.status_code}</span>
              )
            },
            { key: 'response_time_ms', header: 'Latency', align: 'right', render: (row) => fmtMs(row.response_time_ms) },
            { key: 'payload_bytes', header: 'Bytes', align: 'right', render: (row) => fmtNum(row.payload_bytes) },
            { key: 'source', header: 'Source', render: (row) => <span className="muted small">{row.source}</span> },
            { key: 'created_at', header: 'Recorded', render: (row) => fmtDate(row.created_at) }
          ]}
        />
      </Card>
    </>
  )
}
