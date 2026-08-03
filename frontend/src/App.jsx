import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

const Callback = lazy(() => import('./pages/Callback'))
const AccountAnalysisDemo = lazy(() => import('./pages/AccountAnalysisDemo'))
const BrandCampaign = lazy(() => import('./pages/BrandCampaign'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const ImageEditor = lazy(() => import('./pages/ImageEditor'))
const SinglePostInsights = lazy(() => import('./pages/SinglePostInsights'))
const TrendRecommendations = lazy(() => import('./pages/TrendRecommendations'))

function PageLoader() {
    return <main className="app-page-loader" aria-live="polite">Loading workspace...</main>
}

function App() {
    return (
        <BrowserRouter>
            <Suspense fallback={<PageLoader />}>
                <Routes>
                    <Route path="/" element={<Navigate to="/analytics" replace />} />
                    <Route path="/dashboard" element={<Navigate to="/analytics" replace />} />
                    <Route path="/analytics" element={<Dashboard />} />
                    <Route path="/image-editor" element={<ImageEditor />} />
                    <Route path="/account-analysis-demo" element={<AccountAnalysisDemo />} />
                    <Route path="/brand/campaign" element={<BrandCampaign />} />
                    <Route path="/post/:media_id" element={<SinglePostInsights />} />
                    <Route path="/trends" element={<TrendRecommendations />} />
                    <Route path="/auth/callback" element={<Callback />} />
                </Routes>
            </Suspense>
        </BrowserRouter>
    )
}

export default App


