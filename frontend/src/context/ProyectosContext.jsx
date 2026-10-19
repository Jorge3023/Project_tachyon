import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../services/api'
import { useAuth } from './AuthContext'

const ProyectosContext = createContext({ proyectos: [], recargar: () => {} })

/* Lista de proyectos del usuario (carpetas para agrupar archivos). Se comparte entre la barra lateral y las páginas. */
export function ProyectosProvider({ children }) {
  const { usuario } = useAuth()
  const [proyectos, setProyectos] = useState([])

  const recargar = useCallback(() => {
    if (!usuario) { setProyectos([]); return Promise.resolve() }
    return api.get('/proyectos').then(r => setProyectos(r.data)).catch(() => {})
  }, [usuario])

  useEffect(() => { recargar() }, [recargar])

  return <ProyectosContext.Provider value={{ proyectos, recargar }}>{children}</ProyectosContext.Provider>
}

export const useProyectos = () => useContext(ProyectosContext)
