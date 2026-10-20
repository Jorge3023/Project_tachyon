import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '@/features/auth/AuthContext'
import api from '@/shared/api'
import { useProyectos } from '@/features/proyectos/ProyectosContext'
import { usePrincipal } from '@/features/dashboard/PrincipalContext'
import PageHeader from '@/shared/components/PageHeader'
import FilaArchivo from '@/shared/components/FilaArchivo'
import Vacio from '@/shared/components/Vacio'
import Cargando from '@/shared/components/Cargando'

function MetricCard({ label, value, sub, color = 'gray', icon, to }) {
  const colors = {
    blue:   'bg-brand-50 text-brand-600',
    green:  'bg-green-50 text-green-600',
    violet: 'bg-violet-50 text-violet-600',
    gray:   'bg-gray-100 text-gray-500',
  }
  const cuerpo = (
    <>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500">{label}</span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${colors[color]}`}>{icon}</div>
      </div>
      <p className="text-3xl font-semibold text-gray-900 mt-2 tabular-nums">{value ?? '—'}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </>
  )
  return to
    ? <Link to={to} className="metric-card block hover:border-brand-100 hover:shadow-sm transition">{cuerpo}</Link>
    : <div className="metric-card">{cuerpo}</div>
}

const iconoArchivo = (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
)
const iconoFilas = (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
  </svg>
)
const iconoCompartir = (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
  </svg>
)

const iconoCarpeta = (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
  </svg>
)
const saludo = () => { const h = new Date().getHours(); return h < 12 ? 'Buenos días' : h < 19 ? 'Buenas tardes' : 'Buenas noches' }

function Paso({ hecho, titulo, children, accion }) {
  return (
    <li className="flex gap-3">
      <span aria-hidden="true" className={'mt-0.5 w-5 h-5 rounded-full flex items-center justify-center text-[11px] flex-shrink-0 ' +
        (hecho ? 'bg-green-500 text-white' : 'border border-gray-300 text-transparent')}>✓</span>
      <div className="min-w-0">
        <p className={'text-sm font-medium ' + (hecho ? 'text-gray-400 line-through' : 'text-gray-900')}>{titulo}</p>
        <p className="text-xs text-gray-400 mt-0.5">{children}</p>
        {accion}
      </div>
    </li>
  )
}

export default function Resumen() {
  const { usuario } = useAuth()
  const navigate = useNavigate()
  const { proyectos } = useProyectos()
  const { principal } = usePrincipal()
  const [archivos, setArchivos] = useState([])
  const [cargando, setCargando] = useState(true)
  const [error,    setError]    = useState(false)

  useEffect(() => {
    setCargando(true); setError(false)
    api.get('/archivos?origen=todos')
      .then(r => setArchivos(r.data.filter(a => a.estado === 'procesado')))
      .catch(() => setError(true))
      .finally(() => setCargando(false))
  }, [])

  const hoyTxt = new Date().toLocaleDateString('es-MX', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  })
  const hoy = hoyTxt.charAt(0).toUpperCase() + hoyTxt.slice(1)
  const propios      = archivos.filter(a => a.es_mio)
  const compartidos  = archivos.filter(a => !a.es_mio)
  const totalFilas   = archivos.reduce((n, a) => n + (a.filas || 0), 0)
  const recientes    = archivos.slice(0, 6)
  const primerNombre = (usuario?.nombre || '').split(' ')[0]

  const ultimo = propios[0] || recientes[0]
  const resumenTxt = cargando ? '' : archivos.length === 0
    ? 'Sube tu primer Excel o CSV y en un minuto tendrás un dashboard.'
    : `${archivos.length} ${archivos.length === 1 ? 'archivo listo' : 'archivos listos'} para analizar · ${totalFilas.toLocaleString('es-MX')} filas en total.`

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <PageHeader titulo={principal ? 'Resumen' : 'Inicio'} subtitulo={hoy} />

      <main className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5">

        {/* Bienvenida */}
        <section aria-label="Bienvenida" className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-brand-900 via-brand-700 to-brand-600 text-white p-6 md:p-8">
          <div aria-hidden="true" className="absolute -right-16 -top-16 w-64 h-64 rounded-full bg-white/5" />
          <div aria-hidden="true" className="absolute right-24 -bottom-20 w-48 h-48 rounded-full bg-white/5" />
          <div className="relative max-w-2xl">
            <h2 className="text-xl md:text-2xl font-semibold">{saludo()}{primerNombre ? `, ${primerNombre}` : ''}</h2>
            <p className="text-sm text-white/75 mt-1.5 min-h-[1.25rem]">{resumenTxt}</p>
            <div className="flex flex-wrap gap-2 mt-5">
              <button onClick={() => navigate('/archivos')} className="inline-flex items-center gap-2 bg-white text-brand-700 hover:bg-brand-50 font-medium px-4 py-2 rounded-lg text-sm transition-colors">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v12m0-12l-4 4m4-4l4 4M4 20h16" /></svg>
                Subir un archivo
              </button>
              {ultimo && (
                <button onClick={() => navigate(`/datos/${ultimo.id}/dashboard`)} className="inline-flex items-center gap-2 bg-white/10 hover:bg-white/20 border border-white/25 text-white font-medium px-4 py-2 rounded-lg text-sm transition-colors max-w-full">
                  <span className="truncate">Continuar con {ultimo.nombre}</span><span aria-hidden="true">→</span>
                </button>
              )}
            </div>
          </div>
        </section>

        {/* Cifras */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          <MetricCard label="Mis archivos" value={cargando ? '…' : propios.length} sub="Procesados y listos" color="blue" icon={iconoArchivo} to="/archivos" />
          <MetricCard label="Filas en total" value={cargando ? '…' : totalFilas.toLocaleString('es-MX')} sub="Tuyas y compartidas" color="green" icon={iconoFilas} />
          <MetricCard label="Compartidos conmigo" value={cargando ? '…' : compartidos.length} sub="Solo lectura" color="violet" icon={iconoCompartir} />
          <MetricCard label="Proyectos" value={proyectos.length} sub="Carpetas propias" color="gray" icon={iconoCarpeta} />
        </div>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem] items-start">
          {/* Recientes */}
          <div className="card">
            <div className="flex items-center justify-between gap-2 mb-1">
              <h2 className="text-sm font-semibold text-gray-900">Datos recientes</h2>
              {archivos.length > 0 && <Link to="/archivos" className="text-xs text-brand-600 hover:underline">Ver todos</Link>}
            </div>
            {error ? (
              <p className="text-sm text-red-600 py-8 text-center">No se pudieron cargar tus archivos. Intenta de nuevo en un momento.</p>
            ) : cargando ? (
              <Cargando />
            ) : recientes.length === 0 ? (
              <Vacio titulo="Aún no tienes datos">Sube cualquier Excel o CSV: detectamos las columnas y tú confirmas.</Vacio>
            ) : (
              <div className="divide-y divide-gray-50">
                {recientes.map(a => (
                  <FilaArchivo key={a.id} nombre={a.nombre}
                    detalle={`${a.filas?.toLocaleString('es-MX') ?? 0} filas`
                      + (a.es_mio ? '' : ` · compartido por ${a.subido_por_nombre || 'otro usuario'}`)
                      + ` · ${new Date(a.subido_en).toLocaleDateString('es-MX')}`}>
                    <button onClick={() => navigate(`/datos/${a.id}`)} className="btn-ghost text-xs">Ver datos</button>
                    <button onClick={() => navigate(`/datos/${a.id}/dashboard`)} className="btn-secondary text-xs">Dashboard</button>
                  </FilaArchivo>
                ))}
              </div>
            )}
          </div>

          {/* Cómo empezar + proyectos */}
          <div className="space-y-5">
            {!(propios.length > 0 && principal) && <div className="card">
              <h2 className="text-sm font-semibold text-gray-900 mb-4">Cómo empezar</h2>
              <ol className="space-y-4">
                <Paso hecho={propios.length > 0} titulo="Sube un archivo">Excel o CSV; confirmas las columnas detectadas.</Paso>
                <Paso hecho={!!principal} titulo="Marca tu dashboard principal">Con ☆ «Hacer principal» lo verás al entrar.</Paso>
                <Paso hecho={false} titulo="Exporta o comparte">Descárgalo como imagen, PDF o PowerPoint, o compártelo por correo.</Paso>
              </ol>
            </div>}
            {proyectos.length > 0 && (
              <div className="card">
                <h2 className="text-sm font-semibold text-gray-900 mb-3">Tus proyectos</h2>
                <div className="space-y-1.5">
                  {proyectos.map(p => (
                    <button key={p.id} onClick={() => navigate(`/proyecto/${p.id}`)}
                      className="w-full flex items-center gap-3 text-left rounded-lg px-3 py-2 hover:bg-gray-50 transition-colors">
                      <span className="text-gray-400">{iconoCarpeta}</span>
                      <span className="flex-1 min-w-0 text-sm text-gray-900 truncate">{p.nombre}</span>
                      <span className="text-xs text-gray-400">{p.num_archivos}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
