/**
 * Screen 4 — Thumbnail Generator
 *
 * Shows 4 AI-generated thumbnail concept options the creator can select,
 * download, or use as a creative brief.
 */

import { useState, useEffect } from 'react'

export default function ThumbnailGenerator({ ideaId, ideaTitle, accountUrl, onClose, onUseThumbnail }) {
    const [thumbnails, setThumbnails] = useState([])
    const [selected, setSelected] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)
    const [downloading, setDownloading] = useState(null)

    const fetchThumbnails = async () => {
        setLoading(true)
        setError(null)
        try {
            const r = await fetch(`${accountUrl}/ideas/${ideaId}/generate-thumbnails`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            })
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            const data = await r.json()
            setThumbnails(data.thumbnails || [])
            if ((data.thumbnails || []).length > 0) {
                setSelected(data.thumbnails[0])
            }
        } catch (e) {
            setError(e.message)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => { fetchThumbnails() }, [ideaId])

    const handleDownload = (type) => {
        if (!selected) return
        setDownloading(type)
        setTimeout(() => setDownloading(null), 1500)

        if (type === 'image') {
            const a = document.createElement('a')
            a.href = selected.image_url
            a.download = `${selected.label || 'thumbnail'}.png`
            a.click()
        } else if (type === 'prompt') {
            const blob = new Blob([selected.prompt], { type: 'text/plain' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `${selected.label || 'prompt'}.txt`
            a.click()
            URL.revokeObjectURL(url)
        }
    }

    return (
        <div className="cs-modal-overlay cs-modal-overlay--open" onClick={onClose}>
            <div className="cs-modal cs-thumbnail-modal" onClick={e => e.stopPropagation()}>
                <div className="cs-modal__header">
                    <button className="cs-btn cs-btn--ghost" onClick={onClose}>← Back to Idea Details</button>
                    <button
                        className="cs-btn cs-btn--ghost"
                        onClick={fetchThumbnails}
                        disabled={loading}
                    >
                        {loading ? 'Generating...' : 'Regenerate'}
                    </button>
                </div>

                <div className="cs-thumbnail__content">
                    <p className="cs-thumbnail__instruction">Choose your preferred thumbnail</p>

                    {loading && (
                        <div className="cs-thumbnail__grid">
                            {[1, 2, 3, 4].map(i => (
                                <div key={i} className="cs-thumbnail__card cs-thumbnail__card--skeleton">
                                    <div className="cs-skeleton cs-skeleton--thumb" style={{ height: '100%', minHeight: '200px' }} />
                                    <div className="cs-skeleton cs-skeleton--text" style={{ width: '70%', margin: '0.5rem auto' }} />
                                </div>
                            ))}
                            <p className="cs-thumbnail__loading-msg">Generating thumbnails…</p>
                        </div>
                    )}

                    {error && (
                        <div className="cs-thumbnail__error">
                            <p>Couldn't generate thumbnails</p>
                            <button className="cs-btn cs-btn--primary" onClick={fetchThumbnails}>Retry</button>
                        </div>
                    )}

                    {!loading && !error && (
                        <div className="cs-thumbnail__grid">
                            {thumbnails.map((thumb, i) => (
                                <div
                                    key={thumb.id || i}
                                    className={`cs-thumbnail__card ${selected?.id === thumb.id ? 'cs-thumbnail__card--selected' : ''}`}
                                    onClick={() => setSelected(thumb)}
                                >
                                    <div className="cs-thumbnail__img-wrap">
                                        <img
                                            src={thumb.image_url}
                                            alt={thumb.label}
                                            className="cs-thumbnail__img"
                                            onError={(e) => { e.target.style.display = 'none' }}
                                        />
                                        <div className="cs-thumbnail__img-fallback">
                                            <span>🎬</span>
                                        </div>
                                    </div>
                                    <span className="cs-thumbnail__label">{thumb.label}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Action bar */}
                {!loading && !error && thumbnails.length > 0 && (
                    <div className="cs-thumbnail__actions">
                        <button
                            className="cs-btn cs-btn--ghost"
                            onClick={() => handleDownload('image')}
                            disabled={!selected || downloading}
                        >
                            {downloading === 'image' ? '✓ Downloaded' : 'Download'}
                        </button>
                        <button
                            className="cs-btn cs-btn--ghost"
                            onClick={() => handleDownload('prompt')}
                            disabled={!selected || downloading}
                        >
                            {downloading === 'prompt' ? '✓ Downloaded' : 'Download Prompt'}
                        </button>
                        <button
                            className="cs-btn cs-btn--primary"
                            onClick={() => onUseThumbnail?.(selected)}
                            disabled={!selected}
                        >
                            Use This Thumbnail
                        </button>
                    </div>
                )}
            </div>
        </div>
    )
}
