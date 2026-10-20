import { fmtNum } from '../../lib/dash'

/** Líneas pequeñas bajo una gráfica (aviso del servidor, correlación, media…). Las usan el editor y la exportación. */
export default function Notas({ widget, datos }) {
  if (!datos || datos.error) return null
  return (
    <>
      {datos.advertencia && <p className="text-[11px] text-gray-400 mt-2">{datos.advertencia}</p>}
      {widget.tipo === 'dispersion' && datos.total > 0 && (
        <p className="text-[11px] text-gray-400 mt-2">
          {datos.correlacion !== null && <>Correlación r = {fmtNum(datos.correlacion)} · </>}
          {datos.muestra < datos.total ? `muestra de ${fmtNum(datos.muestra)} de ${fmtNum(datos.total)} puntos` : `${fmtNum(datos.total)} puntos`}
        </p>
      )}
      {widget.tipo === 'histograma' && datos.media !== undefined && (
        <p className="text-[11px] text-gray-400 mt-2">Media {fmtNum(datos.media)} · Mediana {fmtNum(datos.mediana)} · {fmtNum(datos.n)} filas</p>
      )}
    </>
  )
}
