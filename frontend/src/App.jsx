import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import { clearSession, getToken } from './api.js'
import Login from './pages/Login.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Runs from './pages/Runs.jsx'
import RunDetail from './pages/RunDetail.jsx'
import ApiMetrics from './pages/ApiMetrics.jsx'
import DataQuality from './pages/DataQuality.jsx'
import Performance from './pages/Performance.jsx'
import Gates from './pages/Gates.jsx'
import Chatbot from './pages/Chatbot.jsx'
import NotFound from './pages/NotFound.jsx'

export default function App() {
  const [token, setToken] = useState(getToken())

  useEffect(() => {
    const onLogin = () => setToken(getToken())
    const onLogout = () => setToken('')
    window.addEventListener('aqp:login', onLogin)
    window.addEventListener('aqp:unauthorized', onLogout)
    return () => {
      window.removeEventListener('aqp:login', onLogin)
      window.removeEventListener('aqp:unauthorized', onLogout)
    }
  }, [])

  const logout = useCallback(() => {
    clearSession()
    setToken('')
  }, [])

  return (
    <Routes>
      <Route path="/login" element={token ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route element={token ? <Layout onLogout={logout} /> : <Navigate to="/login" replace />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="/runs/:runKey" element={<RunDetail />} />
        <Route path="/metrics" element={<ApiMetrics />} />
        <Route path="/data-quality" element={<DataQuality />} />
        <Route path="/performance" element={<Performance />} />
        <Route path="/gates" element={<Gates />} />
        <Route path="/chatbot" element={<Chatbot />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
