import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from '@/features/auth/AuthContext'
import { ProyectosProvider } from '@/features/proyectos/ProyectosContext'
import { PrincipalProvider } from '@/features/dashboard/PrincipalContext'
import AppLayout from '@/shared/components/AppLayout'
import Cargando from '@/shared/components/Cargando'
import Login from '@/features/auth/pages/Login'
import ElegirUsername from '@/features/auth/pages/ElegirUsername'
import Inicio from '@/features/dashboard/pages/Inicio'
import Resumen from '@/features/dashboard/pages/Resumen'
import Archivos from '@/features/archivos/pages/Archivos'
import VerDatos from '@/features/archivos/pages/VerDatos'
import Proyecto from '@/features/proyectos/pages/Proyecto'
import Usuarios from '@/features/usuarios/pages/Usuarios'

// El editor y la exportación traen las librerías de gráficas, mapa, PDF y PowerPoint:
// se descargan solo cuando se abre esa pantalla.
const DashboardEditor = lazy(() => import('@/features/dashboard/pages/DashboardEditor'))
const Exportar = lazy(() => import('@/features/exportar/pages/Exportar'))

/** Pantalla que exige sesión (y, si se pide, ser administrador) y se muestra dentro del menú lateral. */
function Privada({ children, admin = false }) {
  const { usuario, cargando } = useAuth()
  if (cargando) return <Cargando pantalla />
  if (!usuario) return <Navigate to="/" replace />
  // Primer ingreso: antes de ver nada, debe elegir su nombre de usuario
  if (usuario.necesita_username) return <ElegirUsername />
  if (admin && usuario.rol !== 'admin') return <Navigate to="/dashboard" replace />
  return (
    <AppLayout>
      <Suspense fallback={<Cargando />}>{children}</Suspense>
    </AppLayout>
  )
}

function Rutas() {
  const { usuario } = useAuth()
  return (
    <Routes>
      {/* Con sesión se va al inicio; sin sesión se muestra el login */}
      <Route path="/" element={usuario ? <Navigate to="/dashboard" replace /> : <Login />} />

      <Route path="/dashboard" element={<Privada><Inicio /></Privada>} />
      <Route path="/resumen" element={<Privada><Resumen /></Privada>} />
      <Route path="/archivos" element={<Privada><Archivos /></Privada>} />
      <Route path="/datos/:id" element={<Privada><VerDatos /></Privada>} />
      <Route path="/datos/:id/dashboard" element={<Privada><DashboardEditor /></Privada>} />
      <Route path="/datos/:id/exportar" element={<Privada><Exportar /></Privada>} />
      <Route path="/proyecto/:id" element={<Privada><Proyecto /></Privada>} />
      <Route path="/usuarios" element={<Privada admin><Usuarios /></Privada>} />

      {/* Cualquier otra ruta vuelve al inicio */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <AuthProvider>
        <ProyectosProvider>
          <PrincipalProvider>
            <Rutas />
          </PrincipalProvider>
        </ProyectosProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
