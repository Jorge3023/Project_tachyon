import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import api from '@/shared/api'
import SubirArchivo from '@/features/archivos/components/SubirArchivo'
import { useProyectos } from '@/features/proyectos/ProyectosContext'

export default function Proyecto() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { proyectos, recargar } = useProyectos()
  const proyecto = proyectos.find(p => String(p.id) === id)

  const [archivos,   setArchivos]   = useState([])
  const [cargando,   setCargando]   = useState(true)
  const [editando,   setEditando]   = useState(false)
  const [nombre,     setNombre]     = useState('')
  const [error,      setError]      = useState('')
  const [borrando,   setBorrando]   = useState(false)

  const cargar = () =>
    api.get(`/archivos?origen=mios&proyecto=${id}`)
      .then(r => setArchivos(r.data.filter(a => a.estado === 'procesado')))
      .catch(() => {})
      .finally(() => setCargando(false))

  useEffect(() => { setCargando(true); setEditando(false); setBorrando(false); cargar() }, [id])

  const renombrar = async (e) => {
    e.preventDefault(); setError('')
    try {
      await api.patch(`/proyectos/${id}`, { nombre })
      await recargar(); setEditando(false)
    } catch (err) { setError(err.response?.data?.detail || 'No se pudo renombrar') }
  }

  const eliminar = async () => {
    try {
      await api.delete(`/proyectos/${id}`)
      await recargar(); navigate('/archivos')
    } catch (err) { setError(err.response?.data?.detail || 'No se pudo eliminar') }
  }

  const quitar = async (a) => {
    try {
      await api.put(`/archivos/${a.id}/proyecto`, { proyecto_id: null })
      setArchivos(l => l.filter(x => x.id !== a.id)); recargar()
    } catch { /* sin cambios */ }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <header className="bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between gap-4">
        <div className="min-w-0">
          {editando ? (
            <form onSubmit={renombrar} className="flex items-center gap-2">
              <input autoFocus value={nombre} onChange={e => setNombre(e.target.value)} maxLength={40}
                aria-label="Nombre del proyecto" className="input py-1 text-sm" />
              <button className="btn-primary text-xs py-1.5" type="submit">Guardar</button>
              <button className="btn-ghost text-xs" type="button" onClick={() => { setEditando(false); setError('') }}>Cancelar</button>
            </form>
          ) : (
            <h1 className="text-base font-semibold text-gray-900 truncate">{proyecto?.nombre || 'Proyecto'}</h1>
          )}
          <p className="text-xs text-gray-400 mt-0.5">
            {error ? <span className="text-red-600">{error}</span> : 'Un proyecto agrupa tus archivos y, pronto, sus dashboards.'}
          </p>
        </div>
        {proyecto && !editando && (
          <div className="flex items-center gap-1 flex-shrink-0">
            <button className="btn-ghost text-xs" onClick={() => { setNombre(proyecto.nombre); setEditando(true); setError('') }}>Renombrar</button>
            {borrando ? (
              <>
                <span className="text-xs text-gray-500">¿Eliminar? Tus archivos se conservan.</span>
                <button className="btn-ghost text-xs text-red-600 hover:bg-red-50" onClick={eliminar}>Sí, eliminar</button>
                <button className="btn-ghost text-xs" onClick={() => setBorrando(false)}>No</button>
              </>
            ) : (
              <button className="btn-ghost text-xs text-red-500 hover:bg-red-50" onClick={() => setBorrando(true)}>Eliminar proyecto</button>
            )}
          </div>
        )}
      </header>

      <main className="flex-1 overflow-y-auto p-6 space-y-5">
        <SubirArchivo proyectoId={Number(id)} onGuardado={() => { cargar(); recargar() }} />

        <div className="card">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Archivos de este proyecto</h2>
          {cargando ? (
            <div className="flex justify-center py-8">
              <div className="w-5 h-5 border-2 border-brand-600 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : archivos.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              <p className="text-sm text-gray-500">Este proyecto aún no tiene archivos</p>
              <p className="text-xs mt-1">Sube uno arriba, o asigna uno existente desde <Link to="/archivos" className="text-brand-600 hover:underline">Mis archivos</Link>.</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-50">
              {archivos.map(a => (
                <div key={a.id} className="flex items-center gap-4 py-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{a.nombre}</p>
                    <p className="text-xs text-gray-400">
                      {`${a.filas?.toLocaleString('es-MX') ?? 0} filas · ${new Date(a.subido_en).toLocaleDateString('es-MX')}`}
                    </p>
                  </div>
                  <button onClick={() => quitar(a)} className="btn-ghost text-xs">Quitar del proyecto</button>
                  <button onClick={() => navigate(`/datos/${a.id}/dashboard`)}
                    className="btn-ghost text-brand-600 hover:text-brand-700 hover:bg-brand-50 text-xs">Dashboard</button>
                  <button onClick={() => navigate(`/datos/${a.id}`)} className="btn-ghost text-gray-500 text-xs">Ver datos</button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card bg-gray-50 border-dashed">
          <h2 className="text-sm font-semibold text-gray-700">Dashboards</h2>
          <p className="text-xs text-gray-500 mt-1">
            Abre el «Dashboard» de cualquiera de sus archivos: te proponemos gráficas según sus columnas y las modificas a tu gusto.
          </p>
        </div>
      </main>
    </div>
  )
}
