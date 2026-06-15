import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell
} from 'recharts'
import api from '../services/api'

const LINEAS   = ['Todas', 'A', 'B', 'C', 'D', 'E']
const COLORES  = ['#185FA5', '#059669', '#D85A30', '#7C3AED', '#DB2777']
const PERIODOS = [{ key: 'dia', label: 'Hoy' }, { key: 'semana', label: 'Semana' }, { key: 'mes', label: 'Mes' }]

function MetricCard({ label, value, sub, color = 'gray', icon }) {
  const colors = {
    blue:   'bg-brand-50  text-brand-600',
    green:  'bg-green-50  text-green-600',
    red:    'bg-red-50    text-red-500',
    amber:  'bg-amber-50  text-amber-600',
    purple: 'bg-purple-50 text-purple-600',
    gray:   'bg-gray-100  text-gray-500',
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

function SinDatos({ onCargar, esAdmin }) {
  return (
    <div className="flex flex-col items-center justify-center h-48 text-center">
      <div className="w-12 h-12 bg-gray-100 rounded-xl flex items-center justify-center mb-3">
        <svg className="w-6 h-6 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10" />
        </svg>
      </div>
      <p className="text-sm text-gray-400 mb-3">Sin datos para este periodo</p>
      {esAdmin && (
        <button onClick={onCargar} className="btn-primary text-xs py-1.5">
          Cargar archivo Excel
        </button>
      )}
    </div>
  )
}

export default function Dashboard({ lineaFija = null }) {
  const { usuario } = useAuth()
  const navigate    = useNavigate()
  const esAdmin     = usuario?.rol === 'admin'
  const lineaBloqueada = lineaFija ? String(lineaFija).toUpperCase() : null

  const [periodo,   setPeriodo]   = useState('dia')
  const [lineaFlt,  setLineaFlt]  = useState('Todas')
  const [resumen,   setResumen]   = useState(null)
  const [modelos,   setModelos]   = useState([])
  const [porLinea,  setPorLinea]  = useState([])
  const [tendencia, setTendencia] = useState([])
  const [rendLineas,setRendLineas]= useState([])
  const [cargando,  setCargando]  = useState(true)

  const lineaActiva = lineaBloqueada || lineaFlt
  const lineaParam = lineaActiva === 'Todas' ? '' : lineaActiva

  const hoy = new Date().toLocaleDateString('es-MX', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  })

  useEffect(() => {
    setCargando(true)
    const q = (path) => api.get(path + (lineaParam ? `${path.includes('?') ? '&' : '?'}linea=${lineaParam}` : ''))
    Promise.all([
      q(`/dashboard/resumen?periodo=${periodo}`),
      q(`/dashboard/por-modelo?periodo=${periodo}`),
      q(`/dashboard/por-linea?periodo=${periodo}`),
      q(`/dashboard/tendencia?periodo=${periodo}`),
      q(`/dashboard/rendimiento-lineas?periodo=${periodo}`),
    ]).then(([res, mod, pl, tend, rend]) => {
      setResumen(res.data)
      setModelos(mod.data)
      setPorLinea(pl.data)
      setTendencia(tend.data.map(d => ({ ...d, fecha: d.fecha?.slice(5) })))
      setRendLineas(rend.data)
    }).catch(() => {
      setResumen(null)
      setModelos([])
      setPorLinea([])
      setTendencia([])
      setRendLineas([])
    }).finally(() => setCargando(false))
  }, [periodo, lineaParam])

  const fmt = (n) => typeof n === 'number' ? n.toLocaleString('es-MX') : n

  return (
    <div className="flex-1 flex flex-col overflow-hidden">

      {/* Topbar */}
      <header className="bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-base font-semibold text-gray-900">
            {lineaBloqueada ? `Dashboard de Línea ${lineaBloqueada}` : 'Dashboard General'}
          </h1>
          <p className="text-xs text-gray-400 mt-0.5 capitalize">{hoy}</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap justify-end">

          {/* Filtro por línea */}
          {!lineaBloqueada && (
            <div className="flex bg-gray-100 rounded-lg p-0.5">
              {LINEAS.map(l => (
                <button key={l} onClick={() => setLineaFlt(l)}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 ` +
                    (lineaFlt === l ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
                  {l === 'Todas' ? 'Todas' : `Línea ${l}`}
                </button>
              ))}
            </div>
          )}

          {/* Filtro por periodo */}
          <div className="flex bg-gray-100 rounded-lg p-0.5">
            {PERIODOS.map(p => (
              <button key={p.key} onClick={() => setPeriodo(p.key)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 ` +
                  (periodo === p.key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
                {p.label}
              </button>
            ))}
          </div>

          {esAdmin && (
            <>
              {lineaActiva !== 'Todas' && (
                <button
                  onClick={() => navigate(`/reportes?linea=${lineaActiva}`)}
                  className="btn-primary bg-violet-600 hover:bg-violet-700 text-xs"
                >
                  Reportes de Línea {lineaActiva}
                </button>
              )}
              <button onClick={() => navigate('/archivos')} className="btn-primary">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                Cargar Excel
              </button>
            </>
          )}
        </div>
      </header>

      {/* Contenido */}
      <main className="flex-1 overflow-y-auto p-6 space-y-6">

        {/* Fuente de datos */}
        {resumen && resumen.fuente !== 'real' && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs w-fit bg-amber-50 text-amber-700">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            Sin archivos cargados — sube un archivo Excel o de Hoja de calculo (.xlsx/.xls)
          </div>
        )}

        {/* Métricas */}
        <div className="grid grid-cols-5 gap-4">
          <MetricCard label="Piezas conformes" value={cargando ? '…' : fmt(resumen?.unidades)}
            color="green"
            icon={<svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>} />
          <MetricCard label="Piezas no conformes" value={cargando ? '…' : fmt(resumen?.rechazos)}
            color="red"
            icon={<svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>} />
          <MetricCard label="Eficiencia operativa" value={cargando ? '…' : `${resumen?.eficiencia ?? 0}%`}
            color="blue"
            icon={<svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10" /></svg>} />
          <MetricCard label="Tiempo de paro" value={cargando ? '…' : `${resumen?.tiempo_paro ?? 0}h`}
            color="amber"
            icon={<svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>} />
          <MetricCard label="Tiempo efectivo" value={cargando ? '…' : `${resumen?.horas_reales ?? 0}h`}
            color="purple"
            icon={<svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>} />
        </div>

        {/* Gráficas fila 1 */}
        <div className="grid grid-cols-3 gap-5">

          {/* Piezas por modelo */}
          <div className="card col-span-2">
            <h2 className="text-sm font-semibold text-gray-900 mb-1">Producción por modelo</h2>
            <p className="text-xs text-gray-400 mb-4">Top 10 — piezas conformes vs no conformes</p>
            {modelos.length === 0
              ? <SinDatos onCargar={() => navigate('/archivos')} esAdmin={esAdmin} />
              : (
                <ResponsiveContainer width="100%" height={210}>
                  <BarChart data={modelos} layout="vertical" margin={{ top: 0, right: 20, left: 10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 10, fill: '#9ca3af' }} />
                    <YAxis type="category" dataKey="ProductID" width={160}
                      tick={{ fontSize: 9, fill: '#6b7280' }}
                      tickFormatter={v => v.length > 22 ? v.slice(0, 22) + '…' : v} />
                    <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #e5e7eb' }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="qty_passed" name="Piezas conformes" fill="#185FA5" radius={[0,3,3,0]} />
                    <Bar dataKey="qty_failed" name="Piezas no conformes" fill="#f87171" radius={[0,3,3,0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
          </div>

          {/* Rendimiento por línea */}
          <div className="card">
            <h2 className="text-sm font-semibold text-gray-900 mb-1">Eficiencia por línea</h2>
            <p className="text-xs text-gray-400 mb-4">% promedio (tiempo efectivo / tiempo de ciclo)</p>
            {rendLineas.length === 0
              ? <SinDatos onCargar={() => navigate('/archivos')} esAdmin={esAdmin} />
              : (
                <ResponsiveContainer width="100%" height={210}>
                  <BarChart data={rendLineas} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="linea" tick={{ fontSize: 11, fill: '#9ca3af' }}
                      tickFormatter={v => `L-${v}`} />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#9ca3af' }}
                      tickFormatter={v => `${v}%`} />
                    <Tooltip formatter={v => [`${v}%`, 'Eficiencia operativa']}
                      contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #e5e7eb' }} />
                    <Bar dataKey="rendimiento" radius={[4, 4, 0, 0]}>
                      {rendLineas.map((_, i) => <Cell key={i} fill={COLORES[i % COLORES.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
          </div>
        </div>

        {/* Gráficas fila 2 */}
        <div className="grid grid-cols-3 gap-5">

          {/* Tendencia */}
          <div className="card col-span-2">
            <h2 className="text-sm font-semibold text-gray-900 mb-1">Tendencia histórica</h2>
            <p className="text-xs text-gray-400 mb-4">Piezas conformes y no conformes por fecha</p>
            {tendencia.length === 0
              ? <SinDatos onCargar={() => navigate('/archivos')} esAdmin={esAdmin} />
              : (
                <ResponsiveContainer width="100%" height={180}>
                  <LineChart data={tendencia} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="fecha" tick={{ fontSize: 10, fill: '#9ca3af' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} />
                    <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #e5e7eb' }} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Line type="monotone" dataKey="qty_passed" name="Piezas conformes"
                      stroke="#185FA5" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="qty_failed" name="Piezas no conformes"
                      stroke="#f87171" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
          </div>

          {/* Tabla por línea */}
          <div className="card">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Resumen por línea</h2>
            {porLinea.length === 0
              ? <SinDatos onCargar={() => navigate('/archivos')} esAdmin={esAdmin} />
              : (
                <div className="space-y-2">
                  {porLinea.map((l, i) => (
                    <div key={l.linea} className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50">
                      <div className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ background: COLORES[i % COLORES.length] }} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-gray-900">Línea {l.linea}</p>
                        <p className="text-xs text-gray-400">
                          {l.qty_passed?.toLocaleString()} conformes · {l.qty_failed?.toLocaleString()} no conformes
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs font-semibold text-gray-900">
                          {typeof l.rendimiento === 'number' ? l.rendimiento.toFixed(1) : '—'}%
                        </p>
                        <p className="text-xs text-amber-600">{l.horas_muertas?.toFixed(1)}h de paro</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
          </div>
        </div>

      </main>
    </div>
  )
}
