import { useState, useMemo } from 'react'

/**
 * Revenue Calculator Component
 * Displays rate recommendation with breakdown and optimization tips
 */
function RevenueCalculator({ data }) {
    if (!data) return null

    const {
        base_rate = 0,
        recommended_rate = 0,
        rate_min = 0,
        rate_max = 0,
        cpm_estimate = 0,
        breakdown = {},
        optimization_tips = [],
        revenue_projections = {}
    } = data

    return (
        <div className="ai-detail-card">
            <span className="post-section-kicker">Revenue Optimization</span>
            <div className="section-heading compact">
                <h2>Rate Recommendation</h2>
            </div>

            {/* Main Rate Display */}
            <div style={{
                textAlign: 'center',
                padding: '1.5rem',
                background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1), rgba(59, 130, 246, 0.1))',
                borderRadius: '16px',
                marginBottom: '1rem'
            }}>
                <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                    Recommended Rate
                </div>
                <div style={{ fontSize: '2.5rem', fontWeight: 'bold', color: 'var(--text-primary)' }}>
                    ${Math.round(rate_min)} - ${Math.round(rate_max)}
                </div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
                    per post (sweet spot: ${Math.round(recommended_rate)})
                </div>
            </div>

            {/* Rate Breakdown */}
            <div style={{ marginBottom: '1rem' }}>
                <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                    RATE BREAKDOWN
                </h4>
                <div className="dashboard-bar-list">
                    <div className="dashboard-bar-row">
                        <div className="dashboard-bar-copy">
                            <span>Base Rate (from ER)</span>
                            <strong>${Math.round(breakdown.base_rate || 0)}</strong>
                        </div>
                    </div>
                    <div className="dashboard-bar-row">
                        <div className="dashboard-bar-copy">
                            <span>Engagement Component</span>
                            <strong>+${Math.round(breakdown.engagement_component || 0)}</strong>
                        </div>
                    </div>
                    <div className="dashboard-bar-row">
                        <div className="dashboard-bar-copy">
                            <span>Follower Multiplier</span>
                            <strong>+${Math.round(breakdown.follower_component || 0)}</strong>
                        </div>
                    </div>
                    <div className="dashboard-bar-row">
                        <div className="dashboard-bar-copy">
                            <span>Niche Premium</span>
                            <strong>+${Math.round(breakdown.niche_component || 0)}</strong>
                        </div>
                    </div>
                    <div className="dashboard-bar-row">
                        <div className="dashboard-bar-copy">
                            <span>Quality Premium</span>
                            <strong>+${Math.round(breakdown.quality_premium || 0)}</strong>
                        </div>
                    </div>
                </div>
            </div>

            {/* Optimization Tips */}
            {optimization_tips.length > 0 && (
                <div style={{ marginBottom: '1rem' }}>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                        OPTIMIZATION TIPS
                    </h4>
                    <ul style={{ margin: 0, paddingLeft: '1.1rem', color: 'var(--text-primary)', lineHeight: 1.8 }}>
                        {optimization_tips.slice(0, 4).map((tip, i) => (
                            <li key={i} style={{ fontSize: '0.9rem' }}>{tip}</li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Revenue Projections */}
            {revenue_projections.monthly_deals_4 && (
                <div>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                        REVENUE PROJECTIONS (Annual)
                    </h4>
                    <div className="dashboard-bar-list">
                        <div className="dashboard-bar-row">
                            <div className="dashboard-bar-copy">
                                <span>Conservative (4 deals/mo)</span>
                                <strong>${Math.round(revenue_projections.monthly_deals_4[0] * 12).toLocaleString()} - ${Math.round(revenue_projections.monthly_deals_4[1] * 12).toLocaleString()}</strong>
                            </div>
                        </div>
                        <div className="dashboard-bar-row">
                            <div className="dashboard-bar-copy">
                                <span>Moderate (8 deals/mo)</span>
                                <strong>${Math.round(revenue_projections.monthly_deals_8[0] * 12).toLocaleString()} - ${Math.round(revenue_projections.monthly_deals_8[1] * 12).toLocaleString()}</strong>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}


/**
 * Risk Assessment Component
 * Displays risk level and detected issues
 */
function RiskDashboard({ data }) {
    if (!data) return null

    const {
        overall_risk_level = 'low',
        risks = [],
        risk_count = 0,
        recommended_actions = []
    } = data

    const getRiskColor = (level) => {
        switch (level) {
            case 'critical': return '#ef4444'
            case 'high': return '#f97316'
            case 'medium': return '#eab308'
            case 'low': return '#22c55e'
            default: return '#6b7280'
        }
    }

    const getRiskIcon = (level) => {
        switch (level) {
            case 'critical': return '🔴'
            case 'high': return '🟠'
            case 'medium': return '🟡'
            case 'low': return '🟢'
            default: return '⚪'
        }
    }

    return (
        <div className="ai-detail-card">
            <span className="post-section-kicker">Risk Assessment</span>
            <div className="section-heading compact">
                <h2>Risk Assessment</h2>
            </div>

            {/* Overall Status */}
            <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '1rem',
                background: `${getRiskColor(overall_risk_level)}15`,
                borderRadius: '12px',
                marginBottom: '1rem',
                border: `1px solid ${getRiskColor(overall_risk_level)}30`
            }}>
                <span style={{ fontSize: '1.5rem' }}>{getRiskIcon(overall_risk_level)}</span>
                <div>
                    <div style={{ fontWeight: 'bold', color: getRiskColor(overall_risk_level) }}>
                        {overall_risk_level.toUpperCase()} RISK
                    </div>
                    <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        {risk_count} issue{risk_count !== 1 ? 's' : ''} detected
                    </div>
                </div>
            </div>

            {/* Risk List */}
            {risks.length > 0 && (
                <div style={{ marginBottom: '1rem' }}>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                        ACTIVE RISKS
                    </h4>
                    {risks.slice(0, 4).map((risk, i) => (
                        <div
                            key={risk.id || i}
                            style={{
                                padding: '0.75rem',
                                marginBottom: '0.5rem',
                                background: 'var(--bg-secondary)',
                                borderRadius: '8px',
                                borderLeft: `3px solid ${getRiskColor(risk.level)}`
                            }}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <strong style={{ fontSize: '0.9rem' }}>{risk.title}</strong>
                                <span style={{
                                    fontSize: '0.75rem',
                                    padding: '0.2rem 0.5rem',
                                    borderRadius: '4px',
                                    background: `${getRiskColor(risk.level)}20`,
                                    color: getRiskColor(risk.level)
                                }}>
                                    {risk.level.toUpperCase()}
                                </span>
                            </div>
                            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '0.5rem 0 0 0' }}>
                                {risk.description}
                            </p>
                        </div>
                    ))}
                </div>
            )}

            {/* Recommended Actions */}
            {recommended_actions.length > 0 && (
                <div>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                        RECOMMENDED ACTIONS
                    </h4>
                    <ul style={{ margin: 0, paddingLeft: '1.1rem', color: 'var(--text-primary)', lineHeight: 1.8 }}>
                        {recommended_actions.slice(0, 3).map((action, i) => (
                            <li key={i} style={{ fontSize: '0.9rem' }}>{action}</li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    )
}


/**
 * Brand Readiness Component
 * Displays detailed brand readiness score with breakdown
 */
function BrandReadinessDetail({ data }) {
    if (!data) return null

    const {
        overall_score = 0,
        overall_label = 'Early Stage',
        content_quality_score = 0,
        brand_safety_score = 0,
        engagement_score = 0,
        consistency_score = 0,
        niche_clarity_score = 0,
        audience_quality_score = 0,
        improvement_opportunities = []
    } = data

    const getScoreColor = (score) => {
        if (score >= 80) return '#22c55e'
        if (score >= 60) return '#3b82f6'
        if (score >= 40) return '#eab308'
        return '#ef4444'
    }

    const scores = [
        { label: 'Content Quality', score: content_quality_score },
        { label: 'Brand Safety', score: brand_safety_score },
        { label: 'Engagement', score: engagement_score },
        { label: 'Consistency', score: consistency_score },
        { label: 'Niche Clarity', score: niche_clarity_score },
        { label: 'Audience Quality', score: audience_quality_score }
    ]

    return (
        <div className="ai-detail-card">
            <span className="post-section-kicker">Brand Readiness</span>
            <div className="section-heading compact">
                <h2>Brand Readiness Score</h2>
            </div>

            {/* Overall Score */}
            <div style={{
                textAlign: 'center',
                padding: '1.5rem',
                background: `linear-gradient(135deg, ${getScoreColor(overall_score)}15, ${getScoreColor(overall_score)}05)`,
                borderRadius: '16px',
                marginBottom: '1rem',
                border: `1px solid ${getScoreColor(overall_score)}30`
            }}>
                <div style={{ fontSize: '3rem', fontWeight: 'bold', color: getScoreColor(overall_score) }}>
                    {Math.round(overall_score)}
                </div>
                <div style={{ fontSize: '1.1rem', color: 'var(--text-primary)', marginTop: '0.25rem' }}>
                    {overall_label}
                </div>
            </div>

            {/* Component Scores */}
            <div className="dashboard-bar-list">
                {scores.map(({ label, score }) => (
                    <div key={label} className="dashboard-bar-row">
                        <div className="dashboard-bar-copy">
                            <span>{label}</span>
                            <strong>{Math.round(score)}/100</strong>
                        </div>
                        <div className="dashboard-progress-track">
                            <div
                                className="dashboard-progress-fill"
                                style={{
                                    width: `${score}%`,
                                    background: getScoreColor(score)
                                }}
                            />
                        </div>
                    </div>
                ))}
            </div>

            {/* Improvement Opportunities */}
            {improvement_opportunities.length > 0 && (
                <div style={{ marginTop: '1rem' }}>
                    <h4 style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                        TOP IMPROVEMENT AREAS
                    </h4>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                        {improvement_opportunities.slice(0, 3).map((area, i) => (
                            <span
                                key={i}
                                style={{
                                    padding: '0.4rem 0.8rem',
                                    background: 'var(--bg-secondary)',
                                    borderRadius: '8px',
                                    fontSize: '0.85rem',
                                    color: 'var(--text-primary)'
                                }}
                            >
                                {area}
                            </span>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}


/**
 * Main Advanced Analysis Component
 * Combines all advanced analysis features
 */
export default function AdvancedAnalysis({ revenueData, riskData, brandReadinessData }) {
    return (
        <div className="dashboard-section-stack">
            <div
                style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                    gap: '1rem'
                }}
            >
                <RevenueCalculator data={revenueData} />
                <RiskDashboard data={riskData} />
            </div>
            <BrandReadinessDetail data={brandReadinessData} />
        </div>
    )
}

export { RevenueCalculator, RiskDashboard, BrandReadinessDetail }
