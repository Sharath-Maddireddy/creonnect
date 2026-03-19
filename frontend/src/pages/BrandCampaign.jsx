import { useMemo, useState } from 'react'

const BAND_CLASS_MAP = {
    EXCELLENT: 'excellent',
    GOOD: 'good',
    MODERATE: 'moderate',
    POOR: 'poor'
}

const BREAKDOWN_META = [
    { key: 'niche_fit', label: 'Niche Fit', color: 'var(--accent-purple)' },
    { key: 'engagement_quality', label: 'Engagement', color: 'var(--accent-green)' },
    { key: 'brand_safety_fit', label: 'Safety', color: 'var(--accent-blue)' },
    { key: 'content_quality_fit', label: 'Quality', color: 'var(--accent-yellow)' },
    { key: 'audience_size_fit', label: 'Audience', color: '#ffffff' }
]

const MANUAL_NICHES = [
    'fitness',
    'food',
    'tech',
    'fashion',
    'travel',
    'gaming',
    'beauty',
    'lifestyle',
    'finance',
    'education',
    'other'
]

function formatFollowerRange(minFollowers, maxFollowers) {
    const min = typeof minFollowers === 'number' ? minFollowers.toLocaleString() : null
    const max = typeof maxFollowers === 'number' ? maxFollowers.toLocaleString() : null
    if (min && max) {
        return `${min} - ${max}`
    }
    if (min && !max) {
        return `${min}+`
    }
    if (!min && max) {
        return `Up to ${max}`
    }
    return 'Not specified'
}

function formatBriefValue(key, value) {
    if (value === null || value === undefined || value === '') {
        return 'Not specified'
    }
    if (key === 'min_engagement_rate' && typeof value === 'number') {
        return `${(value * 100).toFixed(1)}%`
    }
    if ((key === 'min_followers' || key === 'max_followers') && typeof value === 'number') {
        return value.toLocaleString()
    }
    if (Array.isArray(value)) {
        return value.length ? value.join(', ') : 'Not specified'
    }
    return String(value)
}

function CreatorMatchCard({ match }) {
    const [notesOpen, setNotesOpen] = useState(false)
    const bandClass = BAND_CLASS_MAP[match?.match_band] || 'poor'
    const score = typeof match?.total_match_score === 'number' ? Math.round(match.total_match_score) : 0

    return (
        <article className="creator-match-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'flex-start', marginBottom: '1rem', flexWrap: 'wrap' }}>
                <div>
                    <strong style={{ display: 'block', fontSize: '1.1rem', color: 'var(--text-primary)' }}>{match?.account_id || 'Unknown Creator'}</strong>
                    <button
                        type="button"
                        className={`match-band-badge ${bandClass}`}
                        style={{ border: 'none' }}
                    >
                        {match?.match_band || 'POOR'}
                    </button>
                </div>
                <div className="match-score-display">{score}<span style={{ fontSize: '1rem', color: 'var(--text-secondary)' }}> /100</span></div>
            </div>

            <div style={{ marginBottom: '1.25rem' }}>
                {BREAKDOWN_META.map((item) => {
                    const rawValue = typeof match?.[item.key] === 'number' ? match[item.key] : 0
                    const percent = Math.max(0, Math.min(100, (rawValue / 20) * 100))
                    return (
                        <div className="match-breakdown-row" key={item.key}>
                            <span className="match-breakdown-label">{item.label}</span>
                            <div className="match-breakdown-track">
                                <div
                                    className="match-breakdown-fill"
                                    style={{ width: `${percent}%`, background: item.color }}
                                />
                            </div>
                            <span className="match-breakdown-value">{rawValue.toFixed(1)}</span>
                        </div>
                    )
                })}
            </div>

            {match?.disqualified ? (
                <div className="disqualified-banner" style={{ marginBottom: '1rem' }}>
                    <strong style={{ display: 'block', marginBottom: '0.4rem' }}>Disqualified</strong>
                    <ul style={{ margin: 0, paddingLeft: '1.1rem' }}>
                        {(Array.isArray(match?.disqualify_reasons) ? match.disqualify_reasons : []).map((reason) => (
                            <li key={reason}>{reason}</li>
                        ))}
                    </ul>
                </div>
            ) : null}

            <button
                type="button"
                onClick={() => setNotesOpen((current) => !current)}
                style={{
                    background: 'transparent',
                    border: '1px solid var(--border-color)',
                    color: 'var(--text-secondary)',
                    borderRadius: '12px',
                    padding: '0.65rem 0.9rem',
                    cursor: 'pointer'
                }}
            >
                {notesOpen ? 'Hide Notes' : 'Show Notes'}
            </button>

            {notesOpen ? (
                <div style={{ marginTop: '1rem', color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                    {(Array.isArray(match?.notes) ? match.notes : []).length ? (
                        <ul style={{ margin: 0, paddingLeft: '1.1rem' }}>
                            {match.notes.map((note) => (
                                <li key={note}>{note}</li>
                            ))}
                        </ul>
                    ) : (
                        <p style={{ margin: 0 }}>No notes available for this creator.</p>
                    )}
                </div>
            ) : null}
        </article>
    )
}

function BrandCampaign() {
    const [activeTab, setActiveTab] = useState('ai')
    const [prompt, setPrompt] = useState('')
    const [optionalBrandName, setOptionalBrandName] = useState('')
    const [manualForm, setManualForm] = useState({
        brand_name: '',
        niche: 'fitness',
        min_followers: '',
        max_followers: '',
        min_engagement_rate: ''
    })
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')
    const [result, setResult] = useState(null)

    const resultStats = useMemo(() => {
        const matches = Array.isArray(result?.matches) ? result.matches : []
        const disqualifiedCount = typeof result?.disqualified_count === 'number' ? result.disqualified_count : 0
        return {
            evaluated: typeof result?.total_evaluated === 'number' ? result.total_evaluated : matches.length,
            disqualified: disqualifiedCount,
            matches: Math.max(0, matches.length - disqualifiedCount)
        }
    }, [result])

    const submitDiscovery = async () => {
        setLoading(true)
        setError('')
        try {
            const res = await fetch('/api/brand/campaign/discover', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt,
                    brand_name: optionalBrandName || null
                })
            })
            const json = await res.json()
            if (!res.ok) {
                throw new Error(json?.detail || 'Failed to discover creators.')
            }
            setResult(json)
        } catch (err) {
            setError(err.message || 'Failed to discover creators.')
            setResult(null)
        } finally {
            setLoading(false)
        }
    }

    const submitManualMatch = async () => {
        setLoading(true)
        setError('')
        try {
            const payload = {
                brand_profile: {
                    brand_name: manualForm.brand_name,
                    niche: manualForm.niche,
                    min_followers: manualForm.min_followers ? Number(manualForm.min_followers) : null,
                    max_followers: manualForm.max_followers ? Number(manualForm.max_followers) : null,
                    min_engagement_rate: manualForm.min_engagement_rate
                        ? Number(manualForm.min_engagement_rate) / 100
                        : null
                }
            }
            const res = await fetch('/api/brand/campaign/match', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            const json = await res.json()
            if (!res.ok) {
                throw new Error(json?.detail || 'Failed to find creator matches.')
            }
            setResult(json)
        } catch (err) {
            setError(err.message || 'Failed to find creator matches.')
            setResult(null)
        } finally {
            setLoading(false)
        }
    }

    const parsedBriefEntries = useMemo(() => {
        if (!result?.parsed_brief || typeof result.parsed_brief !== 'object') {
            return []
        }
        return Object.entries(result.parsed_brief)
    }, [result])

    return (
        <div className="brand-campaign-page">
            <header className="campaign-header" style={{ marginBottom: '2rem' }}>
                <p className="post-section-kicker">Brand Campaign</p>
                <h1>Find Creators With AI Brief Matching</h1>
                <p style={{ color: 'var(--text-secondary)', maxWidth: '760px', lineHeight: 1.7 }}>
                    Discover the best-fit creators from your pool using either natural-language campaign briefs or direct manual filters.
                </p>
            </header>

            <div className="campaign-tab-bar">
                <button
                    type="button"
                    className={`campaign-tab ${activeTab === 'ai' ? 'active' : ''}`}
                    onClick={() => setActiveTab('ai')}
                >
                    AI Discovery
                </button>
                <button
                    type="button"
                    className={`campaign-tab ${activeTab === 'manual' ? 'active' : ''}`}
                    onClick={() => setActiveTab('manual')}
                >
                    Manual Match
                </button>
            </div>

            <section className="chart-card" style={{ marginBottom: '1.5rem' }}>
                {activeTab === 'ai' ? (
                    <>
                        <label className="campaign-form-field" style={{ display: 'block', marginBottom: '1rem' }}>
                            <span>Campaign Brief</span>
                            <textarea
                                className="campaign-prompt-input"
                                rows={4}
                                value={prompt}
                                onChange={(event) => setPrompt(event.target.value)}
                                placeholder="Describe your ideal creator... e.g. I need a fitness creator with 50k+ followers who makes high-quality workout reels for my protein supplement brand"
                            />
                        </label>

                        <div className="campaign-form-grid" style={{ alignItems: 'end' }}>
                            <label className="campaign-form-field">
                                <span>Brand Name</span>
                                <input
                                    type="text"
                                    value={optionalBrandName}
                                    onChange={(event) => setOptionalBrandName(event.target.value)}
                                    placeholder="Optional brand name"
                                />
                            </label>
                            <div>
                                <button
                                    type="button"
                                    className="campaign-submit-btn"
                                    disabled={loading || prompt.trim().length < 10}
                                    onClick={submitDiscovery}
                                >
                                    {loading ? 'Finding Creators...' : 'Find Creators'}
                                </button>
                            </div>
                        </div>
                    </>
                ) : (
                    <>
                        <div className="campaign-form-grid">
                            <label className="campaign-form-field">
                                <span>Brand Name</span>
                                <input
                                    type="text"
                                    value={manualForm.brand_name}
                                    onChange={(event) => setManualForm((current) => ({ ...current, brand_name: event.target.value }))}
                                    placeholder="Required brand name"
                                />
                            </label>
                            <label className="campaign-form-field">
                                <span>Niche</span>
                                <select
                                    value={manualForm.niche}
                                    onChange={(event) => setManualForm((current) => ({ ...current, niche: event.target.value }))}
                                >
                                    {MANUAL_NICHES.map((niche) => (
                                        <option key={niche} value={niche}>{niche}</option>
                                    ))}
                                </select>
                            </label>
                            <label className="campaign-form-field">
                                <span>Min Followers</span>
                                <input
                                    type="number"
                                    min="0"
                                    value={manualForm.min_followers}
                                    onChange={(event) => setManualForm((current) => ({ ...current, min_followers: event.target.value }))}
                                />
                            </label>
                            <label className="campaign-form-field">
                                <span>Max Followers</span>
                                <input
                                    type="number"
                                    min="0"
                                    value={manualForm.max_followers}
                                    onChange={(event) => setManualForm((current) => ({ ...current, max_followers: event.target.value }))}
                                />
                            </label>
                            <label className="campaign-form-field">
                                <span>Min Engagement Rate %</span>
                                <input
                                    type="number"
                                    min="0"
                                    step="0.1"
                                    value={manualForm.min_engagement_rate}
                                    onChange={(event) => setManualForm((current) => ({ ...current, min_engagement_rate: event.target.value }))}
                                />
                            </label>
                        </div>

                        <div style={{ marginTop: '1.25rem' }}>
                            <button
                                type="button"
                                className="campaign-submit-btn"
                                disabled={loading || !manualForm.brand_name.trim()}
                                onClick={submitManualMatch}
                            >
                                {loading ? 'Finding Matches...' : 'Find Matches'}
                            </button>
                        </div>
                    </>
                )}
            </section>

            {loading ? (
                <section className="chart-card" style={{ display: 'flex', alignItems: 'center', gap: '0.9rem', marginBottom: '1.5rem' }}>
                    <div className="spinner" />
                    <div>
                        <strong style={{ display: 'block', color: 'var(--text-primary)' }}>Searching creator pool</strong>
                        <span style={{ color: 'var(--text-secondary)' }}>Matching creators against your campaign brief.</span>
                    </div>
                </section>
            ) : null}

            {error ? (
                <section className="post-error-card">
                    <p className="post-error-eyebrow">Campaign Error</p>
                    <h2 style={{ marginTop: 0 }}>We couldn&apos;t complete the creator search.</h2>
                    <p>{error}</p>
                    <div className="post-error-actions">
                        <button
                            type="button"
                            className="campaign-submit-btn"
                            onClick={activeTab === 'ai' ? submitDiscovery : submitManualMatch}
                        >
                            Retry
                        </button>
                    </div>
                </section>
            ) : null}

            {result && !error ? (
                <>
                    {parsedBriefEntries.length ? (
                        <section className="parsed-brief-card" style={{ marginBottom: '1.5rem' }}>
                            <p className="post-section-kicker">AI Discovery</p>
                            <h2 style={{ marginTop: 0 }}>AI understood your brief as:</h2>
                            <div className="campaign-form-grid" style={{ marginTop: '1rem' }}>
                                {parsedBriefEntries.map(([key, value]) => (
                                    <div key={key} className="metric-tile" style={{ alignItems: 'flex-start' }}>
                                        <span className="metric-label">{key.replaceAll('_', ' ')}</span>
                                        <strong className="metric-value" style={{ fontSize: '1rem' }}>{formatBriefValue(key, value)}</strong>
                                    </div>
                                ))}
                            </div>
                            {typeof result.ai_explanation === 'string' && result.ai_explanation ? (
                                <p style={{ color: 'var(--text-secondary)', marginBottom: 0, marginTop: '1rem' }}>{result.ai_explanation}</p>
                            ) : null}
                        </section>
                    ) : null}

                    {!parsedBriefEntries.length && result?.brand_profile ? (
                        <section className="parsed-brief-card" style={{ marginBottom: '1.5rem' }}>
                            <p className="post-section-kicker">Manual Match</p>
                            <h2 style={{ marginTop: 0 }}>{result.brand_profile.brand_name}</h2>
                            <div className="campaign-results-stats">
                                <span>Niche: {result.brand_profile.niche || 'Not specified'}</span>
                                <span>Followers: {formatFollowerRange(result.brand_profile.min_followers, result.brand_profile.max_followers)}</span>
                                <span>Min ER: {typeof result.brand_profile.min_engagement_rate === 'number' ? `${(result.brand_profile.min_engagement_rate * 100).toFixed(1)}%` : 'Not specified'}</span>
                            </div>
                        </section>
                    ) : null}

                    <section>
                        <div className="campaign-results-stats" style={{ marginBottom: '1rem' }}>
                            <span>{resultStats.evaluated} creators evaluated</span>
                            <span>{resultStats.disqualified} disqualified</span>
                            <span>{resultStats.matches} matches</span>
                        </div>

                        {Array.isArray(result.matches) && result.matches.length ? (
                            result.matches.map((match) => (
                                <CreatorMatchCard key={`${match.account_id}-${match.total_match_score}`} match={match} />
                            ))
                        ) : (
                            <div className="chart-card" style={{ color: 'var(--text-secondary)' }}>
                                No creators found matching your criteria.
                            </div>
                        )}
                    </section>
                </>
            ) : null}
        </div>
    )
}

export default BrandCampaign
