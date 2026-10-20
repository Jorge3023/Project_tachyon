import { TIPOS, ORDEN_TIPOS, motivoNoDisponible } from '../../lib/dash'

/** Ventana para elegir el tipo de la nueva gráfica. Los tipos que no encajan con las columnas salen deshabilitados con el motivo. */
export default function AgregarGrafica({ columnas, onElegir, onCerrar }) {
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4" role="dialog" aria-modal="true" aria-label="Agregar gráfica"
      onClick={onCerrar} onKeyDown={e => e.key === 'Escape' && onCerrar()}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-xl p-5" onClick={e => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Agregar gráfica</h2>
            <p className="text-xs text-gray-400 mt-0.5">Elige un tipo; luego ajustas las columnas en el panel.</p>
          </div>
          <button type="button" onClick={onCerrar} className="btn-ghost px-2 py-1 text-xs" aria-label="Cerrar">✕</button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[60vh] overflow-auto">
          {ORDEN_TIPOS.map(t => {
            const motivo = motivoNoDisponible(t, columnas)
            return (
              <button key={t} type="button" disabled={!!motivo} onClick={() => onElegir(t)}
                className="text-left border border-gray-200 rounded-lg px-3 py-2.5 hover:border-brand-400 hover:bg-brand-50/30 transition-colors disabled:opacity-50 disabled:hover:border-gray-200 disabled:hover:bg-transparent disabled:cursor-not-allowed">
                <span className="block text-sm font-medium text-gray-900">{TIPOS[t].l}</span>
                <span className="block text-xs text-gray-500 mt-0.5">{motivo || TIPOS[t].d}</span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
