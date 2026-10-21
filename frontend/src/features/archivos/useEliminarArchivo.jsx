import { useState } from 'react'
import api from '@/shared/api'

/** Borrado de archivos con confirmación en la misma fila.
 *  `alTerminar` se llama tras eliminar (para recargar listas y proyectos). */
export default function useEliminarArchivo(alTerminar) {
  const [pendiente, setPendiente] = useState(null)   // archivo que espera confirmación
  const [trabajando, setTrabajando] = useState(false)
  const [error, setError] = useState('')

  const pedir = (archivo) => { setError(''); setPendiente(archivo) }
  const cancelar = () => { setPendiente(null); setError('') }

  const confirmar = async () => {
    if (!pendiente) return
    setTrabajando(true); setError('')
    try {
      await api.delete(`/archivos/${pendiente.id}`)
      setPendiente(null)
      await alTerminar?.()
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo eliminar el archivo')
    } finally { setTrabajando(false) }
  }

  /** Bloque de confirmación para pasar como `pie` de FilaArchivo (null si no corresponde a este archivo). */
  const aviso = (archivo) => pendiente?.id !== archivo.id ? null : (
    <div role="alertdialog" aria-label="Confirmar eliminación"
      className="basis-full rounded-lg bg-red-50 border border-red-100 px-4 py-3 flex flex-wrap items-center gap-3">
      <p className="text-xs text-red-800 flex-1 min-w-[16rem]">
        ¿Eliminar <strong>{archivo.nombre}</strong>? Se borran también sus dashboards guardados y los accesos compartidos. No se puede deshacer.
        {error && <span className="block mt-1 font-medium">{error}</span>}
      </p>
      <div className="flex gap-2">
        <button className="btn-secondary text-xs" onClick={cancelar} disabled={trabajando}>Cancelar</button>
        <button className="text-xs font-medium px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white disabled:opacity-60"
          onClick={confirmar} disabled={trabajando}>
          {trabajando ? 'Eliminando…' : 'Sí, eliminar'}
        </button>
      </div>
    </div>
  )

  return { pedir, aviso, pendiente }
}
