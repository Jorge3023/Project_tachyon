import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '@/shared/api'
import PageHeader from '@/shared/components/PageHeader'
import Cargando from '@/shared/components/Cargando'

const ETIQUETA_ROL = { fecha: 'Fecha', numero: 'Número', categoria: 'Categoría', identificador: 'Identificador', estado: 'Estado', texto: 'Texto' }
const fmt = (n) => (n === undefined || n === null) ? '' : Number(n).toLocaleString('es-MX', { maximumFractionDigits: 2 })

function ResumenColumna({ r }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-gray-900 truncate">{r.nombre}</p>
        <span className="text-[11px] text-gray-400 flex-shrink-0">{ETIQUETA_ROL[r.rol] || r.rol}</span>
      </div>
      {r.rol === 'numero' && r.min !== undefined && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 mt-2 text-xs">
          <dt className="text-gray-400">Suma</dt><dd className="text-right text-gray-700">{fmt(r.suma)}</dd>
          <dt className="text-gray-400">Promedio</dt><dd className="text-right text-gray-700">{fmt(r.media)}</dd>
          <dt className="text-gray-400">Mínimo</dt><dd className="text-right text-gray-700">{fmt(r.min)}</dd>
          <dt className="text-gray-400">Máximo</dt><dd className="text-right text-gray-700">{fmt(r.max)}</dd>
        </dl>
      )}
      {r.rol === 'fecha' && r.desde && (
        <p className="text-xs text-gray-600 mt-2">{r.desde} → {r.hasta}</p>
      )}
      {r.top && (
        <div className="mt-2 space-y-0.5 text-xs">
          <p className="text-gray-400">{r.unicos} valores distintos</p>
          {r.top.slice(0, 3).map(t => (
            <p key={t.valor} className="flex justify-between gap-2 text-gray-600">
              <span className="truncate">{t.valor}</span><span className="text-gray-400">{t.n}</span>
            </p>
          ))}
        </div>
      )}
      {r.nulos > 0 && <p className="text-[11px] text-amber-600 mt-2">{r.nulos} vacíos</p>}
    </div>
  )
}

export default function VerDatos() {
  const { id } = useParams()
  const [datos, setDatos] = useState(null)
  const [pagina, setPagina] = useState(1)
  const [error, setError] = useState('')
  const POR_PAGINA = 25

  useEffect(() => {
    setError('')
    api.get(`/datasets/${id}/datos?pagina=${pagina}&por_pagina=${POR_PAGINA}`)
      .then(r => setDatos(r.data))
      .catch(e => setError(e.response?.status === 404 ? 'No encontramos estos datos (o no tienes acceso).' : 'No se pudieron cargar los datos'))
  }, [id, pagina])

  const paginas = datos ? Math.max(1, Math.ceil(datos.total / POR_PAGINA)) : 1

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <PageHeader
        migas={[{ texto: 'Archivos', to: '/archivos' }, { texto: datos?.archivo.nombre || 'Datos' }]}
        titulo="Datos"
        subtitulo={datos && `${datos.total.toLocaleString('es-MX')} filas · ${datos.columnas.length} columnas${!datos.archivo.es_mio ? ' · compartido contigo (solo lectura)' : ''}`}
        acciones={<Link to={`/datos/${id}/dashboard`} className="btn-secondary text-xs">Ver dashboard</Link>} />

      <main className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5">
        {error && <div className="px-4 py-3 rounded-lg text-sm bg-red-50 text-red-700">{error}</div>}
        {!datos && !error && <Cargando />}
        {datos && (
          <>
            <section aria-label="Resumen por columna" className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
              {datos.resumen.map(r => <ResumenColumna key={r.nombre} r={r} />)}
            </section>

            <section className="card p-0 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 text-gray-500">
                    <tr>{datos.columnas.map(c => <th key={c.nombre} className="text-left font-medium px-3 py-2 whitespace-nowrap">{c.nombre}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {datos.filas.map((f, i) => (
                      <tr key={i} className="hover:bg-gray-50/60">
                        {f.map((v, j) => (
                          <td key={j} className={'px-3 py-1.5 whitespace-nowrap text-gray-700 ' + (datos.columnas[j].rol === 'numero' ? 'text-right tabular-nums' : '')}>
                            {datos.columnas[j].rol === 'numero' ? fmt(v) : (v ?? '')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between px-4 py-2 border-t border-gray-100 text-xs text-gray-500">
                <span>Página {pagina} de {paginas}</span>
                <div className="flex gap-2">
                  <button className="btn-ghost text-xs" disabled={pagina <= 1} onClick={() => setPagina(p => p - 1)}>Anterior</button>
                  <button className="btn-ghost text-xs" disabled={pagina >= paginas} onClick={() => setPagina(p => p + 1)}>Siguiente</button>
                </div>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  )
}
