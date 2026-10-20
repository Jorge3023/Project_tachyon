import { Link } from 'react-router-dom'

/**
 * Encabezado común de todas las páginas internas, para que título, migas y acciones
 * tengan siempre el mismo lugar y se acomoden igual en móvil.
 *  - migas:    [{ texto, to?, onClick?, accion? }]  (`accion` = botón en vez de enlace; la última es la página actual, sin enlace)
 *  - titulo:   texto o nodo (p. ej. un formulario de renombrado)
 *  - subtitulo: línea secundaria
 *  - acciones: botones alineados a la derecha (bajan debajo del título en pantallas chicas)
 *  - children: fila extra bajo el título (avisos, errores…)
 */
export default function PageHeader({ migas, titulo, subtitulo, acciones, children }) {
  return (
    <header className="bg-white border-b border-gray-100 px-4 md:px-6 py-3.5 flex-shrink-0">
      {migas?.length > 0 && (
        <nav aria-label="Ruta" className="text-xs text-gray-400 mb-1 truncate">
          {migas.map((m, i) => (
            <span key={i}>
              {i > 0 && <span className="mx-1" aria-hidden="true">/</span>}
              {m.accion
                ? <button type="button" onClick={m.accion} className="hover:text-gray-600">{m.texto}</button>
                : m.to
                ? <Link to={m.to} onClick={m.onClick} className="hover:text-gray-600">{m.texto}</Link>
                : <span title={m.texto} aria-current={i === migas.length - 1 ? 'page' : undefined}>{m.texto}</span>}
            </span>
          ))}
        </nav>
      )}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-60">
          {typeof titulo === 'string'
            ? <h1 className="text-base font-semibold text-gray-900 truncate">{titulo}</h1>
            : titulo}
          {subtitulo && <p className="text-xs text-gray-400 mt-0.5">{subtitulo}</p>}
        </div>
        {acciones && <div className="flex items-center gap-2 flex-wrap">{acciones}</div>}
      </div>
      {children}
    </header>
  )
}
