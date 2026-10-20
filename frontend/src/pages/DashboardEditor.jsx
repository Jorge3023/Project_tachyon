import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { Grafica, TablaAlternativa, vacio } from '../components/dash/Graficas'
import PanelConfig from '../components/dash/PanelConfig'
import AgregarGrafica from '../components/dash/AgregarGrafica'
import ListaFiltros from '../components/dash/Filtros'
import { CLASE_ANCHO, GRANOS, TIPOS, widgetNuevo, actualizarWidget, subtituloWidget, fmtNum, nuevoId } from '../lib/dash'

const tieneTablaAlt = (t) => ['linea', 'area', 'barras', 'dona', 'pareto', 'histograma', 'calor'].includes(t)
const msg = (e, def) => (typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : def)

function Esqueleto({ alto = 200 }) {
  return <div className="animate-pulse bg-gray-100 rounded-lg" style={{ height: alto }} aria-label="Cargando gráfica" />
}

function Tarjeta({ widget, datos, cargando, editando, seleccionada, onSeleccionar, onDuplicar, onEliminar, dnd }) {
  const [verTabla, setVerTabla] = useState(false)
  const esKpi = widget.tipo === 'kpi'
  const sub = subtituloWidget(widget)
  return (
    <section
      className={`card relative flex flex-col ${CLASE_ANCHO[widget.ancho] || CLASE_ANCHO[6]} col-span-12 ` +
        (esKpi ? 'p-4 ' : '') +
        (editando ? 'cursor-pointer hover:border-brand-300 ' : '') +
        (seleccionada ? 'ring-2 ring-brand-500 border-brand-500 ' : '')}
      aria-label={widget.titulo || TIPOS[widget.tipo].l}
      onClick={editando ? onSeleccionar : undefined}
      draggable={editando} onDragStart={dnd.onDragStart} onDragOver={dnd.onDragOver} onDrop={dnd.onDrop} onDragEnd={dnd.onDragEnd}
    >
      <header className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          {esKpi
            ? <h3 className="text-xs text-gray-500 leading-snug" title={widget.titulo}>{widget.titulo || TIPOS[widget.tipo].l}</h3>
            : <h3 className="text-sm font-semibold text-gray-900 truncate" title={widget.titulo}>{widget.titulo || TIPOS[widget.tipo].l}</h3>}
          {sub && !esKpi && <p className="text-xs text-gray-400 mt-0.5 truncate">{sub}</p>}
        </div>
        <div className="flex items-center gap-0.5 flex-shrink-0" onClick={e => e.stopPropagation()}>
          {tieneTablaAlt(widget.tipo) && datos && !datos.error && !vacio(widget, datos) && (
            <button type="button" onClick={() => setVerTabla(v => !v)} aria-pressed={verTabla} title={verTabla ? 'Ver gráfica' : 'Ver como tabla'}
              className="text-[11px] px-1.5 py-0.5 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100">{verTabla ? 'Gráfica' : 'Tabla'}</button>
          )}
          {editando && (
            <>
              <button type="button" onClick={onDuplicar} title="Duplicar" aria-label="Duplicar gráfica"
                className="text-xs px-1.5 py-0.5 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100">⧉</button>
              <button type="button" onClick={onEliminar} title="Eliminar" aria-label="Eliminar gráfica"
                className="text-xs px-1.5 py-0.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50">🗑</button>
            </>
          )}
        </div>
      </header>

      <div className="flex-1 min-h-0">
        {!datos ? <Esqueleto alto={esKpi ? 48 : 200} />
          : datos.error ? <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{datos.error}</p>
          : vacio(widget, datos) ? <p className="text-xs text-gray-400 py-8 text-center">Sin datos con los filtros actuales.</p>
          : verTabla ? <TablaAlternativa widget={widget} datos={datos} />
          : <div className={cargando ? 'opacity-60 transition-opacity' : 'transition-opacity'}><Grafica widget={widget} datos={datos} /></div>}
      </div>
      {datos && !datos.error && datos.advertencia && <p className="text-[11px] text-gray-400 mt-2">{datos.advertencia}</p>}
      {widget.tipo === 'dispersion' && datos && !datos.error && datos.total > 0 && (
        <p className="text-[11px] text-gray-400 mt-2">
          {datos.correlacion !== null && <>Correlación r = {fmtNum(datos.correlacion)} · </>}
          {datos.muestra < datos.total ? `muestra de ${fmtNum(datos.muestra)} de ${fmtNum(datos.total)} puntos` : `${fmtNum(datos.total)} puntos`}
        </p>
      )}
      {datos && !datos.error && widget.tipo === 'histograma' && datos.media !== undefined && (
        <p className="text-[11px] text-gray-400 mt-2">Media {fmtNum(datos.media)} · Mediana {fmtNum(datos.mediana)} · {fmtNum(datos.n)} filas</p>
      )}
    </section>
  )
}

export default function DashboardEditor() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [info, setInfo] = useState(null)             // respuesta de GET /dashboard
  const [error, setError] = useState('')
  const [config, setConfig] = useState(null)         // lo que se ve (guardado + cambios sin guardar)
  const base = useRef('')                              // JSON de lo último guardado/cargado
  const [resultado, setResultado] = useState(null)
  const [calculando, setCalculando] = useState(false)
  const [errorCalc, setErrorCalc] = useState('')
  const [editando, setEditando] = useState(false)
  const [sel, setSel] = useState(null)
  const [agregando, setAgregando] = useState(false)
  const [nombrando, setNombrando] = useState(null)   // 'nueva' | 'renombrar' | null
  const [nombre, setNombre] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [aviso, setAviso] = useState('')
  const arrastrando = useRef(null)

  const cargar = useCallback(async (vista) => {
    setError('')
    try {
      const r = await api.get(`/datasets/${id}/dashboard`, { params: vista ? { vista } : {} })
      setInfo(r.data); setConfig(r.data.config); base.current = JSON.stringify(r.data.config)
      setResultado(null); setSel(null)
    } catch (e) { setError(msg(e, 'No se pudo abrir el dashboard')) }
  }, [id])
  useEffect(() => { setInfo(null); setEditando(false); cargar() }, [cargar])

  const sucio = !!config && JSON.stringify(config) !== base.current
  const esMio = info?.archivo.es_mio
  const columnas = info?.columnas || []

  // Recalcula (con retraso corto) cada vez que cambia la configuración
  const cuenta = useRef(0)
  useEffect(() => {
    if (!config) return
    const n = ++cuenta.current
    setCalculando(true)
    const t = setTimeout(async () => {
      try {
        const r = await api.post(`/datasets/${id}/dashboard/datos`, { config })
        if (n !== cuenta.current) return
        setResultado(r.data); setErrorCalc('')
      } catch (e) {
        if (n === cuenta.current) setErrorCalc(msg(e, 'No se pudieron calcular las gráficas'))
      } finally { if (n === cuenta.current) setCalculando(false) }
    }, resultado ? 350 : 0)
    return () => clearTimeout(t)
  }, [config, id])

  useEffect(() => {
    if (!sucio) return
    const f = (e) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', f)
    return () => window.removeEventListener('beforeunload', f)
  }, [sucio])

  const confirmarSalida = () => !sucio || window.confirm('Tienes cambios sin guardar. ¿Descartarlos?')
  const avisar = (t) => { setAviso(t); setTimeout(() => setAviso(''), 3500) }

  const cambiarWidgets = (fn) => setConfig(c => ({ ...c, widgets: fn(c.widgets) }))
  const patchWidget = (wid, patch) => cambiarWidgets(ws => ws.map(w => w.id === wid ? actualizarWidget(w, patch) : w))
  const reemplazarWidget = (nuevo) => cambiarWidgets(ws => ws.map(w => w.id === nuevo.id ? nuevo : w))
  const eliminar = (wid) => { cambiarWidgets(ws => ws.filter(w => w.id !== wid)); setSel(s => s === wid ? null : s) }
  const duplicar = (wid) => {
    const copia = { ...config.widgets.find(w => w.id === wid), id: nuevoId() }
    copia.titulo = `${copia.titulo} (copia)`.slice(0, 80)
    cambiarWidgets(ws => { const i = ws.findIndex(w => w.id === wid); return [...ws.slice(0, i + 1), copia, ...ws.slice(i + 1)] })
    setSel(copia.id)
  }
  const mover = (wid, d) => cambiarWidgets(ws => {
    const i = ws.findIndex(w => w.id === wid), j = i + d
    if (j < 0 || j >= ws.length) return ws
    const c = [...ws]; [c[i], c[j]] = [c[j], c[i]]; return c
  })
  const agregar = (tipo) => {
    const w = widgetNuevo(tipo, columnas)
    cambiarWidgets(ws => [...ws, w]); setSel(w.id); setAgregando(false)
    setTimeout(() => document.getElementById(`w-${w.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100)
  }

  const guardar = async () => {
    setGuardando(true)
    try {
      let r
      if (info.vista.id) r = await api.put(`/datasets/${id}/dashboard/${info.vista.id}`, { config })
      else r = await api.post(`/datasets/${id}/dashboard`, { nombre: 'Resumen', config })
      const cfg = r.data.config || config
      base.current = JSON.stringify(cfg); setConfig(cfg)
      const vid = info.vista.id || r.data.id
      setInfo(i => ({ ...i, vista: { id: vid, nombre: r.data.nombre || i.vista.nombre, guardada: true },
        vistas: i.vista.id ? i.vistas : [...i.vistas, { id: vid, nombre: r.data.nombre }] }))
      avisar('Cambios guardados')
    } catch (e) { avisar(msg(e, 'No se pudo guardar')) } finally { setGuardando(false) }
  }
  const descartar = () => { setConfig(JSON.parse(base.current)); setSel(null) }

  const enviarNombre = async (e) => {
    e.preventDefault()
    try {
      if (nombrando === 'nueva') {
        const r = await api.post(`/datasets/${id}/dashboard`, { nombre, config })
        base.current = JSON.stringify(r.data.config)
        setInfo(i => ({ ...i, vista: { id: r.data.id, nombre: r.data.nombre, guardada: true }, vistas: [...i.vistas, { id: r.data.id, nombre: r.data.nombre }] }))
        setConfig(r.data.config)
      } else {
        await api.put(`/datasets/${id}/dashboard/${info.vista.id}`, { nombre })
        setInfo(i => ({ ...i, vista: { ...i.vista, nombre }, vistas: i.vistas.map(v => v.id === i.vista.id ? { ...v, nombre } : v) }))
      }
      setNombrando(null); setNombre('')
    } catch (er) { avisar(msg(er, 'No se pudo guardar el nombre')) }
  }
  const borrarVista = async () => {
    if (!window.confirm(`¿Eliminar la vista «${info.vista.nombre}»?`)) return
    try { await api.delete(`/datasets/${id}/dashboard/${info.vista.id}`); await cargar(); avisar('Vista eliminada') }
    catch (e) { avisar(msg(e, 'No se pudo eliminar')) }
  }
  const cambiarVista = (v) => { if (!confirmarSalida()) return; cargar(v || undefined) }

  const dnd = (w, i) => ({
    onDragStart: (e) => { arrastrando.current = w.id; e.dataTransfer.effectAllowed = 'move' },
    onDragOver: (e) => { if (arrastrando.current && arrastrando.current !== w.id) e.preventDefault() },
    onDrop: (e) => {
      e.preventDefault()
      const de = arrastrando.current; arrastrando.current = null
      if (!de || de === w.id) return
      cambiarWidgets(ws => {
        const from = ws.findIndex(x => x.id === de); const c = [...ws]; const [it] = c.splice(from, 1)
        c.splice(ws.findIndex(x => x.id === w.id), 0, it); return c
      })
    },
    onDragEnd: () => { arrastrando.current = null },
  })

  const widgetSel = useMemo(() => config?.widgets.find(w => w.id === sel) || null, [config, sel])
  const tieneFechas = columnas.some(c => c.rol === 'fecha')

  if (error) return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="card max-w-sm text-center">
        <p className="text-sm text-gray-700">{error}</p>
        <Link to="/archivos" className="btn-ghost justify-center mt-3 text-xs">← Mis archivos</Link>
      </div>
    </div>
  )
  if (!info || !config) return (
    <div className="flex-1 flex items-center justify-center"><div className="w-6 h-6 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" /></div>
  )

  return (
    <div className="flex-1 flex overflow-hidden min-w-0">
      {agregando && <AgregarGrafica columnas={columnas} onElegir={agregar} onCerrar={() => setAgregando(false)} />}

      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto md:overflow-hidden">
        <header className="bg-white border-b border-gray-100 px-4 md:px-6 py-3">
          <p className="text-xs text-gray-400">
            <Link to="/archivos" onClick={e => { if (!confirmarSalida()) e.preventDefault() }} className="hover:text-gray-600">Archivos</Link>
            {' / '}<span title={info.archivo.nombre}>{info.archivo.nombre}</span>
            {' · '}{fmtNum(info.archivo.filas)} filas
          </p>
          <div className="flex items-center justify-between gap-3 flex-wrap mt-1">
            <div className="flex items-center gap-2 flex-wrap min-w-0">
              {nombrando ? (
                <form onSubmit={enviarNombre} className="flex items-center gap-2">
                  <input autoFocus className="input py-1.5 text-sm w-48" value={nombre} onChange={e => setNombre(e.target.value)} maxLength={40}
                    placeholder={nombrando === 'nueva' ? 'Nombre de la vista nueva' : 'Nuevo nombre'} aria-label="Nombre de la vista" />
                  <button className="btn-primary text-xs py-1.5" type="submit">Guardar</button>
                  <button className="btn-ghost text-xs" type="button" onClick={() => setNombrando(null)}>Cancelar</button>
                </form>
              ) : (
                <>
                  <h1 className="text-base font-semibold text-gray-900">Dashboard</h1>
                  <label className="flex items-center gap-1.5 text-xs text-gray-500">
                    Vista:
                    <select value={info.vista.id ?? ''} onChange={e => cambiarVista(e.target.value)} aria-label="Vista"
                      className="text-sm border border-gray-200 rounded-lg px-2 py-1 bg-white text-gray-800">
                      {!info.vista.guardada && <option value="">{info.vista.nombre}</option>}
                      {info.vistas.map(v => <option key={v.id} value={v.id}>{v.nombre}</option>)}
                    </select>
                  </label>
                  {esMio && editando && (
                    <>
                      <button type="button" className="btn-ghost text-xs" onClick={() => { setNombrando('nueva'); setNombre('') }}>+ Nueva vista</button>
                      {info.vista.guardada && <button type="button" className="btn-ghost text-xs" onClick={() => { setNombrando('renombrar'); setNombre(info.vista.nombre) }}>Renombrar</button>}
                      {info.vista.guardada && <button type="button" className="btn-ghost text-xs text-red-500 hover:bg-red-50" onClick={borrarVista}>Eliminar vista</button>}
                    </>
                  )}
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              {aviso && <span role="status" className="text-xs text-green-700 bg-green-50 rounded-lg px-2.5 py-1">{aviso}</span>}
              {sucio && esMio && (
                <>
                  <span className="text-xs text-amber-700">Cambios sin guardar</span>
                  <button className="btn-ghost text-xs" onClick={descartar}>Descartar</button>
                  <button className="btn-primary text-xs py-1.5" onClick={guardar} disabled={guardando}>{guardando ? 'Guardando…' : 'Guardar'}</button>
                </>
              )}
              {sucio && !esMio && <button className="btn-ghost text-xs" onClick={descartar}>Restablecer filtros</button>}
              {esMio && editando && (
                <button className="btn-ghost text-xs border border-gray-200" onClick={() => setAgregando(true)}>+ Agregar gráfica</button>
              )}
              {esMio && (
                <button type="button" onClick={() => { setEditando(e => !e); setSel(null) }} aria-pressed={editando}
                  className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ` +
                    (editando ? 'bg-brand-600 border-brand-600 text-white' : 'border-gray-200 text-gray-700 hover:bg-gray-50')}>
                  {editando ? 'Terminar edición' : 'Modo edición'}
                </button>
              )}
              <Link to={`/datos/${id}`} className="btn-ghost text-xs">Ver datos</Link>
            </div>
          </div>
        </header>

        {/* Filtros globales */}
        <div className="bg-white border-b border-gray-100 px-4 md:px-6 py-2.5 flex items-start gap-4 flex-wrap">
          <div className="flex-1 min-w-[240px]">
            <ListaFiltros archivoId={id} columnas={columnas} filtros={config.filtros} onChange={f => setConfig(c => ({ ...c, filtros: f }))} />
          </div>
          {tieneFechas && (
            <div role="group" aria-label="Granularidad de fechas" className="flex bg-gray-100 rounded-lg p-0.5">
              {GRANOS.map(g => (
                <button key={g.v} type="button" aria-pressed={config.grano === g.v} onClick={() => setConfig(c => ({ ...c, grano: g.v }))}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium ${config.grano === g.v ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>{g.l}</button>
              ))}
            </div>
          )}
          {resultado && (
            <p className="text-xs text-gray-400 py-1.5 whitespace-nowrap" aria-live="polite">
              {resultado.filas_filtradas === resultado.filas_total ? `${fmtNum(resultado.filas_total)} filas` : `${fmtNum(resultado.filas_filtradas)} de ${fmtNum(resultado.filas_total)} filas`}
            </p>
          )}
        </div>

        <main className="md:flex-1 md:overflow-y-auto p-4 md:p-6">
          {errorCalc && <p role="alert" className="mb-4 text-sm text-red-700 bg-red-50 rounded-lg px-4 py-2.5">{errorCalc}</p>}
          {!info.vista.guardada && (
            <p className="mb-4 text-xs text-gray-600 bg-brand-50 rounded-lg px-4 py-2.5">
              {esMio
                ? 'Propuesta automática según el tipo de cada columna. Entra a «Modo edición» para ajustarla y guárdala para conservarla.'
                : 'Propuesta automática según las columnas del archivo.'}
            </p>
          )}
          {!esMio && <p className="mb-4 text-xs text-gray-500">Compartido contigo en solo lectura. Puedes filtrar para explorar; los cambios no se guardan.</p>}

          {config.widgets.length === 0 ? (
            <div className="card text-center py-14">
              <p className="text-sm text-gray-600">Este dashboard no tiene gráficas.</p>
              {esMio && <button className="btn-primary mx-auto mt-3 text-xs" onClick={() => { setEditando(true); setAgregando(true) }}>Agregar la primera gráfica</button>}
            </div>
          ) : (
            <div className="grid grid-cols-12 gap-4">
              {config.widgets.map((w, i) => (
                <div key={w.id} id={`w-${w.id}`} className={`contents`}>
                  <Tarjeta widget={w} datos={resultado?.widgets?.[w.id]} cargando={calculando} editando={editando} seleccionada={sel === w.id}
                    onSeleccionar={() => setSel(w.id)} onDuplicar={() => duplicar(w.id)} onEliminar={() => eliminar(w.id)} dnd={dnd(w, i)} />
                </div>
              ))}
            </div>
          )}
        </main>
      </div>

      {editando && widgetSel && (
        <PanelConfig widget={widgetSel} columnas={columnas} archivoId={id}
          onCambio={patch => patchWidget(widgetSel.id, patch)} onReemplazar={reemplazarWidget}
          onDuplicar={() => duplicar(widgetSel.id)} onEliminar={() => eliminar(widgetSel.id)}
          onMover={d => mover(widgetSel.id, d)}
          puedeSubir={config.widgets[0]?.id !== widgetSel.id} puedeBajar={config.widgets[config.widgets.length - 1]?.id !== widgetSel.id}
          onCerrar={() => setSel(null)} />
      )}
    </div>
  )
}
