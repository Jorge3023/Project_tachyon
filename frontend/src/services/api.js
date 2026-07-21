import axios from 'axios'

// --- MODIFICACIÓN AQUÍ ---
const api = axios.create({
  // Vite inyectará aquí tu URL de Render (ej. https://project-tachyon.onrender.com)
  baseURL: import.meta.env.VITE_API_URL, 
  timeout: 30000,
})
// -------------------------

api.interceptors.response.use(
  res => res,
  err => {
    const url = err.config?.url || ''
    const status = err.response?.status

    // Solo desloguear si es 401 Y NO es el endpoint de upload
    // (el upload puede devolver 401 por contraseña incorrecta, no por sesión)
    if (status === 401 && !url.includes('/archivos/upload')) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }

    return Promise.reject(err)
  }
)

export default api