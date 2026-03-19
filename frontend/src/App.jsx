import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Callback from './pages/Callback'
import BrandCampaign from './pages/BrandCampaign'
import Dashboard from './pages/Dashboard'
import SinglePostInsights from './pages/SinglePostInsights'

function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<Navigate to="/analytics" replace />} />
                <Route path="/dashboard" element={<Navigate to="/analytics" replace />} />
                <Route path="/analytics" element={<Dashboard />} />
                <Route path="/brand/campaign" element={<BrandCampaign />} />
                <Route path="/post/:media_id" element={<SinglePostInsights />} />
                <Route path="/auth/callback" element={<Callback />} />
            </Routes>
        </BrowserRouter>
    )
}

export default App


