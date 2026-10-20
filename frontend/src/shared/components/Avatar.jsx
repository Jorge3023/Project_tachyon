import { useState, useEffect } from 'react'
import api from '@/shared/api'

/* Las fotos requieren sesión, así que se piden con el token y se guardan como URL de objeto.
   La clave incluye la versión (avatar_v): al cambiar la foto se vuelve a pedir. */
const cache = new Map()   // "id:v" -> Promise<url | null>

function cargar(id, v) {
  const clave = `${id}:${v}`
  if (!cache.has(clave)) {
    cache.set(clave, api.get(`/usuarios/${id}/avatar`, { responseType: 'blob' })
      .then(r => URL.createObjectURL(r.data))
      .catch(() => null))
  }
  return cache.get(clave)
}

const TAMANOS = { xs: 'w-6 h-6 text-[10px]', sm: 'w-8 h-8 text-xs', md: 'w-10 h-10 text-sm', lg: 'w-16 h-16 text-xl', xl: 'w-24 h-24 text-3xl' }
const COLORES = ['bg-brand-100 text-brand-700', 'bg-emerald-100 text-emerald-700', 'bg-amber-100 text-amber-700', 'bg-violet-100 text-violet-700', 'bg-rose-100 text-rose-700']

export const iniciales = (texto) =>
  (texto || '').split(/[\s._@-]+/).filter(Boolean).map(p => p[0]).join('').slice(0, 2).toUpperCase() || 'U'

/** Foto de perfil (si la hay) o iniciales sobre un color estable por persona. */
export default function Avatar({ id, version = 0, nombre, tamano = 'sm', className = '' }) {
  const [url, setUrl] = useState(null)
  useEffect(() => {
    let vivo = true
    setUrl(null)
    if (id && version) cargar(id, version).then(u => { if (vivo) setUrl(u) })
    return () => { vivo = false }
  }, [id, version])
  const color = COLORES[(Number(id) || 0) % COLORES.length]
  return url
    ? <img src={url} alt="" className={`${TAMANOS[tamano]} rounded-full object-cover flex-shrink-0 ${className}`} />
    : <div aria-hidden="true" className={`${TAMANOS[tamano]} ${color} rounded-full flex items-center justify-center font-semibold flex-shrink-0 ${className}`}>{iniciales(nombre)}</div>
}
