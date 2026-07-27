import { useState } from 'react'

const SCRIPT_TYPES = [
    { id: 'viral', label: 'Viral Script', description: 'Punchy, fast-paced, hook-first' },
    { id: 'natural', label: 'Natural Script', description: 'Conversational, authentic' },
    { id: 'story', label: 'Story Script', description: 'Narrative, emotional arc' },
]

const TONES = ['friendly', 'professional', 'funny', 'educational', 'luxury']
const LANGUAGES = ['en', 'hi', 'es', 'fr', 'de']

export default function ScriptGenerator({ ideaId, ideaTitle, hook, accountUrl, onClose, onCopy }) {
    const [scriptType, setScriptType] = useState('viral')
    const [tone, setTone] = useState('friendly')
    const [language, setLanguage] = useState('en')
    const [duration, setDuration] = useState(60)
    const [script, setScript] = useState(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    const handleGenerate = async () => {
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
                    duration_seconds: duration,
                }),
            })
            if (res.ok) {
                const data = await res.json()
                setScript(data)
            } else {
                const err = await res.json().catch(() => ({ detail: 'Generation failed' }))
                const errMsg = err.detail || `Failed to generate script (status ${res.status})`
                if (res.status === 404) {
                    setError('Idea not found in database. Use "Generate New Ideas" first to create a persisted idea, then generate a script from it.')
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

    return (
        <div className="cs-modal-backdrop" onClick={onClose}>
            <div className="cs-modal cs-modal--script" onClick={e => e.stopPropagation()}>
                <div className="cs-modal__header">
                    <button className="cs-modal__back" onClick={onClose}>← Back to Idea Details</button>
                    <h3>Script Generator</h3>
                    <p className="cs-modal__subtitle">AI creates script for: {ideaTitle}</p>
                </div>

                <div className="cs-modal__body">
                    {error && (
                        <div className="cs-error">{error}</div>
                    )}

                    {!script ? (
                        <>
                            {/* Script Type */}
                            <div className="cs-form-group">
                                <label className="cs-form-label">Script Type</label>
                                <div className="cs-radio-group">
                                    {SCRIPT_TYPES.map(type => (
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

                            <div className="cs-form-group">
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
                            </div>

                            <button
                                className="cs-btn cs-btn--primary cs-btn--full"
                                onClick={handleGenerate}
                                disabled={loading}
                            >
                                {loading ? 'Generating...' : 'Generate Script'}
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
                                            <span>Scene {scene.scene_number}</span>
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
                                <span>Estimated Duration: {script.estimated_duration_sec}s</span>
                            </div>

                            <div className="cs-form-row">
                                <button className="cs-btn cs-btn--secondary" onClick={() => setScript(null)}>
                                    Regenerate
                                </button>
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
