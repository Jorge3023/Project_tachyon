import { lazy, Suspense } from 'react'
import { usePrincipal } from '@/features/dashboard/PrincipalContext'
import Resumen from './Resumen'

const DashboardEditor = lazy(() => import('./DashboardEditor'))
const Cargando = () => (
  <div className="flex-1 flex items-center justify-center"><div className="w-6 h-6 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" /></div>
)

/* Página de entrada: el dashboard principal del usuario o, si aún no eligió uno, el resumen de sus archivos. */
export default function Inicio() {
  const { principal, cargando } = usePrincipal()
  if (cargando) return <Cargando />
  if (!principal) return <Resumen />
  return (
    <Suspense fallback={<Cargando />}>
      {/* key: al cambiar de principal se vuelve a cargar desde cero */}
      <DashboardEditor key={`${principal.archivo_id}:${principal.vista_id ?? ''}`} archivoId={principal.archivo_id} vistaInicial={principal.vista_id} esInicio />
    </Suspense>
  )
}
