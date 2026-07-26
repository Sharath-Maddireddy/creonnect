import { useState } from 'react'

const PLATFORMS = [
    { id: 'instagram', label: 'Instagram', icon: '📸' },
    { id: 'tiktok', label: 'TikTok', icon: '🎵' },
    { id: 'linkedin', label: 'LinkedIn', icon: '💼' },
]

const CONFLICT_MODES = [
    { id: 'reject', label: 'Reject', description: 'Don\'t schedule if there\'s a conflict' },
    { id: 'warn', label: 'Warn', description: 'Schedule but warn about conflict' },
    { id: 'force', label: 'Force', description: 'Reschedule conflicting items' },
]

export default function ContentPlanner({ ideaId, ideaTitle, onClose, onSchedule }) {
    const [date, setDate] = useState('')
    const [time, setTime] = useState('12:00')
    const [platform, setPlatform] = useState('instagram')
    const [conflictMode, setConflictMode] = useState('reject')
    const [notes, setNotes] = useState('')
    const [loading, setLoading] = useState(false)
    const [conflict, setConflict] = useState(null)

    const handleSchedule = async () => {
        if (!date || !time) return

        setLoading(true)
        setConflict(null)

        try {
            const res = await fetch(`/api/v1/accounts/placeholder/planner/schedule`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({
                    idea_id: ideaId,
                    scheduled_date: date,
                    scheduled_time: time,
                    platform,
                    conflict_resolution: conflictMode,
                    notes: notes || null,
                }),
            })

            const data = await res.json()

            if (res.status === 409) {
                setConflict(data)
            } else if (res.ok) {
                onSchedule(data)
                onClose()
            }
        } catch (e) {
            console.error('Schedule failed:', e)
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="cs-modal-backdrop" onClick={onClose}>
            <div className="cs-modal cs-modal--schedule" onClick={e => e.stopPropagation()}>
                <div className="cs-modal__header">
                    <button className="cs-modal__back" onClick={onClose}>← Back</button>
                    <h3>Schedule Idea</h3>
                </div>

                <div className="cs-modal__body">
                    <div className="cs-schedule-preview">
                        <h4>{ideaTitle}</h4>
                    </div>

                    {/* Date Picker */}
                    <div className="cs-form-group">
                        <label className="cs-form-label">Select Date</label>
                        <input
                            type="date"
                            className="cs-form-input"
                            value={date}
                            onChange={e => setDate(e.target.value)}
                            min={new Date().toISOString().split('T')[0]}
                        />
                    </div>

                    {/* Time Picker */}
                    <div className="cs-form-group">
                        <label className="cs-form-label">Time</label>
                        <input
                            type="time"
                            className="cs-form-input"
                            value={time}
                            onChange={e => setTime(e.target.value)}
                        />
                    </div>

                    {/* Platform */}
                    <div className="cs-form-group">
                        <label className="cs-form-label">Platform</label>
                        <div className="cs-chip-group">
                            {PLATFORMS.map(p => (
                                <button
                                    key={p.id}
                                    className={`cs-chip ${platform === p.id ? 'cs-chip--active' : ''}`}
                                    onClick={() => setPlatform(p.id)}
                                >
                                    {p.icon} {p.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Conflict Resolution */}
                    <div className="cs-form-group">
                        <label className="cs-form-label">If Conflict</label>
                        <div className="cs-chip-group">
                            {CONFLICT_MODES.map(mode => (
                                <button
                                    key={mode.id}
                                    className={`cs-chip ${conflictMode === mode.id ? 'cs-chip--active' : ''}`}
                                    onClick={() => setConflictMode(mode.id)}
                                    title={mode.description}
                                >
                                    {mode.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Notes */}
                    <div className="cs-form-group">
                        <label className="cs-form-label">Notes (Optional)</label>
                        <textarea
                            className="cs-form-textarea"
                            placeholder="Add notes or reminders for this post..."
                            value={notes}
                            onChange={e => setNotes(e.target.value)}
                            rows={3}
                        />
                    </div>

                    {/* Conflict Warning */}
                    {conflict && (
                        <div className="cs-conflict-warning">
                            <h4>⚠️ Schedule Conflict</h4>
                            <p>{conflict.suggestion}</p>
                            <div className="cs-conflict-items">
                                {conflict.conflicting_items?.map(item => (
                                    <div key={item.id} className="cs-conflict-item">
                                        <span>{item.idea_title || 'Another post'}</span>
                                        <span>{item.scheduled_time}</span>
                                    </div>
                                ))}
                            </div>
                            {conflict.available_slots?.length > 0 && (
                                <div className="cs-available-slots">
                                    <span>Available slots: </span>
                                    {conflict.available_slots.map(slot => (
                                        <button
                                            key={slot}
                                            className="cs-slot-btn"
                                            onClick={() => setTime(slot)}
                                        >
                                            {slot}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                <div className="cs-modal__footer">
                    <button className="cs-btn cs-btn--secondary" onClick={onClose}>Cancel</button>
                    <button
                        className="cs-btn cs-btn--primary"
                        onClick={handleSchedule}
                        disabled={!date || !time || loading}
                    >
                        {loading ? 'Scheduling...' : 'Add to Planner'}
                    </button>
                </div>
            </div>
        </div>
    )
}
