/**
 * Screen 1 — Suggestion Details Drawer
 *
 * Slide-over panel showing full idea detail with scores, signals, and CTAs.
 * Opens when a creator clicks an idea card in the main feed.
 */

import { useState, useEffect, useCallback } from 'react'
import ScriptGenerator from './ScriptGenerator'
import CaptionGenerator from './CaptionGenerator'
import { formatCompactNumber } from '../utils/format'

export default function IdeaDetailDrawer({ idea, accountUrl, onClose, onCopy, onGenerate }) {
    const [detail, setDetail] = useState(idea || null)
    const [loading, setLoading] = useState(!idea)
    const [error, setError] = useState(null)
    const [showScriptGen, setShowScriptGen] = useState(false)
    const [showCaptionGen, setShowCaptionGen] = useState(false)
    const [scoreAnim, setScoreAnim] = useState(false)
    const [isOpen, setIsOpen] = useState(false)

    // Animate on mount
    useEffect(() => {
        requestAnimationFrame(() => setIsOpen(true))
        setTimeout(() => setScoreAnim(true), 150)
    }, [])

    // Close handler with animation
    const handleClose = useCallback(() => {
        setIsOpen(false)
        setTimeout(() => onClose?.(), 300)
    }, [onClose])

    // Fetch full detail if needed
    useEffect(() => {
        if (idea && idea.id && !idea.id.startsWith('trend-')) {
            setLoading(true)
            fetch(`${accountUrl}/ideas/${idea.id}`, { credentials: 'include' })
                .then(r => r.ok ? r.json() : Promise.reject(r))
                .then(d => { setDetail(d); setLoading(false) })
                .catch(() => { setDetail(idea); setLoading(false) })
        } else {
            setDetail(idea)
            setLoading(false)
        }
    }, [idea, accountUrl])

// ── Listen for ESC ─────────────────────────────────────────────────
    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') handleClose() }
        window.addEventListener('keydown', onKey)
        return () => window.removeEventListener('keydown', onKey)
    }, [handleClose])

// ── Score helpers ───────────────────────────────────────────────────
    const opportunityScore = detail?.opportunity_score ?? detail?.engagement_score ?? 0
    const opportunityBand = opportunityScore >= 80 ? 'Very High' : opportunityScore >= 60 ? 'High' : opportunityScore >= 40 ? 'Moderate' : 'Low'
    const gaugeAngle = (opportunityScore / 100) * 180
    const reachMin = detail?.expected_reach_min || detail?.expected_views_min || 0
    const reachMax = detail?.expected_reach_max || detail?.expected_views_max || 0
    const difficulty = detail?.difficulty || 'Medium'
    const contentStyle = detail?.content_style || detail?.content_type || 'Reel'
    const hook = detail?.hook || ''
    const tags = detail?.tags || []
    const bestTime = detail?.best_time || detail?.best_time_to_post || null
    const duration = detail?.duration_seconds || 30

    if (loading) {
        return (
            <div className="cs-drawer-overlay cs-drawer-overlay--open" onClick={handleClose}>
                <div className="cs-drawer cs-drawer--loading" onClick={e => e.stopPropagation()}>
                    <div className="cs-drawer__skeleton">
                        <div className="cs-skeleton cs-skeleton--thumb" />
                        <div className="cs-skeleton cs-skeleton--title" />
                        <div className="cs-skeleton cs-skeleton--text" />
                        <div className="cs-skeleton cs-skeleton--text" />
                        <div className="cs-skeleton cs-skeleton--gauge" />
                    </div>
                </div>
            </div>
        )
    }

    if (error && !detail) {
        return (
            <div className="cs-drawer-overlay cs-drawer-overlay--open" onClick={handleClose}>
                <div className="cs-drawer cs-drawer--error" onClick={e => e.stopPropagation()}>
                    <h3>Couldn't load idea details</h3>
                    <p>{error}</p>
                    <button className="cs-btn cs-btn--primary" onClick={() => window.location.reload()}>Retry</button>
                </div>
            </div>
        )
    }

    return (
        <>
            <div
                className={`cs-drawer-overlay ${isOpen ? 'cs-drawer-overlay--open' : ''}`}
                onClick={handleClose}
            >
                <div
                    className={`cs-drawer ${isOpen ? 'cs-drawer--open' : ''}`}
                    onClick={e => e.stopPropagation()}
                >
                    {/* Back link */}
                    <button className="cs-drawer__back" onClick={handleClose}>
                        ← Back to Suggestions
                    </button>

                    {/* Close ✕ */}
                    <button className="cs-drawer__close" onClick={handleClose}>✕</button>

                    <div className="cs-drawer__body">
                        {/* ── Left Column ── */}
                        <div className="cs-drawer__left">
                            {/* Thumbnail area */}
                            <div className="cs-drawer__thumb">
                                <div className="cs-drawer__thumb-placeholder">
                                    <span className="cs-drawer__thumb-icon">🎬</span>
                                </div>
                            </div>

                            {/* Momentum badge */}
                            {detail?.momentum && (
                                <span className={`cs-badge cs-badge--momentum cs-badge--${detail.momentum}`}>
                                    🚀 {detail.momentum === 'peaking' ? 'Peaking Now' : detail.momentum === 'rising' ? 'Rising Potential' : 'Trending'}
                                </span>
                            )}

                            {/* Title */}
                            <h2 className="cs-drawer__title">{detail?.title || detail?.suggested_title}</h2>

                            {/* Tags row */}
                            <div className="cs-drawer__tags">
                                {contentStyle && <span className="cs-tag cs-tag--style">{contentStyle}</span>}
                                {detail?.trend_reference && <span className="cs-tag cs-tag--trend">{detail.trend_reference}</span>}
                                {difficulty && <span className={`cs-tag cs-tag--difficulty cs-tag--${difficulty.toLowerCase()}`}>{difficulty}</span>}
                            </div>

                            {/* Hook quote */}
                            {hook && (
                                <blockquote className="cs-drawer__hook">
                                    &ldquo;{hook}&rdquo;
                                </blockquote>
                            )}

                            {/* Description */}
                            {detail?.description && (
                                <p className="cs-drawer__desc">{detail.description}</p>
                            )}

                            {/* Rationale */}
                            {detail?.rationale && (
                                <div className="cs-drawer__rationale">
                                    <h4>Why this idea?</h4>
                                    <p>{detail.rationale}</p>
                                </div>
                            )}

                            {/* Duration */}
                            <div className="cs-drawer__duration">
                                <span className="cs-drawer__duration-icon">⏱</span>
                                <span>{duration}s – {Math.ceil(duration / 15) * 15}s</span>
                            </div>
                        </div>

                        {/* ── Right Column ── */}
                        <div className="cs-drawer__right">
                            {/* Opportunity Score Gauge */}
                            <div className="cs-gauge">
                                <div className="cs-gauge__ring">
                                    <svg viewBox="0 0 120 70" className="cs-gauge__svg">
                                        <path
                                            d="M10 60 A50 50 0 0 1 110 60"
                                            fill="none"
                                            stroke="var(--border-color)"
                                            strokeWidth="8"
                                            strokeLinecap="round"
                                        />
                                        <path
                                            d="M10 60 A50 50 0 0 1 110 60"
                                            fill="none"
                                            stroke="var(--purple-500)"
                                            strokeWidth="8"
                                            strokeLinecap="round"
                                            strokeDasharray={`${gaugeAngle} 200`}
                                            className={`cs-gauge__arc ${scoreAnim ? 'cs-gauge__arc--anim' : ''}`}
                                            style={{ transition: 'stroke-dasharray 1.2s cubic-bezier(0.4, 0, 0.2, 1)' }}
                                        />
                                    </svg>
                                    <div className={`cs-gauge__value ${scoreAnim ? 'cs-gauge__value--anim' : ''}`}>
                                        <span className="cs-gauge__score">{Math.round(opportunityScore)}</span>
                                        <span className="cs-gauge__label">/100</span>
                                    </div>
                                </div>
                                <span className={`cs-gauge__band cs-gauge__band--${opportunityBand.toLowerCase().replace(' ', '-')}`}>
                                    {opportunityBand}
                                </span>
                            </div>

                            {/* Stats Grid */}
                            <div className="cs-stats-grid">
                                <div className="cs-stat">
                                    <span className="cs-stat__label">Expected Reach</span>
                                    <span className="cs-stat__value">{reachMin ? `${formatCompactNumber(reachMin)} – ${formatCompactNumber(reachMax)}` : '—'}</span>
                                </div>
                                <div className="cs-stat">
                                    <span className="cs-stat__label">Difficulty</span>
                                    <span className="cs-stat__value">{difficulty}</span>
                                </div>
                                <div className="cs-stat">
                                    <span className="cs-stat__label">Competition</span>
                                    <span className="cs-stat__value">Low</span>
                                </div>
                            </div>

                            {/* Hashtags */}
                            {tags.length > 0 && (
                                <div className="cs-drawer__hashtags">
                                    <h4>Suggested Hashtags</h4>
                                    <div className="cs-hashtag-chips">
                                        {tags.slice(0, 5).map((t, i) => (
                                            <span key={i} className="cs-hashtag-chip">#{typeof t === 'string' ? t : t.tag || t.name || t}</span>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Best Time */}
                            {bestTime && (
                                <div className="cs-drawer__best-time">
                                    <span className="cs-drawer__best-time-icon">🕐</span>
                                    <span>Best Time to Post: <strong>{bestTime}</strong></span>
                                </div>
                            )}

                            {/* Content Type */}
                            <div className="cs-drawer__content-type">
                                <span>Content Type: <strong>{contentStyle}</strong></span>
                            </div>
                        </div>
                    </div>

                    {/* ── Bottom CTA Bar ── */}
                    <div className="cs-drawer__cta-bar">
                        <button
                            className="cs-btn cs-btn--primary"
                            onClick={() => onGenerate ? onGenerate('script', detail) : setShowScriptGen(true)}
                        >
                            Generate Script
                        </button>
                        <button
                            className="cs-btn cs-btn--ghost"
                            onClick={() => onGenerate ? onGenerate('caption', detail) : setShowCaptionGen(true)}
                        >
                            Generate Caption
                        </button>
                        <button
                            className="cs-btn cs-btn--ghost"
                            onClick={() => onGenerate ? onGenerate('thumbnail', detail) : null}
                        >
                            Open Image Editor
                        </button>
                        <button
                            className="cs-btn cs-btn--icon"
                            onClick={() => onCopy?.(detail)}
                            title="Copy idea"
                        >
                            📋
                        </button>
                    </div>
                </div>
            </div>

            {/* Modals opened from drawer */}
            {showScriptGen && (
                <ScriptGenerator
                    ideaId={detail?.id || idea?.id || ''}
                    ideaTitle={detail?.title || detail?.suggested_title || ''}
                    hook={hook}
                    accountUrl={accountUrl}
                    onClose={() => setShowScriptGen(false)}
                    onCopy={() => console.log('Script copied')}
                />
            )}
            {showCaptionGen && (
                <CaptionGenerator
                    ideaId={detail?.id || idea?.id || ''}
                    ideaTitle={detail?.title || detail?.suggested_title || ''}
                    accountUrl={accountUrl}
                    onClose={() => setShowCaptionGen(false)}
                    onCopy={() => console.log('Caption copied')}
                />
            )}
        </>
    )
}
