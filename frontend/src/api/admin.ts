import api from './client'

export const adminApi = {
  listarTasas: (params?: { anyo?: number; tipo?: string; fuente?: string }) =>
    api.get('/admin/tasas-mercado', { params }),

  listarAnyos: () => api.get('/admin/tasas-mercado/anyos'),

  crearTasa: (datos: {
    fuente: string
    anyo: number
    tipo: string
    ramo_keyword?: string | null
    tasa_pct: number
    es_default?: boolean
    notas?: string
  }) => api.post('/admin/tasas-mercado', datos),

  actualizarTasa: (id: string, datos: {
    fuente?: string
    tasa_pct?: number
    es_default?: boolean
    notas?: string
  }) => api.patch(`/admin/tasas-mercado/${id}`, datos),

  eliminarTasa: (id: string) => api.delete(`/admin/tasas-mercado/${id}`),

  resetDatos: () => api.post('/admin/reset-datos'),
}
