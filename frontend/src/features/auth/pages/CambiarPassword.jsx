import { useAuth } from '@/features/auth/AuthContext'
import FormPassword from '@/features/auth/components/FormPassword'

// Pantalla obligatoria cuando la contraseña es temporal (la puso el administrador): antes de ver nada,
// la persona elige una que solo ella conozca.
export default function CambiarPassword() {
  const { usuario, logout } = useAuth()

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <h1 className="text-xl font-semibold text-gray-900">Elige tu contraseña</h1>
          <p className="text-sm text-gray-500 mt-1">
            La contraseña con la que entraste a <span className="font-medium text-gray-700">{usuario?.correo}</span> es
            temporal. Cámbiala por una que solo tú conozcas.
          </p>
        </div>

        <div className="card">
          {/* Al guardar, la sesión se actualiza y esta pantalla da paso a la siguiente */}
          <FormPassword etiquetaActual="Contraseña temporal" textoBoton="Guardar y continuar" />
        </div>

        <button onClick={logout} className="block mx-auto mt-5 text-xs text-gray-400 hover:text-gray-600">
          Cerrar sesión
        </button>
      </div>
    </div>
  )
}
