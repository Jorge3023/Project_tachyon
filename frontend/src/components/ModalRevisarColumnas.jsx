import { useState } from 'react'
import api from '../services/api'

const ETIQUETA_ROL = {
  fecha: 'Fecha',
  numero: 'Número (medida)',
  categoria: 'Categoría',
  identificador: 'Identificador',
  estado: 'Estado',
  texto: 'Texto libre',
  ignorar: 'Ignorar columna',
}

// Pantalla de revisión: el sistema propone el tipo de cada columna y la persona lo corrige antes de guardar.
export default function ModalRevisarColumnas({ analisis: inicial, onCancelar, onGuardado }) {
  const [analisis, setAnalisis] = useState(inicial)
  const [cols, setCols] = useState(inicial.columnas)
  const [filaEnc, setFilaEnc] = useState(inicial.fila_encabezado + 1)   // se muestra desde 1
  const [guardarPlantilla, setGuardarPlantilla] = useState(!inicial.plantilla)
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
      const r = await api.get(`/datasets/${analisis.archivo_id}/analisis?${params}`)
      setAnalisis(r.data); setCols(r.data.columnas); setFilaEnc(r.data.fila_encabezado + 1)
    } catch (e) {
      setError(e.response?.data?.detail || 'No se pudo volver a leer el archivo')
    } finally { setRecargando(false) }
  }

  const cambiar = (i, campo, valor) =>
    setCols(cs => cs.map((c, j) => j === i ? { ...c, [campo]: valor, ...(campo === 'rol' ? { revisar: false, confianza: 1 } : {}) } : c))

  const activas = cols.filter(c => c.rol !== 'ignorar').length
  const dudosas = cols.filter(c => c.revisar && c.rol !== 'ignorar').length

  const guardar = async () => {
    setTrabajando(true); setError('')
    try {
      const r = await api.post(`/datasets/${analisis.archivo_id}/confirmar`, {
        hoja: analisis.hoja, fila_encabezado: analisis.fila_encabezado,
        columnas: cols.map(c => ({ nombre: c.nombre, rol: c.rol, nombre_mostrar: c.nombre_mostrar })),
        guardar_plantilla: guardarPlantilla, nombre_plantilla: nombrePlantilla,
      })
      onGuardado(r.data)
    } catch (e) {
      setError(e.response?.data?.detail || 'No se pudo guardar')
      setTrabajando(false)
    }
  }

  const cancelar = async () => {
    try { await api.delete(`/datasets/${analisis.archivo_id}/borrador`) } catch { /* ya no existe */ }
    onCancelar()
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" role="dialog" aria-modal="true">
      <div className="bg-white rounded-2xl w-full max-w-5xl max-h-[92vh] flex flex-col shadow-xl">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900">Revisar columnas — {analisis.nombre}</h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {analisis.filas.toLocaleString()} filas · {analisis.columnas.length} columnas detectadas.
            Corrige lo que no esté bien; así sabremos cómo interpretar tus datos.
          </p>
        </div>

        <div className="px-6 py-4 overflow-y-auto space-y-4">
          {analisis.plantilla && (
            <div className="px-3 py-2 rounded-lg bg-brand-50 border border-brand-100 text-xs text-brand-700">
              Reconocimos este formato: aplicamos tu plantilla “{analisis.plantilla.nombre}”
              {analisis.plantilla.similitud < 1 && ` (${Math.round(analisis.plantilla.similitud * 100)}% de coincidencia)`}.
            </div>
          )}

          <div className="flex flex-wrap items-end gap-4">
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

          <div className="overflow-x-auto border border-gray-100 rounded-xl">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 text-gray-500">
                <tr>
                  <th className="text-left font-medium px-3 py-2">Columna del archivo</th>
                  <th className="text-left font-medium px-3 py-2">Nombre en tu tablero</th>
                  <th className="text-left font-medium px-3 py-2">Tipo</th>
                  <th className="text-left font-medium px-3 py-2">Ejemplos</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {cols.map((c, i) => (
                  <tr key={c.nombre + i} className={c.rol === 'ignorar' ? 'opacity-50' : ''}>
                    <td className="px-3 py-2 align-top">
                      <p className="font-medium text-gray-800">{c.nombre}</p>
                      {c.revisar && c.rol !== 'ignorar'
                        ? <span className="badge-warn mt-1 inline-block" title={c.razon}>Revisar</span>
                        : <p className="text-[11px] text-gray-400 mt-0.5">{Math.round(c.confianza * 100)}% seguro</p>}
                    </td>
                    <td className="px-3 py-2 align-top">
                      <input className="input" aria-label={`Nombre de ${c.nombre}`} value={c.nombre_mostrar}
                        onChange={e => cambiar(i, 'nombre_mostrar', e.target.value)} />
                    </td>
                    <td className="px-3 py-2 align-top">
                      <select className="input" aria-label={`Tipo de ${c.nombre}`} value={c.rol}
                        onChange={e => cambiar(i, 'rol', e.target.value)}>
                        {analisis.roles.map(r => <option key={r} value={r}>{ETIQUETA_ROL[r] || r}</option>)}
                      </select>
                      <p className="text-[11px] text-gray-400 mt-1 max-w-[16rem]">{c.razon}</p>
                    </td>
                    <td className="px-3 py-2 align-top text-gray-500 max-w-[16rem]">
                      <p className="truncate">{(c.ejemplos || []).join(' · ')}</p>
                      <p className="text-[11px] text-gray-400 mt-0.5">{c.unicos} distintos · {Math.round(c.nulos_pct * 100)}% vacíos</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <details className="text-xs">
            <summary className="cursor-pointer text-gray-500 hover:text-gray-700">Vista previa de las primeras filas</summary>
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
        </div>

        <div className="px-6 py-4 border-t border-gray-100 space-y-3">
          {error && <p className="text-xs text-red-600">{error}</p>}
          <div className="flex flex-wrap items-center gap-4 justify-between">
            <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={guardarPlantilla} onChange={e => setGuardarPlantilla(e.target.checked)} />
                Guardar como plantilla para archivos con estas columnas
              </label>
              {guardarPlantilla && (
                <input className="input w-52" aria-label="Nombre de la plantilla" value={nombrePlantilla}
                  onChange={e => setNombrePlantilla(e.target.value)} placeholder="Nombre de la plantilla" />
              )}
            </div>
            <div className="flex items-center gap-2">
              {dudosas > 0 && <span className="text-xs text-amber-600">{dudosas} por revisar</span>}
              <button type="button" onClick={cancelar} className="px-4 py-2 rounded-lg border border-gray-200 text-sm text-gray-500 hover:bg-gray-50">
                Cancelar
              </button>
              <button type="button" onClick={guardar} disabled={trabajando || recargando || activas === 0}
                className="btn-primary disabled:opacity-50">
                {trabajando ? 'Guardando…' : `Guardar ${activas} ${activas === 1 ? 'columna' : 'columnas'}`}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
