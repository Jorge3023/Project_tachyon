import { useState } from 'react'
import api, { ESPERA_ARCHIVOS } from '@/shared/api'

const ETIQUETA_ROL = {
  fecha: 'Fecha',
  numero: 'Número (medida)',
  categoria: 'Categoría',
  identificador: 'Identificador',
  estado: 'Estado',
  texto: 'Texto libre',
  ignorar: 'Ignorar columna',
}

const ETIQUETA_FORMATO = { numero: 'Número', moneda: 'Moneda ($)', porcentaje: 'Porcentaje (%)' }
const lista = (xs) => xs.map(x => `«${x}»`).join(', ')

/** Lo que pasará con los valores de la columna con el tipo elegido (se avisa antes de guardar). */
function avisosColumna(c) {
  const out = []
  const l = c.lectura?.[c.rol]
  if (l?.n > 0) {
    out.push(`${l.n.toLocaleString('es-MX')} ${l.n === 1 ? 'valor no se puede' : 'valores no se pueden'} leer como ${c.rol === 'numero' ? 'número' : 'fecha'}` +
      `${l.ejemplos?.length ? ` (${lista(l.ejemplos)})` : ''}: ${l.n === 1 ? 'quedará vacío' : 'quedarán vacíos'}.`)
  }
  if ((c.rol === 'categoria' || c.rol === 'estado') && c.variantes?.length) {
    out.push(`Se unificará la escritura: ${c.variantes.map(([a, b]) => `«${a}» → «${b}»`).join(', ')}.`)
  }
  return out
}

// Pantalla de revisión: el sistema propone el tipo de cada columna y la persona lo corrige antes de guardar.
// modo «edicion»: la misma pantalla para corregir las columnas de un archivo que ya se guardó.
export default function ModalRevisarColumnas({ analisis: inicial, proyectoId = null, onCancelar, onGuardado }) {
  const edicion = inicial.modo === 'edicion'
  const [analisis, setAnalisis] = useState(inicial)
  const [cols, setCols] = useState(inicial.columnas)
  const [filaEnc, setFilaEnc] = useState(inicial.fila_encabezado + 1)   // se muestra desde 1
  const [guardarPlantilla, setGuardarPlantilla] = useState(!inicial.plantilla && !edicion)
  const [vista, setVista] = useState('todas')          // todas | revisar | avisos
  const [nombrePlantilla, setNombrePlantilla] = useState(inicial.nombre.replace(/\.[^.]+$/, ''))
  const [trabajando, setTrabajando] = useState(false)
  const [recargando, setRecargando] = useState(false)
  const [error, setError] = useState('')

  const reanalizar = async (hoja, fila1) => {
    setRecargando(true); setError('')
    try {
      const params = new URLSearchParams()
      if (hoja) params.set('hoja', hoja)
      if (fila1 !== null) params.set('fila_encabezado', String(Math.max(0, fila1 - 1)))
      const r = await api.get(`/datasets/${analisis.archivo_id}/${edicion ? 'columnas' : 'analisis'}?${params}`, { timeout: ESPERA_ARCHIVOS })
      setAnalisis(r.data); setCols(r.data.columnas); setFilaEnc(r.data.fila_encabezado + 1)
    } catch (e) {
      setError(e.response?.data?.detail || 'No se pudo volver a leer el archivo')
    } finally { setRecargando(false) }
  }

  const cambiar = (i, campo, valor) =>
    setCols(cs => cs.map((c, j) => j === i ? { ...c, [campo]: valor, ...(campo === 'rol' ? { revisar: false, confianza: 1 } : {}) } : c))

  const activas = cols.filter(c => c.rol !== 'ignorar').length
  const dudosas = cols.filter(c => c.revisar && c.rol !== 'ignorar').length
  const conAvisos = cols.filter(c => c.rol !== 'ignorar' && avisosColumna(c).length).length

  const guardar = async () => {
    setTrabajando(true); setError('')
    try {
      const r = await api.post(`/datasets/${analisis.archivo_id}/${edicion ? 'columnas' : 'confirmar'}`, {
        hoja: analisis.hoja, fila_encabezado: analisis.fila_encabezado,
        columnas: cols.map(c => ({ nombre: c.nombre, rol: c.rol, nombre_mostrar: c.nombre_mostrar,
          formato: c.rol === 'numero' ? (c.formato || 'numero') : null })),
        guardar_plantilla: guardarPlantilla, nombre_plantilla: nombrePlantilla, proyecto_id: proyectoId,
      }, { timeout: ESPERA_ARCHIVOS })
      onGuardado(r.data)
    } catch (e) {
      setError(e.response?.data?.detail || 'No se pudo guardar')
      setTrabajando(false)
    }
  }

  const cancelar = async () => {
    if (!edicion) { try { await api.delete(`/datasets/${analisis.archivo_id}/borrador`) } catch { /* ya no existe */ } }
    onCancelar()
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 md:p-4" role="dialog" aria-modal="true">
      <div className="bg-white md:rounded-2xl w-full max-w-5xl h-full md:h-auto md:max-h-[92vh] flex flex-col shadow-xl">
        <div className="px-4 md:px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900">{edicion ? 'Corregir columnas' : 'Revisar columnas'} — {analisis.nombre}</h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {analisis.filas.toLocaleString('es-MX')} filas · {analisis.columnas.length} columnas.{' '}
            {edicion
              ? 'Cambia el tipo, el nombre o el formato. Tus vistas se conservan: los nombres nuevos se actualizan y, si una gráfica ya no encaja, se quita al abrirla (con aviso).'
              : 'Corrige lo que no esté bien; así sabremos cómo interpretar tus datos.'}
          </p>
          {edicion && !analisis.origen_disponible && (
            <p className="text-xs text-amber-700 mt-1.5">Este archivo se guardó antes de conservar el original: las columnas que ignoraste ya no se pueden recuperar.</p>
          )}
        </div>

        <div className="px-4 md:px-6 py-4 overflow-y-auto space-y-4">
          {analisis.plantilla && (
            <div className="px-3 py-2 rounded-lg bg-brand-50 border border-brand-100 text-xs text-brand-700">
              Reconocimos este formato: aplicamos tu plantilla “{analisis.plantilla.nombre}”
              {analisis.plantilla.similitud < 1 && ` (${Math.round(analisis.plantilla.similitud * 100)}% de coincidencia)`}.
            </div>
          )}

          <div className={`flex flex-wrap items-end gap-4 ${edicion && !analisis.origen_disponible ? 'hidden' : ''}`}>
            {analisis.hojas.length > 1 && (
              <label className="text-xs text-gray-500">
                Hoja
                <select className="input mt-1 block min-w-[10rem]" value={analisis.hoja} disabled={recargando}
                  onChange={e => reanalizar(e.target.value, null)}>
                  {analisis.hojas.map(h => <option key={h}>{h}</option>)}
                </select>
              </label>
            )}
            <label className="text-xs text-gray-500">
              Fila de encabezados
              <input type="number" min={1} className="input mt-1 block w-24" value={filaEnc} disabled={recargando}
                onChange={e => setFilaEnc(e.target.value === '' ? '' : Number(e.target.value))}
                onBlur={() => filaEnc !== analisis.fila_encabezado + 1 && filaEnc !== '' && reanalizar(analisis.hoja, filaEnc)}
                onKeyDown={e => e.key === 'Enter' && filaEnc !== '' && reanalizar(analisis.hoja, filaEnc)} />
            </label>
            {analisis.sin_encabezado && (
              <p className="text-xs text-amber-600 pb-2">No encontramos encabezados; les pusimos “Columna N”. Puedes renombrarlas.</p>
            )}
            {recargando && <span className="w-4 h-4 mb-2 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />}
          </div>

          <details className="text-xs group">
            <summary className="cursor-pointer text-gray-500 hover:text-gray-700 select-none">Ver las primeras filas del archivo</summary>
            <div className="overflow-x-auto mt-2 border border-gray-100 rounded-xl">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 text-gray-500">
                  <tr>{analisis.vista_previa.columnas.map(n => <th key={n} className="text-left font-medium px-3 py-1.5 whitespace-nowrap">{n}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {analisis.vista_previa.filas.map((f, i) => (
                    <tr key={i}>{f.map((v, j) => <td key={j} className="px-3 py-1.5 whitespace-nowrap text-gray-600">{v ?? ''}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          {(dudosas > 0 || conAvisos > 0) && (
            <div role="group" aria-label="Qué columnas mostrar" className="flex flex-wrap gap-1 text-xs">
              {[['todas', `Todas (${cols.length})`], dudosas > 0 && ['revisar', `Por revisar (${dudosas})`], conAvisos > 0 && ['avisos', `Con avisos (${conAvisos})`]]
                .filter(Boolean).map(([v, l]) => (
                  <button key={v} type="button" aria-pressed={vista === v} onClick={() => setVista(v)}
                    className={`px-2.5 py-1 rounded-md border ${vista === v ? 'bg-gray-900 border-gray-900 text-white' : 'border-gray-200 text-gray-600 hover:bg-gray-50'}`}>{l}</button>
                ))}
            </div>
          )}

          {/* Una fila por columna. En pantallas angostas cada columna es una tarjeta apilada. */}
          <div className="border border-gray-100 rounded-xl divide-y divide-gray-100">
            <div className="hidden md:grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_11rem_minmax(0,1.2fr)] gap-3 px-3 py-2 bg-gray-50 text-[11px] font-medium text-gray-500 rounded-t-xl">
              <span>Columna del archivo</span><span>Nombre en tu tablero</span><span>Tipo</span><span>Ejemplos</span>
            </div>
            {cols.map((c, i) => {
              const avisos = c.rol !== 'ignorar' ? avisosColumna(c) : []
              const revisar = c.revisar && c.rol !== 'ignorar'
              if (vista === 'revisar' && !revisar) return null
              if (vista === 'avisos' && !avisos.length) return null
              return (
                <div key={c.nombre + i} className={`px-3 py-2.5 md:grid md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_11rem_minmax(0,1.2fr)] md:gap-3 md:items-start text-xs ${c.rol === 'ignorar' ? 'opacity-50' : ''}`}>
                  <div className="flex items-center gap-2 min-w-0 mb-1.5 md:mb-0 md:pt-2">
                    <p className="font-medium text-gray-800 truncate" title={c.nombre}>{c.nombre}</p>
                    {revisar && <span className="badge-warn flex-shrink-0" title={c.razon}>Revisar</span>}
                  </div>
                  <div className="grid grid-cols-2 gap-2 md:contents">
                    <input className="input py-1.5" aria-label={`Nombre de ${c.nombre}`} value={c.nombre_mostrar}
                      onChange={e => cambiar(i, 'nombre_mostrar', e.target.value)} />
                    <div className="flex flex-col gap-1.5 min-w-0">
                      <select className="input py-1.5" aria-label={`Tipo de ${c.nombre}`} value={c.rol} title={c.razon}
                        onChange={e => cambiar(i, 'rol', e.target.value)}>
                        {analisis.roles.map(r => <option key={r} value={r}>{ETIQUETA_ROL[r] || r}</option>)}
                      </select>
                      {c.rol === 'numero' && (
                        <select className="input py-1 text-xs" aria-label={`Formato de ${c.nombre}`} value={c.formato || 'numero'}
                          onChange={e => cambiar(i, 'formato', e.target.value)} title="Cómo se muestran los valores">
                          {Object.entries(ETIQUETA_FORMATO).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        </select>
                      )}
                    </div>
                  </div>
                  <div className="text-gray-500 min-w-0 mt-1.5 md:mt-0 md:pt-1.5">
                    <p className="truncate" title={(c.ejemplos || []).join(' · ')}>{(c.ejemplos || []).join(' · ')}</p>
                    <p className="text-[11px] text-gray-400 mt-0.5">{c.unicos} distintos · {Math.round(c.nulos_pct)} % vacíos</p>
                  </div>
                  {(revisar || avisos.length > 0) && (
                    <div className="md:col-span-4 mt-1.5 md:mt-0 space-y-0.5">
                      {revisar && <p className="text-[11px] text-gray-500">{c.razon}</p>}
                      {avisos.map((a, k) => <p key={k} className="text-[11px] text-amber-700">{a}</p>)}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        <div className="px-4 md:px-6 py-3 md:py-4 border-t border-gray-100 space-y-3">
          {error && <p className="text-xs text-red-600">{error}</p>}
          <div className="flex flex-wrap items-center gap-4 justify-between">
            <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={guardarPlantilla} onChange={e => setGuardarPlantilla(e.target.checked)} />
                {edicion ? 'Actualizar la plantilla para archivos con estas columnas' : 'Guardar como plantilla para archivos con estas columnas'}
              </label>
              {guardarPlantilla && (
                <input className="input w-52" aria-label="Nombre de la plantilla" value={nombrePlantilla}
                  onChange={e => setNombrePlantilla(e.target.value)} placeholder="Nombre de la plantilla" />
              )}
            </div>
            <div className="flex items-center gap-2">
              {dudosas > 0 && <span className="text-xs text-amber-600">{dudosas} por revisar</span>}
              {conAvisos > 0 && <span className="text-xs text-amber-600">{conAvisos} con avisos</span>}
              <button type="button" onClick={cancelar} className="px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-500 hover:bg-gray-50">
                Cancelar
              </button>
              <button type="button" onClick={guardar} disabled={trabajando || recargando || activas === 0}
                className="btn-primary disabled:opacity-50">
                {trabajando ? 'Guardando…' : edicion ? 'Guardar cambios' : `Guardar ${activas} ${activas === 1 ? 'columna' : 'columnas'}`}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
