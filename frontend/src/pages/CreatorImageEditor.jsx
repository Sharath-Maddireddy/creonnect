import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

const API_BASE = '/api/v1/creator/image-editor'
const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'cancelled'])
const MAX_POLL_MS = 6 * 60 * 1000

function messageFor(response, fallback) {
    return response?.detail || response?.message || fallback
}

function formatJobStatus(status) {
    return status ? `${status.slice(0, 1).toUpperCase()}${status.slice(1)}` : 'Ready'
}

export default function CreatorImageEditor() {
    const location = useLocation()
    const [config, setConfig] = useState(null)
    const [file, setFile] = useState(null)
    const [remoteSourceUrl, setRemoteSourceUrl] = useState('')
    const [sourceUrl, setSourceUrl] = useState('')
    const [normalizedSourceUrl, setNormalizedSourceUrl] = useState('')
    const [selection, setSelection] = useState({ goal_id: '', style_id: '', event_id: 'none', enhancement_ids: [], output_format: 'png' })
    const [job, setJob] = useState(null)
    const [selectedCandidateId, setSelectedCandidateId] = useState('')
    const [history, setHistory] = useState([])
    const [pollTimedOut, setPollTimedOut] = useState(false)
    const pollStartedAt = useRef(0)
    const [canvas, setCanvas] = useState({ zoom: 100, flipped: false, fit: 'contain', compare: 50 })
    const [loading, setLoading] = useState(true)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState('')
    const [sourcePreparing, setSourcePreparing] = useState(false)

    useEffect(() => {
        let active = true
        Promise.all([
            fetch(`${API_BASE}/config`, { credentials: 'include' }),
            fetch(`${API_BASE}/jobs?limit=20&skip=0`, { credentials: 'include' }),
        ]).then(async ([configResponse, historyResponse]) => {
            const configPayload = await configResponse.json().catch(() => ({}))
            const historyPayload = await historyResponse.json().catch(() => [])
            if (!configResponse.ok) throw new Error(messageFor(configPayload, 'Unable to load editor choices.'))
            if (!active) return
            setConfig(configPayload)
            setSelection((current) => ({
                ...current,
                style_id: current.style_id || configPayload.styles?.[0]?.id || '',
                goal_id: current.goal_id || configPayload.goals?.[0]?.id || '',
                event_id: configPayload.events?.some((item) => item.id === current.event_id) ? current.event_id : (configPayload.events?.[0]?.id || 'none'),
                output_format: configPayload.output_formats?.includes(current.output_format) ? current.output_format : (configPayload.output_formats?.[0] || 'png'),
            }))
            if (historyResponse.ok && Array.isArray(historyPayload)) {
                setHistory(historyPayload)
                const restoredJob = historyPayload.find((item) => !TERMINAL_STATUSES.has(item.status))
                    || historyPayload.find((item) => item.status === 'succeeded')
                    || historyPayload[0]
                if (restoredJob) setJob(restoredJob)
            }
        }).catch((loadError) => active && setError(loadError.message)).finally(() => active && setLoading(false))
        return () => { active = false }
    }, [])

    useEffect(() => {
        const routedSource = location.state?.sourceUrl
        if (!routedSource || file) return
        let active = true
        setSourcePreparing(true)
        fetch(routedSource)
            .then(async (response) => {
                if (!response.ok) throw new Error('Unable to load the media passed from the previous screen.')
                const blob = await response.blob()
                return new File([blob], location.state?.fileName || 'routed-image', { type: location.state?.mimeType || blob.type || 'image/png' })
            })
            .then((routedFile) => active && setFile(routedFile))
            .catch((routedError) => active && setError(routedError.message))
            .finally(() => active && setSourcePreparing(false))
        return () => { active = false }
    }, [file, location.state])

    useEffect(() => {
        if (!file) {
            setSourceUrl('')
            return undefined
        }
        const url = URL.createObjectURL(file)
        setSourceUrl(url)
        return () => URL.revokeObjectURL(url)
    }, [file])

    useEffect(() => {
        pollStartedAt.current = Date.now()
        setPollTimedOut(false)
    }, [job?.id])

    useEffect(() => {
        if (!job || TERMINAL_STATUSES.has(job.status)) return undefined
        if (pollTimedOut) return undefined
        if (Date.now() - pollStartedAt.current >= MAX_POLL_MS) {
            setPollTimedOut(true)
            setError('Generation is taking longer than expected. Check history later or start a new generation.')
            return undefined
        }
        const timer = window.setTimeout(async () => {
            try {
            const response = await fetch(`${API_BASE}/jobs/${encodeURIComponent(job.id)}`, { credentials: 'include' })
            const payload = await response.json().catch(() => ({}))
            if (!response.ok) throw new Error(messageFor(payload, 'Unable to refresh generation progress.'))
                setJob(payload)
                setHistory((items) => [payload, ...items.filter((item) => item.id !== payload.id)])
            } catch (pollError) {
                setError(pollError.message)
            }
        }, job.next_poll_after_ms || 3500)
        return () => window.clearTimeout(timer)
    }, [job, pollTimedOut])

    const selectedEnhancements = useMemo(() => new Set(selection.enhancement_ids), [selection.enhancement_ids])
    const selectedStyle = useMemo(
        () => config?.styles?.find((style) => style.id === selection.style_id),
        [config, selection.style_id],
    )
    const previewSourceUrl = normalizedSourceUrl || sourceUrl || remoteSourceUrl.trim() || job?.source_url || ''
    const selectedCandidate = job?.candidates?.find((candidate) => candidate.id === selectedCandidateId) || job?.candidates?.[0]
    const resultPreviewUrl = selectedCandidate?.result_url || job?.result_url || ''
    const jobStatusMessage = job?.status === 'failed'
        ? (job.error?.message || 'Generation failed. Please retry.')
        : `${job?.progress_stage || formatJobStatus(job?.status)} · ${job?.progress_percent || 0}%`

    const toggleEnhancement = (enhancement) => {
        setSelection((current) => {
            const next = new Set(current.enhancement_ids)
            if (next.has(enhancement.id)) next.delete(enhancement.id)
            else {
                next.add(enhancement.id)
                enhancement.mutually_exclusive_with.forEach((id) => next.delete(id))
            }
            return { ...current, enhancement_ids: [...next] }
        })
    }

    const handleSourceChange = async (event) => {
        const selected = event.target.files?.[0] || null
        if (!selected) return
        setRemoteSourceUrl('')
        setNormalizedSourceUrl('')
        if (!selected.type.startsWith('video/')) {
            setFile(selected)
            return
        }
        setSourcePreparing(true)
        setError('')
        try {
            const videoUrl = URL.createObjectURL(selected)
            const frame = await new Promise((resolve, reject) => {
                const video = document.createElement('video')
                video.muted = true
                video.preload = 'metadata'
                video.src = videoUrl
                video.onloadeddata = () => {
                    const canvas = document.createElement('canvas')
                    canvas.width = video.videoWidth
                    canvas.height = video.videoHeight
                    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
                    canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('Unable to capture a video frame.')), 'image/jpeg', .92)
                }
                video.onerror = () => reject(new Error('This video could not be read by your browser.'))
            })
            URL.revokeObjectURL(videoUrl)
            setFile(new File([frame], `${selected.name.replace(/\.[^.]+$/, '')}-cover.jpg`, { type: 'image/jpeg' }))
        } catch (sourceError) {
            setError(sourceError.message)
        } finally {
            setSourcePreparing(false)
            event.target.value = ''
        }
    }

    const startGeneration = async () => {
        if (!file && !remoteSourceUrl.trim()) return setError('Choose an image or paste a public image URL before generating.')
        setSubmitting(true)
        setError('')
        try {
            const headers = { 'Idempotency-Key': crypto.randomUUID() }
            const response = file
                ? await (() => {
                    const body = new FormData()
                    body.append('image', file)
                    Object.entries(selection).forEach(([key, value]) => body.append(key, key === 'enhancement_ids' ? JSON.stringify(value) : value))
                    return fetch(`${API_BASE}/jobs`, { method: 'POST', credentials: 'include', body, headers })
                })()
                : await fetch(`${API_BASE}/jobs/from-url`, {
                    method: 'POST', credentials: 'include', headers: { ...headers, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ...selection, source_url: remoteSourceUrl.trim() }),
                })
            const payload = await response.json().catch(() => ({}))
            if (!response.ok) throw new Error(messageFor(payload, 'Unable to start generation.'))
            if (payload.source_url) setNormalizedSourceUrl(payload.source_url)
            setJob(payload)
            setHistory((items) => [payload, ...items.filter((item) => item.id !== payload.id)])
        } catch (submitError) {
            setError(submitError.message)
        } finally {
            setSubmitting(false)
        }
    }

    const cancelJob = async () => {
        try {
            const response = await fetch(`${API_BASE}/jobs/${job.id}/cancel`, { method: 'POST', credentials: 'include' })
            const payload = await response.json().catch(() => ({}))
            if (!response.ok) throw new Error(messageFor(payload, 'Unable to cancel generation.'))
            setJob(payload)
        } catch (cancelError) {
            setError(cancelError.message)
        }
    }

    const retryJob = async () => {
        try {
            const response = await fetch(`${API_BASE}/jobs/${job.id}/retry`, { method: 'POST', credentials: 'include' })
            const payload = await response.json().catch(() => ({}))
            if (!response.ok) throw new Error(messageFor(payload, 'Unable to retry generation.'))
            setJob(payload)
            setHistory((items) => [payload, ...items])
        } catch (retryError) {
            setError(retryError.message)
        }
    }

    if (loading) return <main className="creator-image-editor"><p>Loading image editor…</p></main>
    if (!config) return (
        <main className="creator-image-editor">
            <h1>Image Editor unavailable</h1>
            <p className="creator-image-editor__error" role="alert">{error || 'Sign in to Creonnect, then reopen the editor.'}</p>
            <Link to="/analytics">Back to analytics</Link>
        </main>
    )

    return (
        <main className="creator-image-editor">
            <header className="creator-image-editor__header">
                <div><p className="creator-image-editor__eyebrow">Creator Image Editor</p><h1>Single-image Editor</h1><p>Create polished, on-brand visuals from structured choices.</p></div>
                <nav><Link to="/analytics">Back to analytics</Link></nav>
            </header>
            {error && <p className="creator-image-editor__error" role="alert">{error}</p>}
            <div className="creator-image-editor__layout">
                <section className="creator-image-editor__controls" aria-label="Generation controls">
                    <label className="creator-image-editor__upload">Source image or video
                        <input type="file" accept="image/jpeg,image/png,image/webp,image/heic,image/heif,video/mp4,video/*" onChange={handleSourceChange} />
                        <span>{sourcePreparing ? 'Preparing source…' : (file?.name || 'Choose an image, HEIC photo, or browser-readable video (max 25 MB)')}</span>
                    </label>
                    <label>Or paste a public image URL<input type="url" value={remoteSourceUrl} placeholder="https://…" onChange={(event) => { setRemoteSourceUrl(event.target.value); if (event.target.value) { setFile(null); setNormalizedSourceUrl('') } }} /></label>
                    <label>Style<select value={selection.style_id} onChange={(event) => setSelection((current) => ({ ...current, style_id: event.target.value }))}>{config.styles.map((style) => <option value={style.id} key={style.id}>{style.label} · {style.is_rotating ? 'Limited' : 'Evergreen'}</option>)}</select>{selectedStyle?.is_rotating && <span className="creator-image-editor__limited-badge">Limited-time filter</span>}</label>
                    <label>Goal<select value={selection.goal_id} onChange={(event) => setSelection((current) => ({ ...current, goal_id: event.target.value }))}>{config.goals.map((goal) => <option value={goal.id} key={goal.id}>{goal.label}</option>)}</select></label>
                    <label>Event<select value={selection.event_id} onChange={(event) => setSelection((current) => ({ ...current, event_id: event.target.value }))}>{config.events.map((event) => <option value={event.id} key={event.id}>{event.label}</option>)}</select></label>
                    <label>Export format<select value={selection.output_format} onChange={(event) => setSelection((current) => ({ ...current, output_format: event.target.value }))}>{config.output_formats.map((format) => <option value={format} key={format}>{format.toUpperCase()}</option>)}</select></label>
                    <fieldset><legend>Enhance</legend>{config.enhancements.map((enhancement) => <label className="creator-image-editor__check" key={enhancement.id}><input type="checkbox" checked={selectedEnhancements.has(enhancement.id)} onChange={() => toggleEnhancement(enhancement)} />{enhancement.label}</label>)}</fieldset>
                    <p className="creator-image-editor__identity-note">People are supported. The editor instructs the model to preserve every person's identity and keeps generation to one tightly constrained result.</p>
                    <button type="button" onClick={startGeneration} disabled={(!file && !remoteSourceUrl.trim()) || sourcePreparing || submitting || job?.cancel_allowed}>{submitting ? 'Starting…' : 'Generate image'}</button>
                </section>
                <section className="creator-image-editor__workspace" aria-live="polite">
                    <div className="creator-image-editor__canvas-tools" aria-label="Preview controls">
                        <label>Zoom <input type="range" min="50" max="300" value={canvas.zoom} onChange={(event) => setCanvas((current) => ({ ...current, zoom: Number(event.target.value) }))} /> {canvas.zoom}%</label>
                        <button type="button" onClick={() => setCanvas((current) => ({ ...current, flipped: !current.flipped }))}>Flip</button>
                        <button type="button" onClick={() => setCanvas((current) => ({ ...current, fit: current.fit === 'contain' ? 'cover' : 'contain' }))}>{canvas.fit === 'contain' ? 'Crop to fill' : 'Fit to canvas'}</button>
                    </div>
                    <div className="creator-image-editor__preview"><h2>Original</h2>{previewSourceUrl ? <img style={{ objectFit: canvas.fit, transform: `scale(${canvas.zoom / 100}) scaleX(${canvas.flipped ? -1 : 1})` }} src={previewSourceUrl} alt="Selected source" /> : <p>{file?.name?.match(/\.hei[cf]$/i) ? 'Your HEIC image will be converted for preview when generation begins.' : 'Choose a source image to begin.'}</p>}</div>
                    <div className="creator-image-editor__preview"><h2>Generated result</h2>{resultPreviewUrl ? <img style={{ objectFit: canvas.fit, transform: `scale(${canvas.zoom / 100}) scaleX(${canvas.flipped ? -1 : 1})` }} src={resultPreviewUrl} alt="Generated image" /> : <p>{job ? jobStatusMessage : 'Your result will appear here.'}</p>}</div>
                    {job?.candidates?.length > 1 && <div className="creator-image-editor__candidates"><strong>Choose your favorite</strong>{job.candidates.map((candidate, index) => <button className={candidate.id === selectedCandidate?.id ? 'is-selected' : ''} type="button" key={candidate.id} onClick={() => setSelectedCandidateId(candidate.id)}><img src={candidate.result_url} alt={`Candidate ${index + 1}`} /><span>{index === 0 ? 'Best match' : `Variant ${index + 1}`} · {candidate.score}/100</span></button>)}</div>}
                    {previewSourceUrl && resultPreviewUrl && <div className="creator-image-editor__compare"><label>Compare original / result <input type="range" min="0" max="100" value={canvas.compare} onChange={(event) => setCanvas((current) => ({ ...current, compare: Number(event.target.value) }))} /></label><div className="creator-image-editor__compare-frame"><img src={previewSourceUrl} alt="Original for comparison" /><img style={{ clipPath: `inset(0 ${100 - canvas.compare}% 0 0)` }} src={resultPreviewUrl} alt="Generated result for comparison" /></div></div>}
                    {job && <div className="creator-image-editor__job"><strong>{jobStatusMessage}</strong>{job.cancel_allowed && <button type="button" onClick={cancelJob}>Cancel</button>}{job.retry_allowed && <button type="button" onClick={retryJob}>Retry</button>}{resultPreviewUrl && <a href={resultPreviewUrl} download>Download result</a>}</div>}
                </section>
            </div>
            <section className="creator-image-editor__history"><h2>Generation history</h2>{history.length ? <ul>{history.map((item) => <li key={item.id}><button type="button" onClick={() => setJob(item)}>{formatJobStatus(item.status)} · {item.created_at ? new Date(item.created_at).toLocaleString() : item.id}</button></li>)}</ul> : <p>Your latest generations will appear here.</p>}</section>
        </main>
    )
}
