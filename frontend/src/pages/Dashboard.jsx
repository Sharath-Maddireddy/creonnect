import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
    LineChart,
    Line,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer
} from 'recharts'

const PILLAR_COLORS = {
    content_quality: '#3b82f6',
    engagement_quality: '#10b981',
    niche_fit: '#8b5cf6',
    consistency: '#f59e0b',
    brand_safety: '#ef4444'
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function formatCompactNumber(value) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return 'N/A'
    }
    return value.toLocaleString()
}

function formatEngagementPercent(value) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return 'N/A'
    }
    return `${value.toFixed(2)}%`
}

function formatPostDate(value) {
    if (!value) {
        return 'Date unavailable'
    }
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) {
        return 'Date unavailable'
    }
    return parsed.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    })
}

function truncateText(value, maxLength = 80) {
    if (typeof value !== 'string' || !value.trim()) {
        return 'No caption or AI summary available.'
    }
    const normalized = value.trim()
    if (normalized.length <= maxLength) {
        return normalized
    }
    return `${normalized.slice(0, maxLength - 3)}...`
}

function clampValue(value, min, max) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return min
    }
    return Math.max(min, Math.min(max, value))
}

function formatPercentFromRatio(value) {
    if (typeof value !== 'number' || Number.isNaN(value)) {
        return 'N/A'
    }
    return `${(value * 100).toFixed(1)}%`
}

function formatPillarName(value) {
    if (typeof value !== 'string' || !value.trim()) {
        return 'Unknown Pillar'
    }
    return value
        .split('_')
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ')
}

function recommendationToneClass(level) {
    if (level === 'HIGH') return 'high'
    if (level === 'MEDIUM') return 'medium'
    return 'low'
}

function driverTone(type) {
    return type === 'POSITIVE' ? 'positive' : 'limiting'
}

function directionArrow(direction) {
    if (typeof direction !== 'string') {
        return '-'
    }
    const normalized = direction.toLowerCase()
    if (normalized.includes('up') || normalized.includes('acceler') || normalized.includes('grow')) {
        return '↑'
    }
    if (normalized.includes('down') || normalized.includes('declin') || normalized.includes('drop')) {
        return '↓'
    }
    return '→'
}

function ActionPlanItems(actionPlan) {
    if (!actionPlan || typeof actionPlan !== 'object') {
        return []
    }
    if (Array.isArray(actionPlan.strategies)) {
        return actionPlan.strategies.filter((item) => typeof item === 'string' && item.trim())
    }

    const keys = ['weekly_plan', 'content_suggestions', 'posting_schedule', 'cta_tips']
    const items = []
    keys.forEach((key) => {
        const value = actionPlan[key]
        if (Array.isArray(value)) {
            value.forEach((item) => {
                if (typeof item === 'string' && item.trim()) {
                    items.push(item)
                }
            })
        }
    })
    return items
}

function AccountHealthGauge({ score, band }) {
    const [animatedScore, setAnimatedScore] = useState(0)
    const normalizedScore = clampValue(score, 0, 100)
    const radius = 74
    const circumference = Math.PI * radius
    const progress = circumference - (animatedScore / 100) * circumference

    useEffect(() => {
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
    }, [normalizedScore])

    return (
        <div className="ai-gauge-card" style={{ minHeight: '100%' }}>
            <p className="post-section-kicker">Account Health Score</p>
            <div className="ai-gauge-wrap">
                <svg className="ai-gauge" viewBox="0 0 200 120" role="img" aria-label={`Account health score ${normalizedScore}`}>
                    <defs>
                        <linearGradient id="accountHealthGaugeGradient" x1="0%" y1="0%" x2="100%" y2="0%">
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
                        stroke="url(#accountHealthGaugeGradient)"
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

function Dashboard() {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [userId, setUserId] = useState('')
    const [username, setUsername] = useState('')
    const [postSort, setPostSort] = useState('date')
    const [analyzingPostId, setAnalyzingPostId] = useState('')
    const navigate = useNavigate()

    const fetchDashboard = async (currentUserId) => {
        setLoading(true)
        setError(null)
        try {
            const url = currentUserId ? `/api/creator/analytics?user_id=${encodeURIComponent(currentUserId)}` : `/api/creator/analytics`
            const res = await fetch(url)
            if (res.status === 401) {
                // If token expired or not found, just fallback to demo mode
                const demoRes = await fetch(`/api/creator/analytics`)
                if (!demoRes.ok) throw new Error('Failed to fetch demo dashboard data')
                const json = await demoRes.json()
                setData(json)
                return
            }
            if (!res.ok) throw new Error('Failed to fetch dashboard data')
            const json = await res.json()
            setData(json)
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        const storedUserId = localStorage.getItem('user_id') || ''
        const storedUsername = localStorage.getItem('username') || 'Demo User'
        setUserId(storedUserId)
        setUsername(storedUsername)
    }, [])

    useEffect(() => {
        fetchDashboard(userId)
    }, [userId])

    const sortedPosts = useMemo(() => {
        const posts = data?.posts
        const sortablePosts = Array.isArray(posts) ? [...posts] : []
        sortablePosts.sort((left, right) => {
            if (postSort === 'views') {
                return (right.views || 0) - (left.views || 0)
            }
            if (postSort === 'engagement') {
                return (right.engagement_rate_by_views || 0) - (left.engagement_rate_by_views || 0)
            }

            const leftDate = new Date(left.published_at || left.timestamp || left.created_at || 0).getTime()
            const rightDate = new Date(right.published_at || right.timestamp || right.created_at || 0).getTime()
            return rightDate - leftDate
        })
        return sortablePosts
    }, [postSort, data?.posts])

    if (loading) {
        return (
            <div className="loading-container">
                <div className="spinner"></div>
                <p>Loading dashboard...</p>
            </div>
        )
    }

    if (error) {
        return (
            <div className="error-container">
                <p>Error: {error}</p>
                <button onClick={() => fetchDashboard(userId)}>Retry</button>
            </div>
        )
    }

    const { summary, posts, charts } = data
    const accountHealth = data?.account_health || {}
    const contentTypeBreakdown = data?.content_type_breakdown || {}
    const actionPlanItems = useMemo(() => ActionPlanItems(data?.action_plan), [data?.action_plan])

    // Color for growth score
    const getGrowthColor = (score) => {
        if (score >= 80) return 'green'
        if (score >= 50) return 'yellow'
        return 'red'
    }

    // Format chart data
    const engagementData = charts.engagement_over_time.map((item, i) => ({
        date: item.date ? new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : `Post ${i + 1}`,
        value: item.value ? parseFloat(item.value.toFixed(2)) : 0
    }))

    const viewsData = charts.views_over_time.map((item, i) => ({
        date: item.date ? new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : `Post ${i + 1}`,
        value: item.value || 0
    }))

    const pillarCards = useMemo(() => {
        const pillars = accountHealth?.pillars && typeof accountHealth.pillars === 'object' ? accountHealth.pillars : {}
        return Object.entries(pillars).map(([key, pillar]) => ({
            key,
            label: formatPillarName(key),
            color: PILLAR_COLORS[key] || 'var(--accent-blue)',
            score: pillar?.score ?? 0,
            band: pillar?.band || 'UNKNOWN',
            notes: Array.isArray(pillar?.notes) ? pillar.notes : []
        }))
    }, [accountHealth?.pillars])

    const accountHealthDrivers = Array.isArray(accountHealth?.drivers) ? accountHealth.drivers : []
    const accountHealthRecommendations = Array.isArray(accountHealth?.recommendations) ? accountHealth.recommendations : []

    const contentTypeChartData = useMemo(() => {
        return ['REEL', 'IMAGE'].map((type) => ({
            type,
            avgEngagement: contentTypeBreakdown?.[type]?.avg_engagement_rate ?? 0,
            count: contentTypeBreakdown?.[type]?.count ?? 0
        }))
    }, [contentTypeBreakdown])

    const bestHoursRaw = Array.isArray(summary?.best_time_to_post?.best_hours)
        ? summary.best_time_to_post.best_hours
        : []

    const bestPostingHeatmap = useMemo(() => {
        const hours = Array.from(new Set(bestHoursRaw.map((item) => item?.hour).filter((value) => Number.isInteger(value)))).sort((a, b) => a - b)
        const fallbackHours = hours.length ? hours : [9, 12, 18, 21]
        const maxEngagement = bestHoursRaw.reduce((max, item) => {
            const value = typeof item?.avg_engagement === 'number' ? item.avg_engagement : 0
            return Math.max(max, value)
        }, 0)

        const grid = DAYS.map((day) => ({
            day,
            cells: fallbackHours.map((hour) => {
                const match = bestHoursRaw.find((item) => item?.day === day && item?.hour === hour)
                const value = typeof match?.avg_engagement === 'number' ? match.avg_engagement : 0
                const intensity = maxEngagement > 0 ? value / maxEngagement : 0
                return {
                    hour,
                    value,
                    intensity
                }
            })
        }))

        return {
            hours: fallbackHours,
            grid
        }
    }, [bestHoursRaw, summary?.best_time_to_post?.best_hours])

    const handleOpenPost = async (post) => {
        if (!post?.post_id || !post?.media_url || analyzingPostId) {
            return
        }

        setAnalyzingPostId(post.post_id)
        setError(null)
        try {
            const response = await fetch('/api/post-analysis', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    post_id: post.post_id,
                    creator_id: summary?.username || '',
                    platform: 'instagram',
                    post_type: post.post_type || 'IMAGE',
                    media_url: post.media_url,
                    thumbnail_url: post.thumbnail_url || '',
                    caption_text: post.caption_text || '',
                    hashtags: Array.isArray(post.hashtags) ? post.hashtags : [],
                    likes: post.likes || 0,
                    comments: post.comments || 0,
                    views: post.views ?? null,
                    audio_name: post.audio_name || null,
                    posted_at: post.published_at || null
                })
            })

            if (!response.ok) {
                const payload = await response.json().catch(() => ({}))
                throw new Error(payload?.detail || 'Failed to analyze post before opening insights')
            }

            navigate(`/post/${encodeURIComponent(post.post_id)}`)
        } catch (err) {
            setError(err.message || 'Failed to analyze post before opening insights')
        } finally {
            setAnalyzingPostId('')
        }
    }

    return (
        <div className="dashboard">
            {/* Header */}
            <div className="dashboard-header">
                <h1>Creator Analytics</h1>
                <p className="username">@{username || summary.username}</p>
            </div>

            {/* Summary Cards */}
            <div className="summary-grid">
                <div className="summary-card">
                    <div className="label">Growth Score</div>
                    <div className={`value ${getGrowthColor(summary.growth_score)}`}>
                        {summary.growth_score}
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Engagement %</div>
                    <div className="value blue">
                        {summary.avg_engagement_rate_by_views?.toFixed(2)}%
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Avg Views</div>
                    <div className="value">
                        {summary.avg_views?.toLocaleString()}
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Reach Ratio</div>
                    <div className="value purple">
                        {summary.views_to_followers_ratio?.toFixed(2)}x
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Posts / Week</div>
                    <div className="value">
                        {summary.posts_per_week?.toFixed(1)}
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Niche</div>
                    <div className="value" style={{ fontSize: '1.25rem', textTransform: 'capitalize' }}>
                        {summary.niche?.primary_niche || 'Unknown'}
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Followers</div>
                    <div className="value">
                        {typeof summary.followers === 'number' ? summary.followers.toLocaleString() : 'N/A'}
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Momentum</div>
                    <div className="value blue" style={{ fontSize: '1.5rem' }}>
                        {directionArrow(summary.momentum?.direction)} {summary.momentum?.direction || 'Stable'}
                    </div>
                    <div className="label" style={{ marginTop: '0.5rem' }}>
                        {typeof summary.momentum?.percentage === 'number'
                            ? `${summary.momentum.percentage.toFixed(1)}%`
                            : typeof summary.momentum?.momentum_value === 'number'
                                ? `${summary.momentum.momentum_value.toFixed(1)} score`
                                : 'No momentum data'}
                    </div>
                </div>
            </div>

            <div
                className="posts-section"
                style={{
                    marginTop: '1.5rem',
                    display: 'grid',
                    gap: '1rem'
                }}
            >
                <div className="posts-feed-header">
                    <div>
                        <h3>Account Health Score</h3>
                        <p className="posts-feed-subtitle">Deterministic account-level read across quality, engagement, fit, consistency, and safety.</p>
                    </div>
                </div>

                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'minmax(280px, 360px) minmax(0, 1fr)',
                        gap: '1rem'
                    }}
                >
                    <AccountHealthGauge score={accountHealth?.ahs_score ?? 0} band={accountHealth?.ahs_band} />

                    <div
                        style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                            gap: '0.85rem'
                        }}
                    >
                        {pillarCards.map((pillar) => (
                            <div
                                key={pillar.key}
                                className="metric-tile"
                                style={{
                                    background: 'var(--bg-secondary)',
                                    borderRadius: '18px',
                                    border: '1px solid var(--border-color)'
                                }}
                            >
                                <span className="metric-label">{pillar.label}</span>
                                <strong className="metric-value">{Math.round(pillar.score)}</strong>
                                <span className="metric-benchmark metric-benchmark-neutral">{pillar.band}</span>
                                <div
                                    style={{
                                        marginTop: '0.85rem',
                                        width: '100%',
                                        height: '8px',
                                        background: 'rgba(255,255,255,0.06)',
                                        borderRadius: '999px',
                                        overflow: 'hidden'
                                    }}
                                >
                                    <div
                                        style={{
                                            width: `${clampValue(pillar.score, 0, 100)}%`,
                                            height: '100%',
                                            background: pillar.color,
                                            borderRadius: '999px'
                                        }}
                                    />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                        gap: '1rem'
                    }}
                >
                    <div className="ai-detail-card">
                        <span className="post-ai-summary-label">Account Drivers</span>
                        <div className="ai-driver-list">
                            {accountHealthDrivers.length ? accountHealthDrivers.map((driver) => (
                                <article
                                    key={driver.id || driver.label}
                                    className={`ai-driver-item ai-driver-item-${driverTone(driver.type)}`}
                                >
                                    <span className={`ai-driver-icon ai-driver-icon-${driverTone(driver.type)}`}>
                                        {driver.type === 'POSITIVE' ? '+' : '!'}
                                    </span>
                                    <div className="ai-driver-copy">
                                        <strong>{driver.label || 'Untitled driver'}</strong>
                                        <p>{driver.explanation || 'No explanation provided.'}</p>
                                    </div>
                                </article>
                            )) : (
                                <p className="ai-empty-state">No account-level drivers available yet.</p>
                            )}
                        </div>
                    </div>

                    <div className="ai-detail-card">
                        <span className="post-ai-summary-label">Recommendations</span>
                        <div className="ai-recommendation-list">
                            {accountHealthRecommendations.length ? accountHealthRecommendations.map((recommendation) => (
                                <article key={recommendation.id || recommendation.text} className="ai-recommendation-item">
                                    <p>{recommendation.text || 'No recommendation text provided.'}</p>
                                    <span className={`ai-impact-pill ai-impact-pill-${recommendationToneClass(recommendation.impact_level)}`}>
                                        {recommendation.impact_level || 'LOW'}
                                    </span>
                                </article>
                            )) : (
                                <p className="ai-empty-state">No account recommendations available yet.</p>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* Charts */}
            <div className="charts-section">
                <div className="chart-card">
                    <h3>Engagement by Views (%)</h3>
                    <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={engagementData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
                            <XAxis dataKey="date" stroke="#a0a0b0" fontSize={12} />
                            <YAxis stroke="#a0a0b0" fontSize={12} />
                            <Tooltip
                                contentStyle={{ background: '#1a1a24', border: '1px solid #2a2a3a', borderRadius: 8 }}
                                labelStyle={{ color: '#fff' }}
                            />
                            <Line
                                type="monotone"
                                dataKey="value"
                                stroke="#3b82f6"
                                strokeWidth={2}
                                dot={{ fill: '#3b82f6', r: 4 }}
                                activeDot={{ r: 6 }}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                </div>

                <div className="chart-card">
                    <h3>Reel Views</h3>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={viewsData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
                            <XAxis dataKey="date" stroke="#a0a0b0" fontSize={12} />
                            <YAxis stroke="#a0a0b0" fontSize={12} />
                            <Tooltip
                                contentStyle={{ background: '#1a1a24', border: '1px solid #2a2a3a', borderRadius: 8 }}
                                labelStyle={{ color: '#fff' }}
                                formatter={(value) => value.toLocaleString()}
                            />
                            <Bar dataKey="value" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                <div className="chart-card">
                    <h3>Content Type Comparison</h3>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={contentTypeChartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
                            <XAxis dataKey="type" stroke="#a0a0b0" fontSize={12} />
                            <YAxis stroke="#a0a0b0" fontSize={12} tickFormatter={(value) => formatPercentFromRatio(value)} />
                            <Tooltip
                                contentStyle={{ background: '#1a1a24', border: '1px solid #2a2a3a', borderRadius: 8 }}
                                labelStyle={{ color: '#fff' }}
                                formatter={(value, name, item) => {
                                    if (name === 'avgEngagement') {
                                        return [formatPercentFromRatio(value), `Avg Engagement (${item?.payload?.count ?? 0} posts)`]
                                    }
                                    return [value, name]
                                }}
                            />
                            <Bar dataKey="avgEngagement" fill="#3b82f6" radius={[6, 6, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                <div className="chart-card">
                    <h3>Best Posting Times</h3>
                    <div
                        style={{
                            display: 'grid',
                            gridTemplateColumns: `90px repeat(${bestPostingHeatmap.hours.length}, minmax(48px, 1fr))`,
                            gap: '0.45rem',
                            alignItems: 'center'
                        }}
                    >
                        <div></div>
                        {bestPostingHeatmap.hours.map((hour) => (
                            <div key={hour} style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', textAlign: 'center' }}>
                                {`${hour}:00`}
                            </div>
                        ))}
                        {bestPostingHeatmap.grid.map((row) => (
                            <Fragment key={row.day}>
                                <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>{row.day}</div>
                                {row.cells.map((cell) => (
                                    <div
                                        key={`${row.day}-${cell.hour}`}
                                        title={`${row.day} ${cell.hour}:00 - ${formatPercentFromRatio(cell.value)}`}
                                        style={{
                                            height: '44px',
                                            borderRadius: '12px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            fontSize: '0.75rem',
                                            color: cell.intensity > 0.55 ? '#f8fafc' : 'var(--text-secondary)',
                                            border: '1px solid rgba(255,255,255,0.06)',
                                            background: `rgba(59, 130, 246, ${0.12 + cell.intensity * 0.6})`
                                        }}
                                    >
                                        {cell.value > 0 ? `${(cell.value * 100).toFixed(1)}%` : '-'}
                                    </div>
                                ))}
                            </Fragment>
                        ))}
                    </div>
                </div>
            </div>

            <div
                className="posts-section"
                style={{
                    marginTop: '1.5rem',
                    padding: '1px',
                    background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.9), rgba(59, 130, 246, 0.85), rgba(139, 92, 246, 0.85))'
                }}
            >
                <div
                    style={{
                        borderRadius: '23px',
                        background: 'linear-gradient(180deg, rgba(16, 19, 28, 0.98), rgba(11, 13, 20, 0.98))',
                        padding: '1.4rem'
                    }}
                >
                    <div className="posts-feed-header">
                        <div>
                            <h3>AI Action Plan</h3>
                            <p className="posts-feed-subtitle">RAG-assisted strategic next steps for growth and execution.</p>
                        </div>
                    </div>
                    <ul style={{ margin: 0, paddingLeft: '1.1rem', color: 'var(--text-primary)', lineHeight: 1.8 }}>
                        {actionPlanItems.length ? actionPlanItems.map((item, index) => (
                            <li key={`${item}-${index}`}>{item}</li>
                        )) : (
                            <li>No action plan strategies available yet.</li>
                        )}
                    </ul>
                </div>
            </div>

            {/* Post Listing View */}
            <div className="posts-section">
                <div className="posts-feed-header">
                    <div>
                        <h3>Post Listing View</h3>
                        <p className="posts-feed-subtitle">Browse every post with performance signals and AI context.</p>
                    </div>
                    <label className="posts-sort-control">
                        <span>Sort by</span>
                        <select value={postSort} onChange={(event) => setPostSort(event.target.value)}>
                            <option value="date">Date</option>
                            <option value="views">Views</option>
                            <option value="engagement">Engagement Rate</option>
                        </select>
                    </label>
                </div>

                <div className="posts-feed">
                    {sortedPosts.map((post) => {
                        const previewText = truncateText(post.caption_text || post.insights?.[0], 80)
                        const aiSignalLabel = post.ai_signal || post.insights?.[0]
                        const isAnalyzing = analyzingPostId === post.post_id

                        return (
                            <div
                                key={post.post_id}
                                className="post-card"
                                onClick={() => handleOpenPost(post)}
                                onKeyDown={(event) => {
                                    if (event.key === 'Enter' || event.key === ' ') {
                                        event.preventDefault()
                                        handleOpenPost(post)
                                    }
                                }}
                                role="button"
                                tabIndex={0}
                                aria-busy={isAnalyzing}
                            >
                                <div className="post-card-media">
                                    {post.media_url ? (
                                        <img
                                            className="post-card-thumbnail"
                                            src={post.media_url}
                                            alt={post.caption_text || `Post ${post.post_id}`}
                                        />
                                    ) : (
                                        <div className="post-card-thumbnail-fallback">No preview</div>
                                    )}
                                </div>

                                <div className="post-card-body">
                                    <div className="post-card-topline">
                                        <span className="post-card-date">{formatPostDate(post.published_at || post.timestamp)}</span>
                                        {isAnalyzing ? (
                                            <span className="post-ai-signal-badge">
                                                Loading AI...
                                            </span>
                                        ) : aiSignalLabel ? (
                                            <span className="post-ai-signal-badge">
                                                AI Signal
                                            </span>
                                        ) : null}
                                    </div>

                                    <p className="post-card-caption">{previewText}</p>

                                    <div className="post-card-metrics">
                                        <div className="post-card-metric">
                                            <span className="post-card-metric-label">Views</span>
                                            <strong>{formatCompactNumber(post.views)}</strong>
                                        </div>
                                        <div className="post-card-metric">
                                            <span className="post-card-metric-label">Engagement</span>
                                            <strong>{formatEngagementPercent(post.engagement_rate_by_views)}</strong>
                                        </div>
                                        <div className="post-card-metric">
                                            <span className="post-card-metric-label">Likes</span>
                                            <strong>{formatCompactNumber(post.likes)}</strong>
                                        </div>
                                        <div className="post-card-metric">
                                            <span className="post-card-metric-label">Comments</span>
                                            <strong>{formatCompactNumber(post.comments)}</strong>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>
            </div>
        </div>
    )
}

export default Dashboard


