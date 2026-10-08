import api from './client'

export const cargaApi = {
  subirRecibos: (file: File, ejercicio: number) => {
    const form = new FormData()
    form.append('file', file)
    form.append('ejercicio', String(ejercicio))
    return api.post('/carga/recibos', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },

  subirDiario: (file: File, ejercicio: number, tipo_carga: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('ejercicio', String(ejercicio))
    form.append('tipo_carga', tipo_carga)
    return api.post('/carga/diario', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },

  historial: () => api.get('/carga/historial'),

  resumen: (cargaId: string) => api.get(`/carga/${cargaId}/resumen`),

  incidencias: (cargaId: string, params?: { tipo?: string; estado?: string }) =>
    api.get(`/carga/${cargaId}/incidencias`, { params }),

  resolverIncidencia: (cargaId: string, incidenciaId: string, resolucion: string) =>
    api.patch(`/carga/${cargaId}/incidencias/${incidenciaId}/resolver`, null, {
      params: { resolucion },
    }),

  cerrarCarga: (cargaId: string) => api.patch(`/carga/${cargaId}/cerrar`),

  listarHistorico: () => api.get('/carga/historico'),
  eliminarHistorico: (cargaId: string) => api.delete(`/carga/historico/${cargaId}`),

  detalleRecibos: (cargaId: string, params?: { tipo_negocio?: string; ramo?: string; compania?: string; page?: number; page_size?: number }) =>
    api.get(`/carga/${cargaId}/recibos`, { params }),

  detalleApuntes: (cargaId: string, params?: { estado?: string; tipo_cuenta?: string; mes?: number; page?: number; page_size?: number }) =>
    api.get(`/carga/${cargaId}/apuntes`, { params }),
}
