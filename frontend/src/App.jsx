import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import AppLayout from './components/AppLayout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Archivos from './pages/Archivos'
import { LineaPage, ReportesPage } from './pages/Placeholders'

function PrivateRoute({ children }) {
  const { usuario, cargando } = useAuth()
  if (cargando) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-6 h-6 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )
  return usuario ? children : <Navigate to="/login" replace />
}

function AppRoutes() {
  const { usuario } = useAuth()
  return (
    <Routes>
      <Route path="/" element={usuario ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={
        <PrivateRoute>
          <AppLayout><Dashboard /></AppLayout>
        </PrivateRoute>
      } />
      <Route path="/archivos" element={
        <PrivateRoute>
          <AppLayout><Archivos /></AppLayout>
        </PrivateRoute>
      } />
      <Route path="/reportes" element={
        <PrivateRoute>
          <AppLayout><ReportesPage /></AppLayout>
        </PrivateRoute>
      } />
      <Route path="/linea/:id" element={
        <PrivateRoute>
          <AppLayout><LineaPage /></AppLayout>
        </PrivateRoute>
      } />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
