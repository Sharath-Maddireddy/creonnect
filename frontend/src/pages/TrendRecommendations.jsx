import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

// ─── API helpers ──────────────────────────────────────────────────────────────
// All calls go through Vite proxy (/api → http://localhost:8000)
// Auth is via session cookie (set by Instagram OAuth), sent automatically.

function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

function buildScript(trend, rec) {
    const title = rec?.suggested_title || trend?.topic_name || 'Trend idea'
    const why = rec?.rationale || trend?.description || 'This idea fits your current trend opportunity.'
    return [
        `Hook: ${title}`,
        `Scene 1: Open with the problem or moment your audience already recognizes.`,
        `Scene 2: Show the trend angle: ${trend?.topic_name || 'the selected trend'}.`,
        `Scene 3: Add your proof, example, or personal take.`,
        `CTA: Ask viewers to save, comment, or share their version.`,
        `Why it works: ${why}`,
    ].join('\n')
}

function buildCaption(trend, rec) {
    const title = rec?.suggested_title || trend?.topic_name || 'New content idea'
    const impact = rec?.expected_impact || 'Designed to improve discovery and engagement.'
    const tag = trend?.trend_type ? `#${trend.trend_type}` : '#contentideas'
    return `${title}\n\n${impact}\n\nTry this format this week and track saves, shares, and comments.\n\n${tag} #creatoreconomy #trendstrategy`
}

function buildAssistantReply(prompt, data) {
    const text = (prompt || '').trim()
    const niche = data?.niche?.primary_category || 'your niche'
    const trends = data?.global_trends || []
    const recs = data?.recommendations || []
    const firstTrend = trends[0]?.topic_name || 'an evergreen trend'
    if (!text) {
        return 'Ask a specific question about hooks, captions, formats, or content gaps.'
    }
    if (text.toLowerCase().includes('hook')) {
        return `Try these hooks for ${niche}: 1. "Nobody tells you this about ${firstTrend}." 2. "I tested this ${niche} trend so you do not have to." 3. "Save this before you make your next post."`
    }
    if (text.toLowerCase().includes('without showing face')) {
        return `Use hands-only demos, screen recordings, text overlays, POV b-roll, and before/after frames. Anchor the idea around ${firstTrend}.`
    }
    if (text.toLowerCase().includes('carousel')) {
        return `Carousel structure: Slide 1 hook, Slide 2 common mistake, Slide 3 quick framework, Slide 4 example, Slide 5 checklist, Slide 6 CTA to save.`
    }
    const topRec = recs[0]?.suggested_title || firstTrend
    return `For ${niche}, start with "${topRec}". Keep the post specific, show one clear example, and use the CTA from the recommendation card.`
}

// ─── Data Maps ────────────────────────────────────────────────────────────────
const MOMENTUM = {
    rising:  { label: 'Rising',  emoji: '🚀', cls: 'rising'  },
    peaking: { label: 'Peaking', emoji: '🔥', cls: 'peaking' },
    falling: { label: 'Falling', emoji: '📉', cls: 'falling' },
}
const TREND_TYPE = {
    topic:   { label: 'Topic',   icon: '💡', cls: 'topic'   },
    format:  { label: 'Format',  icon: '🎬', cls: 'format'  },
    audio:   { label: 'Audio',   icon: '🎵', cls: 'audio'   },
    hashtag: { label: 'Hashtag', icon: '#️⃣',  cls: 'hashtag' },
}
const NAV_SECTIONS = [
    {
        title: 'CORE',
        items: [
            { icon: '▦',  label: 'Overview',        path: '/analytics'             },
            { icon: '📊', label: 'Analytics',        path: '/analytics'             },
            { icon: '✨', label: 'AI Post Insights',  path: '/analytics'             },
            { icon: '👤', label: 'Account Analysis',  path: '/account-analysis-demo' },
        ]
    },
    {
        title: 'AI STUDIO',
        items: [
            { icon: '📈', label: 'Trend Recommendations', path: '/trends', active: true },
            { icon: '🎯', label: 'Brand Campaigns',        path: '/brand/campaign'       },
        ]
    }
]

// ─── Score Gauge (SVG) ────────────────────────────────────────────────────────
function ScoreGauge({ score, label, color = '#8b5cf6' }) {
    const [animated, setAnimated] = useState(0)
    const radius = 52
    const circ = Math.PI * radius

    useEffect(() => {
        let id = 0, start = 0
        const tick = (ts) => {
            if (!start) start = ts
            const r = Math.min(1, (ts - start) / 900)
            const e = 1 - Math.pow(1 - r, 3)
            setAnimated(Math.round(score * e))
            if (r < 1) id = requestAnimationFrame(tick)
        }
        id = requestAnimationFrame(tick)
        return () => cancelAnimationFrame(id)
    }, [score])

    const progress = circ - (animated / 100) * circ

    return (
        <div className="cs-gauge">
            <svg viewBox="0 0 140 90" className="cs-gauge__svg">
                <defs>
                    <linearGradient id={`g-${label}`} x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#10b981" />
                        <stop offset="55%" stopColor="#3b82f6" />
                        <stop offset="100%" stopColor="#8b5cf6" />
                    </linearGradient>
                </defs>
                <path className="cs-gauge__track" d="M 18 78 A 52 52 0 0 1 122 78" pathLength="100" />
                <path
                    className="cs-gauge__fill"
                    d="M 18 78 A 52 52 0 0 1 122 78"
                    stroke={`url(#g-${label})`}
                    strokeDasharray={circ}
                    strokeDashoffset={progress}
                />
                <text x="70" y="70" textAnchor="middle" className="cs-gauge__num">{animated}</text>
                <text x="70" y="82" textAnchor="middle" className="cs-gauge__sub">/100</text>
            </svg>
            {label && <span className="cs-gauge__label">{label}</span>}
        </div>
    )
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────
function Sidebar({ account }) {
    const navigate = useNavigate()
    return (
        <aside className="cs-sidebar">
            <div className="cs-sidebar__logo">
                <div className="cs-sidebar__logo-mark">CN</div>
                <span className="cs-sidebar__logo-text">CREONNECT</span>
            </div>

            <nav className="cs-sidebar__nav">
                {NAV_SECTIONS.map(sec => (
                    <div key={sec.title} className="cs-sidebar__section">
                        <span className="cs-sidebar__section-title">{sec.title}</span>
                        {sec.items.map(item => (
                            <button
                                key={item.label}
                                className={`cs-sidebar__item${item.active ? ' cs-sidebar__item--active' : ''}`}
                                onClick={() => navigate(item.path)}
                            >
                                <span className="cs-sidebar__item-icon">{item.icon}</span>
                                <span>{item.label}</span>
                                {item.active && <span className="cs-sidebar__new-badge">New</span>}
                            </button>
                        ))}
                    </div>
                ))}
            </nav>

            {account && (
                <div className="cs-sidebar__footer">
                    <span className="cs-sidebar__ig-icon">📷</span>
                    <span className="cs-sidebar__ig-handle">@{account}</span>
                </div>
            )}
        </aside>
    )
}

// ─── Opportunity Banner ───────────────────────────────────────────────────────
function OpportunityBanner({ niche, opportunityBullets, onRefresh, busy }) {
    const score = niche ? Math.round((niche.confidence_score || 0.7) * 100) : 0
    // Use real opportunity_bullets from backend, fallback to niche-based insights
    const insights = (opportunityBullets && opportunityBullets.length > 0)
        ? opportunityBullets.slice(0, 4)
        : niche ? [
            `Primary niche: ${niche.primary_category}`,
            ...(niche.sub_niches || []).slice(0, 3).map(s => `${s} content is trending in your space`),
            'Live trends matched to your strengths',
        ] : []

    return (
        <div className="cs-banner">
            <div className="cs-banner__icon-wrap">
                <div className="cs-banner__icon">📈</div>
            </div>
            <div className="cs-banner__body">
                <div className="cs-banner__title-row">
                    <h2 className="cs-banner__title">AI Weekly Opportunity</h2>
                    <span className="cs-banner__badge">Beta</span>
                </div>
                <p className="cs-banner__sub">
                    {niche
                        ? `Based on your last 30 posts, we've identified ${Math.max(3, (niche.sub_niches?.length || 0) + 3)} high-opportunity content ideas for this week.`
                        : 'Enter your account ID above to generate personalised trend recommendations powered by live AI analysis.'}
                </p>
                <div className="cs-banner__bullets">
                    {insights.map((ins, i) => (
                        <div key={i} className={`cs-banner__bullet cs-banner__bullet--${i === 0 ? 'green' : i === 1 ? 'blue' : 'yellow'}`}>
                            <span className="cs-banner__bullet-dot" />
                            {ins}
                        </div>
                    ))}
                </div>
            </div>
            <div className="cs-banner__right">
                {niche ? (
                    <>
                        <ScoreGauge score={score} label="Opportunity Score" />
                        <p className="cs-banner__score-label">
                            {score >= 80 ? 'Very High' : score >= 60 ? 'High' : 'Moderate'}
                        </p>
                        <button className="cs-generate-btn" onClick={onRefresh} disabled={busy}>
                            {busy ? 'Analysing…' : 'Generate Weekly Plan →'}
                        </button>
                    </>
                ) : (
                    <div className="cs-banner__empty-art">✨</div>
                )}
            </div>
        </div>
    )
}

// ─── Filter Tabs ──────────────────────────────────────────────────────────────
const FILTER_TABS = ['All', 'Reels', 'Carousel', 'Photo', 'Trending', 'Educational', 'Personal Story', 'Brand Friendly', 'Beginner', 'Advanced']

function FilterTabs({ active, onChange }) {
    return (
        <div className="cs-filters">
            {FILTER_TABS.map(tab => (
                <button
                    key={tab}
                    className={`cs-filter-tab${active === tab ? ' cs-filter-tab--active' : ''}`}
                    onClick={() => onChange(tab)}
                >
                    {tab}
                </button>
            ))}
        </div>
    )
}

// ─── Trend + Rec combined card ─────────────────────────────────────────────────
function SuggestionCard({ trend, rec, index, saved, onToggleSave, onGenerate }) {
    const m = MOMENTUM[trend?.momentum] || MOMENTUM.rising
    const t = TREND_TYPE[trend?.trend_type] || TREND_TYPE.topic
    // Use real opportunity_score from backend, fallback to momentum-based
    const scoreVal = rec?.opportunity_score ?? (trend?.momentum === 'peaking' ? 92 : trend?.momentum === 'rising' ? 78 : 55)
    const difficultyMap = { Easy: { label: 'Easy', cls: 'easy' }, Medium: { label: 'Medium', cls: 'medium' }, Hard: { label: 'Hard', cls: 'hard' } }
    const diff = difficultyMap[rec?.difficulty] || null
    const contentStyle = rec?.content_style || t.label
    return (
        <div className="cs-card">
            {/* Left thumbnail */}
            <div className="cs-card__thumb">
                <div className={`cs-card__thumb-inner cs-card__thumb-inner--${t.cls}`}>
                    <span className="cs-card__thumb-icon">{t.icon}</span>
                </div>
            </div>

            {/* Main body */}
            <div className="cs-card__body">
                <div className="cs-card__top">
                    <span className={`cs-pot-badge cs-pot-badge--${m.cls}`}>
                        {m.emoji} {m.label} Potential
                    </span>
                </div>
                <h3 className="cs-card__title">
                    {rec?.suggested_title || trend?.topic_name}
                </h3>
                <div className="cs-card__tags">
                    <span className={`cs-tag cs-tag--${t.cls}`}>{t.icon} {contentStyle}</span>
                    {(trend?.topic_name) && <span className="cs-tag cs-tag--neutral">{trend.topic_name}</span>}
                    {rec?.trend_reference && rec.trend_reference !== trend?.topic_name && (
                        <span className="cs-tag cs-tag--neutral">{rec.trend_reference}</span>
                    )}
                </div>
                {rec?.hook && (
                    <p className="cs-card__hook">
                        <strong>Hook:</strong> "{rec.hook}"
                    </p>
                )}
                {rec?.rationale && !rec?.hook && (
                    <p className="cs-card__hook">
                        <strong>Why:</strong> {rec.rationale.slice(0, 120)}{rec.rationale.length > 120 ? '…' : ''}
                    </p>
                )}
                {trend?.description && (
                    <p className="cs-card__desc">{trend.description.slice(0, 100)}{trend.description.length > 100 ? '…' : ''}</p>
                )}
            </div>

            {/* Stats col */}
            <div className="cs-card__stats">
                {rec?.expected_reach_min != null && rec?.expected_reach_max != null && (
                    <div className="cs-stat">
                        <span className="cs-stat__label">Expected Reach</span>
                        <span className="cs-stat__score">{(rec.expected_reach_min / 1000).toFixed(0)}K – {(rec.expected_reach_max / 1000).toFixed(0)}K</span>
                    </div>
                )}
                <div className="cs-stat">
                    <span className="cs-stat__label">Opportunity Score</span>
                    <div className="cs-stat__score-row">
                        <span className="cs-stat__score">{Math.round(scoreVal)} / 100</span>
                    </div>
                    <div className="cs-stat__bar-bg">
                        <div className="cs-stat__bar-fill" style={{ width: `${scoreVal}%` }} />
                    </div>
                    <span className={`cs-stat__band cs-stat__band--${m.cls}`}>
                        {m.emoji} {scoreVal >= 85 ? 'Very High' : scoreVal >= 70 ? 'High' : 'Moderate'}
                    </span>
                </div>
                {rec?.best_time && (
                    <div className="cs-stat">
                        <span className="cs-stat__label">Best Time</span>
                        <span className="cs-stat__val">{rec.best_time}</span>
                    </div>
                )}
                {diff && (
                    <div className="cs-stat">
                        <span className="cs-stat__label">Difficulty</span>
                        <span className={`cs-stat__band cs-stat__band--${diff.cls}`}>{diff.label}</span>
                    </div>
                )}
                <div className="cs-stat">
                    <span className="cs-stat__label">Content Type</span>
                    <span className="cs-stat__val">{contentStyle}</span>
                </div>
            </div>

            {/* Actions col */}
            <div className="cs-card__actions">
                <button className="cs-action-btn cs-action-btn--primary" onClick={() => onGenerate('script', trend, rec)}>✨ Generate Script</button>
                <button className="cs-action-btn cs-action-btn--ghost" onClick={() => onGenerate('caption', trend, rec)}>📝 Generate Caption</button>
                <button
                    className={`cs-action-btn cs-action-btn--save${saved ? ' cs-action-btn--saved' : ''}`}
                    onClick={() => onToggleSave(trend, rec)}
                >
                    {saved ? '✅ Saved' : '🔖 Save Idea'}
                </button>
            </div>
        </div>
    )
}

// ─── Right Panel ──────────────────────────────────────────────────────────────
function RightPanel({ niche, trends, data, onShowAllTrends, onShowContentGaps, assistantPrompt, setAssistantPrompt, assistantReply, onAskAI }) {
    // Use real audience_match_pct from backend, fallback to positional scoring
    const trendingTopics = trends?.slice(0, 3).map((t, i) => ({
        name: t.topic_name,
        match: t.audience_match_pct ?? (98 - i * 8),
        momentum: t.momentum,
    })) || []

    const dailyInsights = data?.daily_insights
    const contentGaps = data?.content_gaps || []

    return (
        <aside className="cs-right">
            {/* Today's Insights */}
            {dailyInsights && (
                <div className="cs-right-card">
                    <div className="cs-right-card__header">
                        <span className="cs-right-card__title">Today's Insights</span>
                    </div>
                    <div className="cs-insights-grid">
                        {dailyInsights.audience_active_window && (
                            <div className="cs-insight-item">
                                <span className="cs-insight-label">Audience Active</span>
                                <span className="cs-insight-value">{dailyInsights.audience_active_window}</span>
                            </div>
                        )}
                        {dailyInsights.best_content_type && (
                            <div className="cs-insight-item">
                                <span className="cs-insight-label">Best Content Type</span>
                                <span className="cs-insight-value">{dailyInsights.best_content_type}</span>
                            </div>
                        )}
                        {dailyInsights.trending_audio_count != null && (
                            <div className="cs-insight-item">
                                <span className="cs-insight-label">Trending Audio</span>
                                <span className="cs-insight-value">{dailyInsights.trending_audio_count}</span>
                            </div>
                        )}
                        {dailyInsights.competition_level && (
                            <div className="cs-insight-item">
                                <span className="cs-insight-label">Competition</span>
                                <span className={`cs-insight-badge cs-insight-badge--${dailyInsights.competition_level.toLowerCase()}`}>{dailyInsights.competition_level}</span>
                            </div>
                        )}
                        {dailyInsights.overall_opportunity && (
                            <div className="cs-insight-item">
                                <span className="cs-insight-label">Overall Opportunity</span>
                                <span className={`cs-insight-badge cs-insight-badge--${dailyInsights.overall_opportunity.toLowerCase().replace(' ', '-')}`}>{dailyInsights.overall_opportunity}</span>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Pipeline Status */}
            <div className="cs-right-card">
                <div className="cs-right-card__header">
                    <span className="cs-right-card__title">Analysis Pipeline</span>
                </div>
                <div className="cs-pipeline">
                    {[
                        { label: 'Niche Discovery', done: !!niche },
                        { label: 'Trend Fetching',  done: !!(trends?.length) },
                        { label: 'Recommendations', done: !!(data?.recommendations?.length) },
                    ].map((s, i) => (
                        <div key={s.label} className="cs-pipeline__step">
                            <div className={`cs-pipeline__dot${s.done ? ' cs-pipeline__dot--done' : ''}`} />
                            <div className="cs-pipeline__step-info">
                                <span className="cs-pipeline__step-label">{s.label}</span>
                                <span className={`cs-pipeline__step-status${s.done ? ' cs-pipeline__step-status--done' : ''}`}>
                                    {s.done ? '✓ Complete' : '—'}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Niche Insights */}
            {niche && (
                <div className="cs-right-card">
                    <div className="cs-right-card__header">
                        <span className="cs-right-card__title">Niche Detected</span>
                    </div>
                    <div className="cs-niche-summary">
                        <p className="cs-niche-summary__cat">{niche.primary_category}</p>
                        <div className="cs-niche-summary__tags">
                            {(niche.sub_niches || []).map(n => (
                                <span key={n} className="cs-mini-tag">{n}</span>
                            ))}
                        </div>
                        <div className="cs-niche-summary__conf-row">
                            <span className="cs-right-label">Confidence</span>
                            <span className="cs-niche-summary__conf-val" style={{ color: '#10b981' }}>
                                {Math.round((niche.confidence_score || 0) * 100)}%
                            </span>
                        </div>
                        <div className="cs-mini-bar-bg">
                            <div className="cs-mini-bar-fill" style={{ width: `${Math.round((niche.confidence_score || 0) * 100)}%` }} />
                        </div>
                    </div>
                </div>
            )}

            {/* Trending Topics */}
            {trendingTopics.length > 0 && (
                <div className="cs-right-card">
                    <div className="cs-right-card__header">
                        <span className="cs-right-card__title">Trending Topics</span>
                        <button className="cs-right-card__link" onClick={onShowAllTrends}>View All</button>
                    </div>
                    <div className="cs-trending-list">
                        {trendingTopics.map((t, i) => (
                            <div key={t.name} className="cs-trending-item">
                                <div className="cs-trending-item__thumb" style={{
                                    background: ['linear-gradient(135deg,#3b82f6,#8b5cf6)', 'linear-gradient(135deg,#10b981,#3b82f6)', 'linear-gradient(135deg,#f59e0b,#ef4444)'][i]
                                }}>
                                    {['🌊', '💎', '✈️'][i] || '🔥'}
                                </div>
                                <div className="cs-trending-item__body">
                                    <span className="cs-trending-item__name">{t.name}</span>
                                    <span className="cs-trending-item__match">{Math.round(t.match)}% Audience Match</span>
                                </div>
                                <div className="cs-trending-item__spark">
                                    <svg viewBox="0 0 40 20" className="cs-sparkline">
                                        <polyline
                                            points={t.momentum === 'rising' ? '0,16 10,12 20,8 30,4 40,2' : t.momentum === 'peaking' ? '0,10 10,6 20,4 30,6 40,10' : '0,4 10,8 20,12 30,14 40,16'}
                                            fill="none"
                                            stroke={t.momentum === 'falling' ? '#ef4444' : '#10b981'}
                                            strokeWidth="2"
                                        />
                                    </svg>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Content Gaps — now from backend */}
            {contentGaps.length > 0 && (
                <div className="cs-right-card">
                    <div className="cs-right-card__header">
                        <span className="cs-right-card__title">Content Gaps</span>
                        <button className="cs-right-card__link" onClick={onShowContentGaps}>View All</button>
                    </div>
                    <div className="cs-gaps">
                        {contentGaps.slice(0, 3).map((gap, i) => (
                            <div key={i} className="cs-gap">
                                <span className={`cs-gap__icon cs-gap__icon--${gap.severity || 'info'}`}>
                                    {gap.severity === 'warning' ? '⚠️' : gap.severity === 'opportunity' ? '💡' : 'ℹ️'}
                                </span>
                                <span>{gap.description}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Ask AI */}
            <div className="cs-right-card cs-ask-ai">
                <div className="cs-ask-ai__header">
                    <span className="cs-right-card__title">Ask AI Assistant</span>
                    <span className="cs-banner__badge">Beta</span>
                </div>
                <p className="cs-ask-ai__sub">Need custom ideas? Describe what you want to post about.</p>
                <div className="cs-ask-ai__input-wrap">
                    <input
                        className="cs-ask-ai__input"
                        placeholder="e.g. Give me 10 viral trend ideas…"
                        value={assistantPrompt}
                        onChange={e => setAssistantPrompt(e.target.value)}
                        onKeyDown={e => {
                            if (e.key === 'Enter') {
                                onAskAI(assistantPrompt)
                            }
                        }}
                    />
                    <button className="cs-ask-ai__send" onClick={() => onAskAI(assistantPrompt)}>➤</button>
                </div>
                <div className="cs-ask-ai__chips">
                    {['Give me viral hooks', 'Ideas without showing face', 'Educational carousel ideas'].map(c => (
                        <button key={c} className="cs-chip" onClick={() => onAskAI(c)}>{c}</button>
                    ))}
                </div>
                {assistantReply && (
                    <p className="cs-ask-ai__reply">{assistantReply}</p>
                )}
            </div>
        </aside>
    )
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function TrendRecommendations() {
    const [accountInput, setAccountInput] = useState('')
    const [accountId,    setAccountId]    = useState('')
    const [data,         setData]         = useState(null)
    const [loading,      setLoading]      = useState(false)
    const [error,        setError]        = useState(null)
    const [queued,       setQueued]       = useState(false)
    const [jobId,        setJobId]        = useState(null)
    const [polling,      setPolling]      = useState(false)
    const [activeFilter, setActiveFilter] = useState('All')
    const [sortMode,     setSortMode]     = useState('Opportunity')
    const [visibleCount, setVisibleCount] = useState(5)
    const [savedIdeas,   setSavedIdeas]   = useState(() => {
        try {
            return JSON.parse(localStorage.getItem('trend_saved_ideas') || '[]')
        } catch (_) {
            return []
        }
    })
    const [generated, setGenerated] = useState(null)
    const [assistantPrompt, setAssistantPrompt] = useState('')
    const [assistantReply, setAssistantReply] = useState('')
    const [showContentGaps, setShowContentGaps] = useState(false)

    // ── On mount: load user_id from localStorage (set by Dashboard/OAuth flow) ──
    useEffect(() => {
        const storedUserId = localStorage.getItem('user_id') || ''
        if (storedUserId) {
            setAccountInput(storedUserId)
            setAccountId(storedUserId)
                        fetchExisting(storedUserId)
        }
    }, []) // eslint-disable-line react-hooks/exhaustive-deps

    // triggerRefresh defined FIRST to avoid stale closure in fetchExisting
    const triggerRefresh = useCallback(async (id) => {
                setError(null); setLoading(true); setQueued(false); setJobId(null); setData(null)
        try {
            const res = await fetch(`/api/v1/accounts/${encodeURIComponent(id)}/trends/refresh?count=5`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            })
            if (res.status === 401) {
                setError('Not authenticated. Please log in from the Dashboard first.')
                return
            }
            const json = await res.json()
            if (!res.ok) throw new Error(json.detail || `Error ${res.status}`)

            if (json.status === 'queued' && json.job_id) {
                // Rate-limited: backend queued a background job
                setQueued(true); setJobId(json.job_id)
            } else {
                // Synchronous result returned directly
                setData(json)
                setVisibleCount(3)
            }
        } catch (e) { setError(e.message) }
        finally { setLoading(false) }
    }, [])

    const fetchExisting = useCallback(async (id) => {
        setError(null); setLoading(true)
        try {
            // credentials:'include' sends session cookie for authentication
            const res = await fetch(`/api/v1/accounts/${encodeURIComponent(id)}/trends`, {
                credentials: 'include',
            })
            if (res.status === 401) {
                setError('Not authenticated. Please log in from the Dashboard first.')
                return
            }
            if (res.ok) {
                const json = await res.json()
                // Handle both direct TrendAnalysisResult and queued response
                if (json.status === 'queued' && json.job_id) {
                    setQueued(true); setJobId(json.job_id)
                } else {
                    setData(json)
                    setVisibleCount(3)
                }
            } else if (res.status === 404) {
                // No stored result — trigger a refresh automatically
                setLoading(false)  // release loading before refresh sets it again
                await triggerRefresh(id)
            } else {
                const err = await res.json().catch(() => ({}))
                throw new Error(err.detail || `Server error ${res.status}`)
            }
        } catch (e) {
            setError(e.message)
        } finally {
            setLoading(false)
        }
    }, [triggerRefresh]) // eslint-disable-line react-hooks/exhaustive-deps

        // ── Poll background job until finished ───────────────────────────────────
    useEffect(() => {
        if (!jobId || !queued) return
        let cancelled = false
        setPolling(true)
        ;(async () => {
                        for (let i = 0; i < 90; i++) {  // poll for up to 7.5 minutes (90 x 5s)
                await sleep(5000)
                if (cancelled) break  // check after sleep to prevent fetch on unmounted component
                try {
                    const res = await fetch(
                        `/api/v1/accounts/${encodeURIComponent(accountId)}/trends/job/${encodeURIComponent(jobId)}`,
                        { credentials: 'include' }
                    )
                    if (!res.ok) continue
                    const json = await res.json()
                    // Backend returns: {status: 'finished'|'failed'|'queued'|'processing', result?:{}}
                    if (json.status === 'finished' || json.status === 'completed') {
                        setData(json.result ?? json)
                        setVisibleCount(3)
                        setQueued(false); setJobId(null)
                        break
                    }
                    if (json.status === 'failed') {
                        setError(json.error || 'Background analysis failed. Please try refreshing.')
                        setQueued(false)
                        break
                    }
                } catch (_) { /* network error while polling — retry next iteration */ }
            }
            setPolling(false)
        })()
        return () => { cancelled = true }
    }, [jobId, queued, accountId])

    function handleSearch(e) {
        e.preventDefault()
        const id = accountInput.trim()
        if (!id) return
        setAccountId(id)
        // Always try GET first; it auto-falls-through to refresh if no DB result
        fetchExisting(id)
    }

    const busy = loading || polling

    // Filter suggestions
    const allCards = (() => {
        const trends = data?.global_trends || []
        const recs   = data?.recommendations || []
        const cards  = trends.map((t, i) => ({ trend: t, rec: recs[i] || null }))
        const filtered = activeFilter === 'All' ? cards : cards.filter(c => {
            const m = c.trend?.momentum || ''
            const typ = c.trend?.trend_type || ''
            const style = (c.rec?.content_style || '').toLowerCase()
            const diff = (c.rec?.difficulty || '').toLowerCase()
            const filterLower = activeFilter.toLowerCase()
            return (
                filterLower === m ||
                filterLower === typ ||
                style.includes(filterLower) ||
                diff === filterLower ||
                (filterLower === 'trending' && m === 'rising') ||
                (filterLower === 'reels' && typ === 'format') ||
                (filterLower === 'photo' && typ === 'topic')
            )
        })
        return [...filtered].sort((left, right) => {
            if (sortMode === 'Momentum') {
                const order = { peaking: 3, rising: 2, falling: 1 }
                return (order[right.trend?.momentum] || 0) - (order[left.trend?.momentum] || 0)
            }
            if (sortMode === 'Opportunity') {
                return (right.rec?.opportunity_score || 0) - (left.rec?.opportunity_score || 0)
            }
            if (sortMode === 'Reach') {
                return (right.rec?.expected_reach_max || 0) - (left.rec?.expected_reach_max || 0)
            }
            if (sortMode === 'Type') {
                return String(left.trend?.trend_type || '').localeCompare(String(right.trend?.trend_type || ''))
            }
            return 0
        })
    })()
    const visibleCards = allCards.slice(0, visibleCount)

    const niche  = data?.niche
    const trends = data?.global_trends || []

    function ideaKey(trend, rec) {
        return `${trend?.topic_name || 'trend'}::${rec?.suggested_title || ''}`
    }

    function toggleSave(trend, rec) {
        const key = ideaKey(trend, rec)
        setSavedIdeas(prev => {
            const exists = prev.some(item => item.key === key)
            const next = exists
                ? prev.filter(item => item.key !== key)
                : [...prev, { key, trend, rec, saved_at: new Date().toISOString() }]
            localStorage.setItem('trend_saved_ideas', JSON.stringify(next))
            return next
        })
    }

    function handleGenerate(kind, trend, rec) {
        setGenerated({
            kind,
            title: kind === 'script' ? 'Generated Script' : 'Generated Caption',
            body: kind === 'script' ? buildScript(trend, rec) : buildCaption(trend, rec),
        })
    }

    function handleAskAI(prompt) {
        setAssistantPrompt(prompt)
        setAssistantReply(buildAssistantReply(prompt, data))
    }

    return (
        <>
            <div className="cs-layout">
                <Sidebar account={accountId || null} />

                <div className="cs-main">
                    {/* ── Top bar ── */}
                    <div className="cs-topbar">
                        <div className="cs-topbar__left">
                            <h1 className="cs-topbar__title">Content Suggestions <span>✨</span></h1>
                            <p className="cs-topbar__sub">AI powered trend recommendations personalised for your audience</p>
                        </div>
                        <form className="cs-topbar__search" onSubmit={handleSearch}>
                            <span className="cs-topbar__search-icon">🔍</span>
                            <input
                                className="cs-topbar__search-input"
                                placeholder="Search creator account ID…"
                                value={accountInput}
                                onChange={e => setAccountInput(e.target.value)}
                                disabled={busy}
                            />
                            <kbd className="cs-topbar__kbd">⌘ K</kbd>
                        </form>
                        <button className="cs-generate-btn" onClick={() => accountId && triggerRefresh(accountId)} disabled={busy}>
                            ✨ {busy ? 'Analysing…' : 'Generate New Ideas'}
                        </button>
                        <button className="cs-topbar__refresh-icon" onClick={() => accountId && fetchExisting(accountId)} disabled={busy} title="Refresh">↻</button>
                    </div>

                    {/* ── Error ── */}
                    {error && (
                        <div className="cs-error-bar">
                            <span>⚠️ {error}</span>
                            <button onClick={() => accountId && fetchExisting(accountId)}>Retry</button>
                        </div>
                    )}

                    {/* ── Loading state ── */}
                    {busy && (
                        <div className="cs-loading-bar">
                            <div className="cs-loading-bar__fill" />
                            <span>{queued ? 'Analysis queued — polling for results…' : 'Running AI pipeline…'}</span>
                        </div>
                    )}

                    {/* ── Opportunity Banner ── */}
                    <OpportunityBanner niche={niche} opportunityBullets={data?.opportunity_bullets} onRefresh={() => accountId && triggerRefresh(accountId)} busy={busy} />

                    {/* ── Filter Tabs + Sort ── */}
                    <div className="cs-filters-row">
                        <FilterTabs active={activeFilter} onChange={setActiveFilter} />
                        <button
                            className="cs-sort"
                            onClick={() => setSortMode(mode => {
                                const modes = ['Opportunity', 'Reach', 'Momentum', 'Type']
                                const idx = modes.indexOf(mode)
                                return modes[(idx + 1) % modes.length]
                            })}
                        >
                            <span className="cs-sort__label">Sort by: {sortMode}</span>
                            <span className="cs-sort__arrow">▼</span>
                        </button>
                    </div>

                    {/* ── Feed header ── */}
                    {data && (
                        <div className="cs-feed-header">
                            <h2 className="cs-feed-header__title">AI Suggestions <span className="cs-feed-header__info">ℹ</span></h2>
                            <p className="cs-feed-header__sub">
                                Personalised ideas with high potential based on your niche &amp; live trends.
                            </p>
                        </div>
                    )}

                    {/* ── Cards ── */}
                    {data && allCards.length === 0 && (
                        <div className="cs-no-results">No trends match this filter. Try "All".</div>
                    )}

                    {visibleCards.map((c, i) => (
                        <SuggestionCard
                            key={`${c.trend?.topic_name || i}-${c.rec?.suggested_title || i}`}
                            trend={c.trend}
                            rec={c.rec}
                            index={i}
                            saved={savedIdeas.some(item => item.key === ideaKey(c.trend, c.rec))}
                            onToggleSave={toggleSave}
                            onGenerate={handleGenerate}
                        />
                    ))}

                    {/* ── Empty/Initial state ── */}
                    {!data && !busy && !error && (
                        <div className="cs-empty">
                            <div className="cs-empty__icon">📈</div>
                            <h2>Discover your content opportunities</h2>
                            <p>Enter a creator account ID in the search bar above to generate AI-powered trend recommendations based on live global trends.</p>
                            <button className="cs-generate-btn" onClick={() => document.querySelector('.cs-topbar__search-input')?.focus()}>
                                Get Started →
                            </button>
                        </div>
                    )}

                    {data && (
                        <button
                            className="cs-load-more"
                            onClick={() => {
                                if (visibleCount < allCards.length) {
                                    setVisibleCount(count => count + 3)
                                } else if (accountId) {
                                    triggerRefresh(accountId)
                                }
                            }}
                        >
                            ↻ {visibleCount < allCards.length ? 'Load More Trends' : 'Refresh Trends'}
                        </button>
                    )}
                </div>

                <RightPanel
                    niche={niche}
                    trends={trends}
                    data={data}
                    onShowAllTrends={() => {
                        setActiveFilter('All')
                        setVisibleCount(99)
                    }}
                    onShowContentGaps={() => setShowContentGaps(true)}
                    assistantPrompt={assistantPrompt}
                    setAssistantPrompt={setAssistantPrompt}
                    assistantReply={assistantReply}
                    onAskAI={handleAskAI}
                />
            </div>

            {/* ── Modals (outside grid so they don't consume grid columns) ── */}
            {generated && (
                <div className="cs-modal-backdrop" onClick={() => setGenerated(null)}>
                    <div className="cs-modal" onClick={event => event.stopPropagation()}>
                        <div className="cs-modal__header">
                            <h3>{generated.title}</h3>
                            <button onClick={() => setGenerated(null)}>×</button>
                        </div>
                        <pre className="cs-modal__body">{generated.body}</pre>
                    </div>
                </div>
            )}

            {showContentGaps && (
                <div className="cs-modal-backdrop" onClick={() => setShowContentGaps(false)}>
                    <div className="cs-modal" onClick={event => event.stopPropagation()}>
                        <div className="cs-modal__header">
                            <h3>Content Gaps</h3>
                            <button onClick={() => setShowContentGaps(false)}>×</button>
                        </div>
                        <div className="cs-modal__body text">
                            {(data?.content_gaps || []).length > 0 ? (
                                data.content_gaps.map((gap, i) => (
                                    <div key={i} className="cs-gap-detail">
                                        <span className={`cs-gap__icon cs-gap__icon--${gap.severity || 'info'}`}>
                                            {gap.severity === 'warning' ? '⚠️' : gap.severity === 'opportunity' ? '💡' : 'ℹ️'}
                                        </span>
                                        <div>
                                            <p><strong>{gap.description}</strong></p>
                                            {gap.suggested_action && <p className="cs-gap-action">{gap.suggested_action}</p>}
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <p>No content gaps detected. Your content strategy looks well-balanced!</p>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </>
    )
}
