import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

/* En pantallas anchas la barra lateral va fija; en móvil se abre con el botón ☰ y se cierra al navegar. */
export default function AppLayout({ children }) {
  const [abierto, setAbierto] = useState(false)
  const { pathname } = useLocation()
  useEffect(() => { setAbierto(false) }, [pathname])
  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {abierto && <div className="fixed inset-0 bg-black/30 z-30 md:hidden" onClick={() => setAbierto(false)} aria-hidden="true" />}
      <div className={`fixed inset-y-0 left-0 z-40 transition-transform duration-200 md:static md:translate-x-0 ${abierto ? 'translate-x-0' : '-translate-x-full'}`}>
        <Sidebar />
      </div>
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <div className="md:hidden flex items-center gap-3 bg-white border-b border-gray-100 px-4 py-2.5">
          <button type="button" onClick={() => setAbierto(true)} aria-label="Abrir menú" aria-expanded={abierto}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-600 hover:bg-gray-100">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
          </button>
          <span className="text-sm font-semibold text-gray-900">Tachyon</span>
        </div>
        {children}
      </div>
    </div>
  )
}
