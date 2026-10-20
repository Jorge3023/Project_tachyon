import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import api from '@/shared/api'
import SubirArchivo from '@/features/archivos/components/SubirArchivo'
import { useProyectos } from '@/features/proyectos/ProyectosContext'
import PageHeader from '@/shared/components/PageHeader'
import FilaArchivo from '@/shared/components/FilaArchivo'
import Vacio from '@/shared/components/Vacio'
import Cargando from '@/shared/components/Cargando'

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
      <PageHeader
        titulo={editando ? (
          <form onSubmit={renombrar} className="flex items-center gap-2 flex-wrap">
            <input autoFocus value={nombre} onChange={e => setNombre(e.target.value)} maxLength={40}
              aria-label="Nombre del proyecto" className="input py-1 text-sm w-56" />
            <button className="btn-primary text-xs py-1.5" type="submit">Guardar</button>
            <button className="btn-ghost text-xs" type="button" onClick={() => { setEditando(false); setError('') }}>Cancelar</button>
          </form>
        ) : (proyecto?.nombre || 'Proyecto')}
        subtitulo={error ? <span className="text-red-600">{error}</span> : 'Agrupa tus archivos; abre el dashboard de cualquiera desde aquí.'}
        acciones={proyecto && !editando && (
          borrando ? (
            <>
              <span className="text-xs text-gray-500">¿Eliminar? Tus archivos se conservan.</span>
              <button className="btn-danger text-xs" onClick={eliminar}>Sí, eliminar</button>
              <button className="btn-ghost text-xs" onClick={() => setBorrando(false)}>No</button>
            </>
          ) : (
            <>
              <button className="btn-secondary text-xs" onClick={() => { setNombre(proyecto.nombre); setEditando(true); setError('') }}>Renombrar</button>
              <button className="btn-danger text-xs" onClick={() => setBorrando(true)}>Eliminar proyecto</button>
            </>
          )
        )} />

      <main className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5">
        <SubirArchivo proyectoId={Number(id)} onGuardado={() => { cargar(); recargar() }} />

        <div className="card">
          <h2 className="text-sm font-semibold text-gray-900 mb-2">Archivos de este proyecto</h2>
          {cargando ? (
            <Cargando />
          ) : archivos.length === 0 ? (
            <Vacio titulo="Este proyecto aún no tiene archivos">
              Sube uno arriba, o asigna uno existente desde <Link to="/archivos" className="text-brand-600 hover:underline">Mis archivos</Link>.
            </Vacio>
          ) : (
            <div className="divide-y divide-gray-50">
              {archivos.map(a => (
                <FilaArchivo key={a.id} nombre={a.nombre}
                  detalle={`${a.filas?.toLocaleString('es-MX') ?? 0} filas · ${new Date(a.subido_en).toLocaleDateString('es-MX')}`}>
                  <button onClick={() => quitar(a)} className="btn-ghost text-xs">Quitar del proyecto</button>
                  <button onClick={() => navigate(`/datos/${a.id}`)} className="btn-ghost text-xs">Ver datos</button>
                  <button onClick={() => navigate(`/datos/${a.id}/dashboard`)} className="btn-secondary text-xs">Dashboard</button>
                </FilaArchivo>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
