/**
 * Screen 8 — All Suggestions
 *
 * Full-page grid of all AI-generated ideas with filter chips,
 * grid/list toggle, and sort-by controls.
 */

import { useState, useEffect, useMemo } from 'react'

export default function AllSuggestions({ accountUrl, onClose, onSelectIdea }) {
    const [ideas, setIdeas] = useState([])
    const [loading, setLoading] = useState(true)
    const [view, setView] = useState('grid') // grid | list
    const [activeFilter, setActiveFilter] = useState('All')
    const [sortBy, setSortBy] = useState('opportunity')
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)
    const [selectedIds, setSelectedIds] = useState([])
    const perPage = 12

    const filters = ['All', 'Reels', 'Carousel', 'Photo', 'Trending', 'Educational', 'Personal Story', 'Brand Friendly']

    const fetchIdeas = async () => {
        setLoading(true)
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const params = new URLSearchParams({
                sort: sortBy,
                order: 'desc',
                per_page: String(perPage),
                page: String(page),
            })
            if (activeFilter !== 'All') {
                params.set('content_type', activeFilter.toLowerCase())
            }
            const r = await fetch(`${baseUrl}/trends/ideas?${params}`, { credentials: 'include' })
            if (r.ok) {
                const data = await r.json()
                setIdeas(data.data || [])
                setTotal(data.meta?.total_count || 0)
            }
        } catch (e) {
            console.error('Failed to fetch ideas:', e)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => { fetchIdeas() }, [page, activeFilter, sortBy])

    const toggleSelect = (id) => {
        setSelectedIds(prev =>
            prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
        )
    }

    const selectAll = () => {
        if (selectedIds.length === ideas.length) {
            setSelectedIds([])
        } else {
            setSelectedIds(ideas.map(i => i.id))
        }
    }

    const scoreBand = (score) => {
        if (score >= 80) return { label: 'Very High', color: '#10b981' }
        if (score >= 60) return { label: 'High', color: '#7c5cfa' }
        if (score >= 40) return { label: 'Moderate', color: '#f59e0b' }
        return { label: 'Low', color: '#ef4444' }
    }

    return (
        <div className="cs-all-suggestions">
            {/* Header */}
            <div className="cs-all-suggestions__header">
                <div className="cs-all-suggestions__header-left">
                    <h2>All Suggestions</h2>
                    <span className="cs-all-suggestions__count">{total.toLocaleString()} ideas found</span>
                </div>
                <div className="cs-all-suggestions__header-right">
                    <button
                        className={`cs-btn cs-btn--icon ${view === 'grid' ? 'cs-btn--active' : ''}`}
                        onClick={() => setView('grid')}
                        title="Grid view"
                    >
                        ⊞
                    </button>
                    <button
                        className={`cs-btn cs-btn--icon ${view === 'list' ? 'cs-btn--active' : ''}`}
                        onClick={() => setView('list')}
                        title="List view"
                    >
                        ☰
                    </button>
                    <label className="cs-sort-label">
                        Sort by:
                        <select className="cs-select cs-select--sm" value={sortBy} onChange={e => setSortBy(e.target.value)}>
                            <option value="opportunity_score">Opportunity</option>
                            <option value="engagement_score">Engagement</option>
                            <option value="created_at">Newest</option>
                            <option value="updated_at">Recently Updated</option>
                        </select>
                    </label>
                </div>
            </div>

            {/* Filter Chips */}
            <div className="cs-all-suggestions__filters">
                {filters.map(f => (
                    <button
                        key={f}
                        className={`cs-filter-chip ${activeFilter === f ? 'cs-filter-chip--active' : ''}`}
                        onClick={() => { setActiveFilter(f); setPage(1) }}
                    >
                        {f}
                    </button>
                ))}
            </div>

            {/* Ideas Grid / List */}
            {loading ? (
                <div className={`cs-all-suggestions__grid cs-all-suggestions__grid--${view}`}>
                    {Array.from({ length: 6 }, (_, i) => (
                        <div key={i} className="cs-idea-card cs-idea-card--skeleton">
                            <div className="cs-skeleton cs-skeleton--thumb" style={{ aspectRatio: '1/1' }} />
                            <div className="cs-skeleton cs-skeleton--text" style={{ width: '70%', marginTop: '0.5rem' }} />
                            <div className="cs-skeleton cs-skeleton--text" style={{ width: '50%', height: '12px' }} />
                        </div>
                    ))}
                </div>
            ) : ideas.length === 0 ? (
                <div className="cs-all-suggestions__empty">
                    <span>💡</span>
                    <h3>No suggestions yet</h3>
                    <p>Generate ideas from trending topics to see them here</p>
                    <button className="cs-btn cs-btn--primary" onClick={onClose}>Browse Trending Topics</button>
                </div>
            ) : (
                <div className={`cs-all-suggestions__grid cs-all-suggestions__grid--${view}`}>
                    {ideas.map(idea => {
                        const score = idea.opportunity_score || idea.engagement_score || 0
                        const band = scoreBand(score)
                        const isSelected = selectedIds.includes(idea.id)
                        return (
                            <div
                                key={idea.id}
                                className={`cs-idea-card ${isSelected ? 'cs-idea-card--selected' : ''}`}
                                onClick={() => onSelectIdea?.(idea)}
                            >
                                <div className="cs-idea-card__thumb">
                                    <div className="cs-idea-card__thumb-inner">
                                        <span>🎬</span>
                                    </div>
                                    <span className="cs-idea-card__platform-badge">{idea.content_type || 'Reel'}</span>
                                    <button
                                        className={`cs-idea-card__check ${isSelected ? 'cs-idea-card__check--on' : ''}`}
                                        onClick={(e) => { e.stopPropagation(); toggleSelect(idea.id) }}
                                    >
                                        {isSelected ? '✓' : ''}
                                    </button>
                                </div>
                                <div className="cs-idea-card__body">
                                    <h4 className="cs-idea-card__title">{idea.title || 'Content Idea'}</h4>
                                    <div className="cs-idea-card__tags">
                                        {(idea.tags || []).slice(0, 2).map((t, i) => (
                                            <span key={i} className="cs-idea-card__tag">{typeof t === 'string' ? t : '#'}</span>
                                        ))}
                                        <span className="cs-idea-card__tag">{idea.content_type || 'Reel'}</span>
                                    </div>
                                    <div className="cs-idea-card__score">
                                        <span className="cs-idea-card__score-value">{Math.round(score)}</span>
                                        <span className="cs-idea-card__score-divider">/100</span>
                                        <span className="cs-idea-card__score-band" style={{ color: band.color }}>{band.label}</span>
                                    </div>
                                </div>
                                <div className="cs-idea-card__footer">
                                    <button className="cs-btn cs-btn--icon" title="Save">🔖</button>
                                    <button className="cs-btn cs-btn--icon" title="More">•••</button>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}

            {/* Load More + Select Bar */}
            {total > page * perPage && (
                <div className="cs-all-suggestions__load-more">
                    <button className="cs-btn cs-btn--outline cs-btn--wide" onClick={() => setPage(p => p + 1)}>
                        Load More Ideas
                    </button>
                </div>
            )}

            {selectedIds.length > 0 && (
                <div className="cs-all-suggestions__select-bar">
                    <span>{selectedIds.length} Selected</span>
                    <button className="cs-btn cs-btn--link" onClick={selectAll}>Select All</button>
                </div>
            )}
        </div>
    )
}
