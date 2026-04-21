import { useMemo, useState } from 'react'

const BAND_CLASS_MAP = {
    EXCELLENT: 'excellent',
    GOOD: 'good',
    MODERATE: 'moderate',
    POOR: 'poor'
}

const BREAKDOWN_META = [
    { key: 'niche_fit', label: 'Niche Fit', color: 'var(--campaign-accent-pink)' },
    { key: 'engagement_quality', label: 'Engagement', color: 'var(--campaign-accent-emerald)' },
    { key: 'brand_safety_fit', label: 'Safety', color: 'var(--campaign-accent-cyan)' },
    { key: 'content_quality_fit', label: 'Quality', color: 'var(--campaign-accent-gold)' },
    { key: 'audience_size_fit', label: 'Audience', color: 'var(--campaign-accent-silver)' }
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

function formatCreatorTag(accountId) {
    if (!accountId) {
        return 'Unknown Creator'
    }
    return accountId.replace(/_id$/, '').replaceAll('_', '.')
}

function LookalikeCard({ creator }) {
    return (
        <div className="lookalike-card">
            <div className="lookalike-halo" />
            <div className="lookalike-card-content">
                <p className="lookalike-handle">@{creator.username || formatCreatorTag(creator.account_id)}</p>
                <strong>{creator.creator_dominant_category || 'General creator'}</strong>
                <span>{typeof creator.follower_count === 'number' ? `${creator.follower_count.toLocaleString()} followers` : 'Follower count unavailable'}</span>
                {Array.isArray(creator.niche_tags) && creator.niche_tags.length ? (
                    <div className="lookalike-tags">
                        {creator.niche_tags.slice(0, 3).map((tag) => (
                            <span key={`${creator.account_id}-${tag}`}>{tag}</span>
                        ))}
                    </div>
                ) : null}
            </div>
        </div>
    )
}

function CreatorMatchCard({ match }) {
    const [notesOpen, setNotesOpen] = useState(false)
    const [lookalikesOpen, setLookalikesOpen] = useState(false)
    const [lookalikesLoading, setLookalikesLoading] = useState(false)
    const [lookalikesError, setLookalikesError] = useState('')
    const [lookalikes, setLookalikes] = useState([])
    const bandClass = BAND_CLASS_MAP[match?.match_band] || 'poor'
    const score = typeof match?.total_match_score === 'number' ? Math.round(match.total_match_score) : 0

    const loadLookalikes = async () => {
        if (!match?.account_id) {
            return
        }
        if (lookalikesOpen) {
            setLookalikesOpen(false)
            return
        }
        if (lookalikes.length) {
            setLookalikesOpen(true)
            return
        }

        setLookalikesLoading(true)
        setLookalikesError('')
        setLookalikesOpen(true)

        try {
            const response = await fetch(`/api/brand/campaign/lookalikes/${encodeURIComponent(match.account_id)}`)
            const json = await response.json()
            if (!response.ok) {
                throw new Error(json?.detail || 'Unable to load creator lookalikes.')
            }
            setLookalikes(Array.isArray(json?.lookalikes) ? json.lookalikes : [])
        } catch (error) {
            setLookalikesError(error.message || 'Unable to load creator lookalikes.')
        } finally {
            setLookalikesLoading(false)
        }
    }

    return (
        <article className={`creator-match-card glass-card ${bandClass}`}>
            <div className="creator-card-orb creator-card-orb-left" />
            <div className="creator-card-orb creator-card-orb-right" />
            <div className="creator-match-card-shell">
                <div className="creator-card-header">
                    <div>
                        <p className="creator-card-kicker">Creator Match</p>
                        <strong className="creator-card-title">@{formatCreatorTag(match?.account_id)}</strong>
                        <button
                            type="button"
                            className={`match-band-badge ${bandClass}`}
                        >
                            {match?.match_band || 'POOR'}
                        </button>
                    </div>
                    <div className="match-score-display">
                        {score}
                        <span>/100</span>
                    </div>
                </div>

                <div className="creator-breakdown-grid">
                    {BREAKDOWN_META.map((item, index) => {
                        const rawValue = typeof match?.[item.key] === 'number' ? match[item.key] : 0
                        const percent = Math.max(0, Math.min(100, (rawValue / 20) * 100))
                        return (
                            <div className="match-breakdown-row" key={item.key} style={{ '--delay': `${index * 80}ms` }}>
                                <div className="match-breakdown-copy">
                                    <span className="match-breakdown-label">{item.label}</span>
                                    <span className="match-breakdown-value">{rawValue.toFixed(1)}</span>
                                </div>
                                <div className="match-breakdown-track">
                                    <div
                                        className="match-breakdown-fill"
                                        style={{ width: `${percent}%`, '--bar-color': item.color }}
                                    />
                                </div>
                            </div>
                        )
                    })}
                </div>

                {match?.disqualified ? (
                    <div className="disqualified-banner">
                        <strong>Disqualified</strong>
                        <ul>
                            {(Array.isArray(match?.disqualify_reasons) ? match.disqualify_reasons : []).map((reason) => (
                                <li key={reason}>{reason}</li>
                            ))}
                        </ul>
                    </div>
                ) : null}

                <div className="creator-card-actions">
                    <button
                        type="button"
                        className={`creator-card-action ${notesOpen ? 'active' : ''}`}
                        onClick={() => setNotesOpen((current) => !current)}
                    >
                        {notesOpen ? 'Hide Notes' : 'Show Notes'}
                    </button>
                    <button
                        type="button"
                        className={`creator-card-action creator-card-lookalike-btn ${lookalikesOpen ? 'active' : ''}`}
                        onClick={loadLookalikes}
                    >
                        {lookalikesLoading ? 'Finding Lookalikes...' : lookalikesOpen ? 'Hide Lookalikes' : 'Find Lookalikes'}
                    </button>
                </div>

                <div className={`creator-notes-panel ${notesOpen ? 'open' : ''}`}>
                    <div className="creator-notes-inner">
                        {(Array.isArray(match?.notes) ? match.notes : []).length ? (
                            <ul>
                                {match.notes.map((note) => (
                                    <li key={note}>{note}</li>
                                ))}
                            </ul>
                        ) : (
                            <p>No notes available for this creator.</p>
                        )}
                    </div>
                </div>

                <div className={`lookalike-panel ${lookalikesOpen ? 'open' : ''}`}>
                    <div className="lookalike-panel-inner">
                        <div className="lookalike-panel-header">
                            <div>
                                <p className="creator-card-kicker">Semantic Search</p>
                                <h3>Creator Lookalikes</h3>
                            </div>
                            <span>Powered by vector similarity</span>
                        </div>

                        {lookalikesLoading ? (
                            <div className="lookalike-loading">
                                <div className="lookalike-loading-dot" />
                                <div>
                                    <strong>Scanning creator graph</strong>
                                    <p>Finding accounts with similar category, tags, and bio signatures.</p>
                                </div>
                            </div>
                        ) : null}

                        {!lookalikesLoading && lookalikesError ? (
                            <div className="lookalike-error">{lookalikesError}</div>
                        ) : null}

                        {!lookalikesLoading && !lookalikesError && lookalikes.length ? (
                            <div className="lookalike-carousel">
                                {lookalikes.map((creator) => (
                                    <LookalikeCard key={`${match.account_id}-${creator.account_id}`} creator={creator} />
                                ))}
                            </div>
                        ) : null}

                        {!lookalikesLoading && !lookalikesError && !lookalikes.length ? (
                            <div className="lookalike-empty">
                                <div className="lookalike-empty-ring" />
                                <div>
                                    <strong>No lookalikes available yet</strong>
                                    <p>This creator may not have a stored embedding yet, or there are no close matches in the pool.</p>
                                </div>
                            </div>
                        ) : null}
                    </div>
                </div>
            </div>
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
            <div className="campaign-bg campaign-bg-left" />
            <div className="campaign-bg campaign-bg-right" />

            <header className="campaign-header">
                <p className="post-section-kicker">Brand Campaign</p>
                <h1>Find Creators With AI Brief Matching</h1>
                <p className="campaign-header-copy">
                    Discover the best-fit creators from your pool using natural-language campaign briefs or direct manual filters, then expand the shortlist with semantic creator lookalikes in one flow.
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

            <section className="campaign-console glass-card">
                <div className="campaign-console-glow" />
                {activeTab === 'ai' ? (
                    <>
                        <label className="campaign-form-field campaign-form-field-wide">
                            <span>Campaign Brief</span>
                            <textarea
                                className="campaign-prompt-input"
                                rows={4}
                                value={prompt}
                                onChange={(event) => setPrompt(event.target.value)}
                                placeholder="Describe your ideal creator... e.g. I need a fitness creator with 50k+ followers who makes high-quality workout reels for my protein supplement brand"
                            />
                        </label>

                        <div className="campaign-form-grid campaign-form-grid-ai">
                            <label className="campaign-form-field">
                                <span>Brand Name</span>
                                <input
                                    type="text"
                                    value={optionalBrandName}
                                    onChange={(event) => setOptionalBrandName(event.target.value)}
                                    placeholder="Optional brand name"
                                />
                            </label>
                            <div className="campaign-cta-block">
                                <button
                                    type="button"
                                    className="campaign-submit-btn"
                                    disabled={loading || prompt.trim().length < 10}
                                    onClick={submitDiscovery}
                                >
                                    {loading ? 'Finding Creators...' : 'Find Creators'}
                                </button>
                                <p>AI parses the brief, builds the profile, then scores the creator pool.</p>
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

                        <div className="campaign-cta-row">
                            <button
                                type="button"
                                className="campaign-submit-btn"
                                disabled={loading || !manualForm.brand_name.trim()}
                                onClick={submitManualMatch}
                            >
                                {loading ? 'Finding Matches...' : 'Find Matches'}
                            </button>
                            <p>Use direct constraints when you already know the campaign envelope.</p>
                        </div>
                    </>
                )}
            </section>

            {loading ? (
                <section className="campaign-loading-shell glass-card">
                    <div className="campaign-loading-radar">
                        <div className="campaign-loading-ring ring-a" />
                        <div className="campaign-loading-ring ring-b" />
                        <div className="campaign-loading-core" />
                    </div>
                    <div>
                        <strong>Searching creator pool</strong>
                        <p>Running brief extraction, scoring creator fit, and assembling your shortlist.</p>
                    </div>
                </section>
            ) : null}

            {error ? (
                <section className="post-error-card">
                    <p className="post-error-eyebrow">Campaign Error</p>
                    <h2>We couldn&apos;t complete the creator search.</h2>
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

            {!loading && !result && !error ? (
                <section className="campaign-empty-state glass-card">
                    <div className="campaign-empty-state-illustration">
                        <span className="pulse pulse-a" />
                        <span className="pulse pulse-b" />
                        <span className="pulse pulse-c" />
                    </div>
                    <div>
                        <p className="post-section-kicker">Ready To Discover</p>
                        <h2>Turn your brand brief into a ranked creator universe.</h2>
                        <p>
                            Start with AI Discovery for natural-language matching, or use Manual Match when you already know the exact follower and engagement thresholds.
                        </p>
                    </div>
                </section>
            ) : null}

            {result && !error ? (
                <div className="campaign-results-shell">
                    {parsedBriefEntries.length ? (
                        <section className="parsed-brief-card glass-card campaign-brief-card">
                            <div className="campaign-brief-header">
                                <div>
                                    <p className="post-section-kicker">AI Discovery</p>
                                    <h2>AI understood your brief as</h2>
                                </div>
                                <div className="campaign-brief-chip">Brief Extraction</div>
                            </div>
                            <div className="campaign-brief-grid">
                                {parsedBriefEntries.map(([key, value]) => (
                                    <div key={key} className="campaign-brief-tile">
                                        <span className="metric-label">{key.replaceAll('_', ' ')}</span>
                                        <strong className="metric-value campaign-brief-value">{formatBriefValue(key, value)}</strong>
                                    </div>
                                ))}
                            </div>
                            {typeof result.ai_explanation === 'string' && result.ai_explanation ? (
                                <div className="campaign-ai-explanation">
                                    <span>AI Summary</span>
                                    <p>{result.ai_explanation}</p>
                                </div>
                            ) : null}
                        </section>
                    ) : null}

                    {!parsedBriefEntries.length && result?.brand_profile ? (
                        <section className="parsed-brief-card glass-card campaign-brief-card">
                            <div className="campaign-brief-header">
                                <div>
                                    <p className="post-section-kicker">Manual Match</p>
                                    <h2>{result.brand_profile.brand_name}</h2>
                                </div>
                                <div className="campaign-brief-chip">Profile Lock</div>
                            </div>
                            <div className="campaign-results-stats">
                                <span>Niche: {result.brand_profile.niche || 'Not specified'}</span>
                                <span>Followers: {formatFollowerRange(result.brand_profile.min_followers, result.brand_profile.max_followers)}</span>
                                <span>Min ER: {typeof result.brand_profile.min_engagement_rate === 'number' ? `${(result.brand_profile.min_engagement_rate * 100).toFixed(1)}%` : 'Not specified'}</span>
                            </div>
                        </section>
                    ) : null}

                    <section className="campaign-results-section">
                        <div className="campaign-results-overview glass-card">
                            <div className="campaign-results-overview-copy">
                                <p className="post-section-kicker">Results</p>
                                <h2>Creator shortlist</h2>
                            </div>
                            <div className="campaign-results-stats campaign-results-stats-glow">
                                <span>{resultStats.evaluated} creators evaluated</span>
                                <span>{resultStats.disqualified} disqualified</span>
                                <span>{resultStats.matches} matches</span>
                            </div>
                        </div>

                        {Array.isArray(result.matches) && result.matches.length ? (
                            <div className="campaign-match-list">
                                {result.matches.map((match, index) => (
                                    <div
                                        key={`${match.account_id}-${match.total_match_score}`}
                                        className="campaign-match-entry"
                                        style={{ '--entry-delay': `${index * 90}ms` }}
                                    >
                                        <CreatorMatchCard match={match} />
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="campaign-no-results glass-card">
                                <div className="campaign-no-results-icon" />
                                <div>
                                    <strong>No creators found matching your criteria.</strong>
                                    <p>Try widening follower range, loosening the niche, or giving the AI brief more detail.</p>
                                </div>
                            </div>
                        )}
                    </section>
                </div>
            ) : null}
        </div>
    )
}

export default BrandCampaign
