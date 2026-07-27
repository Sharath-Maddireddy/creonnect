/**
 * Screen 17 — Notifications Panel
 *
 * In-app notification bell feed showing alerts for completed AI jobs,
 * new trends, and scheduled post reminders.
 */

import { useState, useEffect, useCallback, useRef } from 'react'

const TYPE_ICONS = {
    generation_complete: '✨',
    weekly_plan_ready: '📅',
    trends_detected: '🔥',
    post_performance: '📈',
    idea_scheduled: '✅',
}

export default function NotificationsPanel({ accountUrl }) {
    const [open, setOpen] = useState(false)
    const [notifications, setNotifications] = useState([])
    const [unreadCount, setUnreadCount] = useState(0)
    const [loading, setLoading] = useState(false)
    const panelRef = useRef(null)

    // Fetch notifications
    useEffect(() => {
        if (!accountUrl) return
        setLoading(true)
        fetch(`${accountUrl}/notifications?limit=10`, { credentials: 'include' })
            .then(r => r.ok ? r.json() : Promise.reject(r))
            .then(d => {
                setNotifications(d.notifications || [])
                setUnreadCount(d.unread_count || 0)
            })
            .catch(() => {})
            .finally(() => setLoading(false))

        // Auto-refresh every 60s
        const interval = setInterval(() => {
            fetch(`${accountUrl}/notifications?limit=10`, { credentials: 'include' })
                .then(r => r.ok ? r.json() : Promise.reject(r))
                .then(d => {
                    setNotifications(d.notifications || [])
                    setUnreadCount(d.unread_count || 0)
                })
                .catch(() => {})
        }, 60000)
        return () => clearInterval(interval)
    }, [accountUrl])

    // Close panel on outside click
    useEffect(() => {
        if (!open) return
        const handler = (e) => {
            if (panelRef.current && !panelRef.current.contains(e.target)) {
                setOpen(false)
            }
        }
        document.addEventListener('mousedown', handler)
        return () => document.removeEventListener('mousedown', handler)
    }, [open])

    const handleMarkAllRead = useCallback(() => {
        fetch(`${accountUrl}/notifications/read-all`, { method: 'PATCH', credentials: 'include' })
            .catch(() => {})
        setUnreadCount(0)
        setNotifications(prev => prev.map(n => ({ ...n, read: true })))
    }, [accountUrl])

    const handleNotificationClick = useCallback((notification) => {
        // Mark as read
        fetch(`${accountUrl}/notifications/${notification.id}/read`, { method: 'PATCH', credentials: 'include' })
            .catch(() => {})
        setUnreadCount(prev => Math.max(0, prev - 1))
        setNotifications(prev => prev.map(n => n.id === notification.id ? { ...n, read: true } : n))
        setOpen(false)

        // Navigate based on type
        if (notification.type === 'generation_complete') {
            window.scrollTo({ top: document.querySelector('.cs-generated-ideas')?.offsetTop || 0, behavior: 'smooth' })
        }
    }, [accountUrl])

    const relativeTime = (iso) => {
        if (!iso) return ''
        const diff = Date.now() - new Date(iso).getTime()
        const mins = Math.floor(diff / 60000)
        if (mins < 1) return 'Just now'
        if (mins < 60) return `${mins}m ago`
        const hours = Math.floor(mins / 60)
        if (hours < 24) return `${hours}h ago`
        return `${Math.floor(hours / 24)}d ago`
    }

    return (
        <div className="cs-notifications" ref={panelRef}>
            {/* Bell Icon */}
            <button
                className="cs-notifications__bell"
                onClick={() => setOpen(!open)}
                title="Notifications"
            >
                🔔
                {unreadCount > 0 && (
                    <span className="cs-notifications__badge">{unreadCount > 9 ? '9+' : unreadCount}</span>
                )}
            </button>

            {/* Panel */}
            {open && (
                <div className="cs-notifications__panel">
                    <div className="cs-notifications__header">
                        <h3>Notifications</h3>
                        {unreadCount > 0 && (
                            <button
                                className="cs-notifications__mark-read"
                                onClick={handleMarkAllRead}
                            >
                                Mark all as read
                            </button>
                        )}
                    </div>

                    <div className="cs-notifications__list">
                        {loading && (
                            <>
                                {[1, 2, 3, 4].map(i => (
                                    <div key={i} className="cs-notifications__skeleton">
                                        <div className="cs-skeleton cs-skeleton--text" style={{ width: '80%' }} />
                                        <div className="cs-skeleton cs-skeleton--text" style={{ width: '50%', height: '12px' }} />
                                    </div>
                                ))}
                            </>
                        )}

                        {!loading && notifications.length === 0 && (
                            <div className="cs-notifications__empty">
                                <span className="cs-notifications__empty-icon">🎉</span>
                                <p>You're all caught up</p>
                            </div>
                        )}

                        {!loading && notifications.map(n => (
                            <div
                                key={n.id}
                                className={`cs-notifications__item ${!n.read ? 'cs-notifications__item--unread' : ''}`}
                                onClick={() => handleNotificationClick(n)}
                            >
                                <span className="cs-notifications__item-icon">
                                    {TYPE_ICONS[n.type] || '🔔'}
                                </span>
                                <div className="cs-notifications__item-content">
                                    <span className="cs-notifications__item-title">{n.title}</span>
                                    <span className="cs-notifications__item-body">{n.body}</span>
                                </div>
                                <span className="cs-notifications__item-time">{relativeTime(n.created_at)}</span>
                                {!n.read && <span className="cs-notifications__item-dot" />}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}
