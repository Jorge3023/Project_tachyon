import { useState } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'

// Pantalla de primer ingreso: el usuario elige su nombre de usuario (una sola vez).
export default function ElegirUsername() {
  const { usuario, actualizarUsuario, logout } = useAuth()
  const [username, setUsername] = useState('')
  const [error, setError] = useState('')
  const [guardando, setGuardando] = useState(false)

  const valido = /^[A-Za-z0-9_.]{3,20}$/.test(username)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!valido) return
    setError('')
    setGuardando(true)
    try {
      const res = await api.post('/auth/username', { username })
      actualizarUsuario(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo guardar. Intenta de nuevo.')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-xl font-semibold text-gray-900">¡Bienvenido!</h1>
          <p className="text-sm text-gray-500 mt-1">
            Es tu primer ingreso con <span className="font-medium text-gray-700">{usuario?.correo}</span>.
            Elige el nombre de usuario con el que te verán los demás.
          </p>
        </div>

        <div className="card">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-600 mb-1.5">Nombre de usuario</label>
              <input
                className="input"
                placeholder="ej. ana.garcia"
                value={username}
                onChange={e => setUsername(e.target.value.trim())}
                maxLength={20}
                autoFocus
              />
              <p className="text-xs text-gray-400 mt-1.5">
                De 3 a 20 caracteres: letras, números, punto o guion bajo. No podrás cambiarlo después.
              </p>
            </div>

            {error && <p className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}

            <button type="submit" className="btn-primary w-full justify-center py-2.5" disabled={!valido || guardando}>
              {guardando ? 'Guardando…' : 'Continuar'}
            </button>
          </form>
        </div>

        <button onClick={logout} className="block mx-auto mt-5 text-xs text-gray-400 hover:text-gray-600">
          Cerrar sesión
        </button>
      </div>
    </div>
  )
}
