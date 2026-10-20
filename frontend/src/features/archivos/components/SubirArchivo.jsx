import { useState, useRef } from 'react'
import api from '@/shared/api'
import ModalRevisarColumnas from './ModalRevisarColumnas'

/* Tarjeta para subir cualquier Excel/CSV: sube, analiza las columnas y abre la pantalla de revisión.
   proyectoId (opcional): el archivo se guarda dentro de ese proyecto. */
export default function SubirArchivo({ proyectoId = null, onGuardado }) {
  const inputRef = useRef()
  const [analisis,   setAnalisis]   = useState(null)
  const [analizando, setAnalizando] = useState(false)
  const [mensaje,    setMensaje]    = useState(null)

  const handleArchivo = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.name.match(/\.(xlsx|xlsm|xls|csv|tsv|txt)$/i)) {
      setMensaje({ tipo: 'error', texto: 'Formatos admitidos: .xlsx, .xls, .csv, .tsv' })
      return
    }
    setMensaje(null); setAnalizando(true)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const r = await api.post('/datasets/analizar', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      setAnalisis(r.data)
    } catch (err) {
      setMensaje({ tipo: 'error', texto: err.response?.data?.detail || 'No se pudo leer el archivo' })
    } finally { setAnalizando(false) }
  }

  return (
    <>
      {analisis && (
        <ModalRevisarColumnas
          analisis={analisis}
          proyectoId={proyectoId}
          onCancelar={() => setAnalisis(null)}
          onGuardado={(r) => {
            setAnalisis(null)
            setMensaje({ tipo: 'ok', texto: r.mensaje })
            onGuardado?.(r)
          }}
        />
      )}

      <div className="card">
        <h2 className="text-sm font-semibold text-gray-900 mb-1">Subir cualquier Excel o CSV</h2>
        <p className="text-xs text-gray-400 mb-4">
          Detectamos las columnas por ti y tú confirmas antes de guardar. Si el formato se repite, lo recordamos con una plantilla.
        </p>
        <button type="button" onClick={() => inputRef.current?.click()} disabled={analizando}
          className="w-full border-2 border-dashed border-gray-200 rounded-xl p-6 text-center cursor-pointer
                     hover:border-brand-400 hover:bg-brand-50/20 transition-all disabled:opacity-60">
          {analizando
            ? <span className="flex items-center gap-2 justify-center text-sm text-gray-600">
                <span className="w-4 h-4 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                Leyendo el archivo…
              </span>
            : <>
                <span className="block text-sm font-medium text-gray-700">Seleccionar archivo</span>
                <span className="block text-xs text-gray-400 mt-1">.xlsx, .xls, .csv, .tsv — hasta 25 MB</span>
              </>}
        </button>
        <input ref={inputRef} type="file" accept=".xlsx,.xlsm,.xls,.csv,.tsv,.txt" className="hidden"
          aria-label="Archivo Excel o CSV" onChange={handleArchivo} />

        {mensaje && (
          <div role="status" className={`mt-4 px-4 py-3 rounded-lg text-sm flex items-start gap-2 ` +
            (mensaje.tipo === 'ok' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700')}>
            {mensaje.tipo === 'ok'
              ? <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
              : <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
            {mensaje.texto}
          </div>
        )}
      </div>
    </>
  )
}
