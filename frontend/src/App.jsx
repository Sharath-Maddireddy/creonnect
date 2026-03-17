import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Callback from './pages/Callback'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'

function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<Navigate to="/login" replace />} />
                <Route path="/login" element={<Login />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/auth/callback" element={<Callback />} />
            </Routes>
        </BrowserRouter>
    )
}

export default App


