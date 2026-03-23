import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis
} from 'recharts'

const METRIC_CONFIG = [
    { key: 'reach', label: 'Reach', benchmarkKey: 'reach_percent_vs_avg' },
    { key: 'impressions', label: 'Impressions', benchmarkKey: 'impressions_percent_vs_avg' },
    { key: 'likes', label: 'Likes', benchmarkKey: 'likes_percent_vs_avg' },
    { key: 'comments', label: 'Comments', benchmarkKey: 'comments_percent_vs_avg' },
    { key: 'saves', label: 'Saves', benchmarkKey: 'saves_percent_vs_avg' },
    { key: 'shares', label: 'Shares', benchmarkKey: 'shares_percent_vs_avg' },
    { key: 'video_views', label: 'Video Views', benchmarkKey: 'impressions_percent_vs_avg', derivedFrom: 'impressions' },
    { key: 'watch_through_rate', label: 'Watch-through Rate', isRate: true, derivedKey: 'watch_through_rate' }
]

function formatNumber(value) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return 'N/A'
    }
    return value.toLocaleString()
}

function formatPercent(value) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return 'N/A'
    }
    return `${(value * 100).toFixed(1)}%`
}

function formatBenchmarkDelta(value) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return { label: 'No benchmark yet', tone: 'neutral' }
    }
    if (value > 0) {
        return { label: `+${value.toFixed(1)}% vs avg`, tone: 'positive' }
    }
    if (value < 0) {
        return { label: `${value.toFixed(1)}% vs avg`, tone: 'negative' }
    }
    return { label: 'On par with avg', tone: 'neutral' }
}

function formatPublishedAt(value) {
    if (!value) {
        return 'Date unavailable'
    }
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) {
        return 'Date unavailable'
    }
    return parsed.toLocaleDateString('en-US', {
        month: 'long',
        day: 'numeric',
        year: 'numeric'
    })
}

function formatTitleCase(value) {
    if (typeof value !== 'string' || !value.trim()) {
        return 'N/A'
    }
    return value
        .split(/[_\s-]+/)
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ')
}

function formatTimelineTick(value, spanMs) {
    if (!value) {
        return ''
    }
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) {
        return ''
    }
    if (spanMs <= 1000 * 60 * 60 * 24) {
        return parsed.toLocaleTimeString('en-US', {
            hour: 'numeric',
            minute: '2-digit'
        })
    }
    return parsed.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric'
    })
}

function buildBenchmarkBand(percentile) {
    if (typeof percentile !== 'number' || Number.isNaN(percentile)) {
        return {
            label: 'Benchmark rank unavailable',
            tone: 'neutral',
            width: 0
        }
    }

    const normalized = Math.max(0, Math.min(1, percentile))
    if (normalized >= 0.75) {
        return { label: 'Top 25% of last 90 days', tone: 'positive', width: normalized * 100 }
    }
    if (normalized >= 0.4) {
        return { label: '25-60% of last 90 days', tone: 'warning', width: normalized * 100 }
    }
    return { label: 'Bottom 40% of last 90 days', tone: 'negative', width: normalized * 100 }
}

function clampScore(value, min, max) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return min
    }
    return Math.max(min, Math.min(max, value))
}

function driverToneClass(type) {
    return type === 'POSITIVE' ? 'positive' : 'limiting'
}

function driverIcon(type) {
    return type === 'POSITIVE' ? '+' : '!'
}

function recommendationToneClass(level) {
    if (level === 'HIGH') return 'high'
    if (level === 'MEDIUM') return 'medium'
    return 'low'
}

function AiContentScoreGauge({ score, band, expanded }) {
    const [animatedScore, setAnimatedScore] = useState(0)
    const normalizedScore = clampScore(score, 0, 100)
    const radius = 74
    const circumference = Math.PI * radius
    const progress = circumference - (animatedScore / 100) * circumference

    useEffect(() => {
        if (!expanded) {
            setAnimatedScore(0)
            return
        }

        let frameId = 0
        let startTime = 0
        const duration = 900

        const tick = (timestamp) => {
            if (!startTime) {
                startTime = timestamp
            }
            const elapsed = timestamp - startTime
            const ratio = Math.min(1, elapsed / duration)
            const eased = 1 - Math.pow(1 - ratio, 3)
            setAnimatedScore(Number((normalizedScore * eased).toFixed(1)))
            if (ratio < 1) {
                frameId = window.requestAnimationFrame(tick)
            }
        }

        frameId = window.requestAnimationFrame(tick)
        return () => window.cancelAnimationFrame(frameId)
    }, [expanded, normalizedScore])

    return (
        <div className="ai-gauge-card">
            <p className="post-section-kicker">AI Content Score</p>
            <div className="ai-gauge-wrap">
                <svg className="ai-gauge" viewBox="0 0 200 120" role="img" aria-label={`AI content score ${normalizedScore}`}>
                    <defs>
                        <linearGradient id="aiGaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stopColor="#10b981" />
                            <stop offset="55%" stopColor="#3b82f6" />
                            <stop offset="100%" stopColor="#8b5cf6" />
                        </linearGradient>
                    </defs>
                    <path
                        className="ai-gauge-track"
                        d="M 26 100 A 74 74 0 0 1 174 100"
                        pathLength="100"
                    />
                    <path
                        className="ai-gauge-progress"
                        d="M 26 100 A 74 74 0 0 1 174 100"
                        strokeDasharray={circumference}
                        strokeDashoffset={progress}
                    />
                </svg>
                <div className="ai-gauge-center">
                    <strong>{Math.round(animatedScore)}</strong>
                    <span>/ 100</span>
                </div>
            </div>
            <p className="ai-gauge-band">{typeof band === 'string' && band ? band : 'UNRATED'}</p>
        </div>
    )
}

function SkeletonTile() {
    return (
        <div className="metric-tile metric-tile-skeleton">
            <div className="skeleton skeleton-label"></div>
            <div className="skeleton skeleton-value"></div>
            <div className="skeleton skeleton-meta"></div>
        </div>
    )
}

function SinglePostInsights() {
    const { media_id: mediaId } = useParams()
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [aiExpanded, setAiExpanded] = useState(false)

    useEffect(() => {
        let cancelled = false

        async function fetchPostInsights() {
            setLoading(true)
            setError('')
            try {
                const response = await fetch(`/api/v1/posts/${encodeURIComponent(mediaId)}/insights`)
                const payload = await response.json().catch(() => ({}))
                if (!response.ok) {
                    throw new Error(payload?.detail || 'Failed to load post insights')
                }
                if (!cancelled) {
                    setData(payload)
                }
            } catch (err) {
                if (!cancelled) {
                    setError(err.message || 'Failed to load post insights')
                    setData(null)
                }
            } finally {
                if (!cancelled) {
                    setLoading(false)
                }
            }
        }

        if (mediaId) {
            fetchPostInsights()
        } else {
            setError('Missing media id')
            setLoading(false)
        }

        return () => {
            cancelled = true
        }
    }, [mediaId])

    const post = data?.post || {}
    const aiAnalysis = data?.ai_analysis || {}
    const coreMetrics = post.core_metrics || {}
    const benchmarkMetrics = post.benchmark_metrics || {}
    const derivedMetrics = post.derived_metrics || {}

    const benchmarkBand = useMemo(
        () => buildBenchmarkBand(benchmarkMetrics.percentile_engagement_rank),
        [benchmarkMetrics.percentile_engagement_rank]
    )

    const reachBreakdownItems = useMemo(() => {
        const breakdown = post.reach_breakdown
        if (!breakdown || typeof breakdown !== 'object' || Array.isArray(breakdown)) {
            return []
        }

        const entries = Object.entries(breakdown)
            .map(([key, value]) => ({
                key,
                label: formatTitleCase(key),
                value: typeof value === 'number' && Number.isFinite(value) ? value : 0
            }))
            .filter((item) => item.value > 0)

        const total = entries.reduce((sum, item) => sum + item.value, 0)
        if (total <= 0) {
            return []
        }

        return entries
            .map((item) => ({
                ...item,
                percentage: item.value / total
            }))
            .sort((left, right) => right.value - left.value)
    }, [post.reach_breakdown])

    const engagementTimeline = useMemo(() => {
        const timeline = Array.isArray(post.engagement_timeline) ? post.engagement_timeline : []
        const normalized = timeline
            .map((point) => {
                const parsedTime = new Date(point?.timestamp)
                const value = point?.cumulative_engagement
                if (Number.isNaN(parsedTime.getTime()) || typeof value !== 'number' || !Number.isFinite(value)) {
                    return null
                }
                return {
                    timestamp: point.timestamp,
                    cumulative_engagement: value,
                    parsedTime: parsedTime.getTime()
                }
            })
            .filter(Boolean)
            .sort((left, right) => left.parsedTime - right.parsedTime)

        return normalized
    }, [post.engagement_timeline])

    const engagementTimelineSpan = useMemo(() => {
        if (engagementTimeline.length < 2) {
            return 0
        }
        return engagementTimeline[engagementTimeline.length - 1].parsedTime - engagementTimeline[0].parsedTime
    }, [engagementTimeline])

    const hasAiInsights = useMemo(() => {
        const drivers = Array.isArray(aiAnalysis.drivers) ? aiAnalysis.drivers : []
        const recommendations = Array.isArray(aiAnalysis.recommendations) ? aiAnalysis.recommendations : []
        const nicheContext = aiAnalysis.niche_context
        return Boolean(
            (typeof aiAnalysis.summary === 'string' && aiAnalysis.summary) ||
            drivers.length ||
            recommendations.length ||
            typeof aiAnalysis.ai_content_score === 'number' ||
            (nicheContext && typeof nicheContext === 'object')
        )
    }, [aiAnalysis])

    const metricTiles = useMemo(() => {
        return METRIC_CONFIG.map((metric) => {
            const rawValue = metric.derivedKey
                ? derivedMetrics[metric.derivedKey]
                : coreMetrics[metric.derivedFrom || metric.key]
            const displayValue = metric.isRate ? formatPercent(rawValue) : formatNumber(rawValue)
            const benchmark = formatBenchmarkDelta(benchmarkMetrics[metric.benchmarkKey])
            return {
                ...metric,
                displayValue,
                benchmark
            }
        })
    }, [benchmarkMetrics, coreMetrics, derivedMetrics])

    if (loading) {
        return (
            <div className="post-hero-page">
                <div className="post-hero-shell">
                    <div className="post-hero-topbar">
                        <div className="skeleton skeleton-nav"></div>
                    </div>
                    <div className="post-header-card">
                        <div className="skeleton post-media-skeleton"></div>
                        <div className="post-header-copy">
                            <div className="skeleton skeleton-title"></div>
                            <div className="skeleton skeleton-date"></div>
                            <div className="skeleton skeleton-caption"></div>
                            <div className="skeleton skeleton-caption short"></div>
                        </div>
                    </div>
                    <div className="metric-grid">
                        {Array.from({ length: 8 }).map((_, index) => (
                            <SkeletonTile key={index} />
                        ))}
                    </div>
                    <div className="benchmark-card">
                        <div className="skeleton skeleton-title"></div>
                        <div className="skeleton skeleton-bar"></div>
                    </div>
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="post-hero-page">
                <div className="post-hero-shell">
                    <div className="post-error-card">
                        <p className="post-error-eyebrow">Single Post Insights</p>
                        <h1>We couldn&apos;t load this post.</h1>
                        <p>{error}</p>
                        <div className="post-error-actions">
                            <button className="instagram-button" onClick={() => window.location.reload()}>
                                Retry
                            </button>
                            <Link className="auth-link" to="/dashboard">
                                Back to dashboard
                            </Link>
                        </div>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="post-hero-page">
            <div className="post-hero-shell">
                <div className="post-hero-topbar">
                    <Link className="post-back-link" to="/dashboard">
                        Back to dashboard
                    </Link>
                    <span className="post-route-id">{post.media_id || mediaId}</span>
                </div>

                <section className="post-header-card">
                    <div className="post-media-frame">
                        {post.media_url ? (
                            <img className="post-media-image" src={post.media_url} alt={post.caption_text || 'Post media'} />
                        ) : (
                            <div className="post-media-fallback">No thumbnail available</div>
                        )}
                    </div>
                    <div className="post-header-copy">
                        <p className="post-section-kicker">Post Header</p>
                        <h1>Single Post Insights</h1>
                        <p className="post-published-at">{formatPublishedAt(post.published_at)}</p>
                        <p className="post-caption-text">
                            {post.caption_text || 'No caption available for this post.'}
                        </p>
                    </div>
                </section>

                <section className="post-metrics-section">
                    <div className="section-heading">
                        <p className="post-section-kicker">Core Metrics Panel</p>
                        <h2>How this post performed</h2>
                    </div>
                    <div className="metric-grid">
                        {metricTiles.map((tile) => (
                            <article key={tile.key} className="metric-tile">
                                <span className="metric-label">{tile.label}</span>
                                <strong className="metric-value">{tile.displayValue}</strong>
                                <span className={`metric-benchmark metric-benchmark-${tile.benchmark.tone}`}>
                                    {tile.benchmark.label}
                                </span>
                            </article>
                        ))}
                    </div>
                </section>

                {reachBreakdownItems.length ? (
                    <section className="reach-breakdown-section">
                        <div className="section-heading">
                            <p className="post-section-kicker">Reach Breakdown</p>
                            <h2>Where this post was discovered</h2>
                        </div>
                        <div className="metric-grid">
                            {reachBreakdownItems.map((item) => (
                                <article key={item.key} className="metric-tile">
                                    <span className="metric-label">{item.label}</span>
                                    <strong className="metric-value">{formatNumber(item.value)}</strong>
                                    <span className="metric-benchmark metric-benchmark-neutral">
                                        {formatPercent(item.percentage)} of total reach
                                    </span>
                                </article>
                            ))}
                        </div>
                    </section>
                ) : null}

                <section className="benchmark-card">
                    <div className="section-heading compact">
                        <p className="post-section-kicker">Benchmark Bar</p>
                        <h2>Relative engagement rank</h2>
                    </div>
                    <div className="benchmark-meta-row">
                        <span className={`benchmark-pill benchmark-pill-${benchmarkBand.tone}`}>
                            {benchmarkBand.label}
                        </span>
                        <span className="benchmark-percentile">
                            {typeof benchmarkMetrics.percentile_engagement_rank === 'number'
                                ? `${Math.round(benchmarkMetrics.percentile_engagement_rank * 100)}th percentile`
                                : 'No percentile data'}
                        </span>
                    </div>
                    <div className="benchmark-track" aria-hidden="true">
                        <div
                            className={`benchmark-fill benchmark-fill-${benchmarkBand.tone}`}
                            style={{ width: `${benchmarkBand.width}%` }}
                        ></div>
                    </div>
                </section>

                {engagementTimeline.length ? (
                    <section className="benchmark-card engagement-timeline-section">
                        <div className="section-heading compact">
                            <p className="post-section-kicker">Engagement Timeline</p>
                            <h2>How engagement accumulated over time</h2>
                        </div>
                        <ResponsiveContainer width="100%" height={280}>
                            <LineChart data={engagementTimeline}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
                                <XAxis
                                    dataKey="timestamp"
                                    stroke="#a0a0b0"
                                    fontSize={12}
                                    tickFormatter={(value) => formatTimelineTick(value, engagementTimelineSpan)}
                                    minTickGap={24}
                                />
                                <YAxis
                                    stroke="#a0a0b0"
                                    fontSize={12}
                                    tickFormatter={(value) => formatNumber(value)}
                                />
                                <Tooltip
                                    contentStyle={{ background: '#1a1a24', border: '1px solid #2a2a3a', borderRadius: 8 }}
                                    labelStyle={{ color: '#fff' }}
                                    labelFormatter={(value) => {
                                        const parsed = new Date(value)
                                        return Number.isNaN(parsed.getTime())
                                            ? 'Unknown time'
                                            : parsed.toLocaleString('en-US', {
                                                  month: 'short',
                                                  day: 'numeric',
                                                  hour: 'numeric',
                                                  minute: '2-digit'
                                              })
                                    }}
                                    formatter={(value) => [formatNumber(value), 'Cumulative engagement']}
                                />
                                <Line
                                    type="monotone"
                                    dataKey="cumulative_engagement"
                                    stroke="#3b82f6"
                                    strokeWidth={2}
                                    dot={{ fill: '#3b82f6', r: 3 }}
                                    activeDot={{ r: 5 }}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </section>
                ) : null}

                <section className="ai-insights-shell">
                    <div className="ai-insights-toggle-row">
                        <div className="section-heading compact ai-heading-block">
                            <div>
                                <p className="post-section-kicker">AI Analysis</p>
                                <h2>Model-read narrative and action signals</h2>
                            </div>
                        </div>
                        <button
                            type="button"
                            className="ai-expand-button"
                            onClick={() => setAiExpanded((current) => !current)}
                            aria-expanded={aiExpanded}
                        >
                            {aiExpanded ? 'Collapse AI Insights' : 'Expand AI Insights'}
                        </button>
                    </div>

                    {aiExpanded ? (
                        hasAiInsights ? (
                            <div className="ai-insights-grid">
                                <div className="ai-summary-card">
                                    <div className="ai-summary-inner">
                                        <span className="post-ai-summary-label">AI Summary Card</span>
                                        <p className="ai-summary-text">
                                            {typeof aiAnalysis.summary === 'string' && aiAnalysis.summary
                                                ? aiAnalysis.summary
                                                : 'No AI summary is available for this post yet.'}
                                        </p>
                                    </div>
                                </div>

                                <AiContentScoreGauge
                                    score={typeof aiAnalysis.ai_content_score === 'number' ? aiAnalysis.ai_content_score : 0}
                                    band={aiAnalysis.ai_content_band}
                                    expanded={aiExpanded}
                                />

                                {aiAnalysis.niche_context ? (
                                    <div className="ai-detail-card">
                                        <span className="post-ai-summary-label">Competitor Context</span>
                                        <div className="ai-driver-list">
                                            <article className="ai-driver-item">
                                                <div className="ai-driver-copy">
                                                    <strong>Category</strong>
                                                    <p>{aiAnalysis.niche_context.category || 'N/A'}</p>
                                                </div>
                                            </article>
                                            <article className="ai-driver-item">
                                                <div className="ai-driver-copy">
                                                    <strong>Follower Band</strong>
                                                    <p>{aiAnalysis.niche_context.follower_band || 'N/A'}</p>
                                                </div>
                                            </article>
                                            <article className="ai-driver-item">
                                                <div className="ai-driver-copy">
                                                    <strong>Commentary</strong>
                                                    <p>{aiAnalysis.niche_context.commentary || 'No competitor commentary available.'}</p>
                                                </div>
                                            </article>
                                        </div>
                                    </div>
                                ) : null}

                                <div className="ai-detail-card">
                                    <span className="post-ai-summary-label">Performance Drivers</span>
                                    <div className="ai-driver-list">
                                        {(Array.isArray(aiAnalysis.drivers) ? aiAnalysis.drivers : []).length ? (
                                            (aiAnalysis.drivers || []).map((driver, index) => (
                                                <article
                                                    key={driver.id || `${driver.label || 'driver'}-${index}`}
                                                    className={`ai-driver-item ai-driver-item-${driverToneClass(driver.type)}`}
                                                >
                                                    <span className={`ai-driver-icon ai-driver-icon-${driverToneClass(driver.type)}`}>
                                                        {driverIcon(driver.type)}
                                                    </span>
                                                    <div className="ai-driver-copy">
                                                        <strong>{driver.label || 'Untitled driver'}</strong>
                                                        <p>{driver.explanation || 'No explanation provided.'}</p>
                                                    </div>
                                                </article>
                                            ))
                                        ) : (
                                            <p className="ai-empty-state">No AI drivers available for this post yet.</p>
                                        )}
                                    </div>
                                </div>

                                <div className="ai-detail-card">
                                    <span className="post-ai-summary-label">AI Recommendations</span>
                                    <div className="ai-recommendation-list">
                                        {(Array.isArray(aiAnalysis.recommendations) ? aiAnalysis.recommendations : []).length ? (
                                            (aiAnalysis.recommendations || []).map((recommendation, index) => (
                                                <article
                                                    key={recommendation.id || `${recommendation.text || 'recommendation'}-${index}`}
                                                    className="ai-recommendation-item"
                                                >
                                                    <p>{recommendation.text || 'No recommendation text provided.'}</p>
                                                    <span
                                                        className={`ai-impact-pill ai-impact-pill-${recommendationToneClass(
                                                            recommendation.impact_level
                                                        )}`}
                                                    >
                                                        {recommendation.impact_level || 'LOW'}
                                                    </span>
                                                </article>
                                            ))
                                        ) : (
                                            <p className="ai-empty-state">No AI recommendations available for this post yet.</p>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="ai-detail-card">
                                <p className="ai-empty-state">AI analysis has not been generated for this post yet.</p>
                            </div>
                        )
                    ) : null}
                </section>
            </div>
        </div>
    )
}

export default SinglePostInsights
