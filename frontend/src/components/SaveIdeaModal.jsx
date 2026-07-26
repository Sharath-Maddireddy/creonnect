import { useState, useEffect } from 'react'

export default function SaveIdeaModal({ ideaId, accountUrl, onClose, onSave }) {
    const [collections, setCollections] = useState([])
    const [selected, setSelected] = useState([])
    const [newName, setNewName] = useState('')
    const [showCreate, setShowCreate] = useState(false)
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)

    useEffect(() => {
        fetchCollections()
    }, [])

    const fetchCollections = async () => {
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const res = await fetch(`${baseUrl}/collections`, { credentials: 'include' })
            if (res.ok) {
                const data = await res.json()
                setCollections(data)
            }
        } catch (e) {
            console.error('Failed to fetch collections:', e)
        } finally {
            setLoading(false)
        }
    }

    const toggleCollection = (id) => {
        setSelected(prev =>
            prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]
        )
    }

    const handleCreate = async () => {
        if (!newName.trim()) return
        try {
            const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
            const res = await fetch(`${baseUrl}/collections`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ name: newName.trim() }),
            })
            if (res.ok) {
                const coll = await res.json()
                setCollections(prev => [...prev, coll])
                setSelected(prev => [...prev, coll.id])
                setNewName('')
                setShowCreate(false)
            }
        } catch (e) {
            console.error('Failed to create collection:', e)
        }
    }

    const handleSave = async () => {
        setSaving(true)
        for (const collId of selected) {
            try {
                const baseUrl = accountUrl || '/api/v1/accounts/placeholder'
                await fetch(`${baseUrl}/collections/${collId}/ideas`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'include',
                    body: JSON.stringify({ idea_id: ideaId }),
                })
            } catch (e) {
                console.error('Failed to save idea:', e)
            }
        }
        setSaving(false)
        onSave(selected)
        onClose()
    }

    return (
        <div className="cs-modal-backdrop" onClick={onClose}>
            <div className="cs-modal cs-modal--save" onClick={e => e.stopPropagation()}>
                <div className="cs-modal__header">
                    <h3>Save Idea</h3>
                    <p className="cs-modal__subtitle">Add this idea to a collection</p>
                    <button className="cs-modal__close" onClick={onClose}>✕</button>
                </div>

                <div className="cs-modal__body">
                    {loading ? (
                        <div className="cs-loading">Loading collections...</div>
                    ) : (
                        <>
                            <div className="cs-collection-list">
                                {collections.map(coll => (
                                    <label key={coll.id} className="cs-collection-item">
                                        <input
                                            type="checkbox"
                                            checked={selected.includes(coll.id)}
                                            onChange={() => toggleCollection(coll.id)}
                                        />
                                        <span className="cs-collection-item__name">{coll.name}</span>
                                        <span className="cs-collection-item__count">{coll.idea_count}</span>
                                    </label>
                                ))}
                            </div>

                            {showCreate ? (
                                <div className="cs-create-collection">
                                    <input
                                        type="text"
                                        className="cs-form-input"
                                        placeholder="Collection name"
                                        value={newName}
                                        onChange={e => setNewName(e.target.value)}
                                        onKeyDown={e => e.key === 'Enter' && handleCreate()}
                                    />
                                    <button className="cs-btn cs-btn--primary cs-btn--sm" onClick={handleCreate}>
                                        Create
                                    </button>
                                    <button className="cs-btn cs-btn--secondary cs-btn--sm" onClick={() => setShowCreate(false)}>
                                        Cancel
                                    </button>
                                </div>
                            ) : (
                                <button className="cs-create-collection-btn" onClick={() => setShowCreate(true)}>
                                    + Create New Collection
                                </button>
                            )}
                        </>
                    )}
                </div>

                <div className="cs-modal__footer">
                    <button className="cs-btn cs-btn--secondary" onClick={onClose}>Cancel</button>
                    <button
                        className="cs-btn cs-btn--primary"
                        onClick={handleSave}
                        disabled={selected.length === 0 || saving}
                    >
                        {saving ? 'Saving...' : 'Save Idea'}
                    </button>
                </div>
            </div>
        </div>
    )
}
