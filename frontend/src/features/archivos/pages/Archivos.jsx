import { useState, useEffect } from 'react'
import api from '@/shared/api'
import { useNavigate } from 'react-router-dom'
import ModalCompartir from '@/features/archivos/components/ModalCompartir'
import SubirArchivo from '@/features/archivos/components/SubirArchivo'
import { useProyectos } from '@/features/proyectos/ProyectosContext'

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

export default function Archivos() {
  const [archivos,      setArchivos]      = useState([])
  const [origen,        setOrigen]        = useState('todos')   // todos | mios | compartidos
  const [compartiendo,  setCompartiendo]  = useState(null)      // archivo cuyo modal de compartir está abierto
  const { proyectos, recargar: recargarProyectos } = useProyectos()
  const navigate = useNavigate()

  const cargarLista = () =>
    api.get(`/archivos?origen=${origen}`).then(r => setArchivos(r.data)).catch(() => {})

  useEffect(() => { cargarLista() }, [origen])

  const moverA = async (archivo, valor) => {
    const proyecto_id = valor === '' ? null : Number(valor)
    try {
      await api.put(`/archivos/${archivo.id}/proyecto`, { proyecto_id })
      setArchivos(l => l.map(x => x.id === archivo.id ? { ...x, proyecto_id } : x))
      recargarProyectos()
    } catch { /* se queda como estaba */ }
  }

  return (
    <>
      {compartiendo && (
        <ModalCompartir
          archivo={compartiendo}
          onCerrar={() => setCompartiendo(null)}
          onCambio={cargarLista}
        />
      )}

      <div className="flex-1 flex flex-col overflow-hidden">
        <header className="bg-white border-b border-gray-100 px-6 py-4">
          <h1 className="text-base font-semibold text-gray-900">Mis archivos</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            Tus archivos son privados: solo tú los ves, salvo que los compartas por correo.
          </p>
        </header>

        <main className="flex-1 overflow-y-auto p-6 space-y-5">

          <SubirArchivo onGuardado={() => { cargarLista(); recargarProyectos() }} />

          {/* ── Historial ── */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <div className="flex bg-gray-100 rounded-lg p-0.5">
                {[['todos','Todos'],['mios','Mis archivos'],['compartidos','Compartidos conmigo']].map(([k, label]) => (
                  <button key={k} onClick={() => setOrigen(k)}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 ` +
                      (origen === k ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700')}>
                    {label}
                  </button>
                ))}
              </div>
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
                  {origen === 'compartidos' ? 'Nadie ha compartido archivos contigo todavía' : 'Aún no hay archivos cargados'}
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
                        {`${a.filas?.toLocaleString('es-MX') ?? 0} filas`}
                        {a.es_mio ? '' : ` · compartido por ${a.subido_por_nombre || 'otro usuario'}`}
                        {` · ${new Date(a.subido_en).toLocaleDateString('es-MX')}`}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {a.es_mio && a.num_compartidos > 0 && (
                        <span className="text-xs text-gray-400" title="Personas con acceso">
                          {a.num_compartidos} {a.num_compartidos === 1 ? 'persona' : 'personas'}
                        </span>
                      )}
                      {a.es_mio && a.estado === 'procesado' && (
                        <select value={a.proyecto_id ?? ''} onChange={e => moverA(a, e.target.value)}
                          aria-label={`Proyecto de ${a.nombre}`}
                          className="text-xs border border-gray-200 rounded-md py-1 pl-2 pr-6 text-gray-600 bg-white max-w-[9rem]">
                          <option value="">Sin proyecto</option>
                          {proyectos.map(p => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                        </select>
                      )}
                      <EstadoBadge estado={a.estado} />
                      {a.es_mio && a.estado === 'procesado' && (
                        <button onClick={() => setCompartiendo(a)}
                          className="btn-ghost text-xs" title="Compartir por correo">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                              d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                          </svg>
                          Compartir
                        </button>
                      )}
                      {a.estado === 'procesado' && (
                        <>
                          <button onClick={() => navigate(`/datos/${a.id}/dashboard`)}
                            className="btn-ghost text-brand-600 hover:text-brand-700 hover:bg-brand-50 text-xs">
                            Dashboard
                          </button>
                          <button onClick={() => navigate(`/datos/${a.id}`)}
                            className="btn-ghost text-gray-500 text-xs">
                            Ver datos
                          </button>
                        </>
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
