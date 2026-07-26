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
        const pollInterval = setInterval(async () => {
            if (cancelled) return

            try {
                const res = await fetch(
                    `${accountUrl}/trends/generate-ideas/${jobId}/status`,
                    { credentials: 'include' }
                )
                if (!res.ok) throw new Error(`Status ${res.status}`)
                const data = await res.json()

                if (cancelled) return
                setProgress(data)

                if (data.status === 'completed') {
                    clearInterval(pollInterval)
                    onComplete(data.ideas || [])
                } else if (data.status === 'failed') {
                    clearInterval(pollInterval)
                    onError(data.error || 'Generation failed')
                }
            } catch (e) {
                if (!cancelled) {
                    console.error('Poll error:', e)
                }
            }
        }, 2000)

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
                    <p className="cs-modal__subtitle">This may take a few seconds</p>
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
