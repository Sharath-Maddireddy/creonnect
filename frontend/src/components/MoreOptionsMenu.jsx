import { useState } from 'react'

const MENU_ITEMS = [
    { id: 'duplicate', label: 'Duplicate Idea', icon: '📋' },
    { id: 'improve', label: 'Improve This Idea', icon: '✨' },
    { id: 'variations', label: 'Generate Variations', icon: '🔄' },
    { id: 'regenerate', label: 'Regenerate', icon: '🔁' },
    { id: 'type', label: 'Change Content Type', icon: '🎬' },
    { id: 'schedule', label: 'Schedule for Later', icon: '📅' },
    { id: 'hide', label: 'Hide This Idea', icon: '👁' },
    { id: 'delete', label: 'Delete Idea', icon: '🗑', danger: true },
]

export default function MoreOptionsMenu({ ideaId, ideaTitle, onAction, onClose }) {
    const [loading, setLoading] = useState(null)

    const handleAction = async (actionId) => {
        setLoading(actionId)
        try {
            await onAction(actionId, ideaId)
        } finally {
            setLoading(null)
            onClose()
        }
    }

    return (
        <div className="cs-modal-backdrop" onClick={onClose}>
            <div className="cs-menu" onClick={e => e.stopPropagation()}>
                <div className="cs-menu__header">
                    <span className="cs-menu__title">More Options</span>
                    <button className="cs-menu__close" onClick={onClose}>✕</button>
                </div>
                <div className="cs-menu__items">
                    {MENU_ITEMS.map(item => (
                        <button
                            key={item.id}
                            className={`cs-menu__item ${item.danger ? 'cs-menu__item--danger' : ''}`}
                            onClick={() => handleAction(item.id)}
                            disabled={loading !== null}
                        >
                            <span className="cs-menu__icon">{item.icon}</span>
                            <span className="cs-menu__label">{item.label}</span>
                            {loading === item.id && <span className="cs-menu__loading">...</span>}
                        </button>
                    ))}
                </div>
            </div>
        </div>
    )
}
