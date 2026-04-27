import React from 'react'

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props)
        this.state = {
            hasError: false,
            error: null
        }
    }

    static getDerivedStateFromError(error) {
        return {
            hasError: true,
            error
        }
    }

    componentDidCatch(error, errorInfo) {
        console.error('ErrorBoundary caught an error:', error, errorInfo)
    }

    render() {
        const { hasError, error } = this.state
        const { children, fallback } = this.props

        if (hasError) {
            if (fallback) {
                return typeof fallback === 'function'
                    ? fallback({ error, retry: () => window.location.reload() })
                    : fallback
            }

            return (
                <>
                    <style>{`
                        .error-boundary {
                            min-height: 100vh;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            padding: 32px;
                            background: #0f0f11;
                            color: #ffffff;
                            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
                        }

                        .error-boundary__panel {
                            width: 100%;
                            max-width: 560px;
                            padding: 32px;
                            border: 1px solid rgba(255, 255, 255, 0.08);
                            border-radius: 20px;
                            background: linear-gradient(180deg, rgba(31, 41, 55, 0.96) 0%, rgba(17, 24, 39, 0.96) 100%);
                            box-shadow: 0 24px 70px rgba(0, 0, 0, 0.45);
                        }

                        .error-boundary__eyebrow {
                            margin: 0 0 12px;
                            color: #60a5fa;
                            font-size: 12px;
                            font-weight: 700;
                            letter-spacing: 0.16em;
                            text-transform: uppercase;
                        }

                        .error-boundary__title {
                            margin: 0 0 12px;
                            font-size: 32px;
                            line-height: 1.1;
                        }

                        .error-boundary__text {
                            margin: 0 0 20px;
                            color: rgba(255, 255, 255, 0.78);
                            font-size: 15px;
                            line-height: 1.6;
                        }

                        .error-boundary__message {
                            margin: 0 0 24px;
                            padding: 14px 16px;
                            border-radius: 14px;
                            background: rgba(255, 255, 255, 0.05);
                            color: #f3f4f6;
                            font-size: 14px;
                            line-height: 1.5;
                            word-break: break-word;
                        }

                        .error-boundary__button {
                            border: 0;
                            border-radius: 999px;
                            padding: 12px 20px;
                            background: #2563eb;
                            color: #ffffff;
                            font-size: 14px;
                            font-weight: 700;
                            cursor: pointer;
                            transition: background 0.2s ease, transform 0.2s ease;
                        }

                        .error-boundary__button:hover {
                            background: #1d4ed8;
                            transform: translateY(-1px);
                        }

                        .error-boundary__button:focus-visible {
                            outline: 2px solid #93c5fd;
                            outline-offset: 3px;
                        }
                    `}</style>
                    <div className="error-boundary" role="alert">
                        <div className="error-boundary__panel">
                            <p className="error-boundary__eyebrow">Something Broke</p>
                            <h1 className="error-boundary__title">This page hit an unexpected error.</h1>
                            <p className="error-boundary__text">
                                You can retry the page now. If this keeps happening, the issue is likely temporary
                                or needs a code fix.
                            </p>
                            <div className="error-boundary__message">
                                {error?.message || 'Unknown error'}
                            </div>
                            <button
                                type="button"
                                className="error-boundary__button"
                                onClick={() => window.location.reload()}
                            >
                                Retry
                            </button>
                        </div>
                    </div>
                </>
            )
        }

        return children
    }
}

export default ErrorBoundary
