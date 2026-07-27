/**
 * Screen 9 — Niche Details Panel
 *
 * Expanded panel showing creator's niche breakdown with confidence,
 * sub-niches, AI explanation, and content style scoring.
 */

import { useState, useEffect } from 'react'

export default function NicheDetailPanel({ accountUrl, onClose, onRefresh }) {
    const [niche, setNiche] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [confidenceAnim, setConfidenceAnim] = useState(false)

    useEffect(() => {
        setLoading(true)
        fetch(`${accountUrl}/niche`, { credentials: 'include' })
            .then(r => r.ok ? r.json() : Promise.reject(r))
            .then(d => {
                setNiche(d)
                setTimeout(() => setConfidenceAnim(true), 200)
            })
            .catch(e => setError(e.message))
            .finally(() => setLoading(false))
    }, [accountUrl])

    const handleRefresh = async () => {
        setLoading(true)
        setConfidenceAnim(false)
        try {
            const r = await fetch(`${accountUrl}/niche`, { credentials: 'include' })
            const d = await r.json()
            setNiche(d)
            setTimeout(() => setConfidenceAnim(true), 200)
        } catch (e) {
            setError(e.message)
        } finally {
            setLoading(false)
        }
        onRefresh?.()
    }

    if (loading) {
        return (
            <div className="cs-niche-panel">
                <div className="cs-niche-panel__header">
                    <h3>Niche Detected</h3>
                    <button className="cs-modal__close" onClick={onClose}>✕</button>
                </div>
                <div className="cs-niche-panel__skeleton">
                    <div className="cs-skeleton cs-skeleton--text" style={{ width: '50%', height: '28px' }} />
                    <div className="cs-skeleton cs-skeleton--text" style={{ width: '80%', marginTop: '1rem' }} />
                    <div className="cs-skeleton cs-skeleton--text" style={{ width: '100%' }} />
                    <div className="cs-skeleton cs-skeleton--text" style={{ width: '100%' }} />
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div className="cs-niche-panel">
                <div className="cs-niche-panel__header">
                    <h3>Niche Detected</h3>
                    <button className="cs-modal__close" onClick={onClose}>✕</button>
                </div>
                <div className="cs-niche-panel__error">
                    <p>Couldn't load niche analysis</p>
                    <button className="cs-btn cs-btn--primary" onClick={handleRefresh}>Retry</button>
                </div>
            </div>
        )
    }

    return (
        <div className="cs-niche-panel">
            <div className="cs-niche-panel__header">
                <h3>Niche Detected</h3>
                <button className="cs-modal__close" onClick={onClose}>✕</button>
            </div>

            <div className="cs-niche-panel__body">
                {/* Primary niche */}
                <div className="cs-niche-panel__primary">
                    <h2>{niche?.primary_niche || 'Creator'}</h2>
                </div>

                {/* Sub-niches */}
                {niche?.sub_niches?.length > 0 && (
                    <div className="cs-niche-panel__subs">
                        {niche.sub_niches.map((sub, i) => (
                            <span key={i} className="cs-niche-panel__sub-chip">{sub.name}</span>
                        ))}
                    </div>
                )}

                {/* Confidence bar */}
                <div className="cs-niche-panel__confidence">
                    <div className="cs-niche-panel__confidence-header">
                        <span>Confidence</span>
                        <span className="cs-niche-panel__confidence-value">
                            {Math.round((niche?.confidence_score || 0) * 100)}%
                        </span>
                    </div>
                    <div className="cs-niche-panel__confidence-track">
                        <div
                            className="cs-niche-panel__confidence-fill"
                            style={{
                                width: confidenceAnim ? `${Math.round((niche?.confidence_score || 0) * 100)}%` : '0%',
                            }}
                        />
                    </div>
                </div>

                {/* Warning for low confidence */}
                {niche?.confidence_score < 0.5 && (
                    <div className="cs-niche-panel__warning">
                        ⚠️ Not enough posts to detect niche reliably
                    </div>
                )}

                {/* Explanation */}
                <div className="cs-niche-panel__explanation">
                    <h4>Why this niche?</h4>
                    <p>{niche?.explanation || 'Based on your recent content patterns.'}</p>
                </div>

                {/* Content Style */}
                <div className="cs-niche-panel__style">
                    <h4>Content Style</h4>
                    <p>{niche?.content_style_summary || 'Creates engaging content.'}</p>
                </div>

                {/* Strengths */}
                {niche?.creator_strengths?.length > 0 && (
                    <div className="cs-niche-panel__strengths">
                        <h4>Creator Strengths</h4>
                        <div className="cs-niche-panel__strength-list">
                            {niche.creator_strengths.map((s, i) => (
                                <span key={i} className="cs-niche-panel__strength-item">✓ {s}</span>
                            ))}
                        </div>
                    </div>
                )}

                {/* Refresh button */}
                <button
                    className="cs-btn cs-btn--ghost cs-niche-panel__refresh"
                    onClick={handleRefresh}
                    disabled={loading}
                >
                    {loading ? 'Refreshing...' : '🔄 Refresh Niche Analysis'}
                </button>
            </div>
        </div>
    )
}
