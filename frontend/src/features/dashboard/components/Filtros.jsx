import { useState, useEffect, useRef } from 'react'
import api from '@/shared/api'
import { ROL_TEXTO } from '@/features/dashboard/lib/dash'

const _cache = new Map()
/** Valores posibles de una columna (para armar el filtro). Se piden una sola vez por archivo y columna. */
function useValores(archivoId, columna) {
  const clave = `${archivoId}|${columna}`
  const [v, setV] = useState(_cache.get(clave) || null)
  useEffect(() => {
    if (!columna) return
    if (_cache.has(clave)) { setV(_cache.get(clave)); return }
    let vivo = true
    api.get(`/datasets/${archivoId}/valores`, { params: { columna } })
      .then(r => { _cache.set(clave, r.data); if (vivo) setV(r.data) }).catch(() => {})
    return () => { vivo = false }
  }, [clave])
  return v
}

function SelectorValores({ archivoId, filtro, onChange }) {
  const info = useValores(archivoId, filtro.col)
  const [abierto, setAbierto] = useState(false)
  const [q, setQ] = useState('')
  const ref = useRef()
  useEffect(() => {
    if (!abierto) return
    const cerrar = (e) => { if (ref.current && !ref.current.contains(e.target)) setAbierto(false) }
    document.addEventListener('mousedown', cerrar)
    return () => document.removeEventListener('mousedown', cerrar)
  }, [abierto])
  const sel = new Set(filtro.valores || [])
  const valores = (info?.valores || []).filter(x => x.valor.toLowerCase().includes(q.toLowerCase()))
  const alternar = (v) => {
    const s = new Set(sel); s.has(v) ? s.delete(v) : s.add(v)
    onChange({ ...filtro, valores: [...s] })
  }
  const resumen = sel.size === 0 ? 'Todas' : sel.size === 1 ? [...sel][0] : `${sel.size} seleccionadas`
  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setAbierto(a => !a)} aria-haspopup="listbox" aria-expanded={abierto}
        className="text-xs border border-gray-200 rounded-md px-2 py-1 bg-white hover:border-gray-300 max-w-[12rem] truncate">
        {resumen} ▾
      </button>
      {abierto && (
        <div className="absolute z-30 mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg p-2">
          {info?.unicos > 8 && (
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Buscar…" aria-label="Buscar valor"
              className="w-full border border-gray-200 rounded px-2 py-1 text-xs mb-2" />
          )}
          <ul className="max-h-52 overflow-auto space-y-0.5" role="listbox" aria-multiselectable="true">
            {!info && <li className="text-xs text-gray-400 px-1 py-1">Cargando…</li>}
            {valores.map(x => (
              <li key={x.valor}>
                <label className="flex items-center gap-2 text-xs px-1 py-1 rounded hover:bg-gray-50 cursor-pointer">
                  <input type="checkbox" checked={sel.has(x.valor)} onChange={() => alternar(x.valor)} />
                  <span className="truncate flex-1">{x.valor}</span>
                  <span className="text-gray-400 tabular-nums">{x.n}</span>
                </label>
              </li>
            ))}
          </ul>
          {info?.unicos > 100 && <p className="text-[11px] text-gray-400 mt-1">Se muestran los 100 valores más frecuentes.</p>}
          {sel.size > 0 && <button type="button" className="text-xs text-brand-600 mt-1" onClick={() => onChange({ ...filtro, valores: [] })}>Limpiar selección</button>}
        </div>
      )}
    </div>
  )
}

/** Un filtro: etiqueta de la columna + control según su tipo (fechas, rango numérico o categorías). */
export function FiltroCtl({ archivoId, filtro, rol, onChange, onQuitar }) {
  const info = useValores(archivoId, rol === 'fecha' || rol === 'numero' ? filtro.col : null)
  const campoFecha = "text-xs border border-gray-200 rounded-md px-1.5 py-1 bg-white"
  return (
    <div className="flex items-center gap-1.5 bg-gray-50 border border-gray-100 rounded-lg pl-2.5 pr-1 py-1 text-xs">
      <span className="text-gray-500 max-w-[8rem] truncate" title={filtro.col}>{filtro.col}:</span>
      {rol === 'fecha' && (
        <>
          <input type="date" value={filtro.desde || ''} min={info?.min} max={info?.max} aria-label={`${filtro.col} desde`}
            onChange={e => onChange({ ...filtro, desde: e.target.value || null })} className={campoFecha} />
          <span className="text-gray-400">–</span>
          <input type="date" value={filtro.hasta || ''} min={info?.min} max={info?.max} aria-label={`${filtro.col} hasta`}
            onChange={e => onChange({ ...filtro, hasta: e.target.value || null })} className={campoFecha} />
        </>
      )}
      {rol === 'numero' && (
        <>
          <input type="number" value={filtro.min ?? ''} placeholder={info?.min !== undefined ? String(info.min) : 'mín.'} aria-label={`${filtro.col} mínimo`}
            onChange={e => onChange({ ...filtro, min: e.target.value === '' ? null : Number(e.target.value) })} className={`${campoFecha} w-20`} />
          <span className="text-gray-400">–</span>
          <input type="number" value={filtro.max ?? ''} placeholder={info?.max !== undefined ? String(info.max) : 'máx.'} aria-label={`${filtro.col} máximo`}
            onChange={e => onChange({ ...filtro, max: e.target.value === '' ? null : Number(e.target.value) })} className={`${campoFecha} w-20`} />
        </>
      )}
      {rol !== 'fecha' && rol !== 'numero' && <SelectorValores archivoId={archivoId} filtro={filtro} onChange={onChange} />}
      <button type="button" onClick={onQuitar} aria-label={`Quitar filtro de ${filtro.col}`}
        className="w-5 h-5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50 flex items-center justify-center">×</button>
    </div>
  )
}

function filtroVacio(col, rol) {
  if (rol === 'fecha') return { col, desde: null, hasta: null }
  if (rol === 'numero') return { col, min: null, max: null }
  return { col, valores: [] }
}

/** Lista de filtros + "Agregar filtro". Los filtros todavía vacíos no restringen nada (el servidor los ignora). */
export default function ListaFiltros({ archivoId, filtros, columnas, onChange }) {
  const roles = Object.fromEntries(columnas.map(c => [c.nombre, c.rol]))
  const libres = columnas.filter(c => !filtros.some(f => f.col === c.nombre) && c.rol !== 'texto')
  const [agregando, setAgregando] = useState(false)
  return (
    <div className="flex flex-wrap items-center gap-2">
      {filtros.map((f, i) => (
        <FiltroCtl key={f.col} archivoId={archivoId} filtro={f} rol={roles[f.col]}
          onChange={nf => onChange(filtros.map((x, j) => j === i ? nf : x))}
          onQuitar={() => onChange(filtros.filter((_, j) => j !== i))} />
      ))}
      {libres.length > 0 && (agregando ? (
        <select autoFocus aria-label="Columna del filtro" className="text-xs border border-gray-200 rounded-md px-2 py-1.5 bg-white" defaultValue=""
          onBlur={() => setAgregando(false)}
          onChange={e => { if (e.target.value) { onChange([...filtros, filtroVacio(e.target.value, roles[e.target.value])]); setAgregando(false) } }}>
          <option value="" disabled>Elige una columna…</option>
          {libres.map(c => <option key={c.nombre} value={c.nombre}>{c.nombre} ({ROL_TEXTO[c.rol]})</option>)}
        </select>
      ) : (
        <button type="button" onClick={() => setAgregando(true)} className="text-xs text-brand-600 hover:text-brand-700 px-2 py-1 rounded-md hover:bg-brand-50">
          + Agregar filtro
        </button>
      ))}
    </div>
  )
}
