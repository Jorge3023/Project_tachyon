import { useState, useEffect, useRef, useMemo } from 'react'
import { useParams, useSearchParams, useLocation, useNavigate, Link } from 'react-router-dom'
import api from '../services/api'
import ListaFiltros from '../components/dash/Filtros'
import TarjetaFija from '../components/dash/TarjetaFija'
import { GRANOS, TIPOS, TINTA, fmtNum } from '../lib/dash'
import * as X from '../lib/exportar'

const FONDO = '#f8f8f6'
const MAX_XLSX = 50000, MAX_CSV = 500000      // los mismos topes del servidor

const FORMATOS = [
  { v: 'png',  sello: 'PNG',  l: 'Imagen',     d: 'Para chats, correos y documentos' },
  { v: 'pdf',  sello: 'PDF',  l: 'PDF',        d: 'Para imprimir o enviar' },
  { v: 'pptx', sello: 'PPTX', l: 'PowerPoint', d: 'Diapositivas listas para presentar' },
  { v: 'xlsx', sello: 'XLSX', l: 'Excel',      d: 'Datos filtrados y números de cada gráfica' },
  { v: 'csv',  sello: 'CSV',  l: 'CSV',        d: 'Solo los datos filtrados' },
]
const EXT = { png: 'png', pdf: 'pdf', pptx: 'pptx', xlsx: 'xlsx', csv: 'csv' }

function Segmentos({ nombre, etiqueta, valor, opciones, onChange }) {
  return (
    <div>
      <p className="text-xs text-gray-500 mb-1">{etiqueta}</p>
      <div role="radiogroup" aria-label={etiqueta} className="flex bg-gray-100 rounded-lg p-0.5">
        {opciones.map(o => (
          <label key={o.v} className="flex-1 cursor-pointer">
            <input type="radio" name={nombre} className="sr-only peer" checked={valor === o.v} onChange={() => onChange(o.v)} />
            <span className="block text-center text-xs font-medium px-2 py-1.5 rounded-md text-gray-500 hover:text-gray-700 peer-checked:bg-white peer-checked:text-gray-900 peer-checked:shadow-sm peer-focus-visible:ring-2 peer-focus-visible:ring-brand-500">
              {o.l}
            </span>
          </label>
        ))}
      </div>
    </div>
  )
}

function Casilla({ marcada, onChange, children, detalle }) {
  return (
    <label className="flex items-start gap-2 text-sm text-gray-700 cursor-pointer">
      <input type="checkbox" checked={marcada} onChange={e => onChange(e.target.checked)} className="mt-0.5 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
      <span>{children}{detalle && <span className="block text-xs text-gray-400">{detalle}</span>}</span>
    </label>
  )
}

export default function Exportar() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const vistaParam = params.get('vista') || undefined
  const desdeEditor = location.state?.config ? location.state : null      // cambios sin guardar del editor

  const [info, setInfo] = useState(null)
  const [error, setError] = useState('')
  const [config, setConfig] = useState(null)
  const [resultado, setResultado] = useState(null)
  const [calculando, setCalculando] = useState(false)
  const [excluidas, setExcluidas] = useState(() => new Set())
  const [formato, setFormato] = useState('png')
  const [opc, setOpc] = useState({
    pngModo: 'uno', nitidez: 2, encabezado: true,
    pdfTam: 'letter', pdfOri: 'horizontal',
    pptModo: 'agrupar', pptPortada: true,
    xDatos: true, xGraficas: true,
  })
  const poner = (k) => (v) => setOpc(o => ({ ...o, [k]: v }))
  const [ocupado, setOcupado] = useState(false)
  const [progreso, setProgreso] = useState('')
  const [fallo, setFallo] = useState('')
  const [listo, setListo] = useState('')

  const lienzo = useRef(null)
  const rejilla = useRef(null)
  const marco = useRef(null)
  const [anchoMarco, setAnchoMarco] = useState(900)
  const [altoLienzo, setAltoLienzo] = useState(0)

  // 1) Cargar la vista (con los cambios sin guardar del editor, si venimos de él)
  useEffect(() => {
    let vivo = true
    setInfo(null); setError('')
    api.get(`/datasets/${id}/dashboard`, { params: vistaParam ? { vista: vistaParam } : {} })
      .then(r => {
        if (!vivo) return
        const mismaVista = desdeEditor && (desdeEditor.vista ?? null) === (r.data.vista.guardada ? r.data.vista.id : null)
        setInfo(r.data); setConfig(mismaVista ? desdeEditor.config : r.data.config)
      })
      .catch(e => vivo && setError(typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : 'No se pudo abrir el dashboard'))
    return () => { vivo = false }
  }, [id, vistaParam])      // eslint-disable-line react-hooks/exhaustive-deps

  // 2) Calcular las gráficas (con retraso corto cuando se cambian filtros)
  const cuenta = useRef(0)
  useEffect(() => {
    if (!config) return
    const n = ++cuenta.current
    setCalculando(true)
    const t = setTimeout(async () => {
      try {
        const r = await api.post(`/datasets/${id}/dashboard/datos`, { config })
        if (n === cuenta.current) { setResultado(r.data); setFallo('') }
      } catch (e) {
        if (n === cuenta.current) setFallo(typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : 'No se pudieron calcular las gráficas')
      } finally { if (n === cuenta.current) setCalculando(false) }
    }, resultado ? 350 : 0)
    return () => clearTimeout(t)
  }, [config, id])          // eslint-disable-line react-hooks/exhaustive-deps

  const columnas = info?.columnas || []
  const tieneFechas = columnas.some(c => c.rol === 'fecha')
  const todas = config?.widgets || []
  const elegidas = useMemo(() => todas.filter(w => !excluidas.has(w.id)), [todas, excluidas])
  const esRender = formato === 'png' || formato === 'pdf' || formato === 'pptx'
  const ancho = formato === 'pdf' && opc.pdfOri === 'vertical' ? 900 : 1200

  // Título y líneas de contexto (las mismas en la imagen, el PDF y la portada de PowerPoint)
  const stem = (info?.archivo.nombre || '').replace(/\.[A-Za-z0-9]{1,5}$/, '')
  const nombreVista = info?.vista.guardada ? info.vista.nombre : ''
  const titulo = nombreVista ? `${stem} — ${nombreVista}` : stem
  const filtros = X.describirFiltros(config)
  const filtradas = resultado?.filas_filtradas, total = resultado?.filas_total
  const lineas = [
    filtros.length ? `Filtros: ${filtros.join(' · ')}` : 'Sin filtros',
    `${resultado ? `${fmtNum(filtradas)} filas${filtradas < total ? ` de ${fmtNum(total)}` : ''} · ` : ''}${X.fechaLarga()}`,
  ]
  const conEncabezado = opc.encabezado && (formato === 'pdf' || (formato === 'png' && opc.pngModo === 'uno'))

  // Escala de la vista previa: el lienzo mide `ancho` px y se encoge para caber en pantalla
  useEffect(() => {
    if (!esRender || !marco.current) return
    const ro = new ResizeObserver(([e]) => setAnchoMarco(e.contentRect.width))
    ro.observe(marco.current)
    return () => ro.disconnect()
  }, [esRender, !!info, elegidas.length > 0])
  useEffect(() => {
    if (!esRender || !lienzo.current) return
    const ro = new ResizeObserver(([e]) => setAltoLienzo(e.target.offsetHeight))
    ro.observe(lienzo.current)
    return () => ro.disconnect()
  }, [esRender, !!info, elegidas.length > 0])
  const escala = Math.min(1, anchoMarco / ancho)

  const rejillaJsx = useMemo(() => (
    <div ref={rejilla} style={{ display: 'grid', gridTemplateColumns: 'repeat(12, minmax(0, 1fr))', gap: 16, position: 'relative' }}>
      {elegidas.map(w => (
        <div key={w.id} data-wid={w.id} data-titulo={w.titulo || TIPOS[w.tipo].l} className="flex min-w-0"
          style={{ gridColumn: `span ${[3, 4, 6, 8, 12].includes(w.ancho) ? w.ancho : 6}` }}>
          <TarjetaFija widget={w} datos={resultado?.widgets?.[w.id]} />
        </div>
      ))}
    </div>
  ), [elegidas, resultado])

  // ── Exportar ──
  const nombreBase = [stem, nombreVista].filter(Boolean).join('_')
  const idsElegidos = elegidas.map(w => w.id)
  const sinNadaX = formato === 'xlsx' && !opc.xDatos && (!opc.xGraficas || elegidas.every(w => w.tipo === 'tabla'))
  const puedeExportar = !!info && !!resultado && !calculando && !ocupado && !sinNadaX && (!esRender || elegidas.length > 0)

  const exportarServidor = async () => {
    setProgreso(formato === 'xlsx' ? 'Armando el Excel…' : 'Armando el CSV…')
    const r = await X.pedirAlServidor({
      archivoId: id, config, formato, vista: nombreVista,
      datos: formato === 'csv' ? true : opc.xDatos, graficas: formato === 'xlsx' && opc.xGraficas, widgets: idsElegidos,
    })
    X.descargar(r.blob, r.nombre)
    setListo(`${r.nombre} descargado · ${fmtNum(r.filas)} filas${r.truncada ? `. Se exportaron solo las primeras ${fmtNum(r.filas)}; para todas usa CSV (hasta ${fmtNum(MAX_CSV)}).` : ''}`)
  }

  const exportarVisual = async () => {
    setProgreso('Preparando…')
    const { mapaSinFondo } = await X.esperarListo(lienzo.current)
    await X.prepararCaptura(lienzo.current)
    const nombre = X.nombreArchivo(nombreBase, EXT[formato])
    let resumen = ''
    if (formato === 'png' && opc.pngModo === 'uno') {
      setProgreso('Generando la imagen…')
      const { canvas } = await X.capturar(lienzo.current, { ratio: opc.nitidez, fondo: FONDO })
      X.descargar(await X.aBlob(canvas), nombre)
      resumen = `${nombre} descargado`
    } else {
      const medidos = X.medirItems(rejilla.current)
      const anchoGrid = rejilla.current.offsetWidth
      const items = await X.capturarItems(medidos, { ratio: opc.nitidez, onProgreso: setProgreso })
      if (formato === 'png') {
        setProgreso('Comprimiendo las imágenes…')
        const zip = await X.crearZip(items)
        const n = X.nombreArchivo(nombreBase, 'zip')
        X.descargar(zip, n); resumen = `${n} descargado · ${items.length} imágenes`
      } else if (formato === 'pdf') {
        const r = await X.crearPDF({ items, titulo, lineas, tam: opc.pdfTam, orientacion: opc.pdfOri, encabezado: opc.encabezado, anchoGrid, onProgreso: setProgreso })
        X.descargar(r.blob, nombre); resumen = `${nombre} descargado · ${r.paginas} ${r.paginas === 1 ? 'página' : 'páginas'}`
      } else {
        const r = await X.crearPPTX({ items, titulo, lineas, portada: opc.pptPortada, unaPorDiapositiva: opc.pptModo === 'una', anchoGrid, onProgreso: setProgreso })
        X.descargar(r.blob, nombre); resumen = `${nombre} descargado · ${r.diapositivas} diapositivas`
      }
    }
    setListo(resumen + (mapaSinFondo ? '. El mapa salió sin fondo porque no cargaron sus mosaicos (revisa tu conexión).' : ''))
  }

  const exportar = async () => {
    setFallo(''); setListo(''); setOcupado(true)
    try { await (esRender ? exportarVisual() : exportarServidor()) }
    catch (e) { setFallo(await X.mensajeError(e, e?.message || 'No se pudo exportar')) }
    finally { setOcupado(false); setProgreso('') }
  }

  const volver = () => navigate(`/datos/${id}/dashboard`, { state: desdeEditor ? { configPendiente: desdeEditor.config, vista: desdeEditor.vista } : undefined })

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

  const etiquetaFormato = FORMATOS.find(f => f.v === formato)
  const filasX = filtradas ?? 0
  const tope = formato === 'csv' ? MAX_CSV : MAX_XLSX
  const hojas = ['Resumen', ...(opc.xDatos ? ['Datos'] : []), ...(opc.xGraficas ? elegidas.filter(w => w.tipo !== 'tabla').map(w => w.titulo || TIPOS[w.tipo].l) : [])]

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-w-0">
      <header className="bg-white border-b border-gray-100 px-4 md:px-6 py-3">
        <p className="text-xs text-gray-400 truncate">
          <Link to="/archivos" className="hover:text-gray-600">Archivos</Link>{' / '}
          <button type="button" onClick={volver} className="hover:text-gray-600">Dashboard de {info.archivo.nombre}</button>
        </p>
        <div className="flex items-center justify-between gap-3 flex-wrap mt-1">
          <h1 className="text-base font-semibold text-gray-900">Exportar</h1>
          <div className="flex items-center gap-2 flex-wrap">
            <button type="button" className="btn-ghost text-xs" onClick={volver} disabled={ocupado}>← Volver al dashboard</button>
            <button type="button" className="btn-primary text-sm py-2" onClick={exportar} disabled={!puedeExportar}>
              {ocupado ? 'Exportando…' : `Descargar ${etiquetaFormato.l}${formato === 'png' && opc.pngModo === 'varias' ? ' (ZIP)' : ''}`}
            </button>
          </div>
        </div>
        <div aria-live="polite" className="empty:hidden">
          {ocupado && progreso && <p className="mt-2 text-xs text-brand-700 bg-brand-50 rounded-lg px-3 py-1.5 flex items-center gap-2"><span className="w-3 h-3 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />{progreso}</p>}
          {listo && !ocupado && <p role="status" className="mt-2 text-xs text-green-700 bg-green-50 rounded-lg px-3 py-1.5">{listo}</p>}
        </div>
        {fallo && <p role="alert" className="mt-2 text-xs text-red-700 bg-red-50 rounded-lg px-3 py-1.5">{fallo}</p>}
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="p-4 md:p-6 grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)] items-start">
          <fieldset disabled={ocupado} className="space-y-4 min-w-0 m-0 p-0 border-0">
            <legend className="sr-only">Opciones de exportación</legend>

            <section className="card">
              <h2 className="text-sm font-semibold text-gray-900 mb-3">Formato</h2>
              <div role="radiogroup" aria-label="Formato" className="grid grid-cols-1 gap-2">
                {FORMATOS.map(f => (
                  <label key={f.v} className="cursor-pointer">
                    <input type="radio" name="formato" className="sr-only peer" checked={formato === f.v} onChange={() => { setFormato(f.v); setListo(''); setFallo('') }} />
                    <span className="flex items-center gap-3 border border-gray-200 rounded-lg px-3 py-2 hover:border-gray-300 peer-checked:border-brand-600 peer-checked:bg-brand-50/50 peer-focus-visible:ring-2 peer-focus-visible:ring-brand-500">
                      <span className="w-12 text-center text-[11px] font-semibold tracking-wide rounded-md bg-gray-100 text-gray-600 py-1 flex-shrink-0">{f.sello}</span>
                      <span className="min-w-0"><span className="block text-sm font-medium text-gray-900">{f.l}</span><span className="block text-xs text-gray-500">{f.d}</span></span>
                    </span>
                  </label>
                ))}
              </div>
            </section>

            <section className="card space-y-3">
              <h2 className="text-sm font-semibold text-gray-900">Opciones</h2>
              {formato === 'png' && (
                <>
                  <Segmentos nombre="pngModo" etiqueta="Resultado" valor={opc.pngModo} onChange={poner('pngModo')}
                    opciones={[{ v: 'uno', l: 'Una imagen' }, { v: 'varias', l: 'Una por gráfica (ZIP)' }]} />
                  {opc.pngModo === 'uno' && <Casilla marcada={opc.encabezado} onChange={poner('encabezado')}>Incluir título, filtros y fecha</Casilla>}
                </>
              )}
              {formato === 'pdf' && (
                <>
                  <Segmentos nombre="pdfTam" etiqueta="Tamaño de hoja" valor={opc.pdfTam} onChange={poner('pdfTam')} opciones={[{ v: 'letter', l: 'Carta' }, { v: 'a4', l: 'A4' }]} />
                  <Segmentos nombre="pdfOri" etiqueta="Orientación" valor={opc.pdfOri} onChange={poner('pdfOri')} opciones={[{ v: 'horizontal', l: 'Horizontal' }, { v: 'vertical', l: 'Vertical' }]} />
                  <Casilla marcada={opc.encabezado} onChange={poner('encabezado')}>Incluir título, filtros y fecha</Casilla>
                </>
              )}
              {formato === 'pptx' && (
                <>
                  <Segmentos nombre="pptModo" etiqueta="Distribución" valor={opc.pptModo} onChange={poner('pptModo')}
                    opciones={[{ v: 'agrupar', l: 'Varias por diapositiva' }, { v: 'una', l: 'Una por diapositiva' }]} />
                  <Casilla marcada={opc.pptPortada} onChange={poner('pptPortada')}>Incluir diapositiva de portada</Casilla>
                </>
              )}
              {esRender && (
                <Segmentos nombre="nitidez" etiqueta="Nitidez de las imágenes" valor={opc.nitidez} onChange={poner('nitidez')}
                  opciones={[{ v: 2, l: 'Estándar' }, { v: 3, l: 'Alta' }]} />
              )}
              {formato === 'xlsx' && (
                <>
                  <Casilla marcada={opc.xDatos} onChange={poner('xDatos')} detalle="Las filas que deja el filtro, en la hoja «Datos»">Datos del archivo</Casilla>
                  <Casilla marcada={opc.xGraficas} onChange={poner('xGraficas')} detalle="Una hoja con los números detrás de cada gráfica">Resultados de las gráficas</Casilla>
                </>
              )}
              {formato === 'csv' && <p className="text-xs text-gray-500">Se exportan las filas que deja el filtro. Lleva codificación UTF‑8 con marca, así que Excel muestra bien los acentos.</p>}
            </section>

            {formato !== 'csv' && (
              <section className="card">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-sm font-semibold text-gray-900">Gráficas incluidas</h2>
                  <span className="text-xs text-gray-400">{elegidas.length} de {todas.length}</span>
                </div>
                <div className="flex gap-3 mb-2 text-xs">
                  <button type="button" className="text-brand-600 hover:text-brand-700" onClick={() => setExcluidas(new Set())}>Todas</button>
                  <button type="button" className="text-brand-600 hover:text-brand-700" onClick={() => setExcluidas(new Set(todas.map(w => w.id)))}>Ninguna</button>
                </div>
                <ul className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
                  {todas.map(w => (
                    <li key={w.id}>
                      <Casilla marcada={!excluidas.has(w.id)} onChange={on => setExcluidas(s => { const n = new Set(s); on ? n.delete(w.id) : n.add(w.id); return n })}
                        detalle={TIPOS[w.tipo].l}>{w.titulo || TIPOS[w.tipo].l}</Casilla>
                    </li>
                  ))}
                  {todas.length === 0 && <li className="text-xs text-gray-400">Este dashboard no tiene gráficas.</li>}
                </ul>
              </section>
            )}

            <section className="card">
              <h2 className="text-sm font-semibold text-gray-900 mb-1">Filtros</h2>
              <p className="text-xs text-gray-400 mb-3">
                {desdeEditor ? 'Parten de los que tenías en el editor. ' : ''}Aquí solo afectan esta exportación; no cambian tu dashboard.
              </p>
              <ListaFiltros archivoId={id} columnas={columnas} filtros={config.filtros} onChange={f => setConfig(c => ({ ...c, filtros: f }))} />
              {tieneFechas && (
                <div role="group" aria-label="Granularidad de fechas" className="flex bg-gray-100 rounded-lg p-0.5 mt-3 w-fit">
                  {GRANOS.map(g => (
                    <button key={g.v} type="button" aria-pressed={config.grano === g.v} onClick={() => setConfig(c => ({ ...c, grano: g.v }))}
                      className={`px-2.5 py-1 rounded-md text-xs font-medium ${config.grano === g.v ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>{g.l}</button>
                  ))}
                </div>
              )}
            </section>
          </fieldset>

          <section className="min-w-0" aria-label="Vista previa">
            {esRender ? (
              <>
                <div className="flex items-baseline justify-between mb-2">
                  <h2 className="text-sm font-semibold text-gray-900">Vista previa</h2>
                  <p className="text-xs text-gray-400" aria-live="polite">{calculando ? 'Calculando…' : formato === 'pptx' ? 'Cada fila se acomoda en las diapositivas' : formato === 'pdf' ? 'Cada fila se acomoda en las hojas' : 'Así saldrá la imagen'}</p>
                </div>
                {elegidas.length === 0 ? (
                  <div className="card text-center py-14 text-sm text-gray-500">Elige al menos una gráfica para ver la vista previa.</div>
                ) : (
                  <div ref={marco} className="rounded-xl bg-gray-200/60 p-0 overflow-hidden">
                    <div style={{ width: ancho * escala, height: altoLienzo * escala }}>
                      <div ref={lienzo} inert="" aria-hidden="true"
                        style={{ width: ancho, padding: 24, background: FONDO, transform: `scale(${escala})`, transformOrigin: '0 0', pointerEvents: 'none', color: TINTA.primaria }}>
                        {conEncabezado && (
                          <div style={{ marginBottom: 16 }}>
                            <h2 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>{titulo}</h2>
                            {lineas.map((l, i) => <p key={i} style={{ fontSize: 13, color: TINTA.secundaria, margin: '4px 0 0' }}>{l}</p>)}
                          </div>
                        )}
                        {rejillaJsx}
                      </div>
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="card">
                <h2 className="text-sm font-semibold text-gray-900 mb-3">Qué se va a exportar</h2>
                <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm">
                  <dt className="text-gray-500">Archivo</dt><dd className="text-gray-900 min-w-0 break-words">{info.archivo.nombre}</dd>
                  <dt className="text-gray-500">Filas</dt>
                  <dd className="text-gray-900">{resultado ? <>{fmtNum(filasX)}{filasX < total && <span className="text-gray-400"> de {fmtNum(total)}</span>}</> : '…'}</dd>
                  <dt className="text-gray-500">Filtros</dt><dd className="text-gray-900">{filtros.length ? filtros.join(' · ') : 'Ninguno'}</dd>
                  {formato === 'xlsx' && <><dt className="text-gray-500">Hojas</dt><dd className="text-gray-900 min-w-0 break-words">{hojas.join(' · ')}</dd></>}
                </dl>
                {opc.xDatos || formato === 'csv' ? (
                  filasX > tope && (
                    <p role="note" className="mt-4 text-xs text-amber-800 bg-amber-50 rounded-lg px-3 py-2">
                      Hay {fmtNum(filasX)} filas y el límite de {formato === 'csv' ? 'CSV' : 'Excel'} es {fmtNum(tope)}: se exportarán las primeras {fmtNum(tope)}.
                      {formato === 'xlsx' && ` Para exportar más, usa CSV (hasta ${fmtNum(MAX_CSV)}) o agrega filtros.`}
                    </p>
                  )
                ) : null}
                {sinNadaX && <p role="alert" className="mt-4 text-xs text-red-700 bg-red-50 rounded-lg px-3 py-2">Elige al menos «Datos del archivo» o «Resultados de las gráficas».</p>}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
