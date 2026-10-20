import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useParams, Link, useNavigate, useLocation } from 'react-router-dom'
import api from '@/shared/api'
import PageHeader from '@/shared/components/PageHeader'
import Cargando from '@/shared/components/Cargando'
import { usePrincipal } from '@/features/dashboard/PrincipalContext'
import { Grafica, TablaAlternativa, vacio } from '@/features/dashboard/components/Graficas'
import PanelConfig from '@/features/dashboard/components/PanelConfig'
import AgregarGrafica from '@/features/dashboard/components/AgregarGrafica'
import ListaFiltros from '@/features/dashboard/components/Filtros'
import Notas from '@/features/dashboard/components/Notas'
import useTablero from '@/features/dashboard/lib/useTablero'
import { CLASE_ANCHO, GRANOS, TIPOS, widgetNuevo, actualizarWidget, subtituloWidget, fmtNum, nuevoId } from '@/features/dashboard/lib/dash'

const tieneTablaAlt = (t) => ['linea', 'area', 'barras', 'dona', 'pareto', 'histograma', 'calor', 'mapa'].includes(t)
const msg = (e, def) => (typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : def)

function Esqueleto({ alto = 200 }) {
  return <div className="animate-pulse bg-gray-100 rounded-lg" style={{ height: alto }} aria-label="Cargando gráfica" />
}

function Tarjeta({ widget, datos, cargando, editando, seleccionada, levantada, refTarjeta, onAsa, onTecladoAsa, onSeleccionar, onDuplicar, onEliminar }) {
  const [verTabla, setVerTabla] = useState(false)
  const esKpi = widget.tipo === 'kpi'
  const sub = subtituloWidget(widget)
  return (
    <section
      ref={refTarjeta}
      className={`card relative flex flex-col flex-1 min-w-0 ` +
        (esKpi ? 'p-4 ' : '') +
        (editando && !levantada ? 'cursor-pointer hover:border-brand-300 ' : '') +
        (levantada ? 'z-30 shadow-2xl ring-2 ring-brand-500 border-brand-500 cursor-grabbing select-none ' : '') +
        (seleccionada && !levantada ? 'ring-2 ring-brand-500 border-brand-500 ' : '')}
      aria-label={widget.titulo || TIPOS[widget.tipo].l}
      aria-grabbed={editando ? levantada : undefined}
      onClick={editando ? onSeleccionar : undefined}
    >
      <header className="flex items-start justify-between gap-2 mb-2">
        {editando && (
          <button type="button" onPointerDown={onAsa} onKeyDown={onTecladoAsa} onClick={e => e.stopPropagation()}
            className="-ml-1.5 mt-0.5 px-1 py-0.5 rounded text-gray-300 hover:text-gray-600 hover:bg-gray-100 cursor-grab active:cursor-grabbing touch-none flex-shrink-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            title="Arrastra para reordenar (o usa las flechas ↑ ↓ del teclado)" aria-label={`Reordenar «${widget.titulo || TIPOS[widget.tipo].l}»: arrastra o usa las flechas arriba y abajo`}>
            <svg width="14" height="18" viewBox="0 0 14 18" fill="currentColor" aria-hidden="true">
              {[3, 9, 15].map(y => <g key={y}><circle cx="3.5" cy={y} r="1.5" /><circle cx="10.5" cy={y} r="1.5" /></g>)}
            </svg>
          </button>
        )}
        <div className="min-w-0 flex-1">
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
      <Notas widget={widget} datos={datos} />
    </section>
  )
}

export default function DashboardEditor({ archivoId, vistaInicial, esInicio = false }) {
  const { id: idRuta } = useParams()
  const id = archivoId ?? idRuta
  const { principal, fijar, quitar } = usePrincipal()
  const navigate = useNavigate()
  const location = useLocation()
  // Al volver de «Exportar» llegan los cambios sin guardar que se tenían (se usan una sola vez)
  const pendiente = useRef(location.state?.configPendiente ? location.state : null)
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
  const reordenarRef = useRef(null)
  const claveLayout = config ? config.widgets.map(w => `${w.id}:${w.ancho}`).join('|') : ''
  const tablero = useTablero(claveLayout, (de, a) => reordenarRef.current?.(de, a))

  const cargar = useCallback(async (vista) => {
    setError('')
    try {
      const r = await api.get(`/datasets/${id}/dashboard`, { params: vista ? { vista } : {} })
      const p = pendiente.current
      pendiente.current = null
      const retomar = p && (p.vista ?? null) === (r.data.vista.guardada ? r.data.vista.id : null)
      setInfo(r.data); setConfig(retomar ? p.configPendiente : r.data.config); base.current = JSON.stringify(r.data.config)
      setResultado(null); setSel(null)
    } catch (e) { setError(msg(e, 'No se pudo abrir el dashboard')) }
  }, [id])
  useEffect(() => { setInfo(null); setEditando(false); cargar(vistaInicial ?? pendiente.current?.vista ?? undefined) }, [cargar, vistaInicial])

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

  // ★ Dashboard principal: el que se abre al entrar. Es una preferencia de cada usuario (también para archivos compartidos).
  const vistaActual = info?.vista?.guardada ? info.vista.id : null
  const esPrincipal = !!principal && String(principal.archivo_id) === String(id) && (principal.vista_id ?? null) === vistaActual
  const alternarPrincipal = async () => {
    try {
      if (esPrincipal) { await quitar(); avisar('Ya no es tu dashboard principal') }
      else { await fijar(id, vistaActual); avisar('Listo: este dashboard se mostrará al entrar') }
    } catch (e) { avisar(msg(e, 'No se pudo cambiar el dashboard principal')) }
  }

  const confirmarSalida = () => !sucio || window.confirm('Tienes cambios sin guardar. ¿Descartarlos?')
  const avisar = (t) => { setAviso(t); setTimeout(() => setAviso(''), 3500) }

  // Toda alteración de la lista pasa por aquí: se mide antes para animar el cambio
  const cambiarWidgets = (fn) => { tablero.instantanea(); setConfig(c => ({ ...c, widgets: fn(c.widgets) })) }
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

  // Arrastre: la tarjeta `de` pasa a ocupar el lugar de la tarjeta `a`
  reordenarRef.current = (de, a) => cambiarWidgets(ws => {
    const from = ws.findIndex(x => x.id === de), to = ws.findIndex(x => x.id === a)
    if (from < 0 || to < 0 || from === to) return ws
    const c = [...ws]; const [it] = c.splice(from, 1); c.splice(to, 0, it); return c
  })
  const tecladoAsa = (wid) => (e) => {
    if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') { e.preventDefault(); mover(wid, -1) }
    else if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); mover(wid, 1) }
  }

  const widgetSel = useMemo(() => config?.widgets.find(w => w.id === sel) || null, [config, sel])
  const tieneFechas = columnas.some(c => c.rol === 'fecha')

  if (error) return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="card max-w-sm text-center">
        <p className="text-sm text-gray-700">{error}</p>
        <Link to={esInicio ? '/resumen' : '/archivos'} className="btn-ghost justify-center mt-3 text-xs">{esInicio ? 'Ir al resumen' : '← Mis archivos'}</Link>
      </div>
    </div>
  )
  if (!info || !config) return (
    <Cargando />
  )

  return (
    <div className="flex-1 flex overflow-hidden min-w-0">
      {agregando && <AgregarGrafica columnas={columnas} onElegir={agregar} onCerrar={() => setAgregando(false)} />}

      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto md:overflow-hidden">
        <PageHeader
          migas={[
            { texto: 'Archivos', to: '/archivos', onClick: e => { if (!confirmarSalida()) e.preventDefault() } },
            { texto: `${info.archivo.nombre} · ${fmtNum(info.archivo.filas)} filas` },
          ]}
          titulo={
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
                  <h1 className="text-base font-semibold text-gray-900">{esInicio ? 'Inicio' : 'Dashboard'}</h1>
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
                      {info.vista.guardada && <button type="button" className="btn-danger text-xs" onClick={borrarVista}>Eliminar vista</button>}
                    </>
                  )}
                </>
              )}
            </div>
          }
          acciones={<>
              {aviso && <span role="status" className="text-xs text-green-700 bg-green-50 rounded-lg px-2.5 py-1">{aviso}</span>}
              {sucio && esMio && (
                <>
                  <span className="text-xs text-amber-700 whitespace-nowrap">Cambios sin guardar</span>
                  <button className="btn-ghost text-xs" onClick={descartar}>Descartar</button>
                  <button className="btn-primary text-xs py-1.5" onClick={guardar} disabled={guardando}>{guardando ? 'Guardando…' : 'Guardar'}</button>
                </>
              )}
              {sucio && !esMio && <button className="btn-ghost text-xs" onClick={descartar}>Restablecer filtros</button>}
              <button type="button" onClick={alternarPrincipal} aria-pressed={esPrincipal}
                title={esPrincipal ? 'Es tu dashboard principal; clic para quitarlo' : 'Mostrar este dashboard al entrar'}
                className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors flex items-center gap-1.5 whitespace-nowrap ` +
                  (esPrincipal ? 'border-amber-300 bg-amber-50 text-amber-800' : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50 hover:border-gray-300')}>
                <span aria-hidden="true">{esPrincipal ? '★' : '☆'}</span>{esPrincipal ? 'Principal' : 'Hacer principal'}
              </button>
              {esMio && editando && (
                <button className="btn-secondary text-xs" onClick={() => setAgregando(true)}>+ Agregar gráfica</button>
              )}
              {esMio && (
                <button type="button" onClick={() => { setEditando(e => !e); setSel(null) }} aria-pressed={editando}
                  className={`text-xs font-medium px-3 py-1.5 rounded-lg border transition-colors ` +
                    (editando ? 'bg-brand-600 border-brand-600 text-white' : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50 hover:border-gray-300')}>
                  {editando ? 'Terminar edición' : 'Modo edición'}
                </button>
              )}
              <button type="button" className="btn-secondary text-xs" title="Descargar como imagen, PDF, PowerPoint, Excel o CSV"
                onClick={() => navigate(`/datos/${id}/exportar${vistaActual ? `?vista=${vistaActual}` : ''}`, { state: { config, vista: vistaActual } })}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" /></svg>
                Exportar
              </button>
              <Link to={`/datos/${id}`} className="btn-ghost text-xs">Ver datos</Link>
          </>} />

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
            <div ref={tablero.rejilla} className="grid grid-cols-12 gap-4">
              {config.widgets.map(w => {
                const levantada = tablero.arrastrando === w.id
                return (
                  <div key={w.id} id={`w-${w.id}`} ref={tablero.caja(w.id)}
                    className={`relative flex col-span-12 ${CLASE_ANCHO[w.ancho] || CLASE_ANCHO[6]} ${levantada ? 'z-30' : ''}`}>
                    {levantada && <div aria-hidden="true" className="absolute inset-0 rounded-xl border-2 border-dashed border-brand-300 bg-brand-50/60" />}
                    <Tarjeta widget={w} datos={resultado?.widgets?.[w.id]} cargando={calculando} editando={editando} seleccionada={sel === w.id}
                      levantada={levantada} refTarjeta={tablero.tarjeta(w.id)} onAsa={e => tablero.iniciar(e, w.id)} onTecladoAsa={tecladoAsa(w.id)}
                      onSeleccionar={() => setSel(w.id)} onDuplicar={() => duplicar(w.id)} onEliminar={() => eliminar(w.id)} />
                  </div>
                )
              })}
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
