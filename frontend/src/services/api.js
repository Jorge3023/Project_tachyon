import axios from 'axios'

// URL del backend: define VITE_API_URL en el build (ver frontend/.env.example).
// En desarrollo (npm run dev) usa http://localhost:8000 si no la defines.
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://localhost:8000' : ''),
  timeout: 30000,
})

api.interceptors.response.use(
  res => res,
  err => {
    const url = err.config?.url || ''
    const status = err.response?.status

    // Solo desloguear si es 401 Y NO es el endpoint de upload
    // (el upload puede devolver 401 por contraseña incorrecta, no por sesión)
    if (status === 401 && !url.includes('/archivos/upload')) {
      localStorage.removeItem('token')
      window.location.href = import.meta.env.BASE_URL
    }

    return Promise.reject(err)
  }
)

export default api