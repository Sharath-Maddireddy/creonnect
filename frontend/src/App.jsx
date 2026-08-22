import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

const Callback = lazy(() => import('./pages/Callback'))
const BrandCampaign = lazy(() => import('./pages/BrandCampaign'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const CreatorIntelligence = lazy(() => import('./pages/CreatorIntelligence'))
const ImageEditor = lazy(() => import('./pages/ImageEditor'))
const CreatorImageEditor = lazy(() => import('./pages/CreatorImageEditor'))
const SinglePostInsights = lazy(() => import('./pages/SinglePostInsights'))
const PostAnalysisLab = lazy(() => import('./pages/PostAnalysisLab'))
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
                    <Route path="/creator-intelligence" element={<CreatorIntelligence />} />
                    <Route path="/image-editor" element={<ImageEditor />} />
                    <Route path="/creator/image-editor" element={<CreatorImageEditor />} />
                    <Route path="/brand/campaign" element={<BrandCampaign />} />
                    <Route path="/post/:media_id" element={<SinglePostInsights />} />
                    <Route path="/post-analysis" element={<PostAnalysisLab />} />
                    <Route path="/trends" element={<TrendRecommendations />} />
                    <Route path="/auth/callback" element={<Callback />} />
                </Routes>
            </Suspense>
        </BrowserRouter>
    )
}

export default App


