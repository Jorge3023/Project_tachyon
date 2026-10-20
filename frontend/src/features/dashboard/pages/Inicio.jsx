import { lazy, Suspense } from 'react'
import { usePrincipal } from '@/features/dashboard/PrincipalContext'
import Resumen from './Resumen'
import Cargando from '@/shared/components/Cargando'

const DashboardEditor = lazy(() => import('./DashboardEditor'))
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
