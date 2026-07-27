/**
 * Screen 2 — Script Timeline Editor
 *
 * Full redesign per PRD: two-column layout with timeline ruler,
 * draggable scene blocks, and AI Suggestions panel.
 */

import { useState, useCallback, useRef } from 'react'

const TIMELINE_MARKS = [0, 5, 10, 15, 20, 25, 30]
const SCENE_DEFAULTS = [
    { id: 'hook', label: 'HOOK', duration: 3 },
    { id: 'scene_1', label: 'SCENE 1', duration: 6 },
    { id: 'scene_2', label: 'SCENE 2', duration: 8 },
    { id: 'scene_3', label: 'SCENE 3', duration: 7 },
    { id: 'cta', label: 'CTA', duration: 5 },
]

export default function ScriptTimeline({ ideaId, ideaTitle, hook: initialHook, accountUrl, onClose, onCopy }) {
    const [scenes, setScenes] = useState(() =>
        SCENE_DEFAULTS.map(s => ({
            ...s,
            text: s.id === 'hook' ? (initialHook || 'Enter your hook here...') : '',
        }))
    )
    const [aiSuggestions, setAiSuggestions] = useState(null)
    const [aiLoading, setAiLoading] = useState(false)
    const [regenerating, setRegenerating] = useState(false)
    const [draggedIdx, setDraggedIdx] = useState(null)
    const fileInputRef = useRef(null)

    const totalDuration = scenes.reduce((sum, s) => sum + s.duration, 0)
    const timestamps = (() => {
        let current = 0
        return scenes.map(s => {
            const start = current
            const end = current + s.duration
            current = end
            return { start, end }
        })
    })()

    const handleTextChange = useCallback((idx, text) => {
        setScenes(prev => prev.map((s, i) => i === idx ? { ...s, text } : s))
    }, [])

    const handleDurationChange = useCallback((idx, delta) => {
        setScenes(prev => prev.map((s, i) => i === idx ? { ...s, duration: Math.max(1, (s.duration || 3) + delta) } : s))
    }, [])

    const handleAddScene = () => {
        setScenes(prev => {
            const newIdx = prev.length - 1 // before CTA
            const newScene = { id: `scene_${Date.now()}`, label: `SCENE ${prev.filter(s => s.label.startsWith('SCENE')).length + 1}`, duration: 5, text: '' }
            const arr = [...prev]
            arr.splice(newIdx, 0, newScene)
            return arr
        })
    }

    const handleDragStart = (idx) => {
        setDraggedIdx(idx)
        document.body.style.cursor = 'grabbing'
    }

    const handleDrop = (targetIdx) => {
        if (draggedIdx === null || draggedIdx === targetIdx) return
        setScenes(prev => {
            const arr = [...prev]
            const [removed] = arr.splice(draggedIdx, 1)
            arr.splice(targetIdx, 0, removed)
            return arr
        })
        setDraggedIdx(null)
        document.body.style.cursor = ''
    }

    const handleAIImprove = async () => {
        setAiLoading(true)
        setAiSuggestions(null)
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const r = await fetch(`${baseUrl}/ideas/${ideaId}/improve-script-block`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    block_id: 'full',
                    text: scenes.map(s => s.text).join('\n'),
                    tone: 'friendly',
                    instruction: 'improve_all',
                }),
            })
            if (r.ok) {
                const data = await r.json()
                setAiSuggestions([
                    { title: 'Improve Hook', description: data.improved_text?.slice(0, 100) || 'Make your hook more attention-grabbing' },
                    { title: 'Stronger CTA', description: 'End with a clear call-to-action that drives engagement' },
                    { title: 'Pacing Adjustment', description: 'Speed up the middle scenes for better retention' },
                ])
            }
        } catch (e) {
            console.error('AI improve failed:', e)
        } finally {
            setAiLoading(false)
        }
    }

    const handleRegenerate = async () => {
        setRegenerating(true)
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const r = await fetch(`${baseUrl}/trends/generate-script`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    idea_id: ideaId,
                    script_type: 'viral',
                    tone: 'friendly',
                    language: 'en',
                    duration_seconds: totalDuration,
                }),
            })
            if (r.ok) {
                const data = await r.json()
                if (data.scenes) {
                    setScenes(data.scenes.map((s, i) => ({
                        id: `scene_${s.scene_number || i}`,
                        label: s.scene_number === 0 ? 'HOOK' : s.scene_number === data.scenes.length ? 'CTA' : `SCENE ${s.scene_number}`,
                        duration: scenes[i]?.duration || 5,
                        text: s.description || '',
                    })))
                }
            }
        } catch (e) {
            console.error('Regenerate failed:', e)
        } finally {
            setRegenerating(false)
        }
    }

    const handleExport = () => {
        const text = scenes.map((s, i) => {
            const ts = timestamps[i]
            const start = formatTime(ts.start)
            const end = formatTime(ts.end)
            return `[${s.label}] ${start} - ${end}\n${s.text}\n`
        }).join('\n')
        const blob = new Blob([text], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${ideaTitle || 'script'}.txt`
        a.click()
        URL.revokeObjectURL(url)
    }

    const applySuggestion = (suggestion) => {
        // Apply suggestion to the relevant scene
        if (suggestion.title.includes('Hook') && scenes.length > 0) {
            handleTextChange(0, suggestion.description)
        }
    }

    return (
        <div className="cs-modal-overlay cs-modal-overlay--open" onClick={onClose}>
            <div className="cs-modal cs-script-timeline" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="cs-script-timeline__header">
                    <button className="cs-btn cs-btn--ghost" onClick={onClose}>← Back</button>
                    <span className="cs-script-timeline__title">{ideaTitle || 'Script Editor'}</span>
                    <div className="cs-script-timeline__header-actions">
                        <button
                            className="cs-btn cs-btn--ghost"
                            onClick={handleRegenerate}
                            disabled={regenerating}
                        >
                            {regenerating ? 'Regenerating...' : '☁ Regenerate'}
                        </button>
                        <button
                            className="cs-btn cs-btn--ai"
                            onClick={handleAIImprove}
                            disabled={aiLoading}
                        >
                            {aiLoading ? 'Analyzing...' : '✦ AI Improve'}
                        </button>
                    </div>
                </div>

                <div className="cs-script-timeline__body">
                    {/* Left Column — Timeline */}
                    <div className="cs-script-timeline__left">
                        {/* Timeline ruler */}
                        <div className="cs-script-timeline__ruler">
                            {TIMELINE_MARKS.map(mark => (
                                <span key={mark} className="cs-script-timeline__ruler-mark">{mark}s</span>
                            ))}
                        </div>

                        {/* Scene Blocks */}
                        <div className="cs-script-timeline__scenes">
                            {scenes.map((scene, idx) => {
                                const ts = timestamps[idx]
                                return (
                                    <div
                                        key={scene.id}
                                        className={`cs-scene-block ${draggedIdx === idx ? 'cs-scene-block--dragging' : ''}`}
                                        draggable
                                        onDragStart={() => handleDragStart(idx)}
                                        onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('cs-scene-block--dragover') }}
                                        onDragLeave={(e) => e.currentTarget.classList.remove('cs-scene-block--dragover')}
                                        onDrop={(e) => { e.preventDefault(); e.currentTarget.classList.remove('cs-scene-block--dragover'); handleDrop(idx) }}
                                        onDragEnd={() => { setDraggedIdx(null); document.body.style.cursor = '' }}
                                    >
                                        <div className="cs-scene-block__header">
                                            <span className="cs-scene-block__drag-handle">⠿</span>
                                            <span className={`cs-scene-block__label cs-scene-block__label--${scene.id === 'hook' ? 'hook' : scene.id === 'cta' ? 'cta' : 'scene'}`}>
                                                {scene.label}
                                            </span>
                                            <span className="cs-scene-block__timestamp">
                                                {formatTime(ts.start)} - {formatTime(ts.end)}
                                            </span>
                                            <div className="cs-scene-block__thumb">
                                                <span>🎬</span>
                                            </div>
                                            <span className={`cs-scene-block__duration-badge cs-scene-block__duration-badge--${scene.duration >= 6 ? 'long' : 'short'}`}>
                                                {scene.duration}x
                                            </span>
                                            <div className="cs-scene-block__duration-controls">
                                                <button onClick={() => handleDurationChange(idx, -1)}>−</button>
                                                <button onClick={() => handleDurationChange(idx, +1)}>+</button>
                                            </div>
                                        </div>
                                        <textarea
                                            className="cs-scene-block__text"
                                            value={scene.text}
                                            onChange={e => handleTextChange(idx, e.target.value)}
                                            placeholder={`Write ${scene.label.toLowerCase()} script...`}
                                            rows={3}
                                        />
                                    </div>
                                )
                            })}
                        </div>

                        {/* Add Scene */}
                        <button className="cs-script-timeline__add-scene" onClick={handleAddScene}>
                            + Add Scene
                        </button>

                        {/* Footer */}
                        <div className="cs-script-timeline__footer">
                            <span className="cs-script-timeline__total-duration">Total Duration: {totalDuration}s</span>
                            <div className="cs-script-timeline__footer-actions">
                                <button className="cs-btn cs-btn--ghost">☐ Save Draft</button>
                                <button className="cs-btn cs-btn--ghost" onClick={handleExport}>⬆ Export Script</button>
                                <button className="cs-btn cs-btn--ghost">▶ Preview</button>
                            </div>
                        </div>
                    </div>

                    {/* Right Column — AI Suggestions */}
                    <div className="cs-script-timeline__right">
                        <h4 className="cs-script-timeline__suggestions-title">AI Suggestions</h4>
                        {aiLoading && (
                            <div className="cs-script-timeline__suggestions-skeleton">
                                {[1, 2, 3].map(i => (
                                    <div key={i} className="cs-skeleton cs-skeleton--text" style={{ height: '60px', marginBottom: '0.75rem' }} />
                                ))}
                            </div>
                        )}
                        {!aiLoading && !aiSuggestions && (
                            <div className="cs-script-timeline__suggestions-empty">
                                <p>Click <strong>✦ AI Improve</strong> to get AI-powered suggestions for your script.</p>
                            </div>
                        )}
                        {!aiLoading && aiSuggestions && aiSuggestions.map((s, i) => (
                            <div key={i} className="cs-suggestion-card">
                                <div className="cs-suggestion-card__header">
                                    <span className="cs-suggestion-card__title">{s.title}</span>
                                </div>
                                <p className="cs-suggestion-card__desc">{s.description}</p>
                                <button
                                    className="cs-btn cs-btn--ghost cs-suggestion-card__apply"
                                    onClick={() => applySuggestion(s)}
                                >
                                    Apply
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    )
}

function formatTime(seconds) {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return `${m}:${s.toString().padStart(2, '0')}`
}
