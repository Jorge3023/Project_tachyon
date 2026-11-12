import { useState } from 'react'
import { useAuth } from '@/features/auth/AuthContext'

const MIN = 8

/* Formulario para cambiar la propia contraseña. Lo usan la pantalla de primer ingreso y el perfil. */
export default function FormPassword({ etiquetaActual = 'Contraseña actual', textoBoton = 'Cambiar contraseña', onListo }) {
  const { cambiarPassword } = useAuth()
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [repetida, setRepetida] = useState('')
  const [error, setError] = useState('')
  const [guardando, setGuardando] = useState(false)

  const noCoincide = repetida.length > 0 && nueva !== repetida
  const valido = actual.length > 0 && nueva.length >= MIN && nueva === repetida && nueva !== actual

  const enviar = async (e) => {
    e.preventDefault()
    if (!valido) return
    setError(''); setGuardando(true)
    try {
      await cambiarPassword(actual, nueva)
      setActual(''); setNueva(''); setRepetida('')
      onListo?.()
    } catch (err) {
      setError(err.response?.data?.detail || 'No se pudo cambiar la contraseña. Intenta de nuevo.')
    } finally { setGuardando(false) }
  }

  return (
    <form onSubmit={enviar} className="space-y-3 text-left">
      <div>
        <label className="block text-xs text-gray-600 mb-1.5" htmlFor="pw-actual">{etiquetaActual}</label>
        <input id="pw-actual" type="password" className="input" value={actual} onChange={e => setActual(e.target.value)}
          autoComplete="current-password" required />
      </div>
      <div>
        <label className="block text-xs text-gray-600 mb-1.5" htmlFor="pw-nueva">Contraseña nueva</label>
        <input id="pw-nueva" type="password" className="input" value={nueva} onChange={e => setNueva(e.target.value)}
          autoComplete="new-password" minLength={MIN} maxLength={72} required />
        <p className="text-xs text-gray-400 mt-1.5">Mínimo {MIN} caracteres. Al cambiarla se cierran tus otras sesiones.</p>
      </div>
      <div>
        <label className="block text-xs text-gray-600 mb-1.5" htmlFor="pw-repetida">Repite la contraseña nueva</label>
        <input id="pw-repetida" type="password" className="input" value={repetida} onChange={e => setRepetida(e.target.value)}
          autoComplete="new-password" required aria-invalid={noCoincide} />
        {noCoincide && <p className="text-xs text-red-600 mt-1.5">Las contraseñas no coinciden.</p>}
        {nueva.length >= MIN && nueva === actual && <p className="text-xs text-red-600 mt-1.5">Debe ser distinta de la actual.</p>}
      </div>
      {error && <p role="alert" className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}
      <button type="submit" className="btn-primary w-full justify-center py-2.5" disabled={!valido || guardando}>
        {guardando ? 'Guardando…' : textoBoton}
      </button>
    </form>
  )
}
