import { useState } from 'react'

const SCRIPT_TYPES = [
    { id: 'viral', label: 'Viral Script', description: 'Punchy, fast-paced, hook-first' },
    { id: 'natural', label: 'Natural Script', description: 'Conversational, authentic' },
    { id: 'story', label: 'Story Script', description: 'Narrative, emotional arc' },
]

const FORMAT_OPTIONS = {
    reel: SCRIPT_TYPES,
    carousel: [
        { id: 'educational', label: 'Educational Carousel', description: 'Teach one idea slide by slide' },
        { id: 'checklist', label: 'Checklist Carousel', description: 'Saveable steps and frameworks' },
        { id: 'story', label: 'Story Carousel', description: 'A narrative with a clear takeaway' },
    ],
    photo: [
        { id: 'editorial', label: 'Editorial Photo', description: 'A polished single-image post' },
        { id: 'behind_the_scenes', label: 'Behind the Scenes', description: 'An authentic process-focused image' },
        { id: 'quote', label: 'Quote Graphic', description: 'A text-led, saveable visual' },
    ],
}

const TONES = ['friendly', 'professional', 'funny', 'educational', 'luxury']
const LANGUAGES = ['en', 'hi', 'es', 'fr', 'de']

function buildProductionSections(script) {
    if (!script) return null

    const scenes = Array.isArray(script.scenes) ? script.scenes : []
    const spokenLines = [
        script.hook ? `Hook: ${script.hook}` : null,
        ...scenes.map(scene => scene?.description).filter(Boolean),
        script.cta ? `CTA: ${script.cta}` : null,
    ].filter(Boolean)

    const onScreenText = [
        script.hook || null,
        ...scenes.map(scene => scene?.description).filter(Boolean),
        script.cta || null,
    ].filter(Boolean)

    const shotList = scenes.map(scene => ({
        id: scene.scene_number,
        timeRange: scene.time_range,
        title: scene.description,
        visual: scene.visual_notes || 'Use a direct-to-camera or illustrative supporting shot.',
    }))

    return {
        spokenLines,
        onScreenText,
        shotList,
        cta: script.cta,
    }
}

export default function ScriptGenerator({ ideaId, ideaTitle, hook, contentType = 'reel', previewOnly = false, previewScript = null, accountUrl, onClose, onCopy }) {
    const normalizedContentType = FORMAT_OPTIONS[contentType] ? contentType : 'reel'
    const formatOptions = FORMAT_OPTIONS[normalizedContentType]
    const formatLabel = normalizedContentType === 'carousel' ? 'Carousel Plan' : normalizedContentType === 'photo' ? 'Photo Creative Brief' : 'Script Generator'
    const [scriptType, setScriptType] = useState(formatOptions[0].id)
    const [tone, setTone] = useState('friendly')
    const [language, setLanguage] = useState('en')
    const [duration, setDuration] = useState(60)
    const [script, setScript] = useState(previewOnly ? previewScript : null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    const handleGenerate = async () => {
        if (previewOnly) {
            setScript(previewScript)
            return
        }
        setLoading(true)
        setError(null)
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const res = await fetch(`${baseUrl}/trends/generate-script`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    idea_id: ideaId,
                    script_type: scriptType,
                    tone,
                    language,
                    duration_seconds: normalizedContentType === 'reel' ? duration : 15,
                }),
            })
            if (res.ok) {
                const data = await res.json()
                setScript(data)
            } else {
                const err = await res.json().catch(() => ({ detail: 'Generation failed' }))
                const errMsg = err.detail || `Failed to generate script (status ${res.status})`
                if (res.status === 404) {
                    setError('Idea not found in the database yet. Save it or generate full ideas first, then generate a script from it.')
                } else {
                    setError(errMsg)
                }
            }
        } catch (e) {
            console.error('Script generation failed:', e)
            setError('Network error. Please try again.')
        } finally {
            setLoading(false)
        }
    }

    const handleCopy = () => {
        if (script?.full_script) {
            navigator.clipboard.writeText(script.full_script)
            onCopy?.()
        }
    }

    const productionSections = buildProductionSections(script)

    return (
        <div className="cs-modal-backdrop" onClick={onClose}>
            <div className="cs-modal cs-modal--script" onClick={e => e.stopPropagation()}>
                <div className="cs-modal__header">
                    <button className="cs-modal__back" onClick={onClose}>← Back to Idea Details</button>
                    <h3>{formatLabel}</h3>
                    <p className="cs-modal__subtitle">AI creates a {normalizedContentType} production plan for: {ideaTitle}</p>
                </div>

                <div className="cs-modal__body">
                    {error && (
                        <div className="cs-error">{error}</div>
                    )}

                    {previewOnly && script?.preview_note && (
                        <div className="cs-info-banner">{script.preview_note}</div>
                    )}

                    {!script ? (
                        <>
                            {/* Script Type */}
                            <div className="cs-form-group">
                                <label className="cs-form-label">{normalizedContentType === 'reel' ? 'Script Type' : 'Content Approach'}</label>
                                <div className="cs-radio-group">
                                    {formatOptions.map(type => (
                                        <label key={type.id} className="cs-radio">
                                            <input
                                                type="radio"
                                                name="scriptType"
                                                value={type.id}
                                                checked={scriptType === type.id}
                                                onChange={() => setScriptType(type.id)}
                                            />
                                            <span className="cs-radio__label">{type.label}</span>
                                            <span className="cs-radio__desc">{type.description}</span>
                                        </label>
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

                            {normalizedContentType === 'reel' && <div className="cs-form-group">
                                <label className="cs-form-label">Duration: {duration}s</label>
                                <input
                                    type="range"
                                    className="cs-form-range"
                                    min="15"
                                    max="180"
                                    step="5"
                                    value={duration}
                                    onChange={e => setDuration(parseInt(e.target.value))}
                                />
                            </div>}

                            <button
                                className="cs-btn cs-btn--primary cs-btn--full"
                                onClick={handleGenerate}
                                disabled={loading}
                            >
                                {loading ? 'Generating...' : normalizedContentType === 'carousel' ? 'Generate Slide Plan' : normalizedContentType === 'photo' ? 'Generate Photo Brief' : 'Generate Script'}
                            </button>
                        </>
                    ) : (
                        <>
                            {/* Script Preview */}
                            <div className="cs-script-preview">
                                <div className="cs-script-hook">
                                    <strong>Hook:</strong> "{script.hook}"
                                </div>
                                {script.scenes?.map(scene => (
                                    <div key={scene.scene_number} className="cs-script-scene">
                                        <div className="cs-script-scene__header">
                                            <span>{normalizedContentType === 'carousel' ? `Slide ${scene.scene_number}` : normalizedContentType === 'photo' ? 'Photo Direction' : `Scene ${scene.scene_number}`}</span>
                                            <span>{scene.time_range}</span>
                                        </div>
                                        <p>{scene.description}</p>
                                        {scene.visual_notes && (
                                            <small>Visual: {scene.visual_notes}</small>
                                        )}
                                    </div>
                                ))}
                                <div className="cs-script-cta">
                                    <strong>CTA:</strong> {script.cta}
                                </div>
                            </div>

                            <div className="cs-script-meta">
                                {normalizedContentType === 'reel' ? <span>Estimated Duration: {script.estimated_duration_sec}s</span> : <span>{normalizedContentType === 'carousel' ? 'Swipe-ready slide plan' : 'Single-image creative brief'}</span>}
                            </div>

                            {script.full_script && (
                                <div className="cs-script-full">
                                    <div className="cs-script-full__header">Full Script</div>
                                    <div className="cs-script-full__body">{script.full_script}</div>
                                </div>
                            )}

                            {productionSections && (
                                <div className="cs-script-production">
                                    <div className="cs-script-production__header">Creator Format</div>

                                    <div className="cs-script-production__section">
                                        <div className="cs-script-production__label">Voiceover / Spoken Lines</div>
                                        <div className="cs-script-production__list">
                                            {productionSections.spokenLines.map((line, index) => (
                                                <div key={`spoken-${index}`} className="cs-script-production__item">{line}</div>
                                            ))}
                                        </div>
                                    </div>

                                    <div className="cs-script-production__section">
                                        <div className="cs-script-production__label">On-Screen Text</div>
                                        <div className="cs-script-production__list">
                                            {productionSections.onScreenText.map((line, index) => (
                                                <div key={`text-${index}`} className="cs-script-production__item">{line}</div>
                                            ))}
                                        </div>
                                    </div>

                                    <div className="cs-script-production__section">
                                        <div className="cs-script-production__label">Shot List</div>
                                        <div className="cs-script-production__shots">
                                            {productionSections.shotList.map((shot) => (
                                                <div key={`shot-${shot.id}-${shot.timeRange}`} className="cs-script-production__shot">
                                                    <div className="cs-script-production__shot-header">
                                                        <span>Scene {shot.id}</span>
                                                        <span>{shot.timeRange}</span>
                                                    </div>
                                                    <div className="cs-script-production__shot-title">{shot.title}</div>
                                                    <div className="cs-script-production__shot-visual">Visual: {shot.visual}</div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {productionSections.cta && (
                                        <div className="cs-script-production__section">
                                            <div className="cs-script-production__label">CTA</div>
                                            <div className="cs-script-production__item">{productionSections.cta}</div>
                                        </div>
                                    )}
                                </div>
                            )}

                            <div className="cs-form-row">
                                {!previewOnly && (
                                    <button className="cs-btn cs-btn--secondary" onClick={() => setScript(null)}>
                                        Regenerate
                                    </button>
                                )}
                                <button className="cs-btn cs-btn--primary" onClick={handleCopy}>
                                    Copy Script
                                </button>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    )
}
