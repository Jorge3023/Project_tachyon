import { useState } from 'react'
import {
  TIPOS, ORDEN_TIPOS, ANCHOS, GRANOS, AGGS, PALETA, ROL_TEXTO, OPERACIONES, aggsPermitidas, motivoNoDisponible, cambiarTipo,
  candidatasLat, candidatasLon, describirMetrica,
} from '@/features/dashboard/lib/dash'
import ListaFiltros from './Filtros'

const sel = 'w-full text-sm border border-gray-200 rounded-lg px-2.5 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/30'

function Campo({ etiqueta, children, ayuda }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1">{etiqueta}</label>
      {children}
      {ayuda && <p className="text-[11px] text-gray-400 mt-1">{ayuda}</p>}
    </div>
  )
}

function Segmentado({ opciones, valor, onChange, etiqueta, deshabilitadas = [] }) {
  return (
    <div role="group" aria-label={etiqueta} className="flex flex-wrap bg-gray-100 rounded-lg p-0.5 gap-0.5">
      {opciones.map(o => (
        <button key={o.v} type="button" disabled={deshabilitadas.includes(o.v)} aria-pressed={valor === o.v}
          onClick={() => onChange(o.v)}
          className={`flex-1 px-2 py-1.5 rounded-md text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ` +
            (valor === o.v ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
          {o.l}
        </button>
      ))}
    </div>
  )
}

/* Métrica calculada: combina los totales de dos columnas (p. ej. defectuosas ÷ producidas en %). */
function FormMetrica({ columnas, existentes, onGuardar, onCancelar }) {
  const nums = columnas.filter(c => c.rol === 'numero')
  const [m, setM] = useState({ nombre: '', a: nums[0]?.nombre || '', op: 'pct', b: nums[1]?.nombre || nums[0]?.nombre || '' })
  const ocupado = existentes.some(n => n.toLowerCase() === m.nombre.trim().toLowerCase())
  const valido = m.nombre.trim() && !ocupado && m.a && m.b
  const op = OPERACIONES.find(o => o.v === m.op)
  return (
    <div className="rounded-lg border border-brand-200 bg-brand-50/50 p-3 space-y-2.5">
      <p className="text-xs font-medium text-gray-700">Nueva métrica calculada</p>
      <input className="input py-1.5 text-sm" placeholder="Nombre (p. ej. % de defectos)" maxLength={40} value={m.nombre} autoFocus
        onChange={e => setM({ ...m, nombre: e.target.value })} aria-label="Nombre de la métrica" />
      {ocupado && <p className="text-[11px] text-red-600">Ya hay una columna o métrica con ese nombre.</p>}
      <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1.5 items-center text-xs">
        <span className="text-gray-500">A</span>
        <select className={sel} value={m.a} onChange={e => setM({ ...m, a: e.target.value })} aria-label="Columna A">
          {nums.map(c => <option key={c.nombre}>{c.nombre}</option>)}
        </select>
        <span className="text-gray-500">Op.</span>
        <select className={sel} value={m.op} onChange={e => setM({ ...m, op: e.target.value })} aria-label="Operación">
          {OPERACIONES.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
        </select>
        <span className="text-gray-500">B</span>
        <select className={sel} value={m.b} onChange={e => setM({ ...m, b: e.target.value })} aria-label="Columna B">
          {nums.map(c => <option key={c.nombre}>{c.nombre}</option>)}
        </select>
      </div>
      <p className="text-[11px] text-gray-500">{op?.d}. Se calcula con los totales de cada grupo, no fila por fila.</p>
      <div className="flex gap-2 justify-end">
        <button type="button" className="btn-ghost text-xs" onClick={onCancelar}>Cancelar</button>
        <button type="button" className="btn-primary text-xs py-1.5" disabled={!valido}
          onClick={() => onGuardar({ nombre: m.nombre.trim().replace(/\s+/g, ' '), op: m.op, a: m.a, b: m.b })}>Crear y usar</button>
      </div>
    </div>
  )
}

export default function PanelConfig({ widget: w, columnas, metricas = [], usos = {}, onMetricas, archivoId, onCambio, onReemplazar, onDuplicar, onEliminar, onMover, puedeSubir, puedeBajar, onCerrar }) {
  const info = TIPOS[w.tipo]
  const [creando, setCreando] = useState(false)
  const reales = columnas.filter(c => c.rol !== 'calculada')
  const por = (roles) => columnas.filter(c => roles.includes(c.rol))
  const opcionesCol = (roles, incluirNinguna) => (
    <>
      {incluirNinguna && <option value="">{incluirNinguna}</option>}
      {por(roles.filter(r => r !== 'calculada')).map(c => <option key={c.nombre} value={c.nombre}>{c.nombre} ({ROL_TEXTO[c.rol]})</option>)}
      {roles.includes('calculada') && por(['calculada']).length > 0 && (
        <optgroup label="Métricas calculadas">
          {por(['calculada']).map(c => <option key={c.nombre} value={c.nombre}>{c.nombre}</option>)}
        </optgroup>
      )}
    </>
  )
  const aceptaCalculada = (info.campos.medida || []).includes('calculada')
  // Al cambiar de métrica, la agregación por defecto es la natural de esa columna (precio → promedio, importe → suma)
  const elegirMedida = (v) => {
    if (v === '__nueva__') { setCreando(true); return }
    const col = columnas.find(c => c.nombre === v)
    if (!col) { onCambio({ medida: null }); return }
    if (col.rol === 'calculada') { onCambio({ medida: v, agg: 'calc' }); return }
    const permitidas = aggsPermitidas(w.tipo)
    onCambio({ medida: v, agg: permitidas.includes(col.agg) ? col.agg : (permitidas.includes('suma') ? 'suma' : permitidas[0]) })
  }
  const metricaActual = w.agg === 'calc' ? metricas.find(m => m.nombre === w.medida) : null
  const xEsFecha = columnas.find(c => c.nombre === w.x)?.rol === 'fecha'
  const aggs = aggsPermitidas(w.tipo)
  const conSerie = !!info.campos.serie
  return (
    <aside className="fixed inset-y-0 right-0 z-40 w-[88vw] max-w-sm shadow-xl md:static md:z-auto md:w-80 md:max-w-none md:shadow-none flex-shrink-0 bg-white border-l border-gray-100 overflow-y-auto" aria-label="Configurar gráfica">
      <div className="px-5 py-4 border-b border-gray-100 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Configurar gráfica</h2>
          <p className="text-xs text-gray-400 mt-0.5">Los cambios se aplican al instante</p>
        </div>
        <button type="button" onClick={onCerrar} className="btn-ghost px-2 py-1 text-xs" aria-label="Cerrar panel">✕</button>
      </div>

      <div className="p-5 space-y-5">
        <Campo etiqueta="Título">
          <input className="input py-2" value={w.titulo} maxLength={80} onChange={e => onCambio({ titulo: e.target.value })} />
        </Campo>

        <Campo etiqueta="Tipo de visualización">
          <div className="grid grid-cols-2 gap-1.5">
            {ORDEN_TIPOS.map(t => {
              const motivo = t !== w.tipo ? motivoNoDisponible(t, columnas) : null
              return (
                <button key={t} type="button" disabled={!!motivo} title={motivo || TIPOS[t].d} aria-pressed={w.tipo === t}
                  onClick={() => onReemplazar(cambiarTipo(w, t, columnas))}
                  className={`px-2 py-1.5 rounded-lg text-xs border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ` +
                    (w.tipo === t ? 'border-brand-500 bg-brand-50 text-brand-700 font-medium' : 'border-gray-200 text-gray-600 hover:border-gray-300')}>
                  {TIPOS[t].l}
                </button>
              )
            })}
          </div>
        </Campo>

        {w.tipo !== 'tabla' && (
          <div className="space-y-3">
            <p className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Datos</p>
            {info.campos.x && (
              <Campo etiqueta={w.tipo === 'kpi' ? 'Fecha (para comparar con el periodo anterior)' : w.tipo === 'dispersion' ? 'Eje X' : w.tipo === 'histograma' ? 'Columna' : w.tipo === 'dona' || w.tipo === 'pareto' ? 'Categoría' : 'Eje X'}>
                <select className={sel} value={w.x || ''} onChange={e => onCambio({ x: e.target.value || null })}>
                  {opcionesCol(info.campos.x, w.tipo === 'kpi' ? 'Sin comparación' : null)}
                </select>
              </Campo>
            )}
            {info.campos.y && (
              <Campo etiqueta={w.tipo === 'dispersion' ? 'Eje Y' : 'Filas (eje Y)'}>
                <select className={sel} value={w.y || ''} onChange={e => onCambio({ y: e.target.value || null })}>
                  {opcionesCol(info.campos.y)}
                </select>
              </Campo>
            )}
            {w.tipo === 'mapa' && (
              <>
                <Campo etiqueta="Latitud" ayuda="Columna numérica entre −90 y 90.">
                  <select className={sel} value={w.lat || ''} onChange={e => onCambio({ lat: e.target.value || null })}>
                    {candidatasLat(columnas).map(c => <option key={c.nombre} value={c.nombre}>{c.nombre}</option>)}
                  </select>
                </Campo>
                <Campo etiqueta="Longitud" ayuda="Columna numérica entre −180 y 180.">
                  <select className={sel} value={w.lon || ''} onChange={e => onCambio({ lon: e.target.value || null })}>
                    {candidatasLon(columnas).filter(c => c.nombre !== w.lat).map(c => <option key={c.nombre} value={c.nombre}>{c.nombre}</option>)}
                  </select>
                </Campo>
              </>
            )}
            {info.campos.medida && (
              <Campo etiqueta={w.tipo === 'mapa' ? 'Tamaño de los puntos' : 'Métrica'}>
                <select className={sel} value={w.medida || ''} onChange={e => elegirMedida(e.target.value)}>
                  {opcionesCol(info.campos.medida, w.tipo === 'mapa' ? 'Número de filas' : 'Conteo de filas')}
                  {aceptaCalculada && onMetricas && <option value="__nueva__">＋ Nueva métrica calculada…</option>}
                </select>
              </Campo>
            )}
            {creando && (
              <FormMetrica columnas={reales} existentes={[...reales.map(c => c.nombre), ...metricas.map(m => m.nombre)]}
                onCancelar={() => setCreando(false)}
                onGuardar={m => { onMetricas([...metricas, m]); onCambio({ medida: m.nombre, agg: 'calc' }); setCreando(false) }} />
            )}
            {metricaActual && (
              <p className="text-[11px] text-gray-500 bg-gray-50 rounded-lg px-2.5 py-2">
                Se calcula con los totales: {describirMetrica(metricaActual)}.
              </p>
            )}
            {!aceptaCalculada && info.campos.medida && metricas.length > 0 && (
              <p className="text-[11px] text-gray-400">Las métricas calculadas se pueden usar en indicadores, líneas, área, barras y mapa de calor.</p>
            )}
            {info.aggs && w.medida && w.agg !== 'calc' && (
              <Campo etiqueta="Agregación">
                <Segmentado etiqueta="Agregación" valor={w.agg} onChange={v => onCambio({ agg: v })}
                  opciones={AGGS.filter(a => aggs.includes(a.v) && a.v !== 'conteo')} />
              </Campo>
            )}
            {conSerie && (
              <Campo etiqueta={w.tipo === 'mapa' ? 'Color por categoría (opcional)' : 'Desglosar por (opcional)'}>
                <select className={sel} value={w.serie || ''} onChange={e => onCambio({ serie: e.target.value || null })}>
                  {opcionesCol(info.campos.serie, w.tipo === 'mapa' ? 'Un solo color' : 'Sin desglose')}
                </select>
              </Campo>
            )}
            {info.grano && xEsFecha && (
              <Campo etiqueta="Agrupar fechas por" ayuda="«Auto» usa la granularidad del panel de filtros.">
                <Segmentado etiqueta="Granularidad" valor={w.grano || 'auto'} onChange={v => onCambio({ grano: v })} opciones={GRANOS} />
              </Campo>
            )}
            {w.tipo === 'kpi' && w.x && (
              <Campo etiqueta="Comparar por">
                <Segmentado etiqueta="Granularidad" valor={w.grano || 'auto'} onChange={v => onCambio({ grano: v })} opciones={GRANOS} />
              </Campo>
            )}
            {w.tipo === 'barras' && (
              <>
                <Campo etiqueta="Orientación">
                  <Segmentado etiqueta="Orientación" valor={w.orientacion || 'v'} onChange={v => onCambio({ orientacion: v })}
                    opciones={[{ v: 'v', l: 'Vertical' }, { v: 'h', l: 'Horizontal' }]} />
                </Campo>
                {w.serie && (
                  <Campo etiqueta="Series">
                    <Segmentado etiqueta="Series" valor={w.apilado ? 's' : 'a'} onChange={v => onCambio({ apilado: v === 's' })}
                      opciones={[{ v: 'a', l: 'Agrupadas' }, { v: 's', l: 'Apiladas' }]} />
                  </Campo>
                )}
                {!xEsFecha && (
                  <>
                    <Campo etiqueta="Orden">
                      <Segmentado etiqueta="Orden" valor={w.orden || 'desc'} onChange={v => onCambio({ orden: v })}
                        opciones={[{ v: 'desc', l: 'Mayor → menor' }, { v: 'asc', l: 'Menor → mayor' }, { v: 'natural', l: 'Original' }]} />
                    </Campo>
                    <Campo etiqueta="Mostrar las primeras">
                      <input type="number" min={1} max={50} className={sel} value={w.top ?? 10} onChange={e => onCambio({ top: Number(e.target.value) || 10 })} />
                    </Campo>
                  </>
                )}
              </>
            )}
            {(w.tipo === 'dona' || w.tipo === 'pareto' || w.tipo === 'calor') && (
              <Campo etiqueta={w.tipo === 'calor' ? 'Máximo de categorías por eje' : 'Mostrar las principales'}>
                <input type="number" min={2} max={w.tipo === 'pareto' ? 30 : w.tipo === 'calor' ? 15 : 12} className={sel} value={w.top ?? 10}
                  onChange={e => onCambio({ top: Number(e.target.value) || 6 })} />
              </Campo>
            )}
            {w.tipo === 'histograma' && (
              <Campo etiqueta="Intervalos" ayuda="0 = automático">
                <input type="number" min={0} max={60} className={sel} value={w.bins ?? 0} onChange={e => onCambio({ bins: Number(e.target.value) || 0 })} />
              </Campo>
            )}
          </div>
        )}

        {w.tipo === 'tabla' && (
          <div className="space-y-3">
            <p className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Datos</p>
            <Campo etiqueta="Columnas (hasta 10)">
              <ul className="max-h-40 overflow-auto border border-gray-100 rounded-lg p-1.5 space-y-0.5">
                {reales.map(c => (
                  <li key={c.nombre}>
                    <label className="flex items-center gap-2 text-xs px-1 py-0.5 rounded hover:bg-gray-50 cursor-pointer">
                      <input type="checkbox" checked={(w.columnas || []).includes(c.nombre)}
                        onChange={e => {
                          const cur = w.columnas || []
                          const nuevo = e.target.checked ? [...cur, c.nombre] : cur.filter(x => x !== c.nombre)
                          if (nuevo.length >= 1 && nuevo.length <= 10) onCambio({ columnas: reales.map(k => k.nombre).filter(n => nuevo.includes(n)) })
                        }} />
                      <span className="truncate">{c.nombre}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </Campo>
            <Campo etiqueta="Ordenar por">
              <select className={sel} value={w.orden || ''} onChange={e => onCambio({ orden: e.target.value || null })}>
                <option value="">Orden original</option>
                {reales.map(c => <option key={c.nombre} value={c.nombre}>{c.nombre}</option>)}
              </select>
            </Campo>
            {w.orden && (
              <Segmentado etiqueta="Dirección" valor={w.dir || 'desc'} onChange={v => onCambio({ dir: v })}
                opciones={[{ v: 'desc', l: 'Descendente' }, { v: 'asc', l: 'Ascendente' }]} />
            )}
            <Campo etiqueta="Filas a mostrar">
              <input type="number" min={1} max={50} className={sel} value={w.filas ?? 10} onChange={e => onCambio({ filas: Number(e.target.value) || 10 })} />
            </Campo>
          </div>
        )}

        <Campo etiqueta="Ancho en el tablero">
          <Segmentado etiqueta="Ancho" valor={w.ancho} onChange={v => onCambio({ ancho: v })} opciones={ANCHOS} />
        </Campo>

        {['linea', 'area', 'barras', 'dispersion', 'histograma', 'pareto', 'mapa'].includes(w.tipo) && !w.serie && (
          <Campo etiqueta="Color">
            <div className="flex gap-1.5 flex-wrap" role="group" aria-label="Color">
              {PALETA.map((c, i) => (
                <button key={c} type="button" onClick={() => onCambio({ color: i })} aria-label={`Color ${i + 1}`} aria-pressed={(w.color ?? 0) === i}
                  className={`w-6 h-6 rounded-full border-2 ${(w.color ?? 0) === i ? 'border-gray-900' : 'border-white ring-1 ring-gray-200'}`} style={{ background: c }} />
              ))}
            </div>
          </Campo>
        )}

        <Campo etiqueta="Filtros de esta gráfica">
          <ListaFiltros archivoId={archivoId} columnas={reales} filtros={w.filtros || []} onChange={filtros => onCambio({ filtros })} />
        </Campo>

        {metricas.length > 0 && onMetricas && (
          <Campo etiqueta="Métricas calculadas de esta vista">
            <ul className="space-y-1">
              {metricas.map(m => (
                <li key={m.nombre} className="flex items-start gap-2 text-xs">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-gray-700 truncate">{m.nombre}</p>
                    <p className="text-[11px] text-gray-400 truncate">{describirMetrica(m)}</p>
                  </div>
                  <button type="button" disabled={!!usos[m.nombre]} onClick={() => onMetricas(metricas.filter(x => x.nombre !== m.nombre))}
                    title={usos[m.nombre] ? `La usan ${usos[m.nombre]} gráfica(s): cámbialas primero` : 'Quitar la métrica'}
                    className="text-[11px] px-1.5 py-0.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-gray-400">Quitar</button>
                </li>
              ))}
            </ul>
          </Campo>
        )}

        <div className="pt-2 border-t border-gray-100 flex flex-wrap gap-2">
          <button type="button" className="btn-ghost text-xs border border-gray-200" onClick={() => onMover(-1)} disabled={!puedeSubir}>↑ Subir</button>
          <button type="button" className="btn-ghost text-xs border border-gray-200" onClick={() => onMover(1)} disabled={!puedeBajar}>↓ Bajar</button>
          <button type="button" className="btn-ghost text-xs border border-gray-200" onClick={onDuplicar}>Duplicar</button>
          <button type="button" className="btn-ghost text-xs border border-red-200 text-red-600 hover:bg-red-50 ml-auto" onClick={onEliminar}>Eliminar</button>
        </div>
      </div>
    </aside>
  )
}
