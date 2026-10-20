import { useState, useEffect } from 'react'
import api from '../services/api'

// Compartir un archivo (solo lectura) con otras personas, por correo electrónico.
export default function ModalCompartir({ archivo, onCerrar, onCambio }) {
  const [lista, setLista] = useState([])
  const [correo, setCorreo] = useState('')
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(true)
  const [trabajando, setTrabajando] = useState(false)

  const cargar = () =>
    api.get(`/archivos/${archivo.id}/comparticiones`)
      .then(r => setLista(r.data))
      .catch(() => setError('No se pudo cargar la lista'))
      .finally(() => setCargando(false))

  useEffect(() => { cargar() }, [])

  const agregar = async (e) => {
    e.preventDefault()
    if (!correo.trim()) return
    setError(''); setTrabajando(true)
    try {
      await api.post(`/archivos/${archivo.id}/comparticiones`, { correo })
      setCorreo('')
      await cargar()
      onCambio?.()
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo compartir')
    } finally { setTrabajando(false) }
  }

  const quitar = async (c) => {
    setError('')
    try {
      await api.delete(`/archivos/${archivo.id}/comparticiones/${encodeURIComponent(c)}`)
      await cargar()
      onCambio?.()
    } catch { setError('No se pudo quitar') }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onCerrar}>
      <div className="bg-white rounded-2xl w-full max-w-md shadow-xl" onClick={e => e.stopPropagation()}>
        <div className="px-6 py-5 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900">Compartir archivo</h3>
          <p className="text-xs text-gray-400 mt-0.5 truncate">{archivo.nombre}</p>
        </div>

        <div className="px-6 py-4 space-y-4">
          <form onSubmit={agregar} className="flex gap-2">
            <input
              type="email" className="input" placeholder="correo@ejemplo.com"
              value={correo} onChange={e => setCorreo(e.target.value)} autoFocus
            />
            <button type="submit" className="btn-primary flex-shrink-0" disabled={trabajando || !correo.trim()}>
              Compartir
            </button>
          </form>
          <p className="text-xs text-gray-400 -mt-2">
            Podrán ver este archivo y su dashboard, pero no borrarlo ni compartirlo.
            Si la persona aún no tiene cuenta, lo verá cuando entre con ese correo.
          </p>

          {error && <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}

          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">Compartido con</p>
            {cargando ? (
              <p className="text-xs text-gray-400">Cargando…</p>
            ) : lista.length === 0 ? (
              <p className="text-xs text-gray-400">Aún no lo compartes con nadie. Solo tú lo ves.</p>
            ) : (
              <ul className="divide-y divide-gray-50 border border-gray-100 rounded-lg">
                {lista.map(c => (
                  <li key={c.correo} className="flex items-center justify-between px-3 py-2">
                    <span className="text-sm text-gray-700 truncate">{c.correo}</span>
                    <button onClick={() => quitar(c.correo)} className="text-xs text-red-600 hover:text-red-700 flex-shrink-0 ml-3">
                      Quitar
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <div className="px-6 py-4 border-t border-gray-100 flex justify-end">
          <button onClick={onCerrar} className="btn-ghost">Cerrar</button>
        </div>
      </div>
    </div>
  )
}
