import { useState } from 'react'

const PLATFORMS = ['instagram', 'tiktok', 'linkedin']
const TONES = ['friendly', 'professional', 'funny', 'educational', 'luxury']
const LANGUAGES = ['en', 'hi', 'es', 'fr', 'de']

const TIPS = [
    'Open with a strong hook',
    'Add question to increase engagement',
    'Use emoji to increase engagement',
    'Add trending hashtags',
    'Keep it concise and scannable',
]

export default function CaptionGenerator({ ideaId, ideaTitle, hook, accountUrl, onClose, onCopy }) {
    const [platform, setPlatform] = useState('instagram')
    const [tone, setTone] = useState('friendly')
    const [language, setLanguage] = useState('en')
    const [includeHashtags, setIncludeHashtags] = useState(true)
    const [maxHashtags, setMaxHashtags] = useState(10)
    const [captions, setCaptions] = useState(null)
    const [activeCaption, setActiveCaption] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    const handleGenerate = async () => {
        setLoading(true)
        setError(null)
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const res = await fetch(`${baseUrl}/trends/generate-caption`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    idea_id: ideaId,
                    platforms: [platform],
                    tone,
                    language,
                    include_hashtags: includeHashtags,
                    max_hashtags: maxHashtags,
                }),
            })
            if (res.ok) {
                const data = await res.json()
                setCaptions(data.captions)
                setActiveCaption(data.captions[0])
            } else {
                const err = await res.json().catch(() => ({ detail: 'Generation failed' }))
                setError(err.detail || 'Failed to generate caption')
            }
        } catch (e) {
            console.error('Caption generation failed:', e)
            setError('Network error. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    const handleCopy = () => {
        if (activeCaption?.caption_text) {
            navigator.clipboard.writeText(activeCaption.caption_text)
            onCopy?.()
        }
    }

    return (
        <div className="cs-modal-backdrop" onClick={onClose}>
            <div className="cs-modal cs-modal--caption" onClick={e => e.stopPropagation()}>
                <div className="cs-modal__header">
                    <button className="cs-modal__back" onClick={onClose}>← Back to Idea Details</button>
                    <h3>Caption Generator</h3>
                    <p className="cs-modal__subtitle">Create engaging caption for: {ideaTitle}</p>
                </div>

                <div className="cs-modal__body">
                    {error && (
                        <div className="cs-error">{error}</div>
                    )}

                    {!captions ? (
                        <>
                            {/* Platform */}
                            <div className="cs-form-group">
                                <label className="cs-form-label">Platform</label>
                                <div className="cs-chip-group">
                                    {PLATFORMS.map(p => (
                                        <button
                                            key={p}
                                            className={`cs-chip ${platform === p ? 'cs-chip--active' : ''}`}
                                            onClick={() => setPlatform(p)}
                                        >
                                            {p}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Settings */}
                            <div className="cs-form-row">
                                <div className="cs-form-group">
                                    <label className="cs-form-label">Tone</label>
                                    <select className="cs-form-select" value={tone} onChange={e => setTone(e.target.value)}>
                                        {TONES.map(t => <option key={t} value={t}>{t}</option>)}
                                    </select>
                                </div>
                                <div className="cs-form-group">
                                    <label className="cs-form-label">Language</label>
                                    <select className="cs-form-select" value={language} onChange={e => setLanguage(e.target.value)}>
                                        {LANGUAGES.map(l => <option key={l} value={l}>{l}</option>)}
                                    </select>
                                </div>
                            </div>

                            {/* Hashtag Options */}
                            <div className="cs-form-group">
                                <label className="cs-checkbox">
                                    <input
                                        type="checkbox"
                                        checked={includeHashtags}
                                        onChange={e => setIncludeHashtags(e.target.checked)}
                                    />
                                    <span>Include Hashtags</span>
                                </label>
                                {includeHashtags && (
                                    <div className="cs-form-group cs-form-group--nested">
                                        <label className="cs-form-label">Max Hashtags: {maxHashtags}</label>
                                        <input
                                            type="range"
                                            className="cs-form-range"
                                            min="0"
                                            max="30"
                                            value={maxHashtags}
                                            onChange={e => setMaxHashtags(parseInt(e.target.value))}
                                        />
                                    </div>
                                )}
                            </div>

                            {/* Tips */}
                            <div className="cs-tips">
                                <h4>Caption Tips</h4>
                                <ul>
                                    {TIPS.map((tip, i) => (
                                        <li key={i}>{tip}</li>
                                    ))}
                                </ul>
                            </div>

                            <button
                                className="cs-btn cs-btn--primary cs-btn--full"
                                onClick={handleGenerate}
                                disabled={loading}
                            >
                                {loading ? 'Generating...' : 'Generate Caption'}
                            </button>
                        </>
                    ) : (
                        <>
                            {/* Generated Caption */}
                            <div className="cs-caption-preview">
                                <p className="cs-caption-text">{activeCaption?.caption_text}</p>
                            </div>

                            <div className="cs-caption-meta">
                                <span>Characters: {activeCaption?.character_count}</span>
                                <span>Hashtags: {activeCaption?.hashtag_count}</span>
                            </div>

                            {/* Tips Applied */}
                            {activeCaption?.tips_applied?.length > 0 && (
                                <div className="cs-tips cs-tips--applied">
                                    <h4>Tips Applied</h4>
                                    <ul>
                                        {activeCaption.tips_applied.map((tip, i) => (
                                            <li key={i}>{tip}</li>
                                        ))}
                                    </ul>
                                </div>
                            )}

                            <div className="cs-form-row">
                                <button className="cs-btn cs-btn--secondary" onClick={() => { setCaptions(null); setActiveCaption(null) }}>
                                    Regenerate
                                </button>
                                <button className="cs-btn cs-btn--primary" onClick={handleCopy}>
                                    Copy Caption
                                </button>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    )
}
