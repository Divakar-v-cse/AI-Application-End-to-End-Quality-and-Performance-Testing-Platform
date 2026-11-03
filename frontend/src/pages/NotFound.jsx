import { Link } from 'react-router-dom'
import { PageHeader } from '../components/ui.jsx'

export default function NotFound() {
  return (
    <>
      <PageHeader title="Page not found" subtitle="That route does not exist in the quality platform." />
      <div className="card" style={{ padding: 28 }}>
        <p className="muted" style={{ marginBottom: 14 }}>
          Check the navigation on the left, or jump back to the quality dashboard.
        </p>
        <Link className="btn btn-primary" to="/dashboard">
          Go to dashboard
        </Link>
      </div>
    </>
  )
}
