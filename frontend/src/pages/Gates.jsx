import { Link } from 'react-router-dom'
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

function formatActual(item) {
  if (item.actual === null || item.actual === undefined) return '—'
  if (item.unit === '%') return fmtPct(item.actual, 2)
  if (item.unit === 'ms') return `${fmtNum(item.actual)} ms`
  if (item.unit === 'rows') return fmtNum(item.actual)
  return fmtNum(item.actual)
}

function formatThreshold(item) {
  if (item.threshold === null || item.threshold === undefined) return '—'
  if (item.unit === '%') return `${item.threshold}%`
  if (item.unit === 'ms') return `${fmtNum(item.threshold)} ms`
  if (item.unit === 'rows') return `${fmtNum(item.threshold)} rows`
  return fmtNum(item.threshold)
}

export default function Gates() {
  const gates = useFetch(() => api('/api/quality-gates?limit=15'))

  if (gates.loading && !gates.data) return <Spinner label="Evaluating quality gates…" />

  const data = gates.data || {}
  const items = data.items || []
  const config = data.config || []
  const failures = data.recent_failures || []
  const passed = items.filter((item) => item.status === 'passed').length
  const failed = items.filter((item) => item.status === 'failed').length

  const configByKey = Object.fromEntries(config.map((row) => [row.key, row]))

  const columns = [
    {
      key: 'name',
      header: 'Gate',
      render: (row) => (
        <div>
          <strong>{row.name}</strong>
          <div className="mono-sm dim">{row.key}</div>
        </div>
      )
    },
    {
      key: 'operator',
      header: 'Rule',
      render: (row) => {
        const cfg = configByKey[row.key] || row
        return (
          <span className="mono-sm">
            {cfg.operator} {formatThreshold({ ...cfg, actual: row.actual, unit: row.unit ?? cfg.unit })}
          </span>
        )
      }
    },
    {
      key: 'actual',
      header: 'Actual',
      align: 'right',
      render: (row) => <span className="mono-sm">{formatActual(row)}</span>
    },
    {
      key: 'status',
      header: 'Result',
      render: (row) => <StatusPill status={row.status} />
    },
    {
      key: 'blocking',
      header: 'Blocking',
      render: (row) => (row.blocking ? <span className="pill pill-blue">blocks release</span> : <span className="pill pill-grey">advisory</span>)
    }
  ]

  const failureColumns = [
    {
      key: 'run_key',
      header: 'Run',
      render: (row) => <Link to={`/runs/${row.run_key}`}>{row.run_key}</Link>
    },
    { key: 'gate', header: 'Gate' },
    {
      key: 'actual',
      header: 'Actual',
      align: 'right',
      render: (row) => <span className="mono-sm">{fmtNum(row.actual)}</span>
    },
    {
      key: 'threshold',
      header: 'Threshold',
      align: 'right',
      render: (row) => <span className="mono-sm">{fmtNum(row.threshold)}</span>
    },
    { key: 'at', header: 'When', render: (row) => fmtDate(row.at) }
  ]

  return (
    <>
      <PageHeader
        title="CI/CD quality gates"
        subtitle="One engine decides pass/fail for the dashboard, the API and GitHub Actions. Any blocking failure stops the pipeline."
        actions={
          <button type="button" className="btn btn-ghost" onClick={gates.reload}>
            Re-evaluate
          </button>
        }
      />

      <ErrorBanner error={gates.error} onRetry={gates.reload} />

      {data.blocked ? (
        <div className="banner banner-error" data-testid="gates-blocked">
          <div>
            <strong>Release is blocked.</strong>
            <p>
              {failed} of {items.length} gates failed against run {data.latest_run}. Fix the failing metrics or
              the pipeline will fail on the next run.
            </p>
          </div>
          {data.latest_run && (
            <Link className="btn btn-ghost" to={`/runs/${data.latest_run}`}>
              Open run
            </Link>
          )}
        </div>
      ) : (
        <div className="banner banner-ok" data-testid="gates-passed">
          <div>
            <strong>All blocking gates passed.</strong>
            <p>
              Evaluated against run {data.latest_run || '—'} at {fmtDate(data.evaluated_at)}.
            </p>
          </div>
        </div>
      )}

      <div className="kpi-grid">
        <Kpi label="Gates evaluated" value={fmtNum(items.length)} sub={data.latest_run || 'No run yet'} />
        <Kpi label="Passed" value={fmtNum(passed)} tone="green" />
        <Kpi label="Failed" value={fmtNum(failed)} tone={failed ? 'red' : 'default'} />
        <Kpi label="Blocking" value={fmtNum(config.filter((row) => row.blocking).length)} sub="Thresholds that stop CI" tone="violet" />
      </div>

      <div className="grid grid-2">
        <Card title="Gate results" subtitle={`Latest evaluation: ${fmtDate(data.evaluated_at)}`} padded={false}>
          <DataTable columns={columns} rows={items} rowKey={(row) => row.key || row.name} empty="No gates evaluated yet." dense />
        </Card>

        <Card title="Threshold configuration" subtitle="Set through environment variables — no code changes needed." padded={false}>
          <div className="table-wrap">
            <table className="table table-dense">
              <thead>
                <tr>
                  <th>Gate</th>
                  <th>Rule</th>
                  <th>Env var</th>
                </tr>
              </thead>
              <tbody>
                {config.map((row) => (
                  <tr key={row.key}>
                    <td>
                      <strong>{row.name}</strong>
                      {!row.blocking && <div className="mono-sm dim">advisory</div>}
                    </td>
                    <td className="mono-sm">
                      {row.operator} {formatThreshold(row)}
                    </td>
                    <td className="mono-sm dim">
                      {{
                        overall_pass_rate: 'GATE_API_PASS_RATE',
                        api_pass_rate: 'GATE_API_PASS_RATE',
                        ui_pass_rate: 'GATE_UI_PASS_RATE',
                        data_pass_rate: 'GATE_DATA_PASS_RATE',
                        api_p95_latency: 'GATE_API_P95_MS',
                        page_load_budget: 'GATE_PAGE_LOAD_MS',
                        load_error_rate: 'GATE_LOAD_ERROR_RATE',
                        data_failures: 'GATE_DATA_FAILURES',
                        test_volume: '—'
                      }[row.key] || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <Card
        title="Recent gate failures"
        subtitle="Kept for trend analysis — a green run today does not erase last week's regression."
        padded={false}
      >
        <DataTable
          columns={failureColumns}
          rows={failures}
          rowKey={(row) => `${row.run_key}-${row.gate}-${row.at}`}
          empty="No gate failures recorded."
          dense
        />
      </Card>

      <Card title="How CI consumes this" subtitle="Same evaluator, same thresholds, same verdict.">
        <pre className="mono-sm" style={{ margin: 0, overflowX: 'auto', lineHeight: 1.6 }}>{`# .github/workflows/quality-gates.yml
- name: Evaluate quality gates
  run: python scripts/evaluate_gates.py --run-key "$RUN_KEY" --fail-on-block

# exit code 0 -> pipeline continues
# exit code 1 -> blocking gate failed, pipeline stops`}</pre>
      </Card>
    </>
  )
}
