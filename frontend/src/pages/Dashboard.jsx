import { useState, useEffect } from 'react'
import {
    LineChart,
    Line,
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer
} from 'recharts'

function Dashboard() {
    const [data, setData] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(null)

    const fetchDashboard = async () => {
        setLoading(true)
        setError(null)
        try {
            const res = await fetch('/api/creator/dashboard')
            if (!res.ok) throw new Error('Failed to fetch dashboard data')
            const json = await res.json()
            setData(json)
        } catch (err) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchDashboard()
    }, [])

    if (loading) {
        return (
            <div className="loading-container">
                <div className="spinner"></div>
                <p>Loading dashboard...</p>
            </div>
        )
    }

    if (error) {
        return (
            <div className="error-container">
                <p>Error: {error}</p>
                <button onClick={fetchDashboard}>Retry</button>
            </div>
        )
    }

    const { summary, posts, charts } = data

    // Color for growth score
    const getGrowthColor = (score) => {
        if (score >= 80) return 'green'
        if (score >= 50) return 'yellow'
        return 'red'
    }

    // Format chart data
    const engagementData = charts.engagement_over_time.map((item, i) => ({
        date: item.date ? new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : `Post ${i + 1}`,
        value: item.value ? parseFloat(item.value.toFixed(2)) : 0
    }))

    const viewsData = charts.views_over_time.map((item, i) => ({
        date: item.date ? new Date(item.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : `Post ${i + 1}`,
        value: item.value || 0
    }))

    return (
        <div className="dashboard">
            {/* Header */}
            <div className="dashboard-header">
                <h1>Creator Analytics</h1>
                <p className="username">@{summary.username}</p>
            </div>

            {/* Summary Cards */}
            <div className="summary-grid">
                <div className="summary-card">
                    <div className="label">Growth Score</div>
                    <div className={`value ${getGrowthColor(summary.growth_score)}`}>
                        {summary.growth_score}
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Engagement %</div>
                    <div className="value blue">
                        {summary.avg_engagement_rate_by_views?.toFixed(2)}%
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Avg Views</div>
                    <div className="value">
                        {summary.avg_views?.toLocaleString()}
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Reach Ratio</div>
                    <div className="value purple">
                        {summary.views_to_followers_ratio?.toFixed(2)}x
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Posts / Week</div>
                    <div className="value">
                        {summary.posts_per_week?.toFixed(1)}
                    </div>
                </div>
                <div className="summary-card">
                    <div className="label">Niche</div>
                    <div className="value" style={{ fontSize: '1.25rem', textTransform: 'capitalize' }}>
                        {summary.niche?.primary_niche || 'Unknown'}
                    </div>
                </div>
            </div>

            {/* Charts */}
            <div className="charts-section">
                <div className="chart-card">
                    <h3>Engagement by Views (%)</h3>
                    <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={engagementData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
                            <XAxis dataKey="date" stroke="#a0a0b0" fontSize={12} />
                            <YAxis stroke="#a0a0b0" fontSize={12} />
                            <Tooltip
                                contentStyle={{ background: '#1a1a24', border: '1px solid #2a2a3a', borderRadius: 8 }}
                                labelStyle={{ color: '#fff' }}
                            />
                            <Line
                                type="monotone"
                                dataKey="value"
                                stroke="#3b82f6"
                                strokeWidth={2}
                                dot={{ fill: '#3b82f6', r: 4 }}
                                activeDot={{ r: 6 }}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                </div>

                <div className="chart-card">
                    <h3>Reel Views</h3>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={viewsData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
                            <XAxis dataKey="date" stroke="#a0a0b0" fontSize={12} />
                            <YAxis stroke="#a0a0b0" fontSize={12} />
                            <Tooltip
                                contentStyle={{ background: '#1a1a24', border: '1px solid #2a2a3a', borderRadius: 8 }}
                                labelStyle={{ color: '#fff' }}
                                formatter={(value) => value.toLocaleString()}
                            />
                            <Bar dataKey="value" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Posts Table */}
            <div className="posts-section">
                <h3>Post Insights</h3>
                <table className="posts-table">
                    <thead>
                        <tr>
                            <th>Post ID</th>
                            <th>Views</th>
                            <th>Engagement %</th>
                            <th>Likes</th>
                            <th>Comments</th>
                            <th>Insight</th>
                        </tr>
                    </thead>
                    <tbody>
                        {posts.map((post) => (
                            <tr key={post.post_id}>
                                <td>{post.post_id}</td>
                                <td>{post.views?.toLocaleString() || 'N/A'}</td>
                                <td>{post.engagement_rate_by_views?.toFixed(2)}%</td>
                                <td>{post.likes?.toLocaleString()}</td>
                                <td>{post.comments?.toLocaleString()}</td>
                                <td className="insight">
                                    {post.insights?.[0] || 'No insights'}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}

export default Dashboard
