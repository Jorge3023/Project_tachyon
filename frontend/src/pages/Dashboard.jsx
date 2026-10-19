import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import api from '../services/api'

function MetricCard({ label, value, sub, color = 'gray', icon }) {
  const colors = {
    blue:  'bg-brand-50 text-brand-600',
    green: 'bg-green-50 text-green-600',
    gray:  'bg-gray-100 text-gray-500',
  }
  return (
    <div className="metric-card">
      <div className="flex items-center gap-2 mb-2">
        <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${colors[color]}`}>
          {icon}
        </div>
        <span className="text-xs text-gray-500">{label}</span>
      </div>
      <p className="text-2xl font-semibold text-gray-900">{value ?? '—'}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  )
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

export default function Dashboard() {
  const { usuario } = useAuth()
  const navigate = useNavigate()
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

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <header className="bg-white border-b border-gray-100 px-6 py-4">
        <h1 className="text-base font-semibold text-gray-900">
          {primerNombre ? `Hola, ${primerNombre}` : 'Inicio'}
        </h1>
        <p className="text-xs text-gray-400 mt-0.5">{hoy}</p>
      </header>

      <main className="flex-1 overflow-y-auto p-6 space-y-5">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <MetricCard label="Mis archivos"          value={cargando ? '…' : propios.length}
            sub="Procesados y listos para ver" color="blue" icon={iconoArchivo} />
          <MetricCard label="Filas en total"        value={cargando ? '…' : totalFilas.toLocaleString('es-MX')}
            sub="Entre tus archivos y los compartidos" color="green" icon={iconoFilas} />
          <MetricCard label="Compartidos conmigo"   value={cargando ? '…' : compartidos.length}
            sub="Solo lectura" color="gray" icon={iconoCompartir} />
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-900">Tus datos recientes</h2>
            <button onClick={() => navigate('/archivos')} className="btn-primary text-xs py-1.5">
              Subir un archivo
            </button>
          </div>

          {error ? (
            <p className="text-sm text-red-600 py-8 text-center">No se pudieron cargar tus archivos. Intenta de nuevo en un momento.</p>
          ) : cargando ? (
            <div className="flex justify-center py-10">
              <div className="w-5 h-5 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : recientes.length === 0 ? (
            <div className="text-center py-10 text-gray-400">
              <svg className="w-10 h-10 mx-auto mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-sm text-gray-500">Aún no tienes datos</p>
              <p className="text-xs mt-1">Sube cualquier Excel o CSV: detectamos las columnas y tú confirmas.</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-50">
              {recientes.map(a => (
                <div key={a.id} className="flex items-center gap-4 py-3">
                  <div className="w-8 h-8 bg-green-50 rounded-lg flex items-center justify-center flex-shrink-0 text-green-600">
                    {iconoArchivo}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{a.nombre}</p>
                    <p className="text-xs text-gray-400">
                      {`${a.filas?.toLocaleString('es-MX') ?? 0} filas`}
                      {a.es_mio ? '' : ` · compartido por ${a.subido_por_nombre || 'otro usuario'}`}
                      {` · ${new Date(a.subido_en).toLocaleDateString('es-MX')}`}
                    </p>
                  </div>
                  <button onClick={() => navigate(`/datos/${a.id}`)}
                    className="btn-ghost text-brand-600 hover:text-brand-700 hover:bg-brand-50 text-xs flex-shrink-0">
                    Ver datos
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card bg-gray-50 border-dashed">
          <h2 className="text-sm font-semibold text-gray-700">Dashboards a tu medida</h2>
          <p className="text-xs text-gray-500 mt-1">
            Próximamente podrás armar tu propio dashboard con gráficas sobre estos datos y exportarlo.
          </p>
        </div>
      </main>
    </div>
  )
}
