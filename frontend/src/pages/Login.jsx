import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [correo, setCorreo] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setCargando(true)
    try {
      await login(correo, password)
      navigate('/dashboard')
    } catch (err) {
      if (err.response?.status === 401) setError('Correo o contraseña incorrectos')
      else if (!err.response) setError('No se pudo conectar con el servidor. Si lleva un rato sin usarse, puede tardar hasta 1 minuto en despertar: espera e intenta de nuevo.')
      else setError('Ocurrió un error en el servidor. Intenta de nuevo en unos momentos.')
    } finally {
      setCargando(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-brand-600 rounded-xl mb-4">
            <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-gray-900">Tachyon</h1>
          <p className="text-sm text-gray-500 mt-1">Análisis de tus archivos Excel y CSV</p>
        </div>

        {/* Card */}
        <div className="card">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-600 mb-1.5">Correo</label>
              <input
                type="email"
                className="input"
                placeholder="usuario@empresa.com"
                value={correo}
                onChange={e => setCorreo(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1.5">Contraseña</label>
              <input
                type="password"
                className="input"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
              />
            </div>

            {error && (
              <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>
            )}

            <button type="submit" className="btn-primary w-full justify-center py-2.5" disabled={cargando}>
              {cargando ? 'Verificando…' : 'Entrar al sistema'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-gray-400 mt-6">
          Acceso restringido — solo personal autorizado
        </p>
      </div>
    </div>
  )
}
