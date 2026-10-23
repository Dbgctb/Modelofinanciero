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

  listarAnyosIceaDisponibles: () => api.get('/admin/tasas-mercado/icea-anyos-disponibles'),

  poblarTasasIcea: (anyo: number) => api.post('/admin/tasas-mercado/poblar-icea', { anyo }),

  resetDatos: () => api.post('/admin/reset-datos'),

  listarAuxiliaresComision: (params?: { anyo?: number }) =>
    api.get('/admin/auxiliares-comision', { params }),

  listarAuxiliaresComisionAnyos: () => api.get('/admin/auxiliares-comision/anyos'),

  crearAuxiliarComision: (datos: { anyo: number; auxiliar: string; comision_colaborador: number }) =>
    api.post('/admin/auxiliares-comision', datos),

  actualizarAuxiliarComision: (id: string, datos: { comision_colaborador?: number; pct_retencion?: number }) =>
    api.patch(`/admin/auxiliares-comision/${id}`, datos),

  eliminarAuxiliarComision: (id: string) => api.delete(`/admin/auxiliares-comision/${id}`),

  importarAuxiliaresComisionCsv: (anyo: number, file: File) => {
    const fd = new FormData()
    fd.append('anyo', String(anyo))
    fd.append('file', file)
    return api.post('/admin/auxiliares-comision/importar-csv', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}
