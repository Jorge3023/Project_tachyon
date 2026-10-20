import { useState } from 'react'
import api from '../services/api'

const NOMBRE_MOTOR = { postgres: 'PostgreSQL (Supabase)', sqlite: 'SQLite (archivo local)' }
const NOMBRE_ARCHIVOS = { supabase: 'Supabase Storage', local: 'Disco local' }

function Fila({ titulo, valor, ok, detalle }) {
  return (
    <div className="flex items-start gap-3 py-2">
      <span className={'mt-1 w-2.5 h-2.5 rounded-full flex-shrink-0 ' + (ok ? 'bg-green-500' : 'bg-red-500')} aria-hidden="true" />
      <div className="min-w-0">
        <p className="text-sm text-gray-900">{titulo}: <span className="font-medium">{valor}</span> — {ok ? 'funciona' : 'falla'}</p>
        {detalle && <p className="text-xs text-gray-400 mt-0.5 break-words">{detalle}</p>}
      </div>
    </div>
  )
}

// Solo administradores: comprueba de verdad que la base de datos y el almacenamiento responden.
export default function EstadoSistema() {
  const [d, setD] = useState(null)
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState('')

  const comprobar = async () => {
    setCargando(true); setError('')
    try { setD((await api.get('/admin/diagnostico')).data) }
    catch (e) { setError(e.response?.data?.detail || 'No se pudo comprobar el estado') }
    finally { setCargando(false) }
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Estado del sistema</h2>
          <p className="text-xs text-gray-400 mt-0.5">Comprueba que los datos se guardan donde deben (base de datos y archivos).</p>
        </div>
        <button type="button" className="btn-ghost text-xs" onClick={comprobar} disabled={cargando}>
          {cargando ? 'Comprobando…' : 'Comprobar ahora'}
        </button>
      </div>
      {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
      {d && (
        <div className="mt-3 divide-y divide-gray-50">
          <Fila titulo="Base de datos" valor={NOMBRE_MOTOR[d.base_de_datos.motor] || d.base_de_datos.motor}
                ok={d.base_de_datos.ok} detalle={d.base_de_datos.detalle} />
          <Fila titulo="Archivos" valor={NOMBRE_ARCHIVOS[d.archivos.modo] || d.archivos.modo}
                ok={d.archivos.ok} detalle={d.archivos.detalle} />
          {d.advertencias.length > 0 && (
            <ul className="pt-3 space-y-1">
              {d.advertencias.map(a => <li key={a} className="text-xs text-amber-700 bg-amber-50 rounded-md px-3 py-2">{a}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
