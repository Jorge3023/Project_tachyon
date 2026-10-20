/** Fila de un archivo (icono + nombre + detalle) con sus acciones; en móvil las acciones pasan a una segunda línea. */
const icono = (
  <svg className="w-4 h-4 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
      d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
)

export default function FilaArchivo({ nombre, detalle, children }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
      <div className="flex items-center gap-3 flex-1 min-w-[14rem]">
        <div className="w-8 h-8 bg-green-50 rounded-lg flex items-center justify-center flex-shrink-0">{icono}</div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate" title={nombre}>{nombre}</p>
          <p className="text-xs text-gray-400">{detalle}</p>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-wrap pl-11 sm:pl-0">{children}</div>
    </div>
  )
}
