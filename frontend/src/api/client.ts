import axios from 'axios'
import { useAuthStore } from '../store/authStore'
import { apiError } from '../utils/errorHandler'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let isRefreshing = false
let refreshQueue: Array<(token: string) => void> = []

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true

      if (isRefreshing) {
        return new Promise((resolve) => {
          refreshQueue.push((token) => {
            original.headers.Authorization = `Bearer ${token}`
            resolve(api(original))
          })
        })
      }

      isRefreshing = true
      try {
        const refreshToken = useAuthStore.getState().refreshToken
        const res = await axios.post('/api/auth/refresh', { refresh_token: refreshToken })
        const { access_token, refresh_token } = res.data
        useAuthStore.getState().setTokens(access_token, refresh_token)
        refreshQueue.forEach((cb) => cb(access_token))
        refreshQueue = []
        original.headers.Authorization = `Bearer ${access_token}`
        return api(original)
      } catch {
        useAuthStore.getState().logout()
        return Promise.reject(error)
      } finally {
        isRefreshing = false
      }
    }
    if ((import.meta as any).env?.DEV && error.response && error.response.status !== 401) {
      console.error(
        `[API] ${error.config?.method?.toUpperCase()} ${error.config?.url} → ${error.response.status}:`,
        apiError(error),
      )
    }
    return Promise.reject(error)
  }
)

export default api
