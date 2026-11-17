import { fmtNum, fmtValor, etiquetaLarga, fechaCorta } from '@/features/dashboard/lib/dash'

/** Líneas pequeñas bajo una gráfica (aviso del servidor, correlación, media…). Las usan el editor y la exportación. */
export default function Notas({ widget, datos }) {
  if (!datos || datos.error) return null
  return (
    <>
      {datos.advertencia && <p className="text-[11px] text-gray-400 mt-2">{datos.advertencia}</p>}
      {datos.parcial && (
        <p className="text-[11px] text-gray-500 mt-2">
          <span aria-hidden="true" className="inline-block w-4 border-t-2 border-dashed border-gray-400 align-middle mr-1.5" />
          {etiquetaLarga(datos.parcial, datos.grano)}: periodo incompleto, los datos llegan al {fechaCorta(datos.parcial_hasta)}.
        </p>
      )}
      {widget.tipo === 'dispersion' && datos.total > 0 && (
        <p className="text-[11px] text-gray-400 mt-2">
          {datos.correlacion !== null && <>Correlación r = {fmtNum(datos.correlacion)} · </>}
          {datos.muestra < datos.total ? `muestra de ${fmtNum(datos.muestra)} de ${fmtNum(datos.total)} puntos` : `${fmtNum(datos.total)} puntos`}
        </p>
      )}
      {widget.tipo === 'histograma' && datos.media !== undefined && (
        <p className="text-[11px] text-gray-400 mt-2">Media {fmtValor(datos.media, datos.formato)} · Mediana {fmtValor(datos.mediana, datos.formato)} · {fmtNum(datos.n)} filas</p>
      )}
    </>
  )
}
