import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import Callback from './pages/Callback'
import AccountAnalysisDemo from './pages/AccountAnalysisDemo'
import BrandCampaign from './pages/BrandCampaign'
import Dashboard from './pages/Dashboard'
import SinglePostInsights from './pages/SinglePostInsights'

function withErrorBoundary(element) {
    return <ErrorBoundary>{element}</ErrorBoundary>
}

function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<Navigate to="/analytics" replace />} />
                <Route path="/dashboard" element={<Navigate to="/analytics" replace />} />
                <Route path="/analytics" element={withErrorBoundary(<Dashboard />)} />
                <Route path="/account-analysis-demo" element={withErrorBoundary(<AccountAnalysisDemo />)} />
                <Route path="/brand/campaign" element={withErrorBoundary(<BrandCampaign />)} />
                <Route path="/post/:media_id" element={withErrorBoundary(<SinglePostInsights />)} />
                <Route path="/auth/callback" element={withErrorBoundary(<Callback />)} />
            </Routes>
        </BrowserRouter>
    )
}

export default App


