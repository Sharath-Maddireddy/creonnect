import { useState, useEffect } from 'react'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function getWeekStart(date) {
    const d = new Date(date)
    const day = d.getDay()
    const diff = d.getDate() - day + (day === 0 ? -6 : 1)
    d.setDate(diff)
    return d.toISOString().split('T')[0]
}

function addDays(dateStr, days) {
    const d = new Date(dateStr)
    d.setDate(d.getDate() + days)
    return d.toISOString().split('T')[0]
}

function formatDate(dateStr) {
    const d = new Date(dateStr)
    return d.getDate()
}

export default function CalendarView({ accountUrl, onSelectItem }) {
    const [weekStart, setWeekStart] = useState(getWeekStart(new Date()))
    const [schedule, setSchedule] = useState(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchSchedule()
    }, [weekStart])

    const fetchSchedule = async () => {
        setLoading(true)
        try {
            const res = await fetch(
                `${accountUrl}/planner?week_start=${weekStart}`,
                { credentials: 'include' }
            )
            if (res.ok) {
                const data = await res.json()
                setSchedule(data)
            }
        } catch (e) {
            console.error('Failed to fetch schedule:', e)
        } finally {
            setLoading(false)
        }
    }

    const prevWeek = () => setWeekStart(addDays(weekStart, -7))
    const nextWeek = () => setWeekStart(addDays(weekStart, 7))

    const weekDays = Array.from({ length: 7 }, (_, i) => {
        const date = addDays(weekStart, i)
        const daySchedule = schedule?.days?.find(d => d.date === date)
        return {
            date,
            dayName: DAYS[i],
            items: daySchedule?.items || [],
        }
    })

    const weekLabel = `${new Date(weekStart).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} – ${addDays(weekStart, 6).split('-').slice(1).join('/')}`

    return (
        <div className="cs-calendar">
            <div className="cs-calendar__header">
                <h3>Content Planner</h3>
                <div className="cs-calendar__nav">
                    <button className="cs-calendar__nav-btn" onClick={prevWeek}>←</button>
                    <span className="cs-calendar__week">{weekLabel}</span>
                    <button className="cs-calendar__nav-btn" onClick={nextWeek}>→</button>
                </div>
            </div>

            {loading ? (
                <div className="cs-calendar-loading">Loading schedule...</div>
            ) : (
                <div className="cs-calendar__grid">
                    {weekDays.map(day => (
                        <div key={day.date} className="cs-calendar__day">
                            <div className="cs-calendar__day-header">
                                <span className="cs-calendar__day-name">{day.dayName}</span>
                                <span className="cs-calendar__day-date">{formatDate(day.date)}</span>
                            </div>
                            <div className="cs-calendar__day-items">
                                {day.items.length === 0 ? (
                                    <div className="cs-calendar__empty">+</div>
                                ) : (
                                    day.items.map(item => (
                                        <div
                                            key={item.id}
                                            className="cs-calendar__item"
                                            onClick={() => onSelectItem?.(item)}
                                        >
                                            <span className="cs-calendar__item-time">{item.scheduled_at}</span>
                                            <span className="cs-calendar__item-title">{item.idea_title || 'Post'}</span>
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
