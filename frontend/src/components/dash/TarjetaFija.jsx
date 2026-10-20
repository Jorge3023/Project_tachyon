import { Grafica, vacio } from './Graficas'
import Notas from './Notas'
import { TIPOS, TINTA, subtituloWidget } from '../../lib/dash'

/** Tarjeta de una gráfica sin controles de edición: es lo que se fotografía al exportar. */
export default function TarjetaFija({ widget, datos }) {
  const esKpi = widget.tipo === 'kpi'
  const sub = subtituloWidget(widget)
  const titulo = widget.titulo || TIPOS[widget.tipo].l
  return (
    <section className={`card flex flex-col flex-1 min-w-0 ${esKpi ? 'p-4' : ''}`} style={{ borderColor: TINTA.rejilla }} aria-label={titulo}>
      <header className="mb-2">
        {esKpi
          ? <h3 className="text-xs text-gray-500 leading-snug">{titulo}</h3>
          : <h3 className="text-sm font-semibold text-gray-900">{titulo}</h3>}
        {sub && !esKpi && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </header>
      <div className="flex-1 min-h-0">
        {!datos ? <div className="animate-pulse bg-gray-100 rounded-lg" style={{ height: esKpi ? 48 : 200 }} aria-label="Cargando gráfica" />
          : datos.error ? <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{datos.error}</p>
          : vacio(widget, datos) ? <p className="text-xs text-gray-400 py-8 text-center">Sin datos con los filtros actuales.</p>
          : <Grafica widget={widget} datos={datos} />}
      </div>
      <Notas widget={widget} datos={datos} />
    </section>
  )
}
