import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { usePostAnalysis } from '../hooks/usePostAnalysis'

const COMPONENT_ICONS = { S1: '▣', S2: '▤', S3: '●', S4: '♟', S5: '◔', S6: '⬟' }

function numeric(value) {
    return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function format(value, digits = 0) {
    const parsed = numeric(value)
    return parsed === null ? 'Not provided' : parsed.toLocaleString(undefined, { maximumFractionDigits: digits })
}

function scoreTone(value) {
    if (value === null) return 'neutral'
    if (value < 40) return 'low'
    if (value < 65) return 'medium'
    if (value < 80) return 'good'
    return 'strong'
}

function scoreColor(value) {
    return { low: '#ef5b68', medium: '#f0a13d', good: '#7862e8', strong: '#36b978', neutral: '#aab2c1' }[scoreTone(value)]
}

function Sidebar() {
    return <aside className="aip-sidebar">
        <p>CORE</p><Link to="/analytics">▦ <span>Overview</span></Link><Link to="/analytics">⌁ <span>Analytics</span></Link><Link className="active" to="/post-analysis">ϟ <span>AI Post Insights</span></Link><Link to="/analytics">⌁ <span>Account Analysis</span></Link>
        <p>TOOLKITS</p><a>◉ <span>Creator Showcase</span></a><a>⌁ <span>Superlinks</span></a>
        <p>GROWTH & REVENUE</p><a>▣ <span>Auto DM Flows</span></a><a>♧ <span>Digital Store</span></a><a>□ <span>1:1 Booking</span></a>
        <p>AI STUDIO</p><a>▧ <span>Image Editor</span></a><a>☷ <span>Script Generator</span></a>
    </aside>
}

function AnalysisModal({ open, canClose, state, error, values, setters, onClose, onSubmit }) {
    if (!open) return null
    return <div className="aip-modal-backdrop"><section className="aip-modal">
        <header><div><span>✦</span><div><h2>Analyze a post</h2><p>Paste a public media URL. Add slide URLs for a carousel.</p></div></div>{canClose ? <button onClick={onClose}>×</button> : null}</header>
        <form onSubmit={onSubmit}>
            <label>Public post media URL<input value={values.mediaUrl} onChange={(event) => setters.setMediaUrl(event.target.value)} placeholder="https://cdn.example.com/post.jpg" /></label>
            <div className="aip-modal-grid"><label>Carousel slide URLs <small>one per line, optional</small><textarea value={values.mediaUrls} onChange={(event) => setters.setMediaUrls(event.target.value)} /></label><label>Caption <small>optional</small><textarea value={values.caption} onChange={(event) => setters.setCaption(event.target.value)} /></label></div>
            {error ? <p className="aip-form-error">{error}</p> : null}
            <footer><small>Media type is detected automatically. Up to 10 slides.</small><button disabled={state === 'loading'}>{state === 'loading' ? 'Analyzing…' : 'Run analysis →'}</button></footer>
        </form>
    </section></div>
}

function StatCard({ label, value, note, available, accent = 'purple' }) {
    return <article className={`aip-stat ${available ? '' : 'unavailable'}`}><header><span>{label}</span><i>ⓘ</i></header><div><strong>{value}</strong>{available ? <span className={`aip-trend ${accent}`}>● Available</span> : null}</div><small>{note}</small><svg viewBox="0 0 120 28" aria-hidden="true"><path d="M2 22 C14 21,15 9,26 15 S40 3,50 13 S66 25,75 10 S91 18,100 7 S110 13,118 9" /></svg></article>
}

function ScoreMatrix({ components, confidence }) {
    return <section className="aip-card aip-score-matrix"><div className="aip-card-title"><div><span>PERFORMANCE BREAKDOWN</span><h2>Score matrix</h2></div><small>All components · {confidence || 'limited'} confidence</small></div><div className="aip-score-list">{components.map((component) => {
        const value = numeric(component.normalized_value)
        return <article key={component.id}><i style={{ background: scoreColor(value) }}>{COMPONENT_ICONS[component.id]}</i><span>{component.label}</span><div><b style={{ width: `${Math.max(0, Math.min(100, value || 0))}%`, background: scoreColor(value) }} /></div><strong className={`tone-${scoreTone(value)}`}>{format(value, 1)}<small>/100</small></strong></article>
    })}</div></section>
}

function Verdict({ score, evidence, confidence }) {
    const headline = score >= 75 ? 'Highly compelling creative.' : score >= 55 ? 'Promising, with room.' : 'Clear improvement path.'
    const explanation = evidence[0] ? `${evidence[0].label}. ${evidence[0].detail}` : 'This verdict reflects the canonical weighted post score and validated analysis signals.'
    return <section className="aip-card aip-verdict"><span>AI VERDICT</span><h2>✦　{headline}</h2><p>{explanation}</p><footer><b>OVERALL SCORE</b><strong>{format(score, 1)}<small>/100</small></strong><em>{confidence || 'limited'} confidence</em></footer></section>
}

function ContentSignals({ report }) {
    const post = report.post || {}
    const signals = report.vision?.signals || []
    const primary = signals.find((signal) => signal?.is_carousel_aggregate) || signals[0] || {}
    const detectedText = primary.detected_text?.trim()
    return <section className="aip-card aip-signals"><div className="aip-card-title"><div><span>CONTENT SIGNALS</span><h2>What the analysis found</h2></div><small>AI content analysis</small></div><dl><dt>Format</dt><dd>Instagram {post.post_type || 'Post'}</dd><dt>Visual subject</dt><dd>{primary.scene_description || 'Not available'}</dd><dt>Objects</dt><dd>{primary.primary_objects?.join(', ') || primary.objects?.join(', ') || 'Not available'}</dd><dt>On-screen text</dt><dd>{detectedText || 'None detected'}</dd><dt>Slides analyzed</dt><dd>{post.post_type === 'CAROUSEL' ? Math.max(1, signals.length - 1) : 1}</dd></dl></section>
}

function RecommendedMoves({ moves }) {
    return <section className="aip-card aip-recommendations"><span>RECOMMENDED MOVES</span><div className="aip-move-grid">{moves.length ? moves.map((move, index) => <article key={`${move.component_id}-${index}`}><b>{index + 1}</b><i>{['⌖', '☵', '↻'][index] || '✦'}</i><div><h3>{move.title}</h3><p>{move.text}</p><small>{move.component_id} · {move.signal_type.replaceAll('_', ' ')}</small></div><strong>→</strong></article>) : <p>No evidence-grounded move is available for this run.</p>}</div></section>
}

function fallbackMove(evidence) {
    if (evidence.signal_type === 'caption_missing') return { title: 'Add a caption that frames the visual', text: 'Lead with the main takeaway, add one concrete detail, then give viewers a clear next action.' }
    if (evidence.component_id === 'S5') return { title: 'Create a clearer interaction prompt', text: 'Ask for one specific, low-friction action that matches the post’s content.' }
    return { title: `Strengthen ${evidence.label.replace(/^.*?:\s*/, '')}`, text: evidence.detail }
}

export default function PostAnalysisLab() {
    const [mediaUrl, setMediaUrl] = useState('')
    const [mediaUrls, setMediaUrls] = useState('')
    const [caption, setCaption] = useState('')
    const [showForm, setShowForm] = useState(true)
    const { report, state, error, analyze } = usePostAnalysis()

    const score = useMemo(() => numeric(report?.score?.value), [report])
    const evidence = Array.isArray(report?.score_evidence) ? report.score_evidence : []
    const components = Array.isArray(report?.score_components) ? report.score_components : []
    const recommendations = Array.isArray(report?.ai?.recommendations) ? report.ai.recommendations : []
    const moves = evidence.slice(0, 3).map((item) => {
        const linked = recommendations.find((recommendation) => recommendation.component_id === item.component_id)
        const fallback = fallbackMove(item)
        return { component_id: item.component_id, signal_type: item.signal_type, title: linked?.title || linked?.label || fallback.title, text: linked?.text || fallback.text }
    })

    async function runAnalysis(event) {
        event.preventDefault()
        if (!/^https?:\/\//i.test(mediaUrl.trim())) return
        const slides = mediaUrls.split(/\r?\n/).map((value) => value.trim()).filter(Boolean)
        const result = await analyze({ media_url: mediaUrl.trim(), media_urls: [mediaUrl.trim(), ...slides], post_type: slides.length ? 'CAROUSEL' : 'AUTO', caption_text: caption })
        if (result) setShowForm(false)
    }

    const metrics = report?.performance_metrics || {}
    const likes = numeric(metrics.likes?.value)
    const comments = numeric(metrics.comments?.value)
    const saves = numeric(metrics.saves?.value)
    const total = [likes, comments, saves].every((value) => value !== null) ? likes + comments + saves : null
    const interactionValues = [{ label: 'Likes', value: likes, color: '#7657e8' }, { label: 'Saves', value: saves, color: '#398df2' }, { label: 'Comments', value: comments, color: '#64c2ee' }]

    return <main className="aip-shell">
        <header className="aip-topbar"><Link to="/analytics" className="aip-brand"><b>CN</b><span>CREONNECT</span></Link><button>‹</button><strong>AI Post Insights</strong><div><input placeholder="⌕  Search Creonnect" /><span>♧</span><i>D</i></div></header>
        <Sidebar />
        <section className="aip-workspace">
            <nav>⌂　 <u>AI Post Insights</u>　/　 Single post report</nav>
            <header className="aip-report-header"><div><Link to="/analytics">←　Back to posts</Link><div className="aip-pills"><span>● Analysis complete</span><span>◉ {score !== null && score >= 70 ? 'High potential' : 'Post analysis'}</span><span>{report?.post?.post_type || 'Post'}</span></div><h1>Single Post AI Analysis</h1><p>Deep performance review of your post using AI across content, audience and engagement signals.</p><small>POST ID: {report?.post?.post_id || '—'}　•　 PLATFORM: INSTAGRAM</small></div><aside><button>⇧　Export report</button><button onClick={() => setShowForm(true)}>⟳　New analysis</button>{report ? <div className={`aip-score-ring ${scoreTone(score)}`}><strong>{format(score, 1)}</strong><span>/100</span></div> : null}</aside></header>

            {report ? <div className="aip-report">
                <div className="aip-stat-grid"><StatCard label="Reach" value={format(metrics.reach?.value)} available={numeric(metrics.reach?.value) !== null} note={metrics.reach?.reason || 'Awaiting supplied metrics'} /><StatCard label="Watch time" value={metrics.watch_time_seconds?.value ? `${format(metrics.watch_time_seconds.value / 3600, 1)}h` : 'Not provided'} available={numeric(metrics.watch_time_seconds?.value) !== null} note={metrics.watch_time_seconds?.reason || 'Awaiting supplied metrics'} accent="blue" /><StatCard label="Saves" value={format(saves)} available={saves !== null} note={metrics.saves?.reason || 'Awaiting supplied metrics'} /><StatCard label="Likes" value={format(likes)} available={likes !== null} note={metrics.likes?.reason || 'Awaiting supplied metrics'} accent="blue" /></div>

                <div className="aip-engagement-row"><section className="aip-card aip-preview"><span>POST PREVIEW</span><div><img src={report.post?.media_url} alt="Analyzed post" /><b>{report.post?.post_type}</b></div><p>{report.post?.caption_text || 'No caption supplied for this analysis.'}</p></section><section className="aip-card aip-engagement"><span>ENGAGEMENT OVERVIEW</span><div className="aip-interaction-stats">{interactionValues.map((item) => <article key={item.label}><i style={{ color: item.color }}>{item.label === 'Likes' ? '♡' : item.label === 'Saves' ? '▱' : '▢'}</i><span>{item.label}</span><strong>{format(item.value)}</strong></article>)}<article><i>♙</i><span>Total interactions</span><strong>{format(total)}</strong></article></div><h3>INTERACTION MIX　ⓘ</h3>{total ? <><div className="aip-mix-bar">{interactionValues.map((item) => <i key={item.label} style={{ width: `${item.value / total * 100}%`, background: item.color }} />)}</div><div className="aip-mix-legend">{interactionValues.map((item) => <span key={item.label}><i style={{ background: item.color }} />{item.label}<b>{Math.round(item.value / total * 100)}%</b></span>)}</div></> : <div className="aip-no-metrics">Interaction metrics were not provided for this analysis.</div>}</section><section className="aip-finding"><span>✦　AI CONTENT FINDING</span><p>{evidence[0] ? `${evidence[0].label}. ${evidence[0].detail}` : 'No validated content finding is available.'}</p></section></div>

                <div className="aip-analysis-grid"><ScoreMatrix components={components} confidence={report.confidence?.level} /><ContentSignals report={report} /><Verdict score={score} evidence={evidence} confidence={report.confidence?.level} /></div>
                <RecommendedMoves moves={moves} />
            </div> : <div className="aip-empty"><span>✦</span><h2>Analyze your first post</h2><p>Add a public media URL to generate the report.</p><button onClick={() => setShowForm(true)}>New analysis</button></div>}
        </section>
        <AnalysisModal open={showForm} canClose={Boolean(report)} state={state} error={error} values={{ mediaUrl, mediaUrls, caption }} setters={{ setMediaUrl, setMediaUrls, setCaption }} onClose={() => setShowForm(false)} onSubmit={runAnalysis} />
    </main>
}
