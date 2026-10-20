/** Indicador de carga. `pantalla` lo centra ocupando todo el alto de la ventana (usado antes de entrar a la app). */
export default function Cargando({ pantalla = false }) {
  const rueda = <div className="w-6 h-6 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" role="status" aria-label="Cargando" />
  return pantalla
    ? <div className="min-h-screen flex items-center justify-center">{rueda}</div>
    : <div className="flex-1 flex items-center justify-center">{rueda}</div>
}
