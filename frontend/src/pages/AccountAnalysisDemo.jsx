import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { formatDate, formatDecimal, formatNumber, formatPillarName } from '../utils/format'

const ACCOUNT_FIXTURE_URL = '/fixtures/cristiano_account_result.json'
const POST_FIXTURE_URL = '/fixtures/cristiano_result.json'

function bandTone(value) {
    if (value === 'EXCEPTIONAL') return 'success'
    if (value === 'STRONG') return 'info'
    if (value === 'AVERAGE') return 'warning'
    return 'danger'
}

function scoreTone(value) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return 'neutral'
    }
    if (value >= 80) return 'success'
    if (value >= 60) return 'info'
    if (value >= 40) return 'warning'
    return 'danger'
}

function PillarBar({ label, score, band, notes }) {
    const width = Math.max(0, Math.min(100, typeof score === 'number' ? score : 0))
    return (
        <div className="account-demo-pillar-card">
            <div className="account-demo-pillar-head">
                <div>
                    <p className="account-demo-overline">{label}</p>
                    <strong>{formatDecimal(score)}</strong>
                </div>
                <span className={`account-demo-chip ${bandTone(band)}`}>{band || 'UNKNOWN'}</span>
            </div>
            <div className="account-demo-bar-track" aria-hidden="true">
                <div
                    className={`account-demo-bar-fill ${scoreTone(score)}`}
                    style={{ width: `${width}%` }}
                />
            </div>
            {Array.isArray(notes) && notes.length > 0 ? (
                <ul className="account-demo-note-list">
                    {notes.map((note) => (
                        <li key={note}>{note}</li>
                    ))}
                </ul>
            ) : (
                <p className="account-demo-muted">No additional notes for this pillar.</p>
            )}
        </div>
    )
}

function AccountAnalysisDemo() {
    const [accountResult, setAccountResult] = useState(null)
    const [postResult, setPostResult] = useState(null)
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        let cancelled = false

        async function loadFixtures() {
            setLoading(true)
            setError('')
            try {
                const [accountResponse, postResponse] = await Promise.all([
                    fetch(ACCOUNT_FIXTURE_URL),
                    fetch(POST_FIXTURE_URL)
                ])

                if (!accountResponse.ok || !postResponse.ok) {
                    throw new Error('Failed to load Cristiano fixture results.')
                }

                const [accountJson, postJson] = await Promise.all([
                    accountResponse.json(),
                    postResponse.json()
                ])

                if (!cancelled) {
                    setAccountResult(accountJson)
                    setPostResult(postJson)
                }
            } catch (loadError) {
                if (!cancelled) {
                    setError(loadError instanceof Error ? loadError.message : 'Unknown error')
                }
            } finally {
                if (!cancelled) {
                    setLoading(false)
                }
            }
        }

        loadFixtures()
        return () => {
            cancelled = true
        }
    }, [])

    const pillarEntries = useMemo(() => {
        if (!accountResult?.pillars || typeof accountResult.pillars !== 'object') {
            return []
        }
        return Object.entries(accountResult.pillars)
    }, [accountResult])

    const postScoreEntries = useMemo(() => {
        if (!postResult) {
            return []
        }
        return [
            ['S1 Visual Quality', postResult.visual_quality_score?.total],
            ['S2 Caption Effectiveness', postResult.caption_effectiveness_score?.total_0_50],
            ['S3 Content Clarity', postResult.content_clarity_score?.total],
            ['S4 Audience Relevance', postResult.audience_relevance_score?.total_0_50],
            ['S5 Engagement Potential', postResult.engagement_potential_score?.total],
            ['S6 Brand Safety', postResult.brand_safety_score?.total_0_50],
            ['Weighted Post Score', postResult.weighted_post_score?.score]
        ]
    }, [postResult])

    if (loading) {
        return (
            <div className="account-demo-shell">
                <div className="loading-container">
                    <div className="spinner"></div>
                    <p>Loading Cristiano account analysis results...</p>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="account-demo-shell">
                <div className="error-container">
                    <p>{error}</p>
                </div>
            </div>
        )
    }

    return (
        <div className="account-demo-shell">
            <div className="account-demo-page">
                <header className="account-demo-hero">
                    <div>
                        <p className="account-demo-overline">Fixture Viewer</p>
                        <h1>Cristiano Account Analysis</h1>
                        <p className="account-demo-hero-copy">
                            Frontend view of the local `cristiano_account_result.json` account analysis and the related single-post test result.
                        </p>
                    </div>
                    <div className="account-demo-hero-actions">
                        <Link className="account-demo-link" to="/analytics">Back to dashboard</Link>
                    </div>
                </header>

                <section className="account-demo-summary-grid">
                    <article className="account-demo-stat-card">
                        <span className="account-demo-stat-label">AHS Score</span>
                        <strong>{formatDecimal(accountResult?.ahs_score)}</strong>
                        <span className={`account-demo-chip ${bandTone(accountResult?.ahs_band)}`}>{accountResult?.ahs_band || 'UNKNOWN'}</span>
                    </article>
                    <article className="account-demo-stat-card">
                        <span className="account-demo-stat-label">Posts Used</span>
                        <strong>{formatNumber(accountResult?.metadata?.post_count_used)}</strong>
                        <span className="account-demo-muted">Recent posts included</span>
                    </article>
                    <article className="account-demo-stat-card">
                        <span className="account-demo-stat-label">Time Window</span>
                        <strong>{formatNumber(accountResult?.metadata?.time_window_days)}</strong>
                        <span className="account-demo-muted">Days analyzed</span>
                    </article>
                    <article className="account-demo-stat-card">
                        <span className="account-demo-stat-label">History Threshold</span>
                        <strong>{accountResult?.metadata?.min_history_threshold_met ? 'Met' : 'Not Met'}</strong>
                        <span className="account-demo-muted">10-post confidence gate</span>
                    </article>
                </section>

                <section className="account-demo-layout">
                    <div className="account-demo-main">
                        <div className="account-demo-panel">
                            <div className="account-demo-panel-head">
                                <div>
                                    <p className="account-demo-overline">Pillar Breakdown</p>
                                    <h2>What the account analysis is showing</h2>
                                </div>
                            </div>
                            <div className="account-demo-pillar-grid">
                                {pillarEntries.map(([key, pillar]) => (
                                    <PillarBar
                                        key={key}
                                        label={formatPillarName(key)}
                                        score={pillar?.score}
                                        band={pillar?.band}
                                        notes={pillar?.notes}
                                    />
                                ))}
                            </div>
                        </div>

                        <div className="account-demo-panel">
                            <div className="account-demo-panel-head">
                                <div>
                                    <p className="account-demo-overline">Drivers</p>
                                    <h2>What is limiting the score</h2>
                                </div>
                            </div>
                            <div className="account-demo-stack">
                                {(accountResult?.drivers || []).map((driver) => (
                                    <article key={driver.id} className="account-demo-callout limiting">
                                        <div className="account-demo-callout-head">
                                            <strong>{driver.label}</strong>
                                            <span className="account-demo-chip warning">{driver.type}</span>
                                        </div>
                                        <p>{driver.explanation}</p>
                                    </article>
                                ))}
                            </div>
                        </div>

                        <div className="account-demo-panel">
                            <div className="account-demo-panel-head">
                                <div>
                                    <p className="account-demo-overline">Recommendations</p>
                                    <h2>Suggested improvements</h2>
                                </div>
                            </div>
                            <div className="account-demo-stack">
                                {(accountResult?.recommendations || []).map((item) => (
                                    <article key={item.id} className="account-demo-callout recommendation">
                                        <div className="account-demo-callout-head">
                                            <strong>{item.text}</strong>
                                            <span className={`account-demo-chip ${item.impact_level === 'HIGH' ? 'danger' : 'info'}`}>
                                                {item.impact_level}
                                            </span>
                                        </div>
                                        <p className="account-demo-muted">{item.id}</p>
                                    </article>
                                ))}
                            </div>
                        </div>
                    </div>

                    <aside className="account-demo-side">
                        <div className="account-demo-panel">
                            <div className="account-demo-panel-head">
                                <div>
                                    <p className="account-demo-overline">Latest Post Test</p>
                                    <h2>Single post result</h2>
                                </div>
                            </div>
                            <div className="account-demo-post-card">
                                {postResult?.media_url ? (
                                    <img
                                        className="account-demo-post-image"
                                        src={postResult.media_url}
                                        alt="Cristiano post"
                                    />
                                ) : null}
                                <p className="account-demo-post-date">{formatDate(postResult?.published_at)}</p>
                                <p className="account-demo-post-caption">{postResult?.caption_text || 'No caption available.'}</p>
                                <div className="account-demo-mini-grid">
                                    <div>
                                        <span>Likes</span>
                                        <strong>{formatNumber(postResult?.core_metrics?.likes)}</strong>
                                    </div>
                                    <div>
                                        <span>Comments</span>
                                        <strong>{formatNumber(postResult?.core_metrics?.comments)}</strong>
                                    </div>
                                    <div>
                                        <span>Vision</span>
                                        <strong>{postResult?.vision_analysis?.status || 'unknown'}</strong>
                                    </div>
                                    <div>
                                        <span>P Score</span>
                                        <strong>{formatDecimal(postResult?.weighted_post_score?.score)}</strong>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="account-demo-panel">
                            <div className="account-demo-panel-head">
                                <div>
                                    <p className="account-demo-overline">Post Scoring</p>
                                    <h2>Test result metrics</h2>
                                </div>
                            </div>
                            <div className="account-demo-score-table">
                                {postScoreEntries.map(([label, value]) => (
                                    <div key={label} className="account-demo-score-row">
                                        <span>{label}</span>
                                        <strong>{formatDecimal(value)}</strong>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </aside>
                </section>
            </div>
        </div>
    )
}

export default AccountAnalysisDemo
