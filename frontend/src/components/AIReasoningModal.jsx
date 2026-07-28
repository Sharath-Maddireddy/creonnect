/**
 * Screen 10 — AI Reasoning Modal
 *
 * Shows a transparent breakdown of how the opportunity score was computed.
 */

import { useEffect, useMemo, useState } from 'react'

const FACTOR_LABELS = {
    niche_relevance: { label: 'Niche Relevance', icon: '🎯' },
    competitive_score: { label: 'Competitive Score', icon: '⚔️' },
    audience_match: { label: 'Audience Match', icon: '👥' },
    post_performance: { label: 'Post Performance', icon: '📈' },
    best_timing: { label: 'Best Timing', icon: '🕐' },
    momentum_score: { label: 'Trend Momentum', icon: '📈' },
    content_type_match: { label: 'Content Fit', icon: '🎬' },
}

function buildDeterministicFallback(score) {
    const safeScore = Math.round(Math.max(0, Math.min(100, score || 0)))
    const factors = [
        { key: 'niche_relevance', value: Math.min(100, Math.round(safeScore * 0.86)), tooltip: 'How well this topic aligns with your content niche' },
        { key: 'competitive_score', value: Math.min(100, Math.round(safeScore * 0.7)), tooltip: 'Lower is better — less competition for this topic' },
        { key: 'audience_match', value: Math.min(100, Math.round(safeScore * 0.9)), tooltip: 'How well this trend matches your audience interests' },
        { key: 'post_performance', value: Math.min(100, Math.round(safeScore * 0.68)), tooltip: 'Your past performance on similar content' },
        { key: 'best_timing', value: Math.min(100, Math.round(safeScore * 0.76)), tooltip: 'How optimal the posting time is for this content type' },
    ]
    const strongest = factors.reduce((best, factor) => !best || factor.value > best.value ? factor : best, null)
    const weakest = factors.reduce((best, factor) => !best || factor.value < best.value ? factor : best, null)
    return {
        opportunity_score: safeScore,
        factors,
        ai_confidence_pct: Math.max(55, Math.min(95, Math.round(58 + safeScore * 0.35))),
        percentile_rank: Math.max(1, Math.min(99, Math.round(100 - safeScore))),
        strongest_factor: strongest?.key || null,
        weakest_factor: weakest?.key || null,
        summary_explanation: 'Detailed score metadata is unavailable for this draft, so we are showing a conservative breakdown based on the overall score.',
    }
}

export default function AIReasoningModal({ ideaId, accountUrl, opportunityScore, onClose }) {
    const [reasoning, setReasoning] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [animated, setAnimated] = useState(false)

    useEffect(() => {
        let cancelled = false

        if (!ideaId || ideaId.startsWith('trend-')) {
            setReasoning(buildDeterministicFallback(opportunityScore || 75))
            setTimeout(() => setAnimated(true), 100)
            return () => { cancelled = true }
        }

        setLoading(true)
        setError(null)

        fetch(`${accountUrl}/ideas/${ideaId}/reasoning`, { credentials: 'include' })
            .then(r => r.ok ? r.json() : Promise.reject(r))
            .then(d => {
                if (cancelled) return
                setReasoning(d && typeof d === 'object' ? d : buildDeterministicFallback(opportunityScore || 75))
                setTimeout(() => setAnimated(true), 100)
            })
            .catch(() => {
                if (cancelled) return
                setReasoning(buildDeterministicFallback(opportunityScore || 75))
                setError('Showing fallback reasoning because the detailed explanation could not be loaded.')
                setTimeout(() => setAnimated(true), 100)
            })
            .finally(() => {
                if (!cancelled) setLoading(false)
            })

        return () => { cancelled = true }
    }, [ideaId, accountUrl, opportunityScore])

    const score = reasoning?.opportunity_score ?? opportunityScore ?? 0
    const band = score >= 80 ? 'High' : score >= 60 ? 'Good' : score >= 40 ? 'Moderate' : 'Low'
    const percentileText = typeof reasoning?.percentile_rank === 'number'
        ? `Top ${reasoning.percentile_rank}% Ideas`
        : null

    const strongestLabel = useMemo(() => {
        const meta = FACTOR_LABELS[reasoning?.strongest_factor]
        return meta?.label || null
    }, [reasoning?.strongest_factor])

    const weakestLabel = useMemo(() => {
        const meta = FACTOR_LABELS[reasoning?.weakest_factor]
        return meta?.label || null
    }, [reasoning?.weakest_factor])

    return (
        <div className="cs-modal-overlay cs-modal-overlay--open" onClick={onClose}>
            <div className="cs-modal cs-reasoning-modal" onClick={e => e.stopPropagation()}>
                <div className="cs-modal__header">
                    <h2>Why This Score?</h2>
                    <button className="cs-modal__close" onClick={onClose}>✕</button>
                </div>

                <div className="cs-reasoning__score-header">
                    <div className="cs-reasoning__score-circle">
                        <span className="cs-reasoning__score-number">{Math.round(score || 0)}</span>
                        <span className="cs-reasoning__score-divider">/</span>
                        <span className="cs-reasoning__score-max">100</span>
                    </div>
                    <div className="cs-reasoning__band">
                        <span className={`cs-badge cs-badge--${band.toLowerCase()}`}>{band}</span>
                        {percentileText && <span className="cs-reasoning__percentile">{percentileText}</span>}
                    </div>
                </div>

                <div className="cs-reasoning__body">
                    {loading && (
                        <div className="cs-reasoning__skeleton">
                            {[1, 2, 3, 4, 5].map(i => (
                                <div key={i} className="cs-reasoning__bar-skel">
                                    <div className="cs-skeleton cs-skeleton--text" style={{ width: '30%' }} />
                                    <div className="cs-skeleton cs-skeleton--text" style={{ width: '100%', height: '8px' }} />
                                </div>
                            ))}
                        </div>
                    )}

                    {error && (
                        <div className="cs-reasoning__error">
                            <p>{error}</p>
                        </div>
                    )}

                    {!loading && reasoning?.summary_explanation && (
                        <div className="cs-reasoning__summary">
                            <p>{reasoning.summary_explanation}</p>
                            {(strongestLabel || weakestLabel) && (
                                <p>
                                    {strongestLabel && <span><strong>Strongest:</strong> {strongestLabel}</span>}
                                    {strongestLabel && weakestLabel ? ' · ' : ''}
                                    {weakestLabel && <span><strong>Weakest:</strong> {weakestLabel}</span>}
                                </p>
                            )}
                        </div>
                    )}

                    {!loading && Array.isArray(reasoning?.factors) && reasoning.factors.length > 0 && (
                        <div className="cs-reasoning__factors">
                            <h4 className="cs-reasoning__factors-title">Contributing Factors</h4>
                            {reasoning.factors.map((factor, i) => {
                                const meta = FACTOR_LABELS[factor.key] || { label: factor.key, icon: '📊' }
                                return (
                                    <div
                                        key={factor.key}
                                        className={`cs-reasoning__factor ${animated ? 'cs-reasoning__factor--anim' : ''}`}
                                        style={{ animationDelay: `${i * 80}ms` }}
                                        title={factor.tooltip || `${meta.label}: score driven by algorithmic analysis`}
                                    >
                                        <div className="cs-reasoning__factor-header">
                                            <span className="cs-reasoning__factor-icon">{meta.icon}</span>
                                            <span className="cs-reasoning__factor-label">{meta.label}</span>
                                            <span className="cs-reasoning__factor-value">{factor.value}/100</span>
                                        </div>
                                        <div className="cs-reasoning__factor-bar">
                                            <div
                                                className="cs-reasoning__factor-fill"
                                                style={{ '--target-width': `${Math.round(factor.value)}%` }}
                                            />
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </div>

                {!loading && reasoning && typeof reasoning.ai_confidence_pct === 'number' && (
                    <div className="cs-reasoning__confidence">
                        <div className="cs-reasoning__confidence-bar">
                            <span className="cs-reasoning__confidence-label">AI Confidence</span>
                            <span className="cs-reasoning__confidence-value">{reasoning.ai_confidence_pct}%</span>
                        </div>
                        <div className="cs-reasoning__confidence-track">
                            <div className="cs-reasoning__confidence-fill" style={{ width: `${reasoning.ai_confidence_pct}%` }} />
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
