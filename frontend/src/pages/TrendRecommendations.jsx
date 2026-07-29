import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import GenerateIdeasModal from '../components/GenerateIdeasModal'
import GenerationProgress from '../components/GenerationProgress'
import ScriptGenerator from '../components/ScriptGenerator'
import CaptionGenerator from '../components/CaptionGenerator'
import ContentPlanner from '../components/ContentPlanner'
import CalendarView from '../components/CalendarView'
import SaveIdeaModal from '../components/SaveIdeaModal'
import MoreOptionsMenu from '../components/MoreOptionsMenu'
import IdeaDetailDrawer from '../components/IdeaDetailDrawer'
import AllTrendingTopics from '../components/AllTrendingTopics'
import AllTrendingAudio from '../components/AllTrendingAudio'

// ─── API helpers ──────────────────────────────────────────────────────────────
// All calls go through Vite proxy (/api → http://localhost:8000)
// Auth is via session cookie (set by Instagram OAuth), sent automatically.

function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

function isPersistedIdeaId(value) {
    if (typeof value !== 'string') return false
    const trimmed = value.trim()
    if (!trimmed) return false
    if (trimmed.startsWith('trend-')) return false
    if (trimmed.startsWith('quick-')) return false
    return true
}

function topicDisplayName(topic, index = 0) {
    const directName = topic?.topic_name || topic?.name || topic?.title || topic?.topic
    if (typeof directName === 'string' && directName.trim()) return directName.trim()

    const description = typeof topic?.description === 'string' ? topic.description.trim() : ''
    if (description) return description.split(/[.!?]/)[0].slice(0, 72)

    return `Trending topic ${index + 1}`
}

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

function buildScriptPreview(trend, rec) {
    const title = rec?.suggested_title || trend?.topic_name || 'Trend idea'
    const hook = rec?.hook || title
    const why = rec?.rationale || trend?.description || 'This idea fits your current trend opportunity.'
    return {
        idea_id: null,
        hook,
        scenes: [
            {
                scene_number: 1,
                time_range: '0-5s',
                description: `Open with a direct hook around "${hook}".`,
                visual_notes: 'Lead with text-on-screen and a fast first beat.',
            },
            {
                scene_number: 2,
                time_range: '5-20s',
                description: `Introduce the trend angle: ${trend?.topic_name || 'the selected trend'}. Share the specific tension, mistake, or opportunity your audience should notice.`,
                visual_notes: 'Use a quick example, screenshot, or demo moment.',
            },
            {
                scene_number: 3,
                time_range: '20-40s',
                description: `Add your proof, example, or personal take and tie it back to "${title}".`,
                visual_notes: 'Show results, a mini case study, or a step-by-step cut.',
            },
        ],
        cta: 'Ask viewers to save this idea and comment with their version.',
        estimated_duration_sec: rec?.duration_seconds || 40,
        full_script: buildScript(trend, rec),
        preview_only: true,
        preview_note: `Quick draft from the recommendation card. Generate Full Ideas or save this idea first to unlock deeper AI actions.`,
    }
}

function buildCaption(trend, rec) {
    const title = rec?.suggested_title || trend?.topic_name || 'New content idea'
    const impact = rec?.expected_impact || 'Designed to improve discovery and engagement.'
    const tag = trend?.trend_type ? `#${trend.trend_type}` : '#contentideas'
    return `${title}\n\n${impact}\n\nTry this format this week and track saves, shares, and comments.\n\n${tag} #creatoreconomy #trendstrategy`
}

function buildCaptionPreview(trend, rec) {
    const captionText = buildCaption(trend, rec)
    const hashtags = captionText
        .split(/\s+/)
        .filter(token => token.startsWith('#'))
        .map(token => token.replace(/[^\w#]/g, ''))
        .filter(Boolean)

    return [{
        platform: 'instagram',
        caption_text: captionText,
        hashtags,
        character_count: captionText.length,
        hashtag_count: hashtags.length,
        tips_applied: ['Matched to the selected trend card', 'Includes a clear CTA', 'Keeps discovery-focused hashtags'],
        preview_only: true,
        preview_note: 'Quick caption draft from the recommendation card.',
    }]
}

function matchesFilter(card, activeFilter) {
    if (activeFilter === 'All') return true

    const trend = card?.trend || {}
    const rec = card?.rec || {}
    const filter = activeFilter.toLowerCase()
    const formatFamily = String(rec.format_family || '').toLowerCase()
    const angleType = String(rec.angle_type || '').toLowerCase()
    const creatorLevel = String(rec.creator_level || '').toLowerCase()
    const isTrending = rec.is_trending === true

    switch (filter) {
        case 'trending':
            return isTrending
        case 'reels':
            return formatFamily === 'reel'
        case 'carousel':
            return formatFamily === 'carousel'
        case 'photo':
            return formatFamily === 'photo'
        case 'educational':
            return angleType === 'educational'
        case 'personal story':
            return angleType === 'personal_story'
        case 'brand friendly':
            return angleType === 'brand_friendly'
        case 'beginner':
            return creatorLevel === 'beginner'
        case 'advanced':
            return creatorLevel === 'advanced'
        default:
            return false
    }
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
            { icon: '▦', label: 'Overview', path: '/analytics' },
            { icon: '⌁', label: 'Analytics', path: '/analytics' },
            { icon: 'ϟ', label: 'AI Post Insights', path: '/analytics' },
            { icon: '⌁', label: 'Account Analysis', path: '/account-analysis-demo' },
        ]
    },
    {
        title: 'TOOLKITS',
        items: [
            { icon: '◉', label: 'Creator Showcase', path: '/analytics' },
            { icon: '↗', label: 'Superlinks', path: '/analytics' },
        ]
    },
    {
        title: 'GROWTH & REVENUE',
        items: [
            { icon: '♙', label: 'Auto DM Flows', path: '/analytics' },
            { icon: '▣', label: 'Digital Store', path: '/analytics' },
            { icon: '□', label: '1:1 Booking', path: '/analytics' },
            { icon: '▱', label: 'Messaging Hub', path: '/analytics' },
            { icon: '◇', label: 'Brand Collaborations', path: '/brand/campaign' },
        ]
    },
    {
        title: 'AI STUDIO',
        items: [
            { icon: '✦', label: 'Content Suggestions', path: '/trends', active: true },
            { icon: '✎', label: 'Caption Generator', path: '/trends' },
            { icon: '▤', label: 'Script Generator', path: '/trends' },
            { icon: '◈', label: 'Brand Pitch Writer', path: '/brand/campaign' },
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
function OpportunityBanner({ niche, weeklyOpportunity, onRefresh, busy, hasAccount }) {
    const score = typeof weeklyOpportunity?.score === 'number' ? weeklyOpportunity.score : null
    const label = weeklyOpportunity?.label || null
    const insights = Array.isArray(weeklyOpportunity?.bullets) ? weeklyOpportunity.bullets.slice(0, 4) : []

    return (
        <div className="cs-banner">
            <div className="cs-banner__icon-wrap">
                <div className="cs-banner__icon">📈</div>
            </div>
            <div className="cs-banner__body">
                <div className="cs-banner__title-row">
                    <h2 className="cs-banner__title">AI Weekly Opportunity</h2>
                </div>
                <p className="cs-banner__sub">
                    {weeklyOpportunity
                        ? `We've identified ${weeklyOpportunity.idea_count} high-opportunity content idea${weeklyOpportunity.idea_count === 1 ? '' : 's'} for this week.`
                        : niche
                        ? 'Your weekly opportunity summary is being prepared from your latest trend analysis.'
                        : 'Search by creator username, @handle, or account ID to generate personalised trend recommendations powered by live AI analysis.'}
                </p>
                {weeklyOpportunity?.summary_reason && (
                    <p className="cs-banner__sub">{weeklyOpportunity.summary_reason}</p>
                )}
                {insights.length > 0 && (
                    <div className="cs-banner__bullets">
                        {insights.map((ins, i) => (
                            <div key={i} className={`cs-banner__bullet cs-banner__bullet--${i === 0 ? 'green' : i === 1 ? 'blue' : 'yellow'}`}>
                                <span className="cs-banner__bullet-dot" />
                                {ins}
                            </div>
                        ))}
                    </div>
                )}
            </div>
            <div className="cs-banner__right">
                {weeklyOpportunity && score !== null ? (
                    <>
                        <ScoreGauge score={score} label="Opportunity Score" />
                        <p className="cs-banner__score-label">{label}</p>
                        <button className="cs-generate-btn" onClick={onRefresh} disabled={busy || !hasAccount} title={!hasAccount ? 'Load an account first' : 'Generate full ideas from this weekly opportunity'}>
                            {busy ? 'Analyzing…' : 'Generate Full Ideas'}
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
function SuggestionCard({ trend, rec, index, onSaveIdea, onGenerate, onMoreOptions, onCardClick }) {
    const m = MOMENTUM[trend?.momentum] || MOMENTUM.rising
    const t = TREND_TYPE[trend?.trend_type] || TREND_TYPE.topic
    const scoreVal = typeof rec?.opportunity_score === 'number' ? Math.round(rec.opportunity_score) : null
    const difficultyMap = { Easy: { label: 'Easy', cls: 'easy' }, Medium: { label: 'Medium', cls: 'medium' }, Hard: { label: 'Hard', cls: 'hard' } }
    const diff = difficultyMap[rec?.difficulty] || null
    const contentStyle = rec?.content_style || t.label
    return (
        <div className="cs-card" onClick={onCardClick} style={onCardClick ? { cursor: 'pointer' } : undefined}>
            <div className="cs-card__primary">
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
                    {scoreVal != null ? (
                        <>
                            <div className="cs-stat__score-row">
                                <span className="cs-stat__score">{scoreVal} / 100</span>
                            </div>
                            <div className="cs-stat__bar-bg">
                                <div className="cs-stat__bar-fill" style={{ width: `${scoreVal}%` }} />
                            </div>
                            <span className={`cs-stat__band cs-stat__band--${m.cls}`}>
                                {m.emoji} {scoreVal >= 85 ? 'Very High' : scoreVal >= 70 ? 'High' : 'Moderate'}
                            </span>
                        </>
                    ) : (
                        <span className="cs-stat__val">Available after full analysis</span>
                    )}
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
                <button className="cs-action-btn cs-action-btn--primary" onClick={() => onGenerate('script', trend, rec)} title="Generate a full script for this idea">Generate Script</button>
                <button className="cs-action-btn cs-action-btn--ghost" onClick={() => onGenerate('caption', trend, rec)} title="Generate a caption for this idea">Generate Caption</button>
                <button
                    className="cs-action-btn cs-action-btn--save"
                    onClick={() => onSaveIdea(trend, rec)}
                >
                    Save Idea
                </button>
                <button
                    className="cs-action-btn cs-action-btn--ghost"
                    onClick={() => onMoreOptions?.(trend, rec)}
                    title="More options"
                >
                    ...
                </button>
            </div>
        </div>
    )
}

// ─── Right Panel ──────────────────────────────────────────────────────────────
function RightPanel({ niche, trends, data, trendingTopics, trendingAudio, onShowAllTrends, onShowAllAudio, onShowContentGaps, assistantPrompt, setAssistantPrompt, assistantReply, onAskAI }) {
    const dailyInsights = data?.daily_insights
    const contentGaps = data?.content_gaps || []

    return (
        <aside className="cs-right">
            {/* Today's Insights */}
            {dailyInsights && (
                <div className="cs-right-card">
                    <div className="cs-right-card__header">
                        <span className="cs-right-card__title">Today's Insights</span>
                        <span className="cs-right-card__link">📅 View Calendar</span>
                    </div>
                    {/* Audience Active - prominent full-width card */}
                    {dailyInsights.audience_active_window && (
                        <div className="cs-insight-highlight">
                            <span className="cs-insight-label">Audience Active</span>
                            <div className="cs-insight-highlight__row">
                                <span className="cs-insight-highlight__value">{dailyInsights.audience_active_window}</span>
                                <span className="cs-insight-today-badge">Today</span>
                            </div>
                        </div>
                    )}
                    {/* 2-column grid for remaining insights */}
                    <div className="cs-insights-pair">
                        {dailyInsights.best_content_type && (
                            <div className="cs-insight-item">
                                <span className="cs-insight-label">Best Content Type</span>
                                <span className="cs-insight-value">{dailyInsights.best_content_type}</span>
                            </div>
                        )}
                        {dailyInsights.trending_audio_count != null && (
                            <div className="cs-insight-item">
                                <span className="cs-insight-label">Trending Audio</span>
                                <span className="cs-insight-value">
                                    <span className="cs-insight-audio-icon">♪</span> {dailyInsights.trending_audio_count}
                                </span>
                            </div>
                        )}
                    </div>
                    <div className="cs-insights-pair">
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

            {/* Trending Audio */ }
            {trendingAudio.length > 0 && (
                <div className="cs-right-card">
                    <div className="cs-right-card__header">
                        <span className="cs-right-card__title">Trending Audio</span>
                        <button className="cs-right-card__link" onClick={onShowAllAudio}>View All</button>
                    </div>
                    <div className="cs-gaps">
                        {trendingAudio.slice(0, 3).map((audio, i) => (
                            <div key={audio.id || `${audio.audio_name}-${i}`} className="cs-gap">
                                <span className="cs-gap__icon cs-gap__icon--opportunity">♪</span>
                                <div>
                                    <div style={{ fontWeight: 600 }}>{audio.audio_name}</div>
                                    <div className="cs-trending-item__match">
                                        {audio.audience_match_pct}% match · {audio.momentum}
                                    </div>
                                </div>
                            </div>
                        ))}
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
                            <div key={t.id || t.topic_name || i} className="cs-trending-item">
                                <div className="cs-trending-item__thumb" style={{
                                    background: ['linear-gradient(135deg,#3b82f6,#8b5cf6)', 'linear-gradient(135deg,#10b981,#3b82f6)', 'linear-gradient(135deg,#f59e0b,#ef4444)'][i]
                                }}>
                                    {['🌊', '💎', '✈️'][i] || '🔥'}
                                </div>
                                <div className="cs-trending-item__body">
                                    <span className="cs-trending-item__name">{topicDisplayName(t, i)}</span>
                                    <span className="cs-trending-item__match">{Math.round(t.audience_match_pct)}% Audience Match</span>
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
                    <span className="cs-right-card__title">Prompt Assistant</span>
                    <span className="cs-banner__badge">Preview</span>
                </div>
                <p className="cs-ask-ai__sub">Use quick prompts to explore hooks, formats, and content angles.</p>
                <div className="cs-ask-ai__input-wrap">
                    <input
                        className="cs-ask-ai__input"
                        placeholder="e.g. Give me educational reel ideas for this creator"
                        value={assistantPrompt}
                        onChange={e => setAssistantPrompt(e.target.value)}
                        onKeyDown={e => {
                            if (e.key === 'Enter') {
                                onAskAI(assistantPrompt)
                            }
                        }}
                    />
                    <button className="cs-ask-ai__send" onClick={() => onAskAI(assistantPrompt)}>Send</button>
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
    const [notice,       setNotice]       = useState(null)
    const [queued,       setQueued]       = useState(false)
    const [jobId,        setJobId]        = useState(null)
    const [polling,      setPolling]      = useState(false)
    const [activeFilter, setActiveFilter] = useState('All')
    const [sortMode,     setSortMode]     = useState('Opportunity')
    const [visibleCount, setVisibleCount] = useState(5)
    const [quickIdeaMap, setQuickIdeaMap] = useState(() => {
        try {
            return JSON.parse(localStorage.getItem('trend_quick_idea_map') || '{}')
        } catch (_) {
            return {}
        }
    })
    const [hiddenIdeaIds, setHiddenIdeaIds] = useState(() => new Set())
    const [generated, setGenerated] = useState(null)
    const [assistantPrompt, setAssistantPrompt] = useState('')
    const [assistantReply, setAssistantReply] = useState('')
    const [showContentGaps, setShowContentGaps] = useState(false)

    // New modal states
    const [showGenerateModal, setShowGenerateModal] = useState(false)
    const [generationJob, setGenerationJob] = useState(null)
    const [generatedIdeas, setGeneratedIdeas] = useState([])
    const [trendTopics, setTrendTopics] = useState([])
    const [trendAudio, setTrendAudio] = useState([])
    const [showAllTopics, setShowAllTopics] = useState(false)
    const [showAllAudio, setShowAllAudio] = useState(false)
    const [seedTopic, setSeedTopic] = useState('')
    const [showScriptGen, setShowScriptGen] = useState(null) // { ideaId, title, hook }
    const [showCaptionGen, setShowCaptionGen] = useState(null) // { ideaId, title }
    const [showScheduler, setShowScheduler] = useState(null) // { ideaId, title }
    const [showSaveModal, setShowSaveModal] = useState(null) // ideaId
    const [showMoreOptions, setShowMoreOptions] = useState(null) // { ideaId, title }
    const [showIdeaDetail, setShowIdeaDetail] = useState(null) // full idea object
    const [showCalendar, setShowCalendar] = useState(false)
    const [ideaPage, setIdeaPage] = useState(1)
    const [ideaLoading, setIdeaLoading] = useState(false)

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

    useEffect(() => {
        if (!accountId || !data) {
            setTrendTopics([])
            setTrendAudio([])
            return
        }

        let cancelled = false
        ;(async () => {
            try {
                const [topicsRes, audioRes] = await Promise.all([
                    fetch(`/api/v1/accounts/${encodeURIComponent(accountId)}/trends/topics`, { credentials: 'include' }),
                    fetch(`/api/v1/accounts/${encodeURIComponent(accountId)}/trends/audio`, { credentials: 'include' }),
                ])

                const topicsJson = topicsRes.ok ? await topicsRes.json() : { topics: [] }
                const audioJson = audioRes.ok ? await audioRes.json() : { audio_tracks: [] }

                if (!cancelled) {
                    const topics = Array.isArray(topicsJson?.topics) ? topicsJson.topics : []
                    setTrendTopics(topics.slice(0, 3).map((topic, index) => ({
                        ...topic,
                        topic_name: topicDisplayName(topic, index),
                    })))
                    setTrendAudio(Array.isArray(audioJson?.audio_tracks) ? audioJson.audio_tracks.slice(0, 3) : [])
                }
            } catch (_) {
                if (!cancelled) {
                    setTrendTopics([])
                    setTrendAudio([])
                }
            }
        })()

        return () => { cancelled = true }
    }, [accountId, data])

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
        const rawInput = accountInput.trim()
        if (!rawInput) return

        ;(async () => {
            try {
                const res = await fetch(`/api/v1/accounts/resolve?query=${encodeURIComponent(rawInput)}`, {
                    credentials: 'include',
                })
                const resolved = res.ok ? await res.json() : null
                const canonicalId = resolved?.resolved && resolved?.account_id
                    ? resolved.account_id
                    : rawInput.replace(/^@+/, '')

                setAccountId(canonicalId)
                fetchExisting(canonicalId)

                if (resolved && !resolved.resolved) {
                    setError(`We couldn't fully resolve "${rawInput}", so we tried it directly.`)
                } else {
                    setError(null)
                }
            } catch (_) {
                const fallback = rawInput.replace(/^@+/, '')
                setAccountId(fallback)
                fetchExisting(fallback)
            }
        })()
    }

    const busy = loading || polling

    // Filter suggestions
    const allCards = (() => {
        const trends = data?.global_trends || []
        const recs   = data?.recommendations || []
        const cards  = trends.map((t, i) => ({ trend: t, rec: recs[i] || null }))
        const filtered = cards.filter(c => {
            const persistedIdeaId = quickIdeaMap[ideaKey(c.trend, c.rec)]?.ideaId
            return !hiddenIdeaIds.has(persistedIdeaId) && matchesFilter(c, activeFilter)
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
    const weeklyOpportunity = data?.weekly_opportunity || null

    function ideaKey(trend, rec) {
        return `${trend?.topic_name || 'trend'}::${rec?.suggested_title || ''}`
    }

    function rememberQuickIdea(key, idea) {
        setQuickIdeaMap(prev => {
            const next = {
                ...prev,
                [key]: {
                    ideaId: idea.id,
                    title: idea.title,
                    hook: idea.hook || null,
                    persistedAt: new Date().toISOString(),
                },
            }
            localStorage.setItem('trend_quick_idea_map', JSON.stringify(next))
            return next
        })
    }

    function forgetQuickIdea(key) {
        setQuickIdeaMap(prev => {
            if (!prev[key]) return prev
            const next = { ...prev }
            delete next[key]
            localStorage.setItem('trend_quick_idea_map', JSON.stringify(next))
            return next
        })
    }

    async function checkIdeaExists(ideaId) {
        if (!accountId || !isPersistedIdeaId(ideaId)) return false
        try {
            const res = await fetch(`/api/v1/accounts/${encodeURIComponent(accountId)}/ideas/${encodeURIComponent(ideaId)}`, {
                method: 'GET',
                credentials: 'include',
            })
            return res.ok
        } catch {
            return false
        }
    }

    async function ensureIdeaForRecommendation(trend, rec) {
        const key = ideaKey(trend, rec)
        const existing = quickIdeaMap[key]
        if (isPersistedIdeaId(existing?.ideaId)) {
            const stillExists = await checkIdeaExists(existing.ideaId)
            if (stillExists) {
                return {
                    id: existing.ideaId,
                    title: existing.title || rec?.suggested_title || trend?.topic_name || 'Content Idea',
                    hook: existing.hook || rec?.hook || null,
                }
            }
            forgetQuickIdea(key)
        }

        if (existing?.ideaId && !isPersistedIdeaId(existing.ideaId)) {
            forgetQuickIdea(key)
        }

        const res = await fetch(`/api/v1/accounts/${encodeURIComponent(accountId)}/trends/persist-idea`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                trend,
                recommendation: rec,
                source: 'quick_trend_card',
            }),
        })
        const payload = await res.json().catch(() => ({}))
        if (!res.ok) {
            throw new Error(payload.detail || `Could not prepare this idea (${res.status})`)
        }

        rememberQuickIdea(key, payload)
        return payload
    }

    async function handleSaveIdea(trend, rec) {
        if (!accountId) {
            setError('Load an account first before saving ideas.')
            return
        }

        try {
            const idea = await ensureIdeaForRecommendation(trend, rec)
            setShowSaveModal(idea.id)
        } catch (e) {
            setError(e.message)
        }
    }

    async function handleGenerate(kind, trend, rec) {
        if (!accountId) {
            setError('Load an account first before generating scripts or captions.')
            return
        }

        try {
            const idea = await ensureIdeaForRecommendation(trend, rec)
            if (kind === 'script') {
                setShowScriptGen({
                    ideaId: idea.id,
                    title: idea.title,
                    hook: idea.hook || rec?.hook || null,
                    contentType: idea.content_type || rec?.content_type || 'reel',
                })
            } else if (kind === 'caption') {
                setShowCaptionGen({
                    ideaId: idea.id,
                    title: idea.title,
                    hook: idea.hook || rec?.hook || null,
                })
            }
        } catch (e) {
            setError(e.message)
        }
    }

    async function handleDrawerGenerate(kind, idea) {
        try {
            // Trend cards use display-only IDs, so persist the selected card first.
            const persistedIdea = await ensureIdeaForRecommendation(idea, idea)
            setShowIdeaDetail(null)
            if (kind === 'script') {
                setShowScriptGen({
                    ideaId: persistedIdea.id,
                    title: persistedIdea.title,
                    hook: persistedIdea.hook || idea?.hook || null,
                    contentType: persistedIdea.content_type || idea?.content_type || 'reel',
                })
            } else if (kind === 'caption') {
                setShowCaptionGen({
                    ideaId: persistedIdea.id,
                    title: persistedIdea.title,
                    hook: persistedIdea.hook || idea?.hook || null,
                })
            }
        } catch (e) {
            setError(e.message)
        }
    }

    async function handleAskAI(prompt) {
        const message = prompt.trim()
        if (!message || !accountId) return
        setAssistantPrompt(message)
        setAssistantReply('Thinking...')
        try {
            const response = await fetch(`/api/v1/accounts/${encodeURIComponent(accountId)}/trends/ai-assistant`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ message }),
            })
            const payload = await response.json().catch(() => ({}))
            if (!response.ok) throw new Error(payload.detail || 'Assistant request failed')
            setAssistantReply(payload.reply || 'No answer was returned.')
        } catch (e) {
            setAssistantReply('The assistant is unavailable right now. Please try again shortly.')
            setError(e.message)
        }
    }

    // ── New handlers for content suggestion features ──

        async function handleGenerateIdeas(request) {
        setShowGenerateModal(false)
        try {
            const res = await fetch(`/api/v1/accounts/${encodeURIComponent(accountId)}/trends/generate-ideas`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify(request),
            })
            const data = await res.json()
            if (res.ok) {
                setGenerationJob(data)
            } else {
                const errMsg = data.detail || `Server error (${res.status})`
                setError(`Generation failed: ${errMsg}`)
                setShowGenerateModal(true)
            }
        } catch (e) {
            setError(`Generation failed: ${e.message}`)
            setShowGenerateModal(true)
        }
    }

    function handleGenerationComplete(ideas) {
        setGenerationJob(null)
        setGeneratedIdeas(ideas)
        setSeedTopic('')
        // Refresh the data
        if (accountId) fetchExisting(accountId)
    }

    function handleGenerationError(error) {
        setGenerationJob(null)
        setError(error)
    }

    function handleUseTopic(topic) {
        const topicName = topic?.topic_name || topic?.name || ''
        setSeedTopic(topicName)
        setShowAllTopics(false)
        setShowGenerateModal(true)
    }

    function handleUseAudio(audio) {
        const audioName = audio?.audio_name || ''
        setSeedTopic(audioName)
        setShowAllAudio(false)
        setShowGenerateModal(true)
    }

    function handleOpenScript(ideaId, title, hook) {
        setShowScriptGen({ ideaId, title, hook })
    }

    function handleOpenCaption(ideaId, title) {
        setShowCaptionGen({ ideaId, title })
    }

    function handleOpenScheduler(ideaId, title) {
        setShowScheduler({ ideaId, title })
    }

    function handleOpenSave(ideaId) {
        setShowSaveModal(ideaId)
    }

    function handleOpenMoreOptions(ideaId, title) {
        setShowMoreOptions({ ideaId, title })
    }

    function pollIdeaAction(jobId, actionLabel) {
        const maxAttempts = 45
        let attempts = 0

        const poll = async () => {
            try {
                const response = await fetch(
                    `/api/v1/accounts/${encodeURIComponent(accountId)}/ideas/jobs/${encodeURIComponent(jobId)}/status`,
                    { credentials: 'include' },
                )
                const payload = await response.json().catch(() => ({}))
                if (!response.ok) throw new Error(payload.detail || 'Could not check action status')

                if (payload.status === 'completed') {
                    setNotice(`${actionLabel} complete.`)
                    if (accountId) fetchExisting(accountId)
                    return
                }
                if (payload.status === 'failed') {
                    setError(`${actionLabel} failed: ${payload.error || 'Unknown error'}`)
                    return
                }
                if (attempts++ < maxAttempts) {
                    window.setTimeout(poll, 2000)
                } else {
                    setError(`${actionLabel} is still running. Please refresh in a moment.`)
                }
            } catch (e) {
                setError(`${actionLabel} status check failed: ${e.message}`)
            }
        }

        void poll()
    }

        async function handleMoreOptionAction(actionId, ideaId) {
        const baseUrl = `/api/v1/accounts/${encodeURIComponent(accountId)}`

        try {
            switch (actionId) {
                case 'improve':
                    setShowMoreOptions(null)
                    const improveRes = await fetch(`${baseUrl}/ideas/${ideaId}/improve`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({ feedback: 'Make it more engaging', aspect: 'full' }),
                    })
                    const improvePayload = await improveRes.json().catch(() => ({}))
                    if (!improveRes.ok) throw new Error(improvePayload.detail || 'Could not improve this idea')
                    setNotice('Improvement queued. We will refresh this idea when it is ready.')
                    pollIdeaAction(improvePayload.job_id, 'Improvement')
                    break
                case 'variations':
                    setShowMoreOptions(null)
                    const varRes = await fetch(`${baseUrl}/ideas/${ideaId}/variations`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({ count: 3 }),
                    })
                    const variationPayload = await varRes.json().catch(() => ({}))
                    if (!varRes.ok) throw new Error(variationPayload.detail || 'Could not generate variations')
                    setNotice('Variations queued. We will refresh this idea when they are ready.')
                    pollIdeaAction(variationPayload.job_id, 'Variation generation')
                    break
                case 'regenerate':
                    setShowMoreOptions(null)
                    const regenRes = await fetch(`${baseUrl}/ideas/${ideaId}/regenerate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        credentials: 'include',
                        body: JSON.stringify({}),
                    })
                    const regeneratePayload = await regenRes.json().catch(() => ({}))
                    if (!regenRes.ok) throw new Error(regeneratePayload.detail || 'Could not regenerate this idea')
                    setNotice('Regeneration queued. We will refresh this idea when it is ready.')
                    pollIdeaAction(regeneratePayload.job_id, 'Regeneration')
                    break
                case 'schedule':
                    setShowMoreOptions(null)
                    setShowScheduler({ ideaId, title: 'Content Idea' })
                    break
                case 'duplicate': {
                    const response = await fetch(`${baseUrl}/ideas/${ideaId}/duplicate`, { method: 'POST', credentials: 'include' })
                    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Could not duplicate this idea')
                    setNotice('Idea duplicated successfully.')
                    break
                }
                case 'type': {
                    const nextType = window.prompt('Choose content type: reel, carousel, or photo', 'reel')?.trim().toLowerCase()
                    if (!nextType) break
                    const response = await fetch(`${baseUrl}/ideas/${ideaId}`, {
                        method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ content_type: nextType }),
                    })
                    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Could not change content type')
                    setNotice(`Content type changed to ${nextType}.`)
                    break
                }
                case 'hide': {
                    const response = await fetch(`${baseUrl}/ideas/${ideaId}`, {
                        method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ status: 'hidden' }),
                    })
                    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Could not hide this idea')
                    setHiddenIdeaIds(previous => new Set(previous).add(ideaId))
                    setNotice('Idea hidden from recommendations.')
                    break
                }
                case 'delete': {
                    if (!window.confirm('Delete this idea? You can no longer use it to generate scripts or captions.')) break
                    const response = await fetch(`${baseUrl}/ideas/${ideaId}`, { method: 'DELETE', credentials: 'include' })
                    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Could not delete this idea')
                    setHiddenIdeaIds(previous => new Set(previous).add(ideaId))
                    setNotice('Idea deleted successfully.')
                    break
                }
                case 'save':
                    setShowMoreOptions(null)
                    setShowSaveModal(ideaId)
                    break
                default:
                    break
            }
        } catch (e) {
            setError(`Action failed: ${e.message}`)
        }
    }

    return (
        <>
            <div className="cs-layout">
                <Sidebar account={accountId || null} />

                <div className="cs-main">
                    {showAllTopics ? (
                        <AllTrendingTopics
                            accountUrl={`/api/v1/accounts/${encodeURIComponent(accountId)}`}
                            onClose={() => setShowAllTopics(false)}
                            onUseTopic={handleUseTopic}
                        />
                    ) : showAllAudio ? (
                        <AllTrendingAudio
                            accountUrl={`/api/v1/accounts/${encodeURIComponent(accountId)}`}
                            onClose={() => setShowAllAudio(false)}
                            onUseAudio={handleUseAudio}
                        />
                    ) : (
                        <>
                            {/* ── Top bar ── */}
                            <div className="cs-topbar">
                                <div className="cs-topbar__left">
                                    <h1 className="cs-topbar__title">Content Suggestions</h1>
                                    <p className="cs-topbar__sub">AI-powered trend recommendations tailored to your audience</p>
                                </div>
                                <form className="cs-topbar__search" onSubmit={handleSearch}>
                                    <span className="cs-topbar__search-icon">🔍</span>
                                    <input
                                        className="cs-topbar__search-input"
                                        placeholder="Search by creator username, @handle, or account ID…"
                                        value={accountInput}
                                        onChange={e => setAccountInput(e.target.value)}
                                        disabled={busy}
                                    />
                                    <kbd className="cs-topbar__kbd">⌘ K</kbd>
                                </form>
                                <button className="cs-generate-btn" onClick={() => accountId && setShowGenerateModal(true)} disabled={busy || !accountId} title={!accountId ? 'Load an account first' : 'Create full database-backed content ideas'}>
                                    {busy ? 'Analyzing…' : 'Generate Full Ideas'}
                                </button>
                                <button className="cs-topbar__refresh-icon" onClick={() => accountId && fetchExisting(accountId)} disabled={busy} title="Refresh">↻</button>
                            </div>

                            <div className="cs-content-grid">
                                <div className="cs-content-grid__feed">

                    {/* ── Error ── */}
                    {error && (
                        <div className="cs-error-bar">
                            <span>{error}</span>
                            <button onClick={() => accountId && fetchExisting(accountId)}>Retry</button>
                        </div>
                    )}
                    {notice && (
                        <div className="cs-notice-bar">
                            <span>{notice}</span>
                            <button onClick={() => setNotice(null)}>Dismiss</button>
                        </div>
                    )}

                    {/* ── Degraded mode indicator ── */}
                    {data?._meta?.degraded && (
                        <div className="cs-degraded-bar">
                            <span>Limited data available. Some insights may be incomplete. ({data._meta.degraded_reasons?.join(', ') || 'unknown reason'})</span>
                        </div>
                    )}

                    {/* ── Loading state ── */}
                    {busy && (
                        <div className="cs-loading-bar">
                            <div className="cs-loading-bar__fill" />
                            <span>{queued ? 'Analysis queued. Waiting for results…' : 'Running analysis…'}</span>
                        </div>
                    )}

                    {/* ── Opportunity Banner ── */}
                    <OpportunityBanner niche={niche} weeklyOpportunity={weeklyOpportunity} onRefresh={() => accountId && setShowGenerateModal(true)} busy={busy} hasAccount={!!accountId} />

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
                                <h2 className="cs-feed-header__title">Recommended Content Angles <span className="cs-feed-header__info">ℹ</span></h2>
                                <p className="cs-feed-header__sub">
                                    These recommendation cards combine live trend signals with creator fit so you can move quickly from discovery to execution.
                                </p>
                            <p className="cs-feed-header__note">
                                If you open a downstream action from one of these cards, the system saves it as a full working idea automatically so the rest of the workflow can continue without interruption.
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
                            onSaveIdea={handleSaveIdea}
                            onGenerate={handleGenerate}
                            onMoreOptions={async (trend, rec) => {
                                try {
                                    const idea = await ensureIdeaForRecommendation(trend, rec)
                                    setShowMoreOptions({ ideaId: idea.id, title: idea.title })
                                } catch (e) {
                                    setError(e.message)
                                }
                            }}
                            onCardClick={() => setShowIdeaDetail({ ...c.rec, ...c.trend, id: `trend-${i}` })}
                        />
                    ))}

                                        {/* ── Generated Ideas Section ── */}
                    {generatedIdeas.length > 0 && (
                        <>
                            <div className="cs-feed-header">
                                <h2 className="cs-feed-header__title">Generated Ideas <span className="cs-feed-header__info">ℹ</span></h2>
                                <p className="cs-feed-header__sub">
                                    {generatedIdeas.length} full idea{generatedIdeas.length > 1 ? 's' : ''} generated for the complete content workflow.
                                </p>
                            </div>
                            {generatedIdeas.map((idea, i) => (
                                <div key={idea.id || i} className="cs-card cs-card--generated">
                                    <div className="cs-card__primary">
                                        <div className="cs-card__thumb">
                                            <div className="cs-card__thumb-inner cs-card__thumb-inner--topic">
                                                <span className="cs-card__thumb-icon">AI</span>
                                            </div>
                                        </div>
                                        <div className="cs-card__body">
                                            <div className="cs-card__top">
                                                <span className={`cs-pot-badge cs-pot-badge--rising`}>
                                                    Generated
                                                </span>
                                            </div>
                                            <h3 className="cs-card__title">{idea.suggested_title || idea.title || `Idea ${i + 1}`}</h3>
                                            <div className="cs-card__tags">
                                                {idea.content_type && <span className="cs-tag cs-tag--format">{idea.content_type}</span>}
                                                {idea.hook && <span className="cs-tag cs-tag--neutral">{idea.hook.slice(0, 60)}{idea.hook.length > 60 ? '…' : ''}</span>}
                                            </div>
                                            {idea.description && (
                                                <div className="cs-card__explain">
                                                    <span className="cs-card__explain-label">Idea</span>
                                                    <p className="cs-card__desc">{idea.description.slice(0, 180)}{idea.description.length > 180 ? '…' : ''}</p>
                                                </div>
                                            )}
                                            {idea.rationale && (
                                                <div className="cs-card__explain">
                                                    <span className="cs-card__explain-label">Why this idea</span>
                                                    <p className="cs-card__desc">{idea.rationale.slice(0, 180)}{idea.rationale.length > 180 ? '…' : ''}</p>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <div className="cs-card__stats">
                                        {idea.opportunity_score != null && (
                                            <div className="cs-stat">
                                                <span className="cs-stat__label">Opportunity Score</span>
                                                <span className="cs-stat__score">{Math.round(idea.opportunity_score)} / 100</span>
                                                <div className="cs-stat__bar-bg">
                                                    <div className="cs-stat__bar-fill" style={{ width: `${idea.opportunity_score}%` }} />
                                                </div>
                                            </div>
                                        )}
                                        {idea.difficulty && (
                                            <div className="cs-stat">
                                                <span className="cs-stat__label">Difficulty</span>
                                                <span className="cs-stat__val">{idea.difficulty}</span>
                                            </div>
                                        )}
                                    </div>
                                    <div className="cs-card__actions">
                                        <button className="cs-action-btn cs-action-btn--primary" onClick={() => setShowScriptGen({ ideaId: idea.id, title: idea.suggested_title || idea.title, hook: idea.hook, contentType: idea.content_type || 'reel' })}>{idea.content_type === 'carousel' ? 'Generate Slides' : idea.content_type === 'photo' ? 'Generate Photo Brief' : 'Generate Script'}</button>
                                        <button className="cs-action-btn cs-action-btn--ghost" onClick={() => setShowCaptionGen({ ideaId: idea.id, title: idea.suggested_title || idea.title })}>Generate Caption</button>
                                        <button className="cs-action-btn cs-action-btn--save" onClick={() => setShowSaveModal(idea.id)}>Save Idea</button>
                                        <button className="cs-action-btn cs-action-btn--ghost" onClick={() => setShowScheduler({ ideaId: idea.id, title: idea.suggested_title || idea.title })}>Schedule</button>
                                    </div>
                                </div>
                            ))}
                        </>
                    )}

                    {/* ── Empty/Initial state ── */}
                    {!data && !busy && !error && (
                        <div className="cs-empty">
                            <div className="cs-empty__icon">📈</div>
                            <h2>Find content opportunities</h2>
                            <p>Search by creator username, @handle, or account ID to generate AI-powered trend recommendations based on live global trends.</p>
                            <button className="cs-generate-btn" onClick={() => document.querySelector('.cs-topbar__search-input')?.focus()}>
                                Start Search
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
                            {visibleCount < allCards.length ? 'Load More Recommendations' : 'Refresh Recommendations'}
                        </button>
                    )}

                    {/* ── Calendar View Toggle ── */}
                    {accountId && (
                        <div className="cs-calendar-section">
                            <button
                                className="cs-btn cs-btn--secondary"
                                onClick={() => setShowCalendar(!showCalendar)}
                            >
                                {showCalendar ? 'Hide Calendar' : 'View Content Calendar'}
                            </button>
                            {showCalendar && (
                                <CalendarView
                                    accountUrl={`/api/v1/accounts/${encodeURIComponent(accountId)}`}
                                    onSelectItem={(item) => {
                                        console.log('Selected calendar item:', item)
                                    }}
                                />
                            )}
                        </div>
                    )}
                            </div>

                            <RightPanel
                                niche={niche}
                                trends={trends}
                                data={data}
                                trendingTopics={trendTopics}
                                trendingAudio={trendAudio}
                                onShowAllTrends={() => {
                                    setShowAllTopics(true)
                                }}
                                onShowAllAudio={() => {
                                    setShowAllAudio(true)
                                }}
                                onShowContentGaps={() => setShowContentGaps(true)}
                                assistantPrompt={assistantPrompt}
                                setAssistantPrompt={setAssistantPrompt}
                                assistantReply={assistantReply}
                                onAskAI={handleAskAI}
                            />
                            </div>
                        </>
                    )}
                </div>
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

            {/* ── Generate Ideas Modal ── */}
            {showGenerateModal && (
                <GenerateIdeasModal
                    onClose={() => setShowGenerateModal(false)}
                    onGenerate={handleGenerateIdeas}
                    initialTopic={seedTopic}
                />
            )}

            {/* ── Generation Progress ── */}
            {generationJob && (
                <GenerationProgress
                    jobId={generationJob.job_id}
                    accountUrl={`/api/v1/accounts/${encodeURIComponent(accountId)}`}
                    onComplete={handleGenerationComplete}
                    onError={handleGenerationError}
                />
            )}

            {/* ── Script Generator ── */}
            {showScriptGen && (
                <ScriptGenerator
                    ideaId={showScriptGen.ideaId}
                    ideaTitle={showScriptGen.title}
                    hook={showScriptGen.hook}
                    contentType={showScriptGen.contentType}
                    previewOnly={showScriptGen.previewOnly}
                    previewScript={showScriptGen.previewScript}
                    accountUrl={`/api/v1/accounts/${encodeURIComponent(accountId)}`}
                    onClose={() => setShowScriptGen(null)}
                    onCopy={() => console.log('Script copied')}
                />
            )}

            {/* ── Caption Generator ── */}
            {showCaptionGen && (
                <CaptionGenerator
                    ideaId={showCaptionGen.ideaId}
                    ideaTitle={showCaptionGen.title}
                    hook={showCaptionGen.hook}
                    previewOnly={showCaptionGen.previewOnly}
                    previewCaptions={showCaptionGen.previewCaptions}
                    accountUrl={`/api/v1/accounts/${encodeURIComponent(accountId)}`}
                    onClose={() => setShowCaptionGen(null)}
                    onCopy={() => console.log('Caption copied')}
                />
            )}

                        {/* ── Content Planner ── */}
            {showScheduler && (
                <ContentPlanner
                    ideaId={showScheduler.ideaId}
                    ideaTitle={showScheduler.title}
                    accountUrl={`/api/v1/accounts/${encodeURIComponent(accountId)}`}
                    onClose={() => setShowScheduler(null)}
                    onSchedule={(result) => {
                        console.log('Scheduled:', result)
                        setShowScheduler(null)
                        setShowCalendar(true)
                    }}
                />
            )}

            {/* ── Save Idea Modal ── */}
            {showSaveModal && (
                <SaveIdeaModal
                    ideaId={showSaveModal}
                    accountUrl={`/api/v1/accounts/${encodeURIComponent(accountId)}`}
                    onClose={() => setShowSaveModal(null)}
                    onSave={(collections) => {
                        console.log('Saved to collections:', collections)
                        setShowSaveModal(null)
                    }}
                />
            )}

            {/* ── More Options Menu ── */}
            {showMoreOptions && (
                                <MoreOptionsMenu
                    ideaId={showMoreOptions.ideaId}
                    ideaTitle={showMoreOptions.title}
                    onAction={handleMoreOptionAction}
                    onClose={() => setShowMoreOptions(null)}
                />
            )}

            {/* ── Screen 1: Idea Detail Drawer ── */}
            {showIdeaDetail && (
                <IdeaDetailDrawer
                    idea={showIdeaDetail}
                    accountUrl={`/api/v1/accounts/${encodeURIComponent(accountId)}`}
                    onClose={() => setShowIdeaDetail(null)}
                    onGenerate={handleDrawerGenerate}
                    onCopy={(idea) => {
                        // Save to clipboard or trigger save flow
                        const text = `${idea.title || idea.suggested_title}\nHook: ${idea.hook || ''}\nDescription: ${idea.description || idea.rationale || ''}`
                        navigator.clipboard?.writeText(text)
                        alert('Idea copied to clipboard!')
                    }}
                />
            )}
        </>
    )
}
