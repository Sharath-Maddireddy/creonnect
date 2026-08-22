import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

const DEFAULT_FORM = {
    style_id: '',
    intensity_id: 'balanced',
    quality_preset_id: 'standard',
    enabled_control_ids: []
}

function buildDataUrl(mimeType, imageBase64) {
    if (!mimeType || !imageBase64) {
        return ''
    }
    return `data:${mimeType};base64,${imageBase64}`
}

function extractErrorMessage(payload, fallback) {
    if (payload && typeof payload.detail === 'string' && payload.detail.trim()) {
        return payload.detail
    }
    if (payload && typeof payload.message === 'string' && payload.message.trim()) {
        return payload.message
    }
    return fallback
}

export default function ImageEditor() {
    const location = useLocation()
    const sourceIdea = location.state?.sourceIdea || null
    const originLabel = location.state?.originLabel || 'Analytics'
    const backPath = location.state?.fromPath || '/analytics'

    const [config, setConfig] = useState(null)
    const [configLoading, setConfigLoading] = useState(true)
    const [configError, setConfigError] = useState('')

    const [selectedFile, setSelectedFile] = useState(null)
    const [originalPreviewUrl, setOriginalPreviewUrl] = useState('')
    const [originalAsset, setOriginalAsset] = useState(null)
    const [uploading, setUploading] = useState(false)
    const [uploadError, setUploadError] = useState('')

    const [form, setForm] = useState(DEFAULT_FORM)
    const [submitting, setSubmitting] = useState(false)
    const [result, setResult] = useState(null)
    const [requestId, setRequestId] = useState('')
    const [applyError, setApplyError] = useState('')
    const [regenerating, setRegenerating] = useState(false)
    const [editMode, setEditMode] = useState('filter-only')
    const [aiProvider, setAiProvider] = useState('gpt-image')
    const [aiPrompt, setAiPrompt] = useState('')
    const [filterCatalog, setFilterCatalog] = useState([])
    const [aiFilterId, setAiFilterId] = useState('')

    useEffect(() => {
        let isMounted = true
        const loadConfig = async () => {
            setConfigLoading(true)
            setConfigError('')
            try {
                const response = await fetch('/api/v1/image-editor/config', {
                    credentials: 'include'
                })
                const payload = await response.json().catch(() => ({}))
                if (!response.ok) {
                    throw new Error(extractErrorMessage(payload, 'Failed to load image editor config.'))
                }
                if (isMounted) {
                    setConfig(payload)
                    setForm((current) => ({
                        ...current,
                        style_id: current.style_id || payload.styles?.[0]?.id || '',
                        intensity_id: current.intensity_id || payload.intensities?.[0]?.id || 'balanced',
                        quality_preset_id: current.quality_preset_id || payload.quality_presets?.[0]?.id || 'standard'
                    }))
                }
            } catch (error) {
                if (isMounted) {
                    setConfigError(error.message || 'Failed to load image editor config.')
                }
            } finally {
                if (isMounted) {
                    setConfigLoading(false)
                }
            }
        }

        loadConfig()
        return () => {
            isMounted = false
        }
    }, [])

    useEffect(() => {
        let isMounted = true
        const loadCatalog = async () => {
            try {
                const response = await fetch('/api/v1/image-editor/filter-catalog', { credentials: 'include' })
                const payload = await response.json().catch(() => ({}))
                if (!response.ok) {
                    throw new Error(extractErrorMessage(payload, 'Failed to load AI filter catalog.'))
                }
                if (isMounted) {
                    setFilterCatalog(payload.filters || [])
                }
            } catch (error) {
                if (isMounted) {
                    setApplyError(error.message || 'Failed to load AI filter catalog.')
                }
            }
        }
        loadCatalog()
        return () => { isMounted = false }
    }, [])

    useEffect(() => {
        if (!selectedFile) {
            setOriginalPreviewUrl('')
            return undefined
        }

        const nextUrl = URL.createObjectURL(selectedFile)
        setOriginalPreviewUrl(nextUrl)
        return () => {
            URL.revokeObjectURL(nextUrl)
        }
    }, [selectedFile])

    const visibleControls = useMemo(() => {
        return Array.isArray(config?.controls)
            ? config.controls.filter((control) => control.visible_in_filter_only_mode && control.filter_only_compatible)
            : []
    }, [config])

    const selectedStyle = useMemo(() => {
        return Array.isArray(config?.styles)
            ? config.styles.find((style) => style.id === form.style_id) || null
            : null
    }, [config, form.style_id])

    const resultImageUrl = useMemo(() => {
        if (result?.result_asset_id) {
            return `/api/v1/image-editor/assets/${encodeURIComponent(result.result_asset_id)}/content`
        }
        return buildDataUrl(result?.response?.mime_type, result?.response?.image_base64)
    }, [result])

    const resetEditorSession = () => {
        setOriginalAsset(null)
        setResult(null)
        setRequestId('')
        setApplyError('')
        setUploadError('')
    }

    const handleFileChange = (event) => {
        const file = event.target.files?.[0] || null
        setSelectedFile(file)
        resetEditorSession()
    }

    const handleControlToggle = (controlId) => {
        setForm((current) => {
            const selected = new Set(current.enabled_control_ids)
            if (selected.has(controlId)) {
                selected.delete(controlId)
            } else {
                selected.add(controlId)
            }
            return {
                ...current,
                enabled_control_ids: Array.from(selected)
            }
        })
    }

    const ensureUploadedAsset = async () => {
        if (originalAsset) {
            return originalAsset
        }
        if (!selectedFile) {
            throw new Error('Choose an image before applying a filter.')
        }

        setUploading(true)
        setUploadError('')
        try {
            const formData = new FormData()
            formData.append('image', selectedFile)
            const response = await fetch('/api/v1/image-editor/assets', {
                method: 'POST',
                credentials: 'include',
                body: formData
            })
            const payload = await response.json().catch(() => ({}))
            if (!response.ok) {
                throw new Error(extractErrorMessage(payload, `Failed to upload the original image (HTTP ${response.status}).`))
            }
            setOriginalAsset(payload)
            return payload
        } catch (error) {
            setUploadError(error.message || 'Failed to upload the original image.')
            throw error
        } finally {
            setUploading(false)
        }
    }

    const handleApplyFilter = async () => {
        setSubmitting(true)
        setApplyError('')
        try {
            const asset = await ensureUploadedAsset()
            const response = await fetch(
                `/api/v1/image-editor/filters/apply-from-asset?original_asset_id=${encodeURIComponent(asset.asset_id)}`,
                {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(form)
                }
            )
            const payload = await response.json().catch(() => ({}))
            if (!response.ok) {
                throw new Error(extractErrorMessage(payload, `Failed to apply the deterministic filter (HTTP ${response.status}).`))
            }
            setResult(payload)
            setRequestId(payload.request_id || '')
        } catch (error) {
            setApplyError(error.message || 'Failed to apply the deterministic filter.')
        } finally {
            setSubmitting(false)
        }
    }

    const handleRegenerate = async () => {
        if (!requestId) {
            return
        }
        setRegenerating(true)
        setApplyError('')
        try {
            const response = await fetch(`/api/v1/image-editor/filters/${encodeURIComponent(requestId)}/regenerate`, {
                method: 'POST',
                credentials: 'include'
            })
            const payload = await response.json().catch(() => ({}))
            if (!response.ok) {
                throw new Error(extractErrorMessage(payload, `Failed to regenerate the saved filter request (HTTP ${response.status}).`))
            }
            setResult(payload)
        } catch (error) {
            setApplyError(error.message || 'Failed to regenerate the saved filter request.')
        } finally {
            setRegenerating(false)
        }
    }

    const handleAiEdit = async () => {
        if (!aiFilterId && !aiPrompt.trim()) {
            setApplyError('Choose an AI filter or describe the edit you want to make.')
            return
        }
        setSubmitting(true)
        setApplyError('')
        try {
            const asset = await ensureUploadedAsset()
            const response = await fetch('/api/v1/image-editor/ai-edits', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    original_asset_id: asset.asset_id,
                    provider: aiProvider,
                    filter_id: aiFilterId || null,
                    settings: {},
                    prompt: aiPrompt.trim() || null
                })
            })
            const payload = await response.json().catch(() => ({}))
            if (!response.ok) {
                throw new Error(extractErrorMessage(payload, `Failed to generate the AI edit (HTTP ${response.status}).`))
            }
            setResult(payload)
            setRequestId(payload.request_id || '')
        } catch (error) {
            setApplyError(error.message || 'Failed to generate the AI edit.')
        } finally {
            setSubmitting(false)
        }
    }

    const aiCatalogFilters = useMemo(
        () => filterCatalog.filter((item) => item.mode === 'ai-edit'),
        [filterCatalog]
    )
    const selectedAiFilter = aiCatalogFilters.find((item) => item.id === aiFilterId) || null

    return (
        <div className="image-editor-page">
            <div className="image-editor-shell">
                <div className="image-editor-hero">
                    <div>
                        <p className="image-editor-kicker">Backend-Owned Image Editor</p>
                        <h1>Deterministic filter edits, no surprise redraws.</h1>
                        <p className="image-editor-subtitle">
                            This screen uses the new Python backend flow: upload one immutable original,
                            apply a strict filter-only recipe, and regenerate the same saved request instead
                            of producing a different image on every click.
                        </p>
                        {sourceIdea ? (
                            <div className="image-editor-origin-card">
                                <span className="image-editor-origin-card__label">Opened from {originLabel}</span>
                                <strong>{sourceIdea.title || 'Selected idea'}</strong>
                                {sourceIdea.hook ? <p>{sourceIdea.hook}</p> : null}
                            </div>
                        ) : null}
                    </div>
                    <div className="image-editor-hero-actions">
                        <Link className="image-editor-link" to={backPath}>Back to {originLabel}</Link>
                    </div>
                </div>

                {configLoading ? (
                    <div className="loading-container">
                        <div className="spinner"></div>
                        <p>Loading image editor config...</p>
                    </div>
                ) : configError ? (
                    <div className="error-container">
                        <p>{configError}</p>
                    </div>
                ) : (
                    <div className="image-editor-layout">
                        <section className="image-editor-panel image-editor-panel--controls">
                            <div className="image-editor-panel__header">
                                <div>
                                    <span className="image-editor-panel__eyebrow">Step 1</span>
                                    <h2>Choose your source and recipe</h2>
                                </div>
                                <div className="image-editor-badge-row">
                                    <span className="image-editor-badge">{config?.mode}</span>
                                    <span className="image-editor-badge image-editor-badge--muted">
                                        AI edit: explicit only
                                    </span>
                                </div>
                            </div>

                            <label className="image-editor-upload">
                                <span>Original image</span>
                                <input type="file" accept="image/jpeg,image/png,image/webp" onChange={handleFileChange} />
                                <strong>{selectedFile?.name || 'Select a JPG or PNG to start'}</strong>
                                <small>
                                    The backend stores this as the immutable original. Every regenerate call starts from it.
                                </small>
                            </label>

                            <div className="image-editor-mode-tabs">
                                <button
                                    type="button"
                                    className={editMode === 'filter-only' ? 'is-active' : ''}
                                    onClick={() => setEditMode('filter-only')}
                                >
                                    Filter-only
                                </button>
                                <button
                                    type="button"
                                    className={editMode === 'ai-edit' ? 'is-active' : ''}
                                    onClick={() => setEditMode('ai-edit')}
                                >
                                    AI edit
                                </button>
                            </div>

                            {editMode === 'ai-edit' ? (
                                <div className="image-editor-ai-box">
                                    <div className="image-editor-field-grid">
                                        <div className="image-editor-field">
                                            <label htmlFor="ai-provider">Provider</label>
                                            <select id="ai-provider" value={aiProvider} onChange={(event) => setAiProvider(event.target.value)}>
                                                <option value="gpt-image">GPT Image 2</option>
                                                <option value="gemini">Gemini 3.1 Flash Image</option>
                                            </select>
                                        </div>
                                        <div className="image-editor-field">
                                            <label htmlFor="ai-preset">AI filter style</label>
                                            <select
                                                id="ai-preset"
                                                value={aiFilterId}
                                                onChange={(event) => {
                                                    const nextId = event.target.value
                                                    setAiFilterId(nextId)
                                                    const nextFilter = aiCatalogFilters.find((item) => item.id === nextId)
                                                    if (nextFilter?.provider_preference && nextFilter.provider_preference !== 'none') {
                                                        setAiProvider(nextFilter.provider_preference)
                                                    }
                                                }}
                                            >
                                                <option value="">Custom AI edit</option>
                                                {aiCatalogFilters.map((filter) => (
                                                    <option key={filter.id} value={filter.id}>{filter.label}</option>
                                                ))}
                                            </select>
                                        </div>
                                    </div>
                                    {selectedAiFilter ? <p className="image-editor-ai-description">{selectedAiFilter.description}</p> : null}
                                    <div className="image-editor-field">
                                        <label htmlFor="ai-prompt">Additional direction {selectedAiFilter ? '(optional)' : ''}</label>
                                        <textarea
                                            id="ai-prompt"
                                            value={aiPrompt}
                                            onChange={(event) => setAiPrompt(event.target.value)}
                                            placeholder="Example: Replace the background with a warm studio wall while keeping the product unchanged."
                                            rows={4}
                                        />
                                    </div>
                                    <button
                                        className="image-editor-button image-editor-button--primary"
                                        type="button"
                                        onClick={handleAiEdit}
                                        disabled={!selectedFile || submitting || uploading}
                                    >
                                        {submitting || uploading ? 'Generating...' : 'Generate AI Edit'}
                                    </button>
                                </div>
                            ) : null}

                            {editMode === 'filter-only' ? <>
                            <div className="image-editor-field">
                                <label htmlFor="style_id">Style</label>
                                <select
                                    id="style_id"
                                    value={form.style_id}
                                    onChange={(event) => setForm((current) => ({ ...current, style_id: event.target.value }))}
                                >
                                    {(config?.styles || []).map((style) => (
                                        <option key={style.id} value={style.id}>{style.label}</option>
                                    ))}
                                </select>
                                <p>{selectedStyle?.description || 'Pick a deterministic global look.'}</p>
                            </div>

                            <div className="image-editor-field-grid">
                                <div className="image-editor-field">
                                    <label htmlFor="intensity_id">Intensity</label>
                                    <select
                                        id="intensity_id"
                                        value={form.intensity_id}
                                        onChange={(event) => setForm((current) => ({ ...current, intensity_id: event.target.value }))}
                                    >
                                        {(config?.intensities || []).map((intensity) => (
                                            <option key={intensity.id} value={intensity.id}>{intensity.label}</option>
                                        ))}
                                    </select>
                                </div>

                                <div className="image-editor-field">
                                    <label htmlFor="quality_preset_id">Quality preset</label>
                                    <select
                                        id="quality_preset_id"
                                        value={form.quality_preset_id}
                                        onChange={(event) => setForm((current) => ({ ...current, quality_preset_id: event.target.value }))}
                                    >
                                        {(config?.quality_presets || []).map((preset) => (
                                            <option key={preset.id} value={preset.id}>{preset.label}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>

                            <div className="image-editor-field">
                                <label>Allowed controls</label>
                                <div className="image-editor-controls">
                                    {visibleControls.map((control) => (
                                        <label key={control.id} className="image-editor-control-chip">
                                            <input
                                                type="checkbox"
                                                checked={form.enabled_control_ids.includes(control.id)}
                                                onChange={() => handleControlToggle(control.id)}
                                            />
                                            <span>{control.label}</span>
                                        </label>
                                    ))}
                                </div>
                                <p>
                                    These are all backend-approved global adjustments. Structural edits are blocked in filter-only mode.
                                </p>
                            </div>
                            </> : null}

                            {(uploadError || applyError) ? (
                                <div className="image-editor-alert image-editor-alert--error">
                                    {uploadError || applyError}
                                </div>
                            ) : null}

                            <div className="image-editor-actions">
                                <button
                                    className="image-editor-button image-editor-button--primary"
                                    type="button"
                                    onClick={handleApplyFilter}
                                    disabled={editMode !== 'filter-only' || !selectedFile || submitting || uploading}
                                >
                                    {submitting || uploading ? 'Applying...' : 'Apply Deterministic Filter'}
                                </button>
                                <button
                                    className="image-editor-button image-editor-button--secondary"
                                    type="button"
                                    onClick={handleRegenerate}
                                    disabled={editMode !== 'filter-only' || !requestId || regenerating}
                                >
                                    {regenerating ? 'Regenerating...' : 'Regenerate Saved Request'}
                                </button>
                            </div>
                        </section>

                        <section className="image-editor-panel image-editor-panel--preview">
                            <div className="image-editor-preview-grid">
                                <div className="image-editor-preview-card">
                                    <div className="image-editor-preview-card__header">
                                        <span>Original</span>
                                        {originalAsset ? <strong>{originalAsset.width} × {originalAsset.height}</strong> : null}
                                    </div>
                                    <div className="image-editor-preview-frame">
                                        {originalPreviewUrl ? (
                                            <img src={originalPreviewUrl} alt="Original upload preview" />
                                        ) : (
                                            <div className="image-editor-preview-empty">Upload an image to begin.</div>
                                        )}
                                    </div>
                                </div>

                                <div className="image-editor-preview-card">
                                    <div className="image-editor-preview-card__header">
                                        <span>Filtered result</span>
                                        {result?.response ? (
                                            <strong>{result.response.width} × {result.response.height}</strong>
                                        ) : null}
                                    </div>
                                    <div className="image-editor-preview-frame">
                                        {resultImageUrl ? (
                                            <img src={resultImageUrl} alt="Filtered result preview" />
                                        ) : (
                                            <div className="image-editor-preview-empty">
                                                Apply a filter to see the deterministic output here.
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <div className="image-editor-meta">
                                <div className="image-editor-meta-card">
                                    <span>Request status</span>
                                    <strong>{result?.deduplicated ? 'Deduplicated existing result' : result?.mode === 'ai-edit' ? 'AI result saved' : result ? 'Fresh deterministic result' : 'Waiting'}</strong>
                                </div>
                                <div className="image-editor-meta-card">
                                    <span>Request ID</span>
                                    <strong>{requestId || 'Not created yet'}</strong>
                                </div>
                                <div className="image-editor-meta-card">
                                    <span>Request hash</span>
                                    <strong>{result?.request_hash || 'Not created yet'}</strong>
                                </div>
                                <div className="image-editor-meta-card">
                                    <span>Engine</span>
                                    <strong>{result?.model || result?.response?.engine || 'pillow-deterministic-filter'}</strong>
                                </div>
                            </div>

                            <div className="image-editor-guardrails">
                                <h3>Why this stays consistent</h3>
                                <ul>
                                    <li>The uploaded image is stored as an immutable original asset.</li>
                                    <li>The backend hashes the request recipe and reuses an existing saved result when the request matches.</li>
                                    <li>Regenerate replays the saved filter request from the original asset instead of inventing a new variation.</li>
                                </ul>
                            </div>
                        </section>
                    </div>
                )}
            </div>
        </div>
    )
}
