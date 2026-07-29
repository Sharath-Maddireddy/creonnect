import { useEffect, useState } from 'react'

export default function AllTrendingAudio({ accountUrl, onClose, onUseAudio }) {
    const [audioTracks, setAudioTracks] = useState([])
    const [loading, setLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [momentum, setMomentum] = useState('All')
    const [page, setPage] = useState(1)
    const [sortBy, setSortBy] = useState('growth')
    const [sortDir, setSortDir] = useState('desc')
    const [selectedAudio, setSelectedAudio] = useState(null)
    const [total, setTotal] = useState(0)
    const perPage = 10

    const fetchAudio = async () => {
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
            if (momentum !== 'All') params.set('momentum', momentum.toLowerCase())
            const res = await fetch(`${baseUrl}/trends/audio?${params.toString()}`, { credentials: 'include' })
            if (res.ok) {
                const data = await res.json()
                setAudioTracks(Array.isArray(data.audio_tracks) ? data.audio_tracks : [])
                setTotal(Number(data.count || 0))
            } else {
                setAudioTracks([])
                setTotal(0)
            }
        } catch (e) {
            console.error('Failed to fetch audio trends:', e)
            setTotal(0)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => { fetchAudio() }, [accountUrl, search, momentum, page, sortBy, sortDir])

    const totalPages = Math.max(1, Math.ceil(total / perPage))

    useEffect(() => {
        setPage(1)
    }, [search, momentum, sortBy, sortDir])

    const handleSort = (col) => {
        if (sortBy === col) {
            setSortDir(prev => prev === 'asc' ? 'desc' : 'asc')
        } else {
            setSortBy(col)
            setSortDir('desc')
        }
    }

    return (
        <div className="cs-all-topics cs-all-audio">
            <div className="cs-all-topics__header">
                <div className="cs-all-topics__header-left">
                    <h2>Trending Audio</h2>
                    <span className="cs-all-topics__updated">
                        {total} audio trend{total === 1 ? '' : 's'} available
                    </span>
                </div>
                <div className="cs-all-topics__header-right">
                    <button className="cs-btn cs-btn--ghost" onClick={fetchAudio}>🔄 Refresh</button>
                    {onClose && <button className="cs-btn cs-btn--ghost" onClick={onClose}>← Back to Trends</button>}
                </div>
            </div>

            <div className="cs-all-audio__hero">
                <div className="cs-all-audio__hero-icon">♪</div>
                <div className="cs-all-audio__hero-copy">
                    <h3>Use audio trends as a creative shortcut</h3>
                    <p>Find fast-moving sounds with strong audience fit, then turn them into full content ideas in one click.</p>
                </div>
            </div>

            <div className="cs-all-topics__filters">
                <select className="cs-select" value={momentum} onChange={e => { setMomentum(e.target.value); setPage(1) }}>
                    <option>All</option>
                    <option>Rising</option>
                    <option>Peaking</option>
                    <option>Falling</option>
                </select>
                <div className="cs-all-topics__search">
                    <span>🔍</span>
                    <input
                        type="text"
                        placeholder="Search audio trends..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        className="cs-all-topics__search-input"
                    />
                </div>
            </div>

            <div className="cs-all-topics__body">
                <div className="cs-all-topics__table-wrap">
                    <table className="cs-all-topics__table">
                        <thead>
                            <tr>
                                <th style={{ width: '40px' }}>#</th>
                                <th onClick={() => handleSort('name')} className="cs-th--sortable">
                                    AUDIO {sortBy === 'name' && (sortDir === 'asc' ? '↑' : '↓')}
                                </th>
                                <th onClick={() => handleSort('growth')} className="cs-th--sortable">
                                    GROWTH {sortBy === 'growth' && (sortDir === 'asc' ? '↑' : '↓')}
                                </th>
                                <th onClick={() => handleSort('audience_match')} className="cs-th--sortable">
                                    AUDIENCE MATCH {sortBy === 'audience_match' && (sortDir === 'asc' ? '↑' : '↓')}
                                </th>
                                <th>MOMENTUM</th>
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
                            ) : audioTracks.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="cs-all-topics__empty">
                                        No audio trends are available for this creator yet
                                    </td>
                                </tr>
                            ) : (
                                audioTracks.map((audio, i) => (
                                    <tr
                                        key={audio.id || i}
                                        className={`cs-all-topics__row ${selectedAudio?.id === audio.id ? 'cs-all-topics__row--selected' : ''}`}
                                        onClick={() => setSelectedAudio(selectedAudio?.id === audio.id ? null : audio)}
                                    >
                                        <td className="cs-all-topics__rank">{(page - 1) * perPage + i + 1}</td>
                                        <td>
                                            <div className="cs-all-topics__topic-name">{audio.audio_name || 'Audio Trend'}</div>
                                            <div className="cs-all-topics__topic-category">{audio.suggested_angle || 'Suggested reel angle'}</div>
                                            <div className="cs-all-audio__row-tags">
                                                <span className="cs-all-audio__tag">Audio trend</span>
                                                {audio.example_reference && <span className="cs-all-audio__tag cs-all-audio__tag--muted">{audio.example_reference}</span>}
                                            </div>
                                        </td>
                                        <td><span className="cs-growth-badge">+{audio.growth_pct || 0}%</span></td>
                                        <td>
                                            <div className="cs-match-bar">
                                                <div className="cs-match-bar__fill" style={{ width: `${audio.audience_match_pct || 0}%` }} />
                                            </div>
                                            <span className="cs-match-bar__value">{audio.audience_match_pct || 0}%</span>
                                        </td>
                                        <td>
                                            <span className={`cs-insight-badge cs-insight-badge--${String(audio.momentum || 'rising').toLowerCase()}`}>
                                                {audio.momentum}
                                            </span>
                                        </td>
                                        <td>
                                            <button
                                                className="cs-btn cs-btn--ghost cs-btn--sm cs-all-topics__generate-btn"
                                                onClick={(e) => { e.stopPropagation(); onUseAudio?.(audio) }}
                                            >
                                                Generate Full Ideas
                                            </button>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {selectedAudio && (
                    <div className="cs-all-topics__detail">
                        <div className="cs-all-audio__detail-badge">Audio trend</div>
                        <h3>{selectedAudio.audio_name || 'Audio Trend'}</h3>
                        <div className="cs-all-topics__detail-growth">
                            <span className="cs-all-topics__detail-growth-label">Growth (7 Days)</span>
                            <span className="cs-all-topics__detail-growth-value">
                                +{selectedAudio.growth_pct || 0}%
                            </span>
                        </div>
                        <div className="cs-all-audio__wave">
                            <span />
                            <span />
                            <span />
                            <span />
                            <span />
                            <span />
                            <span />
                            <span />
                        </div>
                        <div className="cs-all-topics__detail-stats">
                            <div className="cs-all-topics__detail-stat">
                                <span className="cs-all-topics__detail-stat-label">Audience Match</span>
                                <span className="cs-all-topics__detail-stat-value">{selectedAudio.audience_match_pct || 0}%</span>
                            </div>
                            <div className="cs-all-topics__detail-stat">
                                <span className="cs-all-topics__detail-stat-label">Momentum</span>
                                <span className="cs-all-topics__detail-stat-value">{selectedAudio.momentum || 'rising'}</span>
                            </div>
                        </div>
                        <div className="cs-all-topics__detail-why">
                            <span>Why it fits this creator</span>
                            <p>{selectedAudio.fit_reason || 'This audio trend fits the creator’s niche and current content style.'}</p>
                            <span>Suggested angle</span>
                            <p>{selectedAudio.suggested_angle || 'Use this in a timely reel angle with a strong hook.'}</p>
                            {selectedAudio.example_reference && (
                                <>
                                    <span>Reference cue</span>
                                    <p>{selectedAudio.example_reference}</p>
                                </>
                            )}
                        </div>
                        <button
                            className="cs-btn cs-btn--primary cs-all-topics__detail-cta"
                            onClick={() => onUseAudio?.(selectedAudio)}
                        >
                            Generate Full Ideas
                        </button>
                    </div>
                )}
            </div>

            <div className="cs-all-topics__pagination">
                <span className="cs-all-topics__pagination-info">
                    Showing {total === 0 ? 0 : (page - 1) * perPage + 1} to {Math.min(page * perPage, total)} of {total} audio trends
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
