/**
 * Screen 7 — All Trending Topics
 *
 * Full-page table with sortable columns, filters, growth badges,
 * audience match bars, and side detail panel on row click.
 */

import { useState, useEffect } from 'react'

export default function AllTrendingTopics({ accountUrl, onClose, onUseTopic }) {
    const [topics, setTopics] = useState([])
    const [loading, setLoading] = useState(true)
    const [trendType, setTrendType] = useState('All')
    const [momentum, setMomentum] = useState('All')
    const [competition, setCompetition] = useState('All')
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
                search,
                sort_by: sortBy,
                sort_dir: sortDir,
                limit: String(perPage),
                offset: String((page - 1) * perPage),
            })
            if (trendType !== 'All') params.set('trend_type', trendType.toLowerCase())
            if (momentum !== 'All') params.set('momentum', momentum.toLowerCase())
            if (competition !== 'All') params.set('competition_level', competition.toLowerCase())
            const r = await fetch(`${baseUrl}/trends/topics?${params.toString()}`, { credentials: 'include' })
            if (r.ok) {
                const data = await r.json()
                const rows = data.topics || data.data || []
                setTopics(rows)
                setTotal(data.total || rows.length || 0)
            }
        } catch (e) {
            console.error('Failed to fetch topics:', e)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => { fetchTopics() }, [accountUrl, search, trendType, momentum, competition, page, sortBy, sortDir])

    const totalPages = Math.max(1, Math.ceil(total / perPage))

    useEffect(() => {
        setPage(1)
    }, [search, trendType, momentum, competition, sortBy, sortDir])

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
                    <span className="cs-all-topics__updated">
                        {loading ? 'Refreshing topic signals…' : `${total} topic trend${total === 1 ? '' : 's'} available`}
                    </span>
                </div>
                <div className="cs-all-topics__header-right">
                    <button className="cs-btn cs-btn--ghost" onClick={fetchTopics}>🔄 Refresh</button>
                    {onClose && <button className="cs-btn cs-btn--ghost" onClick={onClose}>← Back to Trends</button>}
                </div>
            </div>

            {/* Filter Bar */}
            <div className="cs-all-topics__filters">
                <select className="cs-select" value={trendType} onChange={e => { setTrendType(e.target.value); setPage(1) }}>
                    <option>All</option>
                    <option>Topic</option>
                    <option>Format</option>
                    <option>Hashtag</option>
                </select>
                <select className="cs-select" value={momentum} onChange={e => { setMomentum(e.target.value); setPage(1) }}>
                    <option>All</option>
                    <option>Rising</option>
                    <option>Peaking</option>
                    <option>Falling</option>
                </select>
                <select className="cs-select" value={competition} onChange={e => { setCompetition(e.target.value); setPage(1) }}>
                    <option>All</option>
                    <option>Low</option>
                    <option>Medium</option>
                    <option>High</option>
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
                            ) : topics.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="cs-all-topics__empty">
                                        No topic trends match this filter
                                    </td>
                                </tr>
                            ) : (
                                topics.map((topic, i) => {
                                    const cmp = competitionColor(topic.competition_level)
                                    const match = topic.audience_match_pct || 0
                                    const growth = topic.growth_pct || 0
                                    const name = topic.topic_name || 'Trending Topic'
                                    const categoryName = topic.trend_type || 'General'
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
                                                    Generate Full Ideas
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
                                +{selectedTopic.growth_pct || 0}%
                            </span>
                        </div>
                        <div className="cs-all-topics__detail-stats">
                            <div className="cs-all-topics__detail-stat">
                                <span className="cs-all-topics__detail-stat-label">Audience Match</span>
                                <span className="cs-all-topics__detail-stat-value">
                                    {selectedTopic.audience_match_pct || 0}%
                                </span>
                            </div>
                            <div className="cs-all-topics__detail-stat">
                                <span className="cs-all-topics__detail-stat-label">Competition</span>
                                <span className="cs-all-topics__detail-stat-value">{selectedTopic.competition_level || 'Low'}</span>
                            </div>
                        </div>
                        <div className="cs-all-topics__detail-why">
                            <span>Why this topic is showing up</span>
                            <p>{selectedTopic.description || 'This topic is currently being surfaced from the creator trend analysis pipeline.'}</p>
                            <span>Why it fits this creator</span>
                            <p>{selectedTopic.why_it_fits || 'This topic aligns with the creator’s niche and recent content patterns.'}</p>
                            {selectedTopic.example_reference && (
                                <>
                                    <span>Reference cue</span>
                                    <p>{selectedTopic.example_reference}</p>
                                </>
                            )}
                        </div>
                        <button
                            className="cs-btn cs-btn--primary cs-all-topics__detail-cta"
                            onClick={() => onUseTopic?.(selectedTopic)}
                        >
                            Generate Full Ideas
                        </button>
                    </div>
                )}
            </div>

            {/* Pagination */}
            <div className="cs-all-topics__pagination">
                <span className="cs-all-topics__pagination-info">
                    Showing {total === 0 ? 0 : (page - 1) * perPage + 1} to {Math.min(page * perPage, total)} of {total} topics
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
