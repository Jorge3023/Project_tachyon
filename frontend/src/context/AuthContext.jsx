import { createContext, useContext, useState, useEffect } from 'react'
import api from '../services/api'

const AuthContext = createContext(null)
const AUTO_LOGOUT_MS = 10 * 60 * 1000

export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null)
  const [cargando, setCargando] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`
      api.get('/auth/me')
        .then(res => setUsuario(res.data))
        .catch(() => localStorage.removeItem('token'))
        .finally(() => setCargando(false))
    } else {
      setCargando(false)
    }
  }, [])

  const login = async (correo, password) => {
    const form = new URLSearchParams()
    form.append('username', correo)
    form.append('password', password)
    const res = await api.post('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
    localStorage.setItem('token', res.data.access_token)
    api.defaults.headers.common['Authorization'] = `Bearer ${res.data.access_token}`
    setUsuario(res.data.usuario)
    return res.data
  }

  const logout = () => {
    localStorage.removeItem('token')
    delete api.defaults.headers.common['Authorization']
    setUsuario(null)
  }

  useEffect(() => {
    if (!usuario) return

    let timeoutId
    const eventos = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart']

    const reiniciarTemporizador = () => {
      clearTimeout(timeoutId)
      timeoutId = setTimeout(() => {
        logout()
      }, AUTO_LOGOUT_MS)
    }

    eventos.forEach((evento) => window.addEventListener(evento, reiniciarTemporizador))
    reiniciarTemporizador()

    return () => {
      clearTimeout(timeoutId)
      eventos.forEach((evento) => window.removeEventListener(evento, reiniciarTemporizador))
    }
  }, [usuario])

  return (
    <AuthContext.Provider value={{ usuario, login, logout, cargando }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
