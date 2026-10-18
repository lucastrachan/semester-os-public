import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <main className="form-page">
      <header>
        <span className="eyebrow">404</span>
        <h1>That page isn't here yet</h1>
        <p>It may be coming in the next build, or the link may be wrong.</p>
      </header>
      <div className="hero-actions" style={{ marginTop: 0 }}>
        <Link to="/today" className="btn-primary">Go to Today</Link>
        <Link to="/study" className="btn-ghost">Study</Link>
      </div>
    </main>
  )
}
