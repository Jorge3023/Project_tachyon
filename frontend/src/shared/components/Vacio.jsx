/** Estado vacío uniforme: icono tenue, título y una línea de ayuda. */
export default function Vacio({ titulo, children }) {
  return (
    <div className="text-center py-10 px-4">
      <svg className="w-10 h-10 mx-auto mb-3 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <p className="text-sm text-gray-600">{titulo}</p>
      {children && <p className="text-xs text-gray-400 mt-1">{children}</p>}
    </div>
  )
}
