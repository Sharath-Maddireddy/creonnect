import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

const GROUPS = [
    { key: 'account', label: 'Overview', description: 'Grade, growth, and account momentum.' },
    { key: 'content', label: 'Content intelligence', description: 'Posts, hooks, craft, and retention.' },
    { key: 'audience', label: 'Audience and timing', description: 'Who is watching and when to publish.' },
    { key: 'competition', label: 'Competitive position', description: 'Comparable creator performance.' },
    { key: 'monetization', label: 'Brand and earnings', description: 'Readiness and market potential.' },
    { key: 'action', label: 'Action plan', description: 'Prioritized work for the next month.' },
]

function titleCase(value) {
    return String(value || '').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function formatValue(value, unit) {
    if (typeof value === 'number') {
        if (unit === 'ratio_0_1') return `${(value * 100).toFixed(1)}%`
        return Number.isInteger(value) ? String(value) : value.toFixed(2)
    }
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        if (typeof value.score === 'number') return `${value.score.toFixed(1)} / 100`
        if (typeof value.average_watch_through_rate === 'number') return `${(value.average_watch_through_rate * 100).toFixed(1)}%`
        if (typeof value.observed_growth_pct === 'number') return `${value.observed_growth_pct.toFixed(1)}% observed growth`
    }
    return null
}

function MetricValue({ metric }) {
    const headline = formatValue(metric.value, metric.unit)
    if (headline) return <strong className="ci-metric-value">{headline}</strong>
    if (Array.isArray(metric.value)) return <strong className="ci-metric-value">{metric.value.length} evidence items</strong>
    if (metric.value && typeof metric.value === 'object') {
        const entries = Object.entries(metric.value).slice(0, 4)
        return (
            <dl className="ci-details">
                {entries.map(([key, value]) => (
                    <div key={key}>
                        <dt>{titleCase(key)}</dt>
                        <dd>{typeof value === 'number' ? value.toLocaleString() : String(value)}</dd>
                    </div>
                ))}
            </dl>
        )
    }
    return <strong className="ci-metric-value">Available</strong>
}

function MetricCard({ metric }) {
    const unavailable = metric.status === 'unavailable'
    return (
        <article className={`ci-metric ${unavailable ? 'ci-metric--unavailable' : ''}`}>
            <div className="ci-metric-heading">
                <div>
                    <p className="ci-overline">{metric.status}</p>
                    <h3>{metric.label}</h3>
                </div>
                {!unavailable && typeof metric.confidence === 'number' ? (
                    <span className="ci-confidence">{Math.round(metric.confidence * 100)}% coverage</span>
                ) : null}
            </div>
            {unavailable ? (
                <div className="ci-unavailable">
                    <p>{metric.availability_guidance}</p>
                    <small>{titleCase(metric.unavailable_reason)}</small>
                </div>
            ) : (
                <>
                    <MetricValue metric={metric} />
                    {metric.evidence?.length ? <p className="ci-evidence">{metric.evidence[0]}</p> : null}
                </>
            )}
        </article>
    )
}

export default function CreatorIntelligence() {
    const [report, setReport] = useState(null)
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        let active = true
        async function loadReport() {
            try {
                const response = await fetch('/api/creator-intelligence/latest')
                if (response.status === 404) throw new Error('Run account analysis to generate your first Creator Intelligence report.')
                if (response.status === 401) throw new Error('Your session has expired. Sign in again to view this report.')
                if (!response.ok) throw new Error('Unable to load the latest Creator Intelligence report.')
                const payload = await response.json()
                if (active) setReport(payload)
            } catch (loadError) {
                if (active) setError(loadError.message)
            } finally {
                if (active) setLoading(false)
            }
        }
        loadReport()
        return () => { active = false }
    }, [])

    if (loading) return <main className="ci-shell"><p className="ci-loading">Preparing Creator Intelligence...</p></main>
    if (error) return <main className="ci-shell"><section className="ci-empty"><h1>Creator Intelligence</h1><p>{error}</p><Link to="/analytics">Return to analytics</Link></section></main>

    const metrics = Array.isArray(report?.metrics) ? report.metrics : []
    const availableCount = metrics.filter((metric) => metric.status !== 'unavailable').length

    return (
        <main className="ci-shell">
            <header className="ci-hero">
                <div>
                    <p className="ci-overline">Creator Intelligence Report</p>
                    <h1>Evidence, not assumptions.</h1>
                    <p>Each insight shows its data status and only appears when the account data supports it.</p>
                </div>
                <div className="ci-hero-meta">
                    <strong>{availableCount} / {metrics.length}</strong>
                    <span>metrics available</span>
                    <Link to="/analytics">Legacy analytics</Link>
                </div>
            </header>

            {GROUPS.map((group) => {
                const groupMetrics = metrics.filter((metric) => metric.category === group.key)
                if (!groupMetrics.length) return null
                return (
                    <section className="ci-section" key={group.key}>
                        <header>
                            <p className="ci-overline">{group.label}</p>
                            <h2>{group.description}</h2>
                        </header>
                        <div className="ci-grid">
                            {groupMetrics.map((metric) => <MetricCard key={metric.metric_id} metric={metric} />)}
                        </div>
                    </section>
                )
            })}
        </main>
    )
}
