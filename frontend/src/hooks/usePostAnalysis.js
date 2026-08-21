import { useCallback, useState } from 'react'

const CONTRACT_VERSION = 'v1'

export function usePostAnalysis() {
    const [report, setReport] = useState(null)
    const [state, setState] = useState('idle')
    const [error, setError] = useState('')

    const analyze = useCallback(async (request) => {
        setState('loading')
        setError('')
        setReport(null)
        try {
            const response = await fetch('/api/v1/post-analysis', {
                method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request)
            })
            const payload = await response.json().catch(() => ({}))
            if (!response.ok) throw new Error(payload?.detail || 'Analysis could not be completed.')
            if (payload?.contract_version !== CONTRACT_VERSION) {
                throw new Error(`This report requires contract ${CONTRACT_VERSION}; received ${payload?.contract_version || 'no version'}.`)
            }
            setReport(payload)
            setState('complete')
            return payload
        } catch (requestError) {
            setError(requestError.message || 'Analysis could not be completed.')
            setState('error')
            return null
        }
    }, [])

    return { report, state, error, analyze, clearReport: () => setReport(null) }
}
