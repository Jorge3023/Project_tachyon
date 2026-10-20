import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import AppLayout from './components/AppLayout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Archivos from './pages/Archivos'
import ElegirUsername from './pages/ElegirUsername'
import Usuarios from './pages/Usuarios'
import VerDatos from './pages/VerDatos'
import Proyecto from './pages/Proyecto'
// El editor trae las librerías de gráficas: se carga solo cuando se abre un dashboard
const DashboardEditor = lazy(() => import('./pages/DashboardEditor'))
import { ProyectosProvider } from './context/ProyectosContext'

function PrivateRoute({ children }) {
  const { usuario, cargando } = useAuth()
  if (cargando) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-6 h-6 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />
    </div>
  )
  if (!usuario) return <Navigate to="/" replace />
  // Primer ingreso: antes de ver nada, debe elegir su nombre de usuario
  if (usuario.necesita_username) return <ElegirUsername />
  return children
}

function AdminRoute({ children }) {
  const { usuario } = useAuth()
  return usuario?.rol === 'admin' ? children : <Navigate to="/dashboard" replace />
}

function AppRoutes() {
  const { usuario } = useAuth()
  return (
    <Routes>
      {/* Ruta Principal: Si está logueado va a Dashboard, si no, muestra Login */}
      <Route path="/" element={usuario ? <Navigate to="/dashboard" replace /> : <Login />} />

      {/* Rutas Protegidas */}
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
      <Route path="/datos/:id/dashboard" element={
        <PrivateRoute>
          <AppLayout>
            <Suspense fallback={<div className="flex-1 flex items-center justify-center"><div className="w-6 h-6 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" /></div>}>
              <DashboardEditor />
            </Suspense>
          </AppLayout>
        </PrivateRoute>
      } />
      <Route path="/datos/:id" element={
        <PrivateRoute>
          <AppLayout><VerDatos /></AppLayout>
        </PrivateRoute>
      } />
      <Route path="/proyecto/:id" element={
        <PrivateRoute>
          <AppLayout><Proyecto /></AppLayout>
        </PrivateRoute>
      } />
      <Route path="/usuarios" element={
        <PrivateRoute>
          <AdminRoute><AppLayout><Usuarios /></AppLayout></AdminRoute>
        </PrivateRoute>
      } />

      {/* Comodín: Cualquier otra ruta no definida redirige al inicio */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <AuthProvider>
        <ProyectosProvider>
          <AppRoutes />
        </ProyectosProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}