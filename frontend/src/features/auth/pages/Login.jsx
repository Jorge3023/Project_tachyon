import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/features/auth/AuthContext'

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

  const [verClave, setVerClave] = useState(false)
  const puntos = [
    ['Detecta tus columnas solo', 'Sube cualquier Excel o CSV; tú confirmas o corriges.'],
    ['Dashboards a tu medida', 'Gráficas, mapas y filtros que editas y guardas.'],
    ['Exporta y comparte', 'Imagen, PDF, PowerPoint, Excel o CSV; comparte por correo.'],
  ]

  return (
    <div className="min-h-screen bg-gray-50 grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">

      {/* Panel de marca (solo pantallas anchas) */}
      <aside className="hidden lg:flex flex-col justify-between p-12 text-white bg-gradient-to-br from-brand-900 via-brand-700 to-brand-600 relative overflow-hidden">
        <div aria-hidden="true" className="absolute -right-24 -bottom-24 w-96 h-96 rounded-full bg-white/5" />
        <div aria-hidden="true" className="absolute right-20 bottom-40 w-40 h-40 rounded-full bg-white/5" />
        <div className="flex items-center gap-3 relative">
          <div className="w-9 h-9 rounded-lg bg-white/15 flex items-center justify-center">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
          </div>
          <span className="text-lg font-semibold">Tachyon</span>
        </div>
        <div className="relative max-w-md">
          <h2 className="text-3xl font-semibold leading-tight">De tu Excel a un dashboard, sin fórmulas ni configuraciones.</h2>
          <ul className="mt-8 space-y-5">
            {puntos.map(([t, d]) => (
              <li key={t} className="flex gap-3">
                <span aria-hidden="true" className="mt-0.5 w-5 h-5 rounded-full bg-white/15 flex items-center justify-center text-[11px] flex-shrink-0">✓</span>
                <span><span className="block text-sm font-medium">{t}</span><span className="block text-sm text-white/70">{d}</span></span>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-white/50 relative">Acceso restringido — solo personal autorizado</p>
      </aside>

      {/* Formulario */}
      <main className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="lg:hidden text-center mb-8">
            <div className="inline-flex items-center justify-center w-12 h-12 bg-brand-600 rounded-xl mb-4">
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
            </div>
            <h1 className="text-xl font-semibold text-gray-900">Tachyon</h1>
            <p className="text-sm text-gray-500 mt-1">Análisis de tus archivos Excel y CSV</p>
          </div>
          <div className="hidden lg:block mb-6">
            <h1 className="text-2xl font-semibold text-gray-900">Bienvenido de nuevo</h1>
            <p className="text-sm text-gray-500 mt-1">Entra con tu correo y contraseña.</p>
          </div>

          <div className="card p-6">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label htmlFor="correo" className="block text-sm text-gray-600 mb-1.5">Correo</label>
                <input id="correo" type="email" className="input" placeholder="usuario@empresa.com" autoComplete="username"
                  value={correo} onChange={e => setCorreo(e.target.value)} required autoFocus />
              </div>
              <div>
                <label htmlFor="clave" className="block text-sm text-gray-600 mb-1.5">Contraseña</label>
                <div className="relative">
                  <input id="clave" type={verClave ? 'text' : 'password'} className="input pr-16" placeholder="••••••••" autoComplete="current-password"
                    value={password} onChange={e => setPassword(e.target.value)} required />
                  <button type="button" onClick={() => setVerClave(v => !v)} aria-pressed={verClave}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-gray-700 px-2 py-1">
                    {verClave ? 'Ocultar' : 'Ver'}
                  </button>
                </div>
              </div>

              {error && <p role="alert" className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">{error}</p>}

              <button type="submit" className="btn-primary w-full justify-center py-2.5" disabled={cargando}>
                {cargando ? 'Verificando…' : 'Entrar al sistema'}
              </button>
            </form>
          </div>
          <p className="lg:hidden text-center text-xs text-gray-400 mt-6">Acceso restringido — solo personal autorizado</p>
        </div>
      </main>
    </div>
  )
}
