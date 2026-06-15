import { useState, useEffect, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import api from '../services/api'

const LINEAS = ['A', 'B', 'C', 'D', 'E']

function EstadoBadge({ estado }) {
  const map = {
    procesado:  'badge-good',
    procesando: 'badge-warn',
    error:      'badge-bad',
    pendiente:  'badge-warn',
  }
  const labels = { procesado:'Procesado', procesando:'Procesando…', error:'Error', pendiente:'Pendiente' }
  return <span className={map[estado] || 'badge-warn'}>{labels[estado] || estado}</span>
}

function ModalConfirmacion({ archivo, linea, onConfirm, onCancel, cargando }) {
  const [pass, setPass] = useState('')
  const [err,  setErr]  = useState('')
  const inputRef = useRef()
  useEffect(() => { setTimeout(() => inputRef.current?.focus(), 50) }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!pass) { setErr('Ingresa tu contraseña'); return }
    setErr('')
    try { await onConfirm(pass) }
    catch (e) { setErr(e.message || 'Contraseña incorrecta') }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-sm shadow-xl">
        <div className="px-6 py-5 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900">Confirmar carga de archivo</h3>
          <p className="text-xs text-gray-400 mt-0.5">Se requiere tu contraseña para registrar esta acción</p>
        </div>
        <div className="px-6 py-4 space-y-3">
          <div className="bg-gray-50 rounded-lg p-3 text-xs space-y-1">
            <p><span className="text-gray-400">Archivo:</span> <span className="font-medium text-gray-700">{archivo}</span></p>
            <p><span className="text-gray-400">Línea:</span>   <span className="font-medium text-gray-700">Línea {linea}</span></p>
          </div>
          <form onSubmit={handleSubmit}>
            <label className="block text-xs text-gray-600 mb-1.5">Tu contraseña</label>
            <input ref={inputRef} type="password" className="input" placeholder="••••••••"
              value={pass} onChange={e => setPass(e.target.value)} />
            {err && <p className="text-xs text-red-600 mt-2">{err}</p>}
            <div className="flex gap-2 mt-4">
              <button type="button" onClick={onCancel}
                className="flex-1 py-2 rounded-lg border border-gray-200 text-sm text-gray-500 hover:bg-gray-50 transition-colors">
                Cancelar
              </button>
              <button type="submit" disabled={cargando}
                className="flex-1 btn-primary justify-center py-2 disabled:opacity-50">
                {cargando ? (
                  <span className="flex items-center gap-2 justify-center">
                    <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"/>
                    Procesando…
                  </span>
                ) : 'Confirmar y cargar'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}

function ResumenCard({ resumen }) {
  if (!resumen) return null
  return (
    <div className="mt-4 p-4 bg-brand-50 rounded-xl border border-brand-100">
      <p className="text-xs font-semibold text-brand-700 mb-3">✓ Análisis completado</p>
      <div className="grid grid-cols-3 gap-2 mb-2">
        {[
          { label:'Registros',      val: resumen.total_registros?.toLocaleString(), color:'text-gray-900' },
          { label:'Piezas OK',      val: resumen.total_passed?.toLocaleString(),    color:'text-green-600' },
          { label:'Piezas Fallidas',val: resumen.total_failed?.toLocaleString(),    color:'text-red-500'  },
        ].map(m => (
          <div key={m.label} className="bg-white rounded-lg p-2.5 text-center">
            <p className={`text-base font-semibold ${m.color}`}>{m.val}</p>
            <p className="text-xs text-gray-400 mt-0.5">{m.label}</p>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[
          { label:'Horas totales',  val: `${resumen.horas_totales?.toFixed(2)}h`,  color:'text-gray-900' },
          { label:'Tiempo muerto',  val: `${resumen.horas_muertas?.toFixed(2)}h`,  color:'text-amber-600' },
          { label:'Horas reales',   val: `${resumen.horas_reales?.toFixed(2)}h`,   color:'text-brand-600' },
        ].map(m => (
          <div key={m.label} className="bg-white rounded-lg p-2.5 text-center">
            <p className={`text-base font-semibold ${m.color}`}>{m.val}</p>
            <p className="text-xs text-gray-400 mt-0.5">{m.label}</p>
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-2 flex-wrap">
        {resumen.linea_produccion && (
          <span className="text-xs text-brand-600 bg-white px-2 py-1 rounded-md border border-brand-100">
            Línea {resumen.linea_produccion}
          </span>
        )}
        <span className="text-xs text-brand-600 bg-white px-2 py-1 rounded-md border border-brand-100">
          {resumen.modelos} modelos
        </span>
        {resumen.fechas?.map(f => (
          <span key={f} className="text-xs text-gray-500 bg-white px-2 py-1 rounded-md border border-gray-100">{f}</span>
        ))}
      </div>
    </div>
  )
}

export default function Archivos() {
  const { usuario } = useAuth()
  const esAdmin     = usuario?.rol === 'admin'

  const [archivos,      setArchivos]      = useState([])
  const [linea,         setLinea]         = useState('A')
  const [archivoSel,    setArchivoSel]    = useState(null)   // archivo pendiente de confirmación
  const [subiendo,      setSubiendo]      = useState(false)
  const [mensaje,       setMensaje]       = useState(null)
  const [ultimoResumen, setUltimoResumen] = useState(null)
  const [descargando,   setDescargando]   = useState(null)
  const inputRef = useRef()

  const cargarLista = () =>
    api.get('/archivos').then(r => setArchivos(r.data)).catch(() => {})

  useEffect(() => { cargarLista() }, [])

  /* El input dispara esto → guardamos el File y mostramos el modal */
  const handleFileSeleccionado = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.match(/\.(xlsx|xls)$/i)) {
      setMensaje({ tipo: 'error', texto: 'Solo se aceptan archivos .xlsx o .xls' })
      return
    }
    e.target.value = ''
    setArchivoSel(file)
  }

  /* El modal llama aquí con la contraseña ya validada */
const handleConfirmar = async (password, fileDirecto = null) => {
  const archivoASubir = fileDirecto || archivoSel
  if (!archivoASubir) {
    setMensaje({ tipo: 'error', texto: 'Selecciona un archivo antes de continuar' })
    return
  }
  setSubiendo(true)
  setMensaje(null)
  setUltimoResumen(null)

  const formData = new FormData()
  formData.append('file', archivoASubir)

  try {
    const res = await api.post(
      `/archivos/upload?linea=${linea}&password_confirmacion=${encodeURIComponent(password)}`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    )
    setMensaje({ tipo: 'ok', texto: res.data.mensaje })
    setUltimoResumen(res.data.resumen)
    setArchivoSel(null)
    cargarLista()
  } catch (err) {
    const detalle = err.response?.data?.detail || 'Error al procesar'
    setMensaje({ tipo: 'error', texto: detalle })
    setArchivoSel(null)
  } finally {
    setSubiendo(false)
  }
}

  const handleDescargar = async (archivo) => {
    setDescargando(archivo.id)
    try {
      const res = await api.get(`/archivos/${archivo.id}/descargar`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data]))
      const a   = Object.assign(document.createElement('a'), {
        href: url, download: archivo.nombre.replace(/\.(xlsx|xls)$/i,'') + '_analisis.xlsx'
      })
      a.click(); URL.revokeObjectURL(url)
    } catch { alert('No se pudo descargar el reporte.') }
    finally  { setDescargando(null) }
  }

  return (
    <>
      {archivoSel && (
        <ModalConfirmacion
          archivo={archivoSel.name}
          linea={linea}
          cargando={subiendo}
          onConfirm={handleConfirmar}
          onCancel={() => setArchivoSel(null)}
        />
      )}

      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="bg-white border-b border-gray-100 px-6 py-4">
          <h1 className="text-base font-semibold text-gray-900">Archivos de producción</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            {esAdmin
              ? 'Carga reportes crudos — la app calcula horas, piezas y tiempo muerto'
              : 'Visualiza y descarga los reportes de análisis'}
          </p>
        </header>

        <main className="flex-1 overflow-y-auto p-6 space-y-5">

          {/* ── Zona de carga (solo admin) ── */}
          {esAdmin && (
            <div className="card">
              <h2 className="text-sm font-semibold text-gray-900 mb-4">Cargar nuevo archivo</h2>

              {/* Selector de línea */}
              <div className="flex items-center gap-3 mb-5">
                <span className="text-xs text-gray-500">Línea</span>
                <div className="flex gap-1.5">
                  {LINEAS.map(l => (
                    <button key={l} onClick={() => setLinea(l)}
                      className={`w-9 h-9 rounded-lg text-sm font-semibold border transition-all ` +
                        (linea === l
                          ? 'bg-brand-600 text-white border-brand-600'
                          : 'bg-white text-gray-500 border-gray-200 hover:border-brand-300')}>
                      {l}
                    </button>
                  ))}
                </div>
              </div>

              <div onClick={() => inputRef.current?.click()}
                className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center
                           cursor-pointer hover:border-brand-400 hover:bg-brand-50/20 transition-all">
                <div className="w-11 h-11 bg-gray-100 rounded-xl flex items-center justify-center mx-auto mb-3">
                  <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
                <p className="text-sm font-medium text-gray-700 mb-1">
                  Seleccionar archivo Excel
                </p>
                <p className="text-xs text-gray-400">
                  .xlsx o .xls — Se pedirá tu contraseña antes de cargar
                </p>
                <input ref={inputRef} type="file" accept=".xlsx,.xls" className="hidden"
                  onChange={handleFileSeleccionado} />
              </div>

              {mensaje && (
                <div className={`mt-4 px-4 py-3 rounded-lg text-sm flex items-start gap-2 ` +
                  (mensaje.tipo === 'ok' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700')}>
                  {mensaje.tipo === 'ok'
                    ? <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                    : <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                  {mensaje.texto}
                </div>
              )}

              <ResumenCard resumen={ultimoResumen} />
            </div>
          )}

          {/* ── Historial ── */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-900">
                {esAdmin ? 'Historial de archivos' : 'Reportes disponibles'}
              </h2>
              <button onClick={cargarLista} className="btn-ghost text-xs">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Actualizar
              </button>
            </div>

            {archivos.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <svg className="w-10 h-10 mx-auto mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-sm">
                  {esAdmin ? 'Aún no hay archivos cargados' : 'No hay reportes disponibles aún'}
                </p>
              </div>
            ) : (
              <div className="divide-y divide-gray-50">
                {archivos.map(a => (
                  <div key={a.id} className="flex items-center gap-4 py-3">
                    <div className="w-8 h-8 bg-green-50 rounded-lg flex items-center justify-center flex-shrink-0">
                      <svg className="w-4 h-4 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                          d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{a.nombre}</p>
                      <p className="text-xs text-gray-400">
                        Línea {a.linea}
                        {a.equipo ? ` · ${a.equipo}` : ''}
                        {` · ${a.filas?.toLocaleString() ?? 0} registros`}
                        {a.subido_por_nombre ? ` · ${a.subido_por_nombre}` : ''}
                        {` · ${new Date(a.subido_en).toLocaleDateString('es-MX')}`}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <EstadoBadge estado={a.estado} />
                      {a.estado === 'procesado' && (
                        <button onClick={() => handleDescargar(a)}
                          disabled={descargando === a.id}
                          className="btn-ghost text-brand-600 hover:text-brand-700 hover:bg-brand-50 text-xs"
                          title="Descargar reporte">
                          {descargando === a.id
                            ? <span className="w-3.5 h-3.5 border-2 border-brand-500 border-t-transparent rounded-full animate-spin block" />
                            : <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                              </svg>}
                          Descargar
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

        </main>
      </div>
    </>
  )
}
