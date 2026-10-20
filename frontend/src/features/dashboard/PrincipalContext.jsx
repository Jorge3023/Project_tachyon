import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '@/shared/api'
import { useAuth } from '@/features/auth/AuthContext'

const PrincipalContext = createContext({ principal: null, cargando: true, fijar: async () => {}, quitar: async () => {}, recargar: async () => {} })

/* Dashboard principal del usuario: el que se muestra al entrar. Se comparte entre la página de inicio, la barra lateral y el editor. */
export function PrincipalProvider({ children }) {
  const { usuario } = useAuth()
  const [principal, setPrincipal] = useState(null)
  const [cargando, setCargando] = useState(true)

  const recargar = useCallback(async () => {
    if (!usuario) { setPrincipal(null); setCargando(false); return }
    try { setPrincipal((await api.get('/me/dashboard-principal')).data.principal) }
    catch { setPrincipal(null) }
    finally { setCargando(false) }
  }, [usuario])

  useEffect(() => { setCargando(true); recargar() }, [recargar])

  const fijar = useCallback(async (archivoId, vistaId = null) => {
    const r = await api.put('/me/dashboard-principal', { archivo_id: Number(archivoId), vista_id: vistaId })
    setPrincipal(r.data.principal)
  }, [])
  const quitar = useCallback(async () => {
    await api.delete('/me/dashboard-principal'); setPrincipal(null)
  }, [])

  return <PrincipalContext.Provider value={{ principal, cargando, fijar, quitar, recargar }}>{children}</PrincipalContext.Provider>
}

export const usePrincipal = () => useContext(PrincipalContext)
