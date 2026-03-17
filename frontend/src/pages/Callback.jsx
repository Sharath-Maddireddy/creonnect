import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

function Callback() {
    const navigate = useNavigate()
    const [error, setError] = useState('')

    useEffect(() => {
        const run = async () => {
            const params = new URLSearchParams(window.location.search)
            const code = params.get('code')
            const state = params.get('state')

            if (!code) {
                setError('Missing authorization code')
                return
            }

            const query = new URLSearchParams({ code })
            if (state) {
                query.set('state', state)
            }

            try {
                const res = await fetch(`/api/auth/instagram/callback?${query.toString()}`)
                if (!res.ok) {
                    throw new Error('Failed to connect Instagram account')
                }
                const data = await res.json()
                if (!data?.user_id) {
                    throw new Error('Missing user_id from server')
                }
                localStorage.setItem('user_id', String(data.user_id))
                if (data?.username) {
                    localStorage.setItem('username', String(data.username))
                }
                navigate('/dashboard', { replace: true })
            } catch (err) {
                setError(err.message || 'Something went wrong')
            }
        }

        run()
    }, [navigate])

    if (error) {
        return (
            <div className="auth-page">
                <div className="auth-card">
                    <h1>Connection failed</h1>
                    <p className="auth-error">{error}</p>
                    <Link className="auth-link" to="/login">
                        Try Again
                    </Link>
                </div>
            </div>
        )
    }

    return (
        <div className="auth-loading">
            <div className="spinner"></div>
            <p>Connecting your Instagram...</p>
        </div>
    )
}

export default Callback
