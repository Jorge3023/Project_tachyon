import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '@/features/auth/AuthContext'
import { useProyectos } from '@/features/proyectos/ProyectosContext'
import { usePrincipal } from '@/features/dashboard/PrincipalContext'
import api from '@/shared/api'

const claseEnlace = ({ isActive }) =>
  'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors duration-100 ' +
  (isActive ? 'bg-brand-50 text-brand-700 font-medium' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50')

const Icono = ({ d }) => (
  <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={d} />
  </svg>
)

const ICONOS = {
  inicio:   'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z',
  resumen:  'M4 6h16M4 12h10M4 18h16',
  archivos: 'M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z',
  usuarios: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z',
  carpeta:  'M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7z',
}

function Enlace({ to, icono, end, children }) {
  return <NavLink to={to} end={end} className={claseEnlace}><Icono d={ICONOS[icono]} />{children}</NavLink>
}

export default function Sidebar() {
  const { usuario, logout } = useAuth()
  const navigate = useNavigate()
  const { proyectos, recargar } = useProyectos()
  const { principal } = usePrincipal()
  const [creando, setCreando] = useState(false)
  const [nuevo,   setNuevo]   = useState('')
  const [errorPr, setErrorPr] = useState('')

  const crearProyecto = async (e) => {
    e.preventDefault(); setErrorPr('')
    try {
      const r = await api.post('/proyectos', { nombre: nuevo })
      await recargar(); setCreando(false); setNuevo('')
      navigate(`/proyecto/${r.data.id}`)
    } catch (err) { setErrorPr(err.response?.data?.detail || 'No se pudo crear') }
  }

  const handleLogout = () => {
    logout()
    navigate('/')
  }

  const iniciales = usuario?.nombre
    ?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || 'U'

  return (
    <aside className="w-56 min-w-[224px] bg-white border-r border-gray-100 flex flex-col h-screen">

      {/* Logo */}
      <div className="px-5 py-5 border-b border-gray-100">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center flex-shrink-0">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-900 leading-tight">Tachyon</p>
            <p className="text-xs text-gray-400">Análisis de datos</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        <p className="text-xs text-gray-400 px-2 pb-2 uppercase tracking-wider">Principal</p>
        <Enlace to="/dashboard" icono="inicio" end>Inicio</Enlace>
        {principal && <Enlace to="/resumen" icono="resumen">Resumen</Enlace>}
        <Enlace to="/archivos" icono="archivos">Mis archivos</Enlace>
        {usuario?.rol === 'admin' && <Enlace to="/usuarios" icono="usuarios">Usuarios</Enlace>}

        {/* Proyectos: carpetas propias para agrupar archivos */}
        <div className="flex items-center justify-between px-2 pt-5 pb-2">
          <p className="text-xs text-gray-400 uppercase tracking-wider">Proyectos</p>
          <button onClick={() => { setCreando(c => !c); setErrorPr('') }} title="Nuevo proyecto" aria-label="Nuevo proyecto"
            className="w-5 h-5 rounded flex items-center justify-center text-gray-400 hover:text-brand-600 hover:bg-brand-50">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </button>
        </div>
        {creando && (
          <form onSubmit={crearProyecto} className="px-1 pb-2">
            <input autoFocus value={nuevo} onChange={e => setNuevo(e.target.value)} maxLength={40}
              placeholder="Nombre del proyecto" aria-label="Nombre del nuevo proyecto" className="input py-1.5 text-sm" />
            {errorPr && <p className="text-xs text-red-600 mt-1">{errorPr}</p>}
            <div className="flex gap-1 mt-1.5">
              <button type="submit" className="btn-primary text-xs py-1 flex-1 justify-center">Crear</button>
              <button type="button" className="btn-ghost text-xs" onClick={() => { setCreando(false); setNuevo(''); setErrorPr('') }}>Cancelar</button>
            </div>
          </form>
        )}
        {proyectos.length === 0 && !creando && (
          <p className="text-xs text-gray-400 px-3 leading-relaxed">Crea un proyecto con “+” para agrupar tus archivos.</p>
        )}
        {proyectos.map(p => (
          <NavLink key={p.id} to={`/proyecto/${p.id}`} className={claseEnlace}>
            <Icono d={ICONOS.carpeta} />
            <span className="truncate flex-1">{p.nombre}</span>
            <span className="text-xs text-gray-400">{p.num_archivos}</span>
          </NavLink>
        ))}
      </nav>

      {/* Usuario */}
      <div className="px-3 py-4 border-t border-gray-100">
        <div className="flex items-center gap-3 px-2 mb-2">
          <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center text-brand-700 text-xs font-semibold flex-shrink-0">
            {iniciales}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">{usuario?.nombre}</p>
            <p className="text-xs text-gray-400 capitalize">{usuario?.rol}</p>
          </div>
        </div>
        <button onClick={handleLogout} className="btn-ghost w-full justify-center text-red-500 hover:text-red-700 hover:bg-red-50 mt-1">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          Cerrar sesión
        </button>
      </div>
    </aside>
  )
}
