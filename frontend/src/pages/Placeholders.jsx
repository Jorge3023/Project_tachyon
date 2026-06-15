import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import Dashboard from './Dashboard'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'

export function LineaPage() {
  const { id } = useParams()
  return <Dashboard lineaFija={id} />
}

export function ReportesPage() {
  const { usuario } = useAuth()
  const esAdmin = usuario?.rol === 'admin'
  const [searchParams] = useSearchParams()
  const linea = (searchParams.get('linea') || '').toUpperCase()

  const [archivos, setArchivos] = useState([])
  const [archivoActivo, setArchivoActivo] = useState(null)
  const [detalle, setDetalle] = useState(null)
  const [cargandoLista, setCargandoLista] = useState(true)
  const [cargandoDetalle, setCargandoDetalle] = useState(false)
  const [eliminandoId, setEliminandoId] = useState(null)
  const [descargandoId, setDescargandoId] = useState(null)

  const cargarArchivos = () => {
    setCargandoLista(true)
    if (!linea) {
      setArchivos([])
      setArchivoActivo(null)
      setDetalle(null)
      setCargandoLista(false)
      return
    }

    api.get(`/archivos?linea=${linea}`)
      .then((res) => {
        const procesados = (res.data || []).filter((a) => a.estado === 'procesado')
        setArchivos(procesados)
        if (!procesados.some((a) => a.id === archivoActivo?.id)) {
          const primero = procesados[0] || null
          setArchivoActivo(primero)
          if (primero) {
            abrirDetalle(primero)
          } else {
            setDetalle(null)
          }
        }
      })
      .catch(() => setArchivos([]))
      .finally(() => setCargandoLista(false))
  }

  useEffect(() => { cargarArchivos() }, [linea])

  const abrirDetalle = (archivo) => {
    setArchivoActivo(archivo)
    setCargandoDetalle(true)
    api.get(`/archivos/${archivo.id}/reporte`)
      .then((res) => setDetalle(res.data))
      .catch(() => setDetalle(null))
      .finally(() => setCargandoDetalle(false))
  }

  const eliminarArchivo = async (archivo) => {
    if (!window.confirm(`¿Eliminar "${archivo.nombre}" de la Línea ${archivo.linea}?`)) return
    setEliminandoId(archivo.id)
    try {
      await api.delete(`/archivos/${archivo.id}`)
      if (archivoActivo?.id === archivo.id) {
        setArchivoActivo(null)
        setDetalle(null)
      }
      await cargarArchivos()
    } finally {
      setEliminandoId(null)
    }
  }

  const descargarArchivo = async (archivo) => {
    setDescargandoId(archivo.id)
    try {
      const res = await api.get(`/archivos/${archivo.id}/descargar`, { responseType: 'blob' })
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = Object.assign(document.createElement('a'), {
        href: url,
        download: archivo.nombre.replace(/\.(xlsx|xls)$/i, '') + '_analisis.xlsx',
      })
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setDescargandoId(null)
    }
  }

  const fmtN = (n) => (typeof n === 'number' ? n.toLocaleString('es-MX') : n ?? '—')

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <header className="bg-white border-b border-gray-100 px-6 py-4">
        <h1 className="text-base font-semibold text-gray-900">Reportes por archivo</h1>
        <p className="text-xs text-gray-400 mt-0.5">
          {linea
            ? `Línea ${linea} · consulta individual de cada carga`
            : 'Selecciona una línea desde el dashboard para abrir reportes por archivo'}
        </p>
      </header>

      <main className="flex-1 overflow-hidden p-6">
        <div className="grid grid-cols-3 gap-5 h-full min-h-0">
          <section className="card col-span-1 min-h-0 flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-900">Archivos procesados</h2>
              <button onClick={cargarArchivos} className="btn-ghost text-xs">Actualizar</button>
            </div>

            {!linea ? (
              <p className="text-xs text-gray-400">Primero elige una línea en el dashboard.</p>
            ) : cargandoLista ? (
              <p className="text-xs text-gray-400">Cargando archivos…</p>
            ) : archivos.length === 0 ? (
              <p className="text-xs text-gray-400">No hay archivos procesados todavía.</p>
            ) : (
              <div className="space-y-2 overflow-y-auto pr-1 min-h-0">
                {archivos.map((a) => (
                  <div
                    key={a.id}
                    className={`w-full p-3 rounded-lg border transition-colors ${
                      archivoActivo?.id === a.id ? 'border-brand-300 bg-brand-50/40' : 'border-gray-100 hover:bg-gray-50'
                    }`}
                  >
                    <button onClick={() => abrirDetalle(a)} className="w-full text-left">
                      <p className="text-sm font-medium text-gray-900 truncate">{a.nombre}</p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        Línea {a.linea} · {new Date(a.subido_en).toLocaleDateString('es-MX')}
                      </p>
                      <p className="text-xs text-gray-400 mt-1">{fmtN(a.filas)} registros procesados</p>
                    </button>
                    <div className="mt-2 pt-2 border-t border-gray-100 flex items-center justify-between">
                      <button
                        onClick={() => descargarArchivo(a)}
                        disabled={descargandoId === a.id}
                        className="btn-primary text-xs py-1.5 px-3"
                      >
                        {descargandoId === a.id ? 'Descargando…' : 'Descargar'}
                      </button>
                      {esAdmin && (
                        <button
                          onClick={() => eliminarArchivo(a)}
                          disabled={eliminandoId === a.id}
                          className="text-xs text-red-600 hover:text-red-700 disabled:opacity-50"
                        >
                          {eliminandoId === a.id ? 'Eliminando…' : 'Eliminar archivo'}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="card col-span-2 min-h-0 flex flex-col">
            {!linea ? (
              <p className="text-sm text-gray-400">Vuelve al dashboard, elige una línea y abre sus reportes.</p>
            ) : !archivoActivo ? (
              <p className="text-sm text-gray-400">Selecciona un archivo para ver su reporte individual.</p>
            ) : cargandoDetalle ? (
              <p className="text-sm text-gray-400">Cargando detalle del archivo…</p>
            ) : !detalle ? (
              <p className="text-sm text-red-500">No se pudo cargar el reporte seleccionado.</p>
            ) : (
              <>
                <div className="mb-4">
                  <p className="text-xs text-gray-500">Archivo seleccionado</p>
                  <p className="text-sm font-semibold text-gray-900">{archivoActivo.nombre}</p>
                  <p className="text-xs text-gray-500 mt-0.5">Línea {archivoActivo.linea}</p>
                </div>

                <div className="grid grid-cols-4 gap-3 mb-5">
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-xs text-gray-500">Registros</p>
                    <p className="text-lg font-semibold text-gray-900">{fmtN(detalle.resumen?.total_registros)}</p>
                  </div>
                  <div className="bg-green-50 rounded-lg p-3">
                    <p className="text-xs text-green-700">Piezas conformes</p>
                    <p className="text-lg font-semibold text-green-700">{fmtN(detalle.resumen?.total_passed)}</p>
                  </div>
                  <div className="bg-red-50 rounded-lg p-3">
                    <p className="text-xs text-red-600">Piezas no conformes</p>
                    <p className="text-lg font-semibold text-red-600">{fmtN(detalle.resumen?.total_failed)}</p>
                  </div>
                  <div className="bg-amber-50 rounded-lg p-3">
                    <p className="text-xs text-amber-700">Tiempo de paro</p>
                    <p className="text-lg font-semibold text-amber-700">{detalle.resumen?.horas_muertas?.toFixed?.(2) ?? '0.00'}h</p>
                  </div>
                </div>

                <div className="overflow-auto border border-gray-100 rounded-lg max-h-[520px]">
                  <table className="min-w-full text-xs">
                    <thead className="bg-gray-50 text-gray-600 sticky top-0 z-10">
                      <tr>
                        <th className="text-left px-3 py-2">Fecha</th>
                        <th className="text-left px-3 py-2">Modelo</th>
                        <th className="text-right px-3 py-2">Pzs conformes</th>
                        <th className="text-right px-3 py-2">Pzs no conformes</th>
                        <th className="text-right px-3 py-2">Tiempo efectivo (h)</th>
                        <th className="text-right px-3 py-2">Eficiencia</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(detalle.reporte || []).slice(0, 120).map((row, idx) => (
                        <tr key={`${row.ProductID}-${idx}`} className="border-t border-gray-100">
                          <td className="px-3 py-2 text-gray-700">{String(row.Date || '').slice(0, 10)}</td>
                          <td className="px-3 py-2 text-gray-900">{row.ProductID}</td>
                          <td className="px-3 py-2 text-right text-gray-700">{fmtN(row.qty_passed)}</td>
                          <td className="px-3 py-2 text-right text-gray-700">{fmtN(row.qty_failed)}</td>
                          <td className="px-3 py-2 text-right text-gray-700">{Number(row.horas_reales || 0).toFixed(3)}</td>
                          <td className="px-3 py-2 text-right text-gray-900">{Number(row['rendimiento_%'] || 0).toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}
