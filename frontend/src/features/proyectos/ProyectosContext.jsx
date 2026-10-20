import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '@/shared/api'
import { useAuth } from '@/features/auth/AuthContext'

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
