import { useState } from 'react'

function Login() {
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')

    const handleConnect = async () => {
        setLoading(true)
        setError('')
        try {
            const res = await fetch('/api/auth/instagram/login')
            if (!res.ok) {
                throw new Error('Failed to start Instagram login')
            }
            const data = await res.json()
            if (!data?.oauth_url) {
                throw new Error('Missing OAuth URL from server')
            }
            window.location.href = data.oauth_url
        } catch (err) {
            setError(err.message || 'Something went wrong')
            setLoading(false)
        }
    }

    return (
        <div className="auth-page">
            <div className="auth-card">
                <h1>Creonnect</h1>
                <p>Connect your Instagram to get started</p>
                {error ? <div className="auth-error">{error}</div> : null}
                <button
                    className="instagram-button"
                    onClick={handleConnect}
                    disabled={loading}
                >
                    {loading ? 'Connecting...' : 'Connect with Instagram'}
                </button>
            </div>
        </div>
    )
}

export default Login
