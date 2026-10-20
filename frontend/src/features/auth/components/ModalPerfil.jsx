import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import api from '@/shared/api'
import { useAuth } from '@/features/auth/AuthContext'
import Avatar from '@/shared/components/Avatar'
import { etiquetaRol } from '@/shared/roles'

const LADO = 256   // la foto se recorta cuadrada y se reduce a 256 px: pesa unos 20-40 KB

/** Recorta al centro y reduce la imagen elegida; devuelve un Blob JPEG listo para enviar. */
async function prepararFoto(archivo) {
  if (!/^image\/(jpeg|png|webp|gif|bmp)$/.test(archivo.type)) throw new Error('Elige una imagen JPG, PNG o WebP')
  const bmp = await createImageBitmap(archivo)
  const lado = Math.min(bmp.width, bmp.height)
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = LADO
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, LADO, LADO)
  ctx.drawImage(bmp, (bmp.width - lado) / 2, (bmp.height - lado) / 2, lado, lado, 0, 0, LADO, LADO)
  bmp.close?.()
  return new Promise((ok, fallo) => canvas.toBlob(b => b ? ok(b) : fallo(new Error('No se pudo procesar la imagen')), 'image/jpeg', 0.85))
}

export default function ModalPerfil({ onCerrar }) {
  const { usuario, actualizarUsuario } = useAuth()
  const entrada = useRef(null)
  const [trabajando, setTrabajando] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const tecla = e => { if (e.key === 'Escape') onCerrar() }
    window.addEventListener('keydown', tecla); return () => window.removeEventListener('keydown', tecla)
  }, [onCerrar])

  const elegir = async (e) => {
    const archivo = e.target.files?.[0]; e.target.value = ''
    if (!archivo) return
    setError(''); setTrabajando(true)
    try {
      const blob = await prepararFoto(archivo)
      const form = new FormData(); form.append('file', blob, 'perfil.jpg')
      const r = await api.put('/auth/avatar', form)
      actualizarUsuario(r.data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'No se pudo guardar la foto')
    } finally { setTrabajando(false) }
  }

  const quitar = async () => {
    setError(''); setTrabajando(true)
    try { const r = await api.delete('/auth/avatar'); actualizarUsuario(r.data) }
    catch { setError('No se pudo quitar la foto') }
    finally { setTrabajando(false) }
  }

  /* Portal: el menú lateral tiene transform, que encerraría el fondo del modal dentro de la barra. */
  return createPortal(
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onCerrar}>
      <div role="dialog" aria-modal="true" aria-label="Tu perfil" onClick={e => e.stopPropagation()}
        className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
        <div className="flex items-start justify-between">
          <h2 className="text-base font-semibold text-gray-900">Tu perfil</h2>
          <button onClick={onCerrar} aria-label="Cerrar" className="text-gray-400 hover:text-gray-700 -mt-1 -mr-1 w-8 h-8 rounded-lg hover:bg-gray-100">✕</button>
        </div>

        <div className="flex flex-col items-center text-center mt-4">
          <Avatar id={usuario.id} version={usuario.avatar_v} nombre={usuario.nombre} tamano="xl" />
          <p className="mt-3 text-sm font-semibold text-gray-900">{usuario.nombre}</p>
          <p className="text-xs text-gray-400">{usuario.correo} · {etiquetaRol(usuario.rol)}</p>
        </div>

        <input ref={entrada} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={elegir} aria-label="Elegir foto de perfil" />
        <div className="flex gap-2 justify-center mt-5">
          <button className="btn-primary text-xs" onClick={() => entrada.current?.click()} disabled={trabajando}>
            {trabajando ? 'Guardando…' : usuario.avatar_v ? 'Cambiar foto' : 'Subir foto'}
          </button>
          {usuario.avatar_v > 0 && <button className="btn-secondary text-xs" onClick={quitar} disabled={trabajando}>Quitar</button>}
        </div>
        <p className="text-[11px] text-gray-400 text-center mt-3">Se recorta en cuadrado y se reduce automáticamente. La ven tú y los administradores.</p>
        {error && <p role="alert" className="mt-3 text-xs text-red-700 bg-red-50 rounded-lg px-3 py-2">{error}</p>}
      </div>
    </div>,
    document.body
  )
}
