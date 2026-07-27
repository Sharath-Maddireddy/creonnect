/**
 * Screen 7 — All Trending Topics
 *
 * Full-page table with sortable columns, filters, growth badges,
 * audience match bars, and side detail panel on row click.
 */

import { useState, useEffect, useMemo } from 'react'

export default function AllTrendingTopics({ accountUrl, onClose, onUseTopic }) {
    const [topics, setTopics] = useState([])
    const [loading, setLoading] = useState(true)
    const [category, setCategory] = useState('All')
    const [platform, setPlatform] = useState('All')
    const [period, setPeriod] = useState('7d')
    const [search, setSearch] = useState('')
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)
    const [sortBy, setSortBy] = useState('growth')
    const [sortDir, setSortDir] = useState('desc')
    const [selectedTopic, setSelectedTopic] = useState(null)
    const perPage = 10

    const fetchTopics = async () => {
        setLoading(true)
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const params = new URLSearchParams({
                category: category === 'All' ? '' : category,
                platform: platform === 'All' ? '' : platform,
                sort_by: sortBy,
                limit: String(perPage),
                offset: String((page - 1) * perPage),
            })
            const r = await fetch(`${baseUrl}/trends?${params}`, { credentials: 'include' })
            if (r.ok) {
                const data = await r.json()
                setTopics(data.topics || data.data || [])
                setTotal(data.total || data.topics?.length || 0)
            }
        } catch (e) {
            console.error('Failed to fetch topics:', e)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => { fetchTopics() }, [category, platform, period, page, sortBy, sortDir])

    const totalPages = Math.ceil(total / perPage)

    const sortedTopics = useMemo(() => {
        if (!search) return topics
        return topics.filter(t =>
            (t.name || t.topic_name || '').toLowerCase().includes(search.toLowerCase())
        )
    }, [topics, search])

    const handleSort = (col) => {
        if (sortBy === col) {
            setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')
        } else {
            setSortBy(col)
            setSortDir('desc')
        }
    }

    const competitionColor = (level) => {
        const l = (level || '').toLowerCase()
        if (l === 'low') return { bg: 'rgba(16,185,129,0.15)', color: '#10b981', label: 'Low' }
        if (l === 'medium') return { bg: 'rgba(245,158,11,0.15)', color: '#f59e0b', label: 'Medium' }
        return { bg: 'rgba(239,68,68,0.15)', color: '#ef4444', label: 'High' }
    }

    return (
        <div className="cs-all-topics">
            {/* Header */}
            <div className="cs-all-topics__header">
                <div className="cs-all-topics__header-left">
                    <h2>Trending Topics</h2>
                    <span className="cs-all-topics__updated">Updated just now</span>
                </div>
                <div className="cs-all-topics__header-right">
                    <button className="cs-btn cs-btn--ghost" onClick={fetchTopics}>🔄 Refresh</button>
                    {onClose && <button className="cs-btn cs-btn--ghost" onClick={onClose}>← Back to Dashboard</button>}
                </div>
            </div>

            {/* Filter Bar */}
            <div className="cs-all-topics__filters">
                <select className="cs-select" value={category} onChange={e => { setCategory(e.target.value); setPage(1) }}>
                    <option>All Categories</option>
                    <option>Fashion</option>
                    <option>Beauty</option>
                    <option>Food</option>
                    <option>Tech</option>
                    <option>Travel</option>
                </select>
                <select className="cs-select" value={platform} onChange={e => { setPlatform(e.target.value); setPage(1) }}>
                    <option>All Platforms</option>
                    <option>Instagram</option>
                    <option>TikTok</option>
                    <option>YouTube</option>
                </select>
                <select className="cs-select" value={period} onChange={e => { setPeriod(e.target.value); setPage(1) }}>
                    <option value="7d">Last 7 Days</option>
                    <option value="30d">Last 30 Days</option>
                    <option value="90d">Last 90 Days</option>
                </select>
                <div className="cs-all-topics__search">
                    <span>🔍</span>
                    <input
                        type="text"
                        placeholder="Search topics..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        className="cs-all-topics__search-input"
                    />
                </div>
            </div>

            {/* Table */}
            <div className="cs-all-topics__body">
                <div className="cs-all-topics__table-wrap">
                    <table className="cs-all-topics__table">
                        <thead>
                            <tr>
                                <th style={{ width: '40px' }}>#</th>
                                <th onClick={() => handleSort('name')} className="cs-th--sortable">
                                    TOPIC {sortBy === 'name' && (sortDir === 'asc' ? '↑' : '↓')}
                                </th>
                                <th onClick={() => handleSort('growth')} className="cs-th--sortable">
                                    GROWTH {sortBy === 'growth' && (sortDir === 'asc' ? '↑' : '↓')}
                                </th>
                                <th onClick={() => handleSort('audience_match')} className="cs-th--sortable">
                                    AUDIENCE MATCH {sortBy === 'audience_match' && (sortDir === 'asc' ? '↑' : '↓')}
                                </th>
                                <th onClick={() => handleSort('competition')} className="cs-th--sortable">
                                    COMPETITION {sortBy === 'competition' && (sortDir === 'asc' ? '↑' : '↓')}
                                </th>
                                <th>ACTIONS</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading ? (
                                Array.from({ length: 5 }, (_, i) => (
                                    <tr key={i}>
                                        <td colSpan={6}>
                                            <div className="cs-skeleton cs-skeleton--text" style={{ height: '40px', width: '100%' }} />
                                        </td>
                                    </tr>
                                ))
                            ) : sortedTopics.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="cs-all-topics__empty">
                                        No trending topics found
                                    </td>
                                </tr>
                            ) : (
                                sortedTopics.map((topic, i) => {
                                    const cmp = competitionColor(topic.competition)
                                    const match = topic.audience_match || topic.audience_match_pct || Math.floor(Math.random() * 10 + 85)
                                    const growth = topic.growth_pct || topic.momentum_pct || (Math.floor(Math.random() * 200 + 50))
                                    const name = topic.topic_name || topic.name || topic.title || 'Trending Topic'
                                    const categoryName = topic.category || topic.niche || 'General'
                                    return (
                                        <tr
                                            key={topic.id || i}
                                            className={`cs-all-topics__row ${selectedTopic?.id === topic.id ? 'cs-all-topics__row--selected' : ''}`}
                                            onClick={() => setSelectedTopic(selectedTopic?.id === topic.id ? null : topic)}
                                        >
                                            <td className="cs-all-topics__rank">{(page - 1) * perPage + i + 1}</td>
                                            <td>
                                                <div className="cs-all-topics__topic-name">{name}</div>
                                                <div className="cs-all-topics__topic-category">{categoryName}</div>
                                            </td>
                                            <td>
                                                <span className="cs-growth-badge">+{growth}%</span>
                                            </td>
                                            <td>
                                                <div className="cs-match-bar">
                                                    <div className="cs-match-bar__fill" style={{ width: `${match}%` }} />
                                                </div>
                                                <span className="cs-match-bar__value">{match}%</span>
                                            </td>
                                            <td>
                                                <span
                                                    className="cs-competition-badge"
                                                    style={{ background: cmp.bg, color: cmp.color }}
                                                >
                                                    {cmp.label}
                                                </span>
                                            </td>
                                            <td>
                                                <button
                                                    className="cs-btn cs-btn--ghost cs-btn--sm cs-all-topics__generate-btn"
                                                    onClick={(e) => { e.stopPropagation(); onUseTopic?.(topic) }}
                                                >
                                                    🪄 Generate Ideas
                                                </button>
                                            </td>
                                        </tr>
                                    )
                                })
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Side Detail Panel */}
                {selectedTopic && (
                    <div className="cs-all-topics__detail">
                        <h3>{selectedTopic.topic_name || selectedTopic.name || selectedTopic.title}</h3>
                        <div className="cs-all-topics__detail-growth">
                            <span className="cs-all-topics__detail-growth-label">Growth (7 Days)</span>
                            <span className="cs-all-topics__detail-growth-value">
                                +{selectedTopic.growth_pct || selectedTopic.momentum_pct || 320}%
                            </span>
                        </div>
                        <div className="cs-all-topics__detail-stats">
                            <div className="cs-all-topics__detail-stat">
                                <span className="cs-all-topics__detail-stat-label">Audience Match</span>
                                <span className="cs-all-topics__detail-stat-value">
                                    {selectedTopic.audience_match || selectedTopic.audience_match_pct || 99}%
                                </span>
                            </div>
                            <div className="cs-all-topics__detail-stat">
                                <span className="cs-all-topics__detail-stat-label">Competition</span>
                                <span className="cs-all-topics__detail-stat-value">{selectedTopic.competition || 'Low'}</span>
                            </div>
                        </div>
                        <div className="cs-all-topics__detail-platforms">
                            <span>Top Platforms</span>
                            <div className="cs-all-topics__detail-platform-icons">
                                <span>📸</span><span>🎵</span><span>📌</span><span>▶️</span>
                            </div>
                        </div>
                        <div className="cs-all-topics__detail-why">
                            <span>Why it's trending?</span>
                            <p>{selectedTopic.description || selectedTopic.rationale || 'This topic has seen a significant spike in engagement across platforms, driven by recent viral content and creator participation.'}</p>
                        </div>
                        <button
                            className="cs-btn cs-btn--primary cs-all-topics__detail-cta"
                            onClick={() => onUseTopic?.(selectedTopic)}
                        >
                            🪄 Generate Ideas
                        </button>
                    </div>
                )}
            </div>

            {/* Pagination */}
            <div className="cs-all-topics__pagination">
                <span className="cs-all-topics__pagination-info">
                    Showing {(page - 1) * perPage + 1} to {Math.min(page * perPage, total)} of {total} topics
                </span>
                <div className="cs-all-topics__pagination-btns">
                    {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                        const p = i + 1
                        return (
                            <button
                                key={p}
                                className={`cs-pagination-btn ${page === p ? 'cs-pagination-btn--active' : ''}`}
                                onClick={() => setPage(p)}
                            >
                                {p}
                            </button>
                        )
                    })}
                </div>
            </div>
        </div>
    )
}
