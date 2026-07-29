import { useEffect, useState } from 'react'

const STEPS = [
    'Analysing your recent content',
    'Researching trending topics',
    'Analysing your audience',
    'Checking competitors',
    'Generating high-potential ideas',
]

export default function GenerationProgress({ jobId, accountUrl, onComplete, onError }) {
    const [progress, setProgress] = useState({
        status: 'processing',
        current_step: 0,
        total_steps: 5,
        step_label: 'Starting...',
        percent_complete: 0,
    })

    useEffect(() => {
        if (!jobId) return

        let cancelled = false
        const MAX_POLL_MS = 360_000 // 6 minutes — reasoning models (gpt-5.6-terra) can take a while
        const startTime = Date.now()
        let consecutivePollErrors = 0

        const poll = async () => {
            if (cancelled) return

            // Timeout guard — stop polling after 2 minutes
            if (Date.now() - startTime > MAX_POLL_MS) {
                if (!cancelled) onError('Generation timed out. Please try again.')
                return
            }

            try {
                const res = await fetch(
                    `${accountUrl}/trends/generate-ideas/${jobId}/status`,
                    { credentials: 'include' }
                )
                if (!res.ok) throw new Error(`Status ${res.status}`)
                const data = await res.json()

                if (cancelled) return
                consecutivePollErrors = 0
                setProgress(data)

                if (data.status === 'completed') {
                    onComplete(data.ideas || [])
                } else if (data.status === 'failed') {
                    onError(data.error || 'Generation failed')
                }
            } catch (e) {
                consecutivePollErrors += 1
                if (!cancelled && consecutivePollErrors >= 3) {
                    onError('Unable to check generation status. Please verify the API is running and try again.')
                }
            }
        }

        // Start immediately so the UI reflects a queued/failed job without an
        // unnecessary initial delay, then continue polling for progress.
        poll()
        const pollInterval = setInterval(poll, 2000)

        return () => {
            cancelled = true
            clearInterval(pollInterval)
        }
    }, [jobId, accountUrl, onComplete, onError])


    return (
        <div className="cs-modal-backdrop">
            <div className="cs-modal cs-modal--progress">
                <div className="cs-modal__header">
                    <h3>Generating Ideas...</h3>
                    <p className="cs-modal__subtitle">This may take 1–3 minutes with our advanced AI model</p>
                </div>

                <div className="cs-modal__body">
                    {/* Progress Bar */}
                    <div className="cs-progress">
                        <div
                            className="cs-progress__bar"
                            style={{ width: `${progress.percent_complete * 100}%` }}
                        />
                    </div>

                    {/* Steps */}
                    <div className="cs-progress-steps">
                        {STEPS.map((step, i) => (
                            <div
                                key={i}
                                className={`cs-progress-step ${
                                    i < progress.current_step ? 'cs-progress-step--done' :
                                    i === progress.current_step ? 'cs-progress-step--active' :
                                    ''
                                }`}
                            >
                                <span className="cs-progress-step__icon">
                                    {i < progress.current_step ? '✓' :
                                     i === progress.current_step ? '○' : '○'}
                                </span>
                                <span className="cs-progress-step__label">{step}</span>
                            </div>
                        ))}
                    </div>

                    {progress.status === 'failed' && (
                        <div className="cs-progress-error">
                            <p>Generation failed: {progress.error}</p>
                            <button className="cs-btn cs-btn--secondary" onClick={onError}>
                                Try Again
                            </button>
                        </div>
                    )}
                </div>

                <div className="cs-modal__footer">
                    <p className="cs-progress-warning">⚠ Please don't close this window</p>
                </div>
            </div>
        </div>
    )
}
