import { useState, useEffect } from 'react'
import api from '@/shared/api'
import PageHeader from '@/shared/components/PageHeader'
import { useAuth } from '@/features/auth/AuthContext'
import EstadoSistema from '@/features/usuarios/components/EstadoSistema'

// Solo administradores: crear cuentas (correo + contraseña temporal) y activar/desactivar.
export default function Usuarios() {
  const { usuario } = useAuth()
  const [lista, setLista] = useState([])
  const [correo, setCorreo] = useState('')
  const [password, setPassword] = useState('')
  const [rol, setRol] = useState('operador')
  const [msg, setMsg] = useState(null)
  const [trabajando, setTrabajando] = useState(false)

  const cargar = () => api.get('/usuarios').then(r => setLista(r.data)).catch(() => {})
  useEffect(() => { cargar() }, [])

  const crear = async (e) => {
    e.preventDefault()
    setMsg(null); setTrabajando(true)
    try {
      await api.post('/usuarios', { correo, password, rol })
      setMsg({ tipo: 'ok', texto: `Cuenta creada para ${correo.trim().toLowerCase()}. Entrégale el correo y la contraseña; elegirá su nombre de usuario al entrar.` })
      setCorreo(''); setPassword('')
      cargar()
    } catch (err) {
      setMsg({ tipo: 'error', texto: err.response?.data?.detail || 'No se pudo crear la cuenta' })
    } finally { setTrabajando(false) }
  }

  const alternar = async (u) => {
    try {
      await api.patch(`/usuarios/${u.id}`, { activo: !u.activo })
      cargar()
    } catch (err) {
      setMsg({ tipo: 'error', texto: err.response?.data?.detail || 'No se pudo cambiar el estado' })
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <PageHeader titulo="Usuarios"
        subtitulo="Crea cuentas y controla quién puede entrar. Los datos de cada usuario son privados, ni tú los ves." />

      <main className="flex-1 overflow-y-auto p-4 md:p-6 space-y-5">
        <EstadoSistema />
        <div className="card">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Nueva cuenta</h2>
          <form onSubmit={crear} className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
            <div className="md:col-span-1">
              <label className="block text-xs text-gray-600 mb-1.5">Correo</label>
              <input type="email" className="input" value={correo} onChange={e => setCorreo(e.target.value)}
                placeholder="persona@empresa.com" required />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1.5">Contraseña temporal (mín. 8)</label>
              <input type="text" className="input" value={password} onChange={e => setPassword(e.target.value)}
                minLength={8} required autoComplete="off" />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1.5">Rol</label>
              <select className="input" value={rol} onChange={e => setRol(e.target.value)}>
                <option value="operador">Usuario</option>
                <option value="admin">Administrador</option>
              </select>
            </div>
            <button type="submit" className="btn-primary justify-center py-2.5" disabled={trabajando}>
              {trabajando ? 'Creando…' : 'Crear cuenta'}
            </button>
          </form>
          {msg && (
            <div className={`mt-4 px-4 py-3 rounded-lg text-sm ` +
              (msg.tipo === 'ok' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700')}>
              {msg.texto}
            </div>
          )}
        </div>

        <div className="card">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Cuentas</h2>
          <div className="divide-y divide-gray-50">
            {lista.map(u => (
              <div key={u.id} className="flex items-center gap-4 py-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {u.username || <span className="text-gray-400 font-normal">sin nombre de usuario aún</span>}
                  </p>
                  <p className="text-xs text-gray-400 truncate">{u.correo} · {u.rol === 'admin' ? 'Administrador' : 'Usuario'}</p>
                </div>
                {u.pendiente_username && <span className="badge-warn">Pendiente de primer ingreso</span>}
                <span className={u.activo ? 'badge-good' : 'badge-bad'}>{u.activo ? 'Activo' : 'Desactivado'}</span>
                {u.id !== usuario?.id && (
                  <button onClick={() => alternar(u)} className="btn-ghost text-xs">
                    {u.activo ? 'Desactivar' : 'Activar'}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}
