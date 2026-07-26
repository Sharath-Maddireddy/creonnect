import { useState } from 'react'

const OPTIMIZATION_GOALS = [
    { id: 'maximum_reach', label: 'Maximum Reach' },
    { id: 'followers', label: 'Followers' },
    { id: 'engagement', label: 'Engagement' },
    { id: 'brand_deals', label: 'Brand Deals' },
    { id: 'saves', label: 'Saves' },
    { id: 'product_sales', label: 'Product Sales' },
]

const CONTENT_TYPES = [
    { id: 'reel', label: 'Reel', icon: '🎬' },
    { id: 'carousel', label: 'Carousel', icon: '📸' },
    { id: 'photo', label: 'Photo', icon: '📷' },
]

const AUDIENCES = [
    { id: 'everyone', label: 'Everyone' },
    { id: '18-24', label: '18-24' },
    { id: '25-34', label: '25-34' },
    { id: '35-44', label: '35-44' },
    { id: '45+', label: '45+' },
    { id: 'gen_z', label: 'Gen Z' },
    { id: 'millennials', label: 'Millennials' },
]

const TONES = [
    { id: 'professional', label: 'Professional' },
    { id: 'funny', label: 'Funny' },
    { id: 'storytelling', label: 'Storytelling' },
    { id: 'luxury', label: 'Luxury' },
    { id: 'educational', label: 'Educational' },
]

export default function GenerateIdeasModal({ onClose, onGenerate }) {
    const [goals, setGoals] = useState(['maximum_reach'])
    const [contentType, setContentType] = useState('reel')
    const [topic, setTopic] = useState('')
    const [audience, setAudience] = useState('everyone')
    const [tones, setTones] = useState(['professional'])
    const [count, setCount] = useState(5)

    const toggleGoal = (id) => {
        setGoals(prev => prev.includes(id) ? prev.filter(g => g !== id) : [...prev, id])
    }

    const toggleTone = (id) => {
        setTones(prev => prev.includes(id) ? prev.filter(t => t !== id) : [...prev, id])
    }

    const handleGenerate = () => {
        onGenerate({
            optimization_goals: goals,
            content_type: contentType,
            topic: topic || null,
            audience,
            tone_of_voice: tones,
            count,
        })
    }

    return (
        <div className="cs-modal-backdrop" onClick={onClose}>
            <div className="cs-modal cs-modal--generate" onClick={e => e.stopPropagation()}>
                <div className="cs-modal__header">
                    <h3>Generate New Ideas</h3>
                    <p className="cs-modal__subtitle">Tell us what you want AI to focus on</p>
                    <button className="cs-modal__close" onClick={onClose}>✕</button>
                </div>

                <div className="cs-modal__body">
                    {/* Optimization Goals */}
                    <div className="cs-form-group">
                        <label className="cs-form-label">Optimize For</label>
                        <div className="cs-chip-group">
                            {OPTIMIZATION_GOALS.map(goal => (
                                <button
                                    key={goal.id}
                                    className={`cs-chip ${goals.includes(goal.id) ? 'cs-chip--active' : ''}`}
                                    onClick={() => toggleGoal(goal.id)}
                                >
                                    {goal.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Content Type */}
                    <div className="cs-form-group">
                        <label className="cs-form-label">Content Type</label>
                        <div className="cs-chip-group">
                            {CONTENT_TYPES.map(type => (
                                <button
                                    key={type.id}
                                    className={`cs-chip ${contentType === type.id ? 'cs-chip--active' : ''}`}
                                    onClick={() => setContentType(type.id)}
                                >
                                    {type.icon} {type.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Topic */}
                    <div className="cs-form-group">
                        <label className="cs-form-label">Topic (Optional)</label>
                        <input
                            type="text"
                            className="cs-form-input"
                            placeholder="e.g., Travel packing, Paris, Budget travel"
                            value={topic}
                            onChange={e => setTopic(e.target.value)}
                        />
                    </div>

                    {/* Audience */}
                    <div className="cs-form-group">
                        <label className="cs-form-label">Audience</label>
                        <select
                            className="cs-form-select"
                            value={audience}
                            onChange={e => setAudience(e.target.value)}
                        >
                            {AUDIENCES.map(a => (
                                <option key={a.id} value={a.id}>{a.label}</option>
                            ))}
                        </select>
                    </div>

                    {/* Tone of Voice */}
                    <div className="cs-form-group">
                        <label className="cs-form-label">Tone of Voice</label>
                        <div className="cs-chip-group">
                            {TONES.map(tone => (
                                <button
                                    key={tone.id}
                                    className={`cs-chip ${tones.includes(tone.id) ? 'cs-chip--active' : ''}`}
                                    onClick={() => toggleTone(tone.id)}
                                >
                                    {tone.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Count */}
                    <div className="cs-form-group">
                        <label className="cs-form-label">Number of Ideas: {count}</label>
                        <input
                            type="range"
                            className="cs-form-range"
                            min="1"
                            max="10"
                            value={count}
                            onChange={e => setCount(parseInt(e.target.value))}
                        />
                    </div>
                </div>

                <div className="cs-modal__footer">
                    <button className="cs-btn cs-btn--secondary" onClick={onClose}>Cancel</button>
                    <button className="cs-btn cs-btn--primary" onClick={handleGenerate}>
                        Generate {count} Ideas ✨
                    </button>
                </div>
            </div>
        </div>
    )
}
