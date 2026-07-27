/**
 * Screen 3 — Caption Editor
 *
 * Full redesign per PRD: platform tabs, variants panel,
 * hashtag chips, emoji row, tone/length controls.
 */

import { useState, useCallback } from 'react'

const PLATFORMS = [
    { id: 'instagram', icon: '📸', label: 'Instagram', charLimit: 2200 },
    { id: 'tiktok', icon: '🎵', label: 'TikTok', charLimit: 300 },
    { id: 'linkedin', icon: '💼', label: 'LinkedIn', charLimit: 1200 },
    { id: 'youtube', icon: '▶️', label: 'YouTube', charLimit: 5000 },
]

const TONES = ['Friendly', 'Professional', 'Witty', 'Emotional', 'Luxury']
const LENGTHS = ['Short', 'Medium', 'Long']

const EMOJIS = ['✨', '🔥', '💄', '👰', '💫', '❤️', '🌟', '💕', '🎉', '📸', '💋', '🎬', '😍', '💎', '🤍', '🫶', '😊', '💝', '🌈', '⚡']

export default function CaptionEditor({ ideaId, ideaTitle, hook: initialHook, accountUrl, onClose }) {
    const [platform, setPlatform] = useState('instagram')
    const [caption, setCaption] = useState('')
    const [hashtags, setHashtags] = useState([])
    const [hashtagInput, setHashtagInput] = useState('')
    const [tone, setTone] = useState('Friendly')
    const [length, setLength] = useState('Medium')
    const [variants, setVariants] = useState([])
    const [loading, setLoading] = useState(false)
    const [regenerating, setRegenerating] = useState(false)
    const [copied, setCopied] = useState(null)

    const activePlatform = PLATFORMS.find(p => p.id === platform) || PLATFORMS[0]

    const handleGenerate = useCallback(async () => {
        setLoading(true)
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const r = await fetch(`${baseUrl}/trends/generate-caption`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    idea_id: ideaId,
                    platforms: [platform],
                    tone: tone.toLowerCase(),
                    language: 'en',
                    include_hashtags: true,
                    max_hashtags: 30,
                }),
            })
            if (r.ok) {
                const data = await r.json()
                const cap = data.captions?.[0]
                if (cap) {
                    setCaption(cap.caption_text || '')
                    setHashtags(cap.hashtags || [])
                }
            }

            // Fetch variants
            const v = await fetch(`${baseUrl}/ideas/${ideaId}/caption/variants`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ count: 4, styles: ['short', 'storytelling', 'question', 'emotional'] }),
            })
            if (v.ok) {
                const vData = await v.json()
                setVariants(vData.variants || [])
            }
        } catch (e) {
            console.error('Caption generation failed:', e)
        } finally {
            setLoading(false)
        }
    }, [accountUrl, ideaId, platform, tone])

    const handleRegenerate = () => {
        setRegenerating(true)
        handleGenerate().finally(() => setRegenerating(false))
    }

    const handleAddHashtag = () => {
        if (hashtagInput.trim() && hashtags.length < 30) {
            const tag = hashtagInput.trim().replace(/^#/, '')
            if (!hashtags.includes(`#${tag}`)) {
                setHashtags(prev => [...prev, `#${tag}`])
            }
            setHashtagInput('')
        }
    }

    const handleRemoveHashtag = (tag) => {
        setHashtags(prev => prev.filter(t => t !== tag))
    }

    const handleCopy = (type) => {
        if (type === 'caption') {
            navigator.clipboard?.writeText(caption)
        } else if (type === 'hashtags') {
            navigator.clipboard?.writeText(hashtags.join(' '))
        }
        setCopied(type)
        setTimeout(() => setCopied(null), 2000)
    }

    const applyVariant = (variant) => {
        setCaption(variant.caption_text || '')
        setHashtags(variant.hashtags || [])
    }

    return (
        <div className="cs-modal-overlay cs-modal-overlay--open" onClick={onClose}>
            <div className="cs-modal cs-caption-editor" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="cs-caption-editor__header">
                    <button className="cs-btn cs-btn--ghost" onClick={onClose}>← Back</button>
                    <span className="cs-caption-editor__title">Caption Editor</span>
                    <button
                        className="cs-btn cs-btn--ghost"
                        onClick={handleRegenerate}
                        disabled={regenerating || loading}
                    >
                        {regenerating ? 'Regenerating...' : '☁ Regenerate'}
                    </button>
                </div>

                <div className="cs-caption-editor__body">
                    {/* Platform Tabs */}
                    <div className="cs-caption-editor__tabs">
                        {PLATFORMS.map(p => (
                            <button
                                key={p.id}
                                className={`cs-caption-editor__tab ${platform === p.id ? 'cs-caption-editor__tab--active' : ''}`}
                                onClick={() => setPlatform(p.id)}
                            >
                                <span>{p.icon}</span>
                                <span>{p.label}</span>
                            </button>
                        ))}
                    </div>

                    <div className="cs-caption-editor__main">
                        {/* Left: Caption Input */}
                        <div className="cs-caption-editor__input-section">
                            {loading ? (
                                <div className="cs-caption-editor__skeleton">
                                    <div className="cs-skeleton cs-skeleton--text" style={{ height: '200px', width: '100%' }} />
                                </div>
                            ) : (
                                <>
                                    <textarea
                                        className="cs-caption-editor__textarea"
                                        value={caption}
                                        onChange={e => setCaption(e.target.value)}
                                        placeholder={`Write a ${tone.toLowerCase()} caption for your ${platform} post...`}
                                        rows={10}
                                    />
                                    <div className="cs-caption-editor__char-count">
                                        {caption.length} / {activePlatform.charLimit.toLocaleString()}
                                    </div>
                                </>
                            )}

                            {/* Hashtags */}
                            <div className="cs-caption-editor__hashtags-section">
                                <div className="cs-caption-editor__hashtags-header">
                                    <span className="cs-caption-editor__hashtags-label">
                                        HASHTAGS ({hashtags.length}/30)
                                    </span>
                                </div>
                                <div className="cs-caption-editor__hashtags">
                                    {hashtags.map((tag, i) => (
                                        <span key={i} className="cs-hashtag-chip cs-hashtag-chip--removable">
                                            {tag}
                                            <button onClick={() => handleRemoveHashtag(tag)}>×</button>
                                        </span>
                                    ))}
                                    <div className="cs-caption-editor__hashtag-add">
                                        <input
                                            type="text"
                                            value={hashtagInput}
                                            onChange={e => setHashtagInput(e.target.value)}
                                            onKeyDown={e => e.key === 'Enter' && handleAddHashtag()}
                                            placeholder="#"
                                            className="cs-caption-editor__hashtag-input"
                                        />
                                        <button onClick={handleAddHashtag} className="cs-caption-editor__hashtag-add-btn">+ Add</button>
                                    </div>
                                </div>
                                <button
                                    className="cs-btn cs-btn--ghost cs-caption-editor__copy-hashtags"
                                    onClick={() => handleCopy('hashtags')}
                                >
                                    {copied === 'hashtags' ? '✓ Copied' : 'Copy Hashtags'}
                                </button>
                            </div>
                        </div>

                        {/* Middle: Variants */}
                        <div className="cs-caption-editor__variants">
                            <div className="cs-caption-editor__variants-header">
                                <span>VARIANTS</span>
                                <button className="cs-btn cs-btn--link">View All</button>
                            </div>
                            {variants.length === 0 && !loading && (
                                <p className="cs-caption-editor__variants-empty">Generate a caption to see variants</p>
                            )}
                            {variants.map((v, i) => (
                                <div
                                    key={i}
                                    className="cs-variant-card"
                                    onClick={() => applyVariant(v)}
                                >
                                    <div className="cs-variant-card__style">
                                        <span className="cs-variant-card__style-dot" />
                                        {v.style || `Variant ${i + 1}`}
                                    </div>
                                    <p className="cs-variant-card__text">{v.caption_text?.slice(0, 100)}{(v.caption_text?.length || 0) > 100 ? '...' : ''}</p>
                                </div>
                            ))}
                        </div>

                        {/* Right: Controls */}
                        <div className="cs-caption-editor__controls">
                            {/* Emoji Row */}
                            <div className="cs-caption-editor__emoji-row">
                                <span className="cs-caption-editor__section-label">EMOJI</span>
                                <div className="cs-caption-editor__emoji-list">
                                    {EMOJIS.map((emoji, i) => (
                                        <button
                                            key={i}
                                            className="cs-emoji-btn"
                                            onClick={() => setCaption(prev => prev + emoji)}
                                        >
                                            {emoji}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Tone */}
                            <div className="cs-caption-editor__control-group">
                                <label className="cs-caption-editor__section-label">Tone</label>
                                <select
                                    className="cs-select"
                                    value={tone}
                                    onChange={e => setTone(e.target.value)}
                                >
                                    {TONES.map(t => (
                                        <option key={t} value={t}>{t}</option>
                                    ))}
                                </select>
                            </div>

                            {/* Length */}
                            <div className="cs-caption-editor__control-group">
                                <label className="cs-caption-editor__section-label">Length</label>
                                <select
                                    className="cs-select"
                                    value={length}
                                    onChange={e => setLength(e.target.value)}
                                >
                                    {LENGTHS.map(l => (
                                        <option key={l} value={l}>{l}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="cs-caption-editor__footer">
                    <button
                        className="cs-btn cs-btn--ghost"
                        onClick={() => handleCopy('caption')}
                    >
                        {copied === 'caption' ? '✓ Copied' : 'Copy Caption'}
                    </button>
                    <button
                        className="cs-btn cs-btn--ghost"
                        onClick={() => handleCopy('hashtags')}
                    >
                        {copied === 'hashtags' ? '✓ Copied' : 'Copy Hashtags'}
                    </button>
                    <button className="cs-btn cs-btn--primary">
                        Save Caption
                    </button>
                </div>
            </div>
        </div>
    )
}
