/**
 * Screen 5 — Save Idea Collections Modal
 *
 * Upgraded per PRD: tabs, search, favorites/all sections,
 * recently used chips, multi-select with count in CTA.
 */

import { useState, useEffect, useMemo } from 'react'

const COLLECTION_ICONS = {
    'favorites': '⭐',
    'travel': '✈️',
    'brand': '🤝',
    'calendar': '📅',
    'education': '📚',
    'beauty': '💄',
    'lifestyle': '🌿',
    'campaign': '📢',
    'reels': '🎬',
    'default': '📁',
}

function getCollectionIcon(name) {
    const lower = name.toLowerCase()
    if (lower.includes('favorite')) return COLLECTION_ICONS.favorites
    if (lower.includes('travel')) return COLLECTION_ICONS.travel
    if (lower.includes('brand') || lower.includes('collab')) return COLLECTION_ICONS.brand
    if (lower.includes('calendar') || lower.includes('next month')) return COLLECTION_ICONS.calendar
    if (lower.includes('educat')) return COLLECTION_ICONS.education
    if (lower.includes('beauty')) return COLLECTION_ICONS.beauty
    if (lower.includes('lifestyle')) return COLLECTION_ICONS.lifestyle
    if (lower.includes('campaign')) return COLLECTION_ICONS.campaign
    if (lower.includes('reels')) return COLLECTION_ICONS.reels
    return COLLECTION_ICONS.default
}

export default function SaveIdeaModal({ ideaId, accountUrl, onClose, onSave }) {
    const [collections, setCollections] = useState([])
    const [selected, setSelected] = useState([])
    const [newName, setNewName] = useState('')
    const [activeTab, setActiveTab] = useState('collections')
    const [searchQuery, setSearchQuery] = useState('')
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)

    useEffect(() => { fetchCollections() }, [])

    const fetchCollections = async () => {
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const r = await fetch(`${baseUrl}/collections?include_counts=true`, { credentials: 'include' })
            if (r.ok) {
                const data = await r.json()
                setCollections(Array.isArray(data) ? data : (data.collections || []))
            }
        } catch (e) {
            console.error('Failed to fetch collections:', e)
        } finally {
            setLoading(false)
        }
    }

    const handleCreate = async () => {
        if (!newName.trim()) return
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const r = await fetch(`${baseUrl}/collections`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ name: newName.trim() }),
            })
            if (r.ok) {
                const coll = await r.json()
                setCollections(prev => [...prev, coll])
                setSelected(prev => [...prev, coll.id])
                setNewName('')
                setActiveTab('collections')
            }
        } catch (e) {
            console.error('Failed to create collection:', e)
        }
    }

    const toggleCollection = (id) => {
        setSelected(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id])
    }

    const handleSave = async () => {
        setSaving(true)
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const r = await fetch(`${baseUrl}/ideas/${ideaId}/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ collection_ids: selected }),
            })
            if (r.ok) {
                const data = await r.json()
                onSave?.(data.saved_to || selected)
                onClose?.()
            }
        } catch (e) {
            console.error('Failed to save idea:', e)
        } finally {
            setSaving(false)
        }
    }

    const handleSelectAll = () => {
        if (selected.length === filteredCollections.length) {
            setSelected([])
        } else {
            setSelected(filteredCollections.map(c => c.id))
        }
    }

    const filteredCollections = useMemo(() => {
        if (!searchQuery) return collections
        return collections.filter(c => c.name.toLowerCase().includes(searchQuery.toLowerCase()))
    }, [collections, searchQuery])

    const favorites = filteredCollections.slice(0, 3)
    const allCollections = filteredCollections
    const recentlyUsed = collections.slice(0, 3)

    return (
        <div className="cs-modal-backdrop" onClick={onClose}>
            <div className="cs-modal cs-modal--save" onClick={e => e.stopPropagation()}>
                <div className="cs-save-modal__header">
                    <div className="cs-save-modal__header-left">
                        <span className="cs-save-modal__icon">🔖</span>
                        <h3>Save Idea</h3>
                    </div>
                    <button className="cs-modal__close" onClick={onClose}>✕</button>
                </div>

                <div className="cs-save-modal__tabs">
                    <button
                        className={`cs-save-modal__tab ${activeTab === 'collections' ? 'cs-save-modal__tab--active' : ''}`}
                        onClick={() => setActiveTab('collections')}
                    >
                        Collections
                    </button>
                    <button
                        className={`cs-save-modal__tab ${activeTab === 'create' ? 'cs-save-modal__tab--active' : ''}`}
                        onClick={() => setActiveTab('create')}
                    >
                        Create New
                    </button>
                </div>

                {activeTab === 'collections' ? (
                    <div className="cs-save-modal__body">
                        <div className="cs-save-modal__search-row">
                            <div className="cs-save-modal__search">
                                <span>🔍</span>
                                <input
                                    type="text"
                                    placeholder="Search collections..."
                                    value={searchQuery}
                                    onChange={e => setSearchQuery(e.target.value)}
                                    className="cs-save-modal__search-input"
                                />
                            </div>
                            <button className="cs-btn cs-btn--link" onClick={handleSelectAll}>
                                {selected.length === filteredCollections.length && filteredCollections.length > 0
                                    ? 'Deselect All' : 'Select All'}
                            </button>
                        </div>

                        {loading ? (
                            <div className="cs-save-modal__card-grid">
                                {[1, 2, 3, 4].map(i => (
                                    <div key={i} className="cs-collection-card cs-collection-card--skeleton">
                                        <div className="cs-skeleton cs-skeleton--text" style={{ height: '80px', width: '100%' }} />
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <>
                                {/* Favorites */}
                                <div className="cs-save-modal__section">
                                    <h4 className="cs-save-modal__section-title">FAVORITES</h4>
                                    <div className="cs-save-modal__card-grid">
                                        {favorites.map(coll => (
                                            <CollectionCard
                                                key={coll.id}
                                                collection={coll}
                                                selected={selected.includes(coll.id)}
                                                onToggle={() => toggleCollection(coll.id)}
                                            />
                                        ))}
                                    </div>
                                </div>

                                {/* All Collections */}
                                <div className="cs-save-modal__section">
                                    <h4 className="cs-save-modal__section-title">ALL COLLECTIONS</h4>
                                    <div className="cs-save-modal__card-grid cs-save-modal__card-grid--two-col">
                                        {allCollections.map(coll => (
                                            <CollectionCard
                                                key={coll.id}
                                                collection={coll}
                                                selected={selected.includes(coll.id)}
                                                onToggle={() => toggleCollection(coll.id)}
                                            />
                                        ))}
                                    </div>
                                    {filteredCollections.length === 0 && (
                                        <p className="cs-save-modal__empty">
                                            {searchQuery ? 'No collections match your search' : 'No collections yet — create your first one!'}
                                        </p>
                                    )}
                                </div>

                                {/* Recently Used */}
                                {recentlyUsed.length > 0 && (
                                    <div className="cs-save-modal__section">
                                        <h4 className="cs-save-modal__section-title">RECENTLY USED</h4>
                                        <div className="cs-save-modal__recent-chips">
                                            {recentlyUsed.map(coll => (
                                                <button
                                                    key={coll.id}
                                                    className="cs-recent-chip"
                                                    onClick={() => toggleCollection(coll.id)}
                                                >
                                                    <span>{getCollectionIcon(coll.name)}</span>
                                                    <span>{coll.name}</span>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                ) : (
                    <div className="cs-save-modal__body cs-save-modal__create">
                        <label className="cs-create-label">Collection Name</label>
                        <input
                            type="text"
                            className="cs-form-input"
                            placeholder="e.g., Summer Campaign Ideas"
                            value={newName}
                            onChange={e => setNewName(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleCreate()}
                            autoFocus
                        />
                        <button
                            className="cs-btn cs-btn--primary"
                            onClick={handleCreate}
                            disabled={!newName.trim()}
                            style={{ marginTop: '1rem', width: '100%' }}
                        >
                            Create Collection
                        </button>
                    </div>
                )}

                <div className="cs-save-modal__footer">
                    <button className="cs-btn cs-btn--ghost" onClick={onClose}>Cancel</button>
                    <button
                        className="cs-btn cs-btn--primary"
                        onClick={handleSave}
                        disabled={selected.length === 0 || saving}
                    >
                        {saving ? 'Saving...' : `Save (${selected.length})`}
                    </button>
                </div>
            </div>
        </div>
    )
}

function CollectionCard({ collection, selected, onToggle }) {
    const icon = getCollectionIcon(collection.name)
    return (
        <div
            className={`cs-collection-card ${selected ? 'cs-collection-card--selected' : ''}`}
            onClick={onToggle}
        >
            <div className="cs-collection-card__check">
                {selected && <span>✓</span>}
            </div>
            <div className="cs-collection-card__content">
                <span className="cs-collection-card__icon">{icon}</span>
                <span className="cs-collection-card__name">{collection.name}</span>
            </div>
            <span className="cs-collection-card__count">{collection.idea_count || 0} ideas</span>
        </div>
    )
}
