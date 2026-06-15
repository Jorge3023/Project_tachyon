import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
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
      window.location.href = '/login'
    }

    return Promise.reject(err)
  }
)

export default api