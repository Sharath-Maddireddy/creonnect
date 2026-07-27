/**
 * Screen 12 — Publish / Schedule
 *
 * Multi-platform scheduling drawer with platform toggles,
 * date/time picker, preview, and advanced options.
 */

import { useState } from 'react'

const PLATFORMS = [
    { id: 'instagram', icon: '📸', label: 'Instagram', subLabel: 'Story', enabled: true },
    { id: 'tiktok', icon: '🎵', label: 'TikTok', subLabel: 'Video', enabled: true },
    { id: 'youtube', icon: '▶️', label: 'YouTube Shorts', subLabel: 'Short', enabled: true },
    { id: 'facebook', icon: '📘', label: 'Facebook', subLabel: 'Post', enabled: false },
    { id: 'linkedin', icon: '💼', label: 'LinkedIn', subLabel: 'Post', enabled: false },
]

const TIMEZONES = [
    '(UTC+05:30) Mumbai, India',
    '(UTC+00:00) London',
    '(UTC-05:00) New York',
    '(UTC-08:00) Los Angeles',
    '(UTC+08:00) Singapore',
    '(UTC+10:00) Sydney',
]

export default function PublishSchedule({ ideaId, ideaTitle, thumbnailUrl, accountUrl, onClose, onSchedule }) {
    const [platforms, setPlatforms] = useState(
        PLATFORMS.filter(p => p.enabled).map(p => p.id)
    )
    const [scheduleMode, setScheduleMode] = useState('later') // 'now' | 'later'
    const [scheduledDate, setScheduledDate] = useState(() => {
        const d = new Date()
        d.setDate(d.getDate() + 1)
        return d.toISOString().slice(0, 10)
    })
    const [scheduledTime, setScheduledTime] = useState('20:30')
    const [timezone, setTimezone] = useState(TIMEZONES[0])
    const [advancedOpen, setAdvancedOpen] = useState(false)
    const [scheduling, setScheduling] = useState(false)
    const [success, setSuccess] = useState(null)

    const togglePlatform = (id) => {
        setPlatforms(prev =>
            prev.includes(id) ? prev.filter(p => p !== id) : [...prev, id]
        )
    }

    const handleSchedule = async () => {
        setScheduling(true)
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const r = await fetch(`${baseUrl}/planner/schedule`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    idea_id: ideaId,
                    scheduled_date: scheduleMode === 'now' ? new Date().toISOString().slice(0, 10) : scheduledDate,
                    scheduled_time: scheduleMode === 'now' ? new Date().toTimeString().slice(0, 8) : `${scheduledTime}:00`,
                    platform: platforms[0] || 'instagram',
                    conflict_resolution: 'warn',
                }),
            })
            if (r.ok) {
                setSuccess(`Scheduled for ${scheduledDate} at ${scheduledTime}`)
                onSchedule?.({
                    platforms,
                    scheduled_at: `${scheduledDate}T${scheduledTime}:00`,
                    timezone,
                })
                setTimeout(() => {
                    setSuccess(null)
                    onClose?.()
                }, 2000)
            }
        } catch (e) {
            console.error('Schedule failed:', e)
        } finally {
            setScheduling(false)
        }
    }

    const formatDate = (isoDate) => {
        const d = new Date(isoDate + 'T00:00:00')
        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    }

    const formatTime = (time24) => {
        const [h, m] = time24.split(':')
        const hour = parseInt(h) || 0
        const ampm = hour >= 12 ? 'PM' : 'AM'
        const h12 = hour % 12 || 12
        return `${h12}:${m} ${ampm}`
    }

    return (
        <div className="cs-modal-overlay cs-modal-overlay--open" onClick={onClose}>
            <div className="cs-modal cs-publish-schedule" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="cs-publish-schedule__header">
                    <button className="cs-btn cs-btn--ghost" onClick={onClose}>← Back to Idea Details</button>
                    <h3>Publish / Schedule</h3>
                    <div />
                </div>

                <div className="cs-publish-schedule__body">
                    {success ? (
                        <div className="cs-publish-schedule__success">
                            <span>✅</span>
                            <p>{success}</p>
                        </div>
                    ) : (
                        <>
                            {/* Platforms */}
                            <div className="cs-publish-schedule__section">
                                <h4 className="cs-publish-schedule__section-title">PLATFORMS</h4>
                                <div className="cs-publish-schedule__platform-list">
                                    {PLATFORMS.map(p => (
                                        <label
                                            key={p.id}
                                            className={`cs-platform-toggle ${platforms.includes(p.id) ? 'cs-platform-toggle--active' : ''}`}
                                        >
                                            <span className="cs-platform-toggle__icon">{p.icon}</span>
                                            <div className="cs-platform-toggle__info">
                                                <span className="cs-platform-toggle__name">{p.label}</span>
                                                <span className="cs-platform-toggle__sub">{p.subLabel}</span>
                                            </div>
                                            <div
                                                className={`cs-toggle-switch ${platforms.includes(p.id) ? 'cs-toggle-switch--on' : ''}`}
                                                onClick={(e) => { e.preventDefault(); togglePlatform(p.id) }}
                                            >
                                                <div className="cs-toggle-switch__knob" />
                                            </div>
                                        </label>
                                    ))}
                                </div>
                            </div>

                            {/* Post Preview */}
                            <div className="cs-publish-schedule__section">
                                <h4 className="cs-publish-schedule__section-title">POST PREVIEW</h4>
                                <div className="cs-publish-schedule__preview">
                                    {thumbnailUrl ? (
                                        <img src={thumbnailUrl} alt="Post preview" className="cs-publish-schedule__preview-img" />
                                    ) : (
                                        <div className="cs-publish-schedule__preview-placeholder">
                                            <span>🎬</span>
                                        </div>
                                    )}
                                    <button className="cs-btn cs-btn--link" style={{ fontSize: '0.75rem' }}>Change Thumbnail</button>
                                </div>
                            </div>

                            {/* Schedule */}
                            <div className="cs-publish-schedule__section">
                                <h4 className="cs-publish-schedule__section-title">SCHEDULE</h4>
                                <div className="cs-publish-schedule__schedule-options">
                                    <button
                                        className={`cs-publish-schedule__mode-btn ${scheduleMode === 'now' ? 'cs-publish-schedule__mode-btn--active' : ''}`}
                                        onClick={() => setScheduleMode('now')}
                                    >
                                        Publish Now
                                    </button>
                                    <button
                                        className={`cs-publish-schedule__mode-btn ${scheduleMode === 'later' ? 'cs-publish-schedule__mode-btn--active' : ''}`}
                                        onClick={() => setScheduleMode('later')}
                                    >
                                        Schedule for Later
                                    </button>
                                </div>

                                {scheduleMode === 'later' && (
                                    <div className="cs-publish-schedule__datetime">
                                        <div className="cs-publish-schedule__datetime-row">
                                            <div className="cs-publish-schedule__date-field">
                                                <label>Date</label>
                                                <input
                                                    type="date"
                                                    value={scheduledDate}
                                                    onChange={e => setScheduledDate(e.target.value)}
                                                    className="cs-form-input cs-form-input--sm"
                                                />
                                            </div>
                                            <div className="cs-publish-schedule__time-field">
                                                <label>Time</label>
                                                <input
                                                    type="time"
                                                    value={scheduledTime}
                                                    onChange={e => setScheduledTime(e.target.value)}
                                                    className="cs-form-input cs-form-input--sm"
                                                />
                                            </div>
                                        </div>
                                        <div className="cs-publish-schedule__date-display">
                                            {formatDate(scheduledDate)} at {formatTime(scheduledTime)}
                                        </div>
                                    </div>
                                )}

                                {/* Timezone */}
                                <div className="cs-publish-schedule__timezone" style={{ marginTop: '0.75rem' }}>
                                    <select
                                        className="cs-select"
                                        value={timezone}
                                        onChange={e => setTimezone(e.target.value)}
                                    >
                                        {TIMEZONES.map(tz => (
                                            <option key={tz} value={tz}>{tz}</option>
                                        ))}
                                    </select>
                                </div>

                                {/* Advanced Options */}
                                <div className="cs-publish-schedule__advanced" style={{ marginTop: '1rem' }}>
                                    <button
                                        className="cs-btn cs-btn--link"
                                        onClick={() => setAdvancedOpen(!advancedOpen)}
                                    >
                                        {advancedOpen ? '▾' : '▸'} Advanced Options
                                    </button>
                                    {advancedOpen && (
                                        <div className="cs-publish-schedule__advanced-content">
                                            <label className="cs-checkbox-label">
                                                <input type="checkbox" /> Cross-post to all platforms simultaneously
                                            </label>
                                            <label className="cs-checkbox-label">
                                                <input type="checkbox" /> Use platform-specific captions
                                            </label>
                                            <label className="cs-checkbox-label">
                                                <input type="checkbox" /> Auto-adjust thumbnail per platform
                                            </label>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </>
                    )}
                </div>

                {/* Footer */}
                <div className="cs-publish-schedule__footer">
                    <button className="cs-btn cs-btn--ghost" onClick={onClose}>Save as Draft</button>
                    <button
                        className="cs-btn cs-btn--primary"
                        onClick={handleSchedule}
                        disabled={platforms.length === 0 || scheduling}
                    >
                        {scheduling ? 'Scheduling...' : 'Schedule Post'}
                    </button>
                </div>
            </div>
        </div>
    )
}
