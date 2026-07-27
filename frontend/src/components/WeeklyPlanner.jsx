/**
 * Screen 6 — Weekly Planner with Drag-and-Drop
 *
 * 7-day calendar view where creators drag scheduled ideas between days.
 * Sidebar shows unscheduled ideas queue.
 */

import { useState, useEffect, useCallback, useRef } from 'react'

const PLATFORM_ICONS = {
    instagram: { icon: '📸', label: 'Instagram', color: '#e1306c' },
    tiktok: { icon: '🎵', label: 'TikTok', color: '#000000' },
    linkedin: { icon: '💼', label: 'LinkedIn', color: '#0a66c2' },
    facebook: { icon: '📘', label: 'Facebook', color: '#1877f2' },
}

function getMonday(date) {
    const d = new Date(date)
    const day = d.getDay()
    const diff = d.getDate() - day + (day === 0 ? -6 : 1)
    return new Date(d.setDate(diff))
}

export default function WeeklyPlanner({ accountUrl, onClose }) {
    const [weekOffset, setWeekOffset] = useState(0)
    const [days, setDays] = useState([])
    const [unscheduledIdeas, setUnscheduledIdeas] = useState([])
    const [loading, setLoading] = useState(true)
    const [draggedItem, setDraggedItem] = useState(null)
    const [dragOverDay, setDragOverDay] = useState(null)
    const [generating, setGenerating] = useState(false)

    const monday = getMonday(Date.now() + weekOffset * 7 * 86400000)
    const weekStart = monday.toISOString().slice(0, 10)
    const monthYear = monday.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })

    // Day names array
    const dayNames = []
    for (let i = 0; i < 7; i++) {
        const d = new Date(monday)
        d.setDate(d.getDate() + i)
        dayNames.push({
            date: d.toISOString().slice(0, 10),
            name: d.toLocaleDateString('en-US', { weekday: 'short' }),
            num: d.getDate(),
            isToday: d.toDateString() === new Date().toDateString(),
        })
    }

    // Fetch calendar data
    const fetchCalendar = useCallback(async () => {
        setLoading(true)
        try {
            const r = await fetch(`${accountUrl}/planner/calendar?week_start=${weekStart}`, { credentials: 'include' })
            if (r.ok) {
                const data = await r.json()
                setDays(data.days || dayNames.map(d => ({ ...d, items: [] })))
            }
        } catch (e) {
            // Fallback to empty days
            setDays(dayNames.map(d => ({ ...d, items: [] })))
        }

        // Fetch unscheduled ideas
        try {
            const r2 = await fetch(`${accountUrl}/trends/ideas?status=generated&per_page=20`, { credentials: 'include' })
            if (r2.ok) {
                const data = await r2.json()
                setUnscheduledIdeas(data.data || [])
            }
        } catch (e) {
            setUnscheduledIdeas([])
        }
        setLoading(false)
    }, [accountUrl, weekStart])

    useEffect(() => { fetchCalendar() }, [fetchCalendar])

    // Drag handlers
    const handleDragStart = (e, item, source = 'sidebar') => {
        setDraggedItem({ ...item, _source: source })
        e.dataTransfer.effectAllowed = 'move'
        e.dataTransfer.setData('text/plain', item.id || '')
        // Shrink the dragged element
        setTimeout(() => { e.target.style.opacity = '0.4' }, 0)
    }

    const handleDragEnd = (e) => {
        e.target.style.opacity = '1'
        setDraggedItem(null)
        setDragOverDay(null)
    }

    const handleDragOver = (e, dayIdx) => {
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
        setDragOverDay(dayIdx)
    }

    const handleDragLeave = (e) => {
        setDragOverDay(null)
    }

    const handleDrop = async (e, targetDayIdx) => {
        e.preventDefault()
        if (!draggedItem) return

        const targetDay = days[targetDayIdx]
        if (!targetDay) return

        // Optimistic update: add to target day
        const newItem = {
            id: draggedItem.id || `new-${Date.now()}`,
            idea_id: draggedItem.idea_id || draggedItem.id,
            platform: draggedItem.platform || 'instagram',
            scheduled_at: `${targetDay.date}T12:00:00`,
            idea_title: draggedItem.title || draggedItem.idea_title || 'Idea',
            status: 'scheduled',
        }

        setDays(prev => prev.map((d, i) => {
            if (i === targetDayIdx) {
                const existing = d.items || []
                if (existing.some(it => it.id === newItem.id)) return d
                return { ...d, items: [...existing, newItem] }
            }
            // Remove from source if it was moved between days
            if (draggedItem._source !== 'sidebar') {
                return { ...d, items: (d.items || []).filter(it => it.id !== newItem.id) }
            }
            return d
        }))

        // Remove from sidebar if dropped from there
        if (draggedItem._source === 'sidebar') {
            setUnscheduledIdeas(prev => prev.filter(i => i.id !== draggedItem.id))
        }

        // Persist to backend
        try {
            await fetch(`${accountUrl}/planner/schedule`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    idea_id: newItem.idea_id,
                    scheduled_date: targetDay.date,
                    scheduled_time: '12:00:00',
                    platform: newItem.platform,
                    conflict_resolution: 'warn',
                }),
            })
        } catch (e) {
            // Revert on failure would need full refetch
            console.error('Failed to schedule:', e)
        }

        setDraggedItem(null)
        setDragOverDay(null)
    }

    // Move item between days (existing chips)
    const handleChipDragStart = (e, item, dayIdx) => {
        e.stopPropagation()
        setDraggedItem({ ...item, _source: 'calendar', _sourceDay: dayIdx })
        e.dataTransfer.effectAllowed = 'move'
    }

    const handleChipDrop = async (e, targetDayIdx) => {
        if (!draggedItem || draggedItem._source !== 'calendar') return
        e.preventDefault()

        const sourceDayIdx = draggedItem._sourceDay
        const targetDay = days[targetDayIdx]
        if (sourceDayIdx === targetDayIdx || !targetDay) {
            setDraggedItem(null)
            return
        }

        // Optimistic move
        setDays(prev => prev.map((d, i) => {
            if (i === sourceDayIdx) return { ...d, items: (d.items || []).filter(it => it.id !== draggedItem.id) }
            if (i === targetDayIdx) return { ...d, items: [...(d.items || []), { ...draggedItem, scheduled_at: `${d.date}T${draggedItem.scheduled_at?.slice(11) || '12:00:00'}` }] }
            return d
        }))

        // Persist move
        try {
            await fetch(`${accountUrl}/planner/${draggedItem.id}`, {
                method: 'PATCH',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scheduled_at: `${targetDay.date}T12:00:00` }),
            })
        } catch (e) {
            fetchCalendar() // Full refetch on failure
        }

        setDraggedItem(null)
        setDragOverDay(null)
    }

    const handleGenerateOptimalWeek = async () => {
        setGenerating(true)
        // Simulate AI planning (would call POST /trends/weekly-plan)
        await new Promise(r => setTimeout(r, 1500))
        setGenerating(false)
        fetchCalendar()
        alert('AI has planned your optimal week! (Simulated)')
    }

    const navigateWeek = (direction) => {
        setWeekOffset(prev => prev + (direction === 'next' ? 1 : -1))
    }

    return (
        <div className="cs-weekly-planner">
            {/* Header */}
            <div className="cs-weekly-planner__header">
                <button className="cs-btn cs-btn--ghost" onClick={onClose}>← Back to Planner</button>
                <div className="cs-weekly-planner__nav">
                    <button className="cs-btn cs-btn--icon" onClick={() => navigateWeek('prev')}>‹</button>
                    <span className="cs-weekly-planner__month">{monthYear}</span>
                    <button className="cs-btn cs-btn--icon" onClick={() => navigateWeek('next')}>›</button>
                </div>
                <button className="cs-btn cs-btn--ghost" onClick={() => setWeekOffset(0)}>Today</button>
                <button
                    className="cs-btn cs-btn--primary"
                    onClick={handleGenerateOptimalWeek}
                    disabled={generating}
                >
                    {generating ? 'Generating...' : '✨ Generate Optimal Week'}
                </button>
            </div>

            <div className="cs-weekly-planner__body">
                {/* Sidebar — Ideas to Plan */}
                <div className="cs-weekly-planner__sidebar">
                    <h4>Ideas to Plan</h4>
                    <div className="cs-weekly-planner__sidebar-list">
                        {unscheduledIdeas.length === 0 && (
                            <p className="cs-weekly-planner__sidebar-empty">No unscheduled ideas</p>
                        )}
                        {unscheduledIdeas.map(idea => (
                            <div
                                key={idea.id}
                                className="cs-weekly-planner__sidebar-item"
                                draggable
                                onDragStart={(e) => handleDragStart(e, idea, 'sidebar')}
                                onDragEnd={handleDragEnd}
                            >
                                <span className="cs-weekly-planner__drag-handle">⠿</span>
                                <span className="cs-weekly-planner__sidebar-item-title">{idea.title}</span>
                                <span className="cs-weekly-planner__sidebar-item-type">{idea.content_type || 'Reel'}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* 7-Day Grid */}
                <div className="cs-weekly-planner__grid">
                    {loading ? (
                        Array.from({ length: 7 }, (_, i) => (
                            <div key={i} className="cs-weekly-planner__day cs-weekly-planner__day--loading">
                                <div className="cs-skeleton cs-skeleton--text" style={{ height: '20px', width: '50%', margin: '0 auto' }} />
                                <div className="cs-skeleton cs-skeleton--text" style={{ height: '40px', marginTop: '1rem' }} />
                            </div>
                        ))
                    ) : (
                        days.map((day, dayIdx) => (
                            <div
                                key={dayIdx}
                                className={`cs-weekly-planner__day ${day.isToday ? 'cs-weekly-planner__day--today' : ''} ${dragOverDay === dayIdx ? 'cs-weekly-planner__day--dragover' : ''}`}
                                onDragOver={(e) => handleDragOver(e, dayIdx)}
                                onDragLeave={handleDragLeave}
                                onDrop={(e) => {
                                    if (draggedItem?._source === 'calendar') {
                                        handleChipDrop(e, dayIdx)
                                    } else {
                                        handleDrop(e, dayIdx)
                                    }
                                }}
                            >
                                <div className="cs-weekly-planner__day-header">
                                    <span className="cs-weekly-planner__day-name">{day.name}</span>
                                    <span className="cs-weekly-planner__day-num">{day.num}</span>
                                </div>
                                <div className="cs-weekly-planner__day-items">
                                    {(day.items || []).map((item, ii) => {
                                        const p = PLATFORM_ICONS[item.platform] || PLATFORM_ICONS.instagram
                                        return (
                                            <div
                                                key={item.id || ii}
                                                className="cs-weekly-planner__chip"
                                                draggable
                                                onDragStart={(e) => handleChipDragStart(e, item, dayIdx)}
                                                onDragEnd={handleDragEnd}
                                                style={{ borderLeftColor: p.color }}
                                            >
                                                <span>{p.icon}</span>
                                                <span className="cs-weekly-planner__chip-title">{item.idea_title || 'Idea'}</span>
                                            </div>
                                        )
                                    })}
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>

            {generating && (
                <div className="cs-weekly-planner__overlay">
                    <div className="cs-weekly-planner__overlay-content">
                        <div className="cs-spinner" />
                        <p>AI is planning your week...</p>
                    </div>
                </div>
            )}
        </div>
    )
}
