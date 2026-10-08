import api from './client'

export const crossSellingApi = {
  getEjercicios: async (): Promise<number[]> => {
    const res = await api.get('/cross-selling/ejercicios')
    return res.data
  },

  getParametros: async () => {
    const res = await api.get('/cross-selling/parametros')
    return res.data
  },

  updateParametros: async (data: any) => {
    const res = await api.put('/cross-selling/parametros', data)
    return res.data
  },

  recalcular: async (ejercicio: number) => {
    const res = await api.post(`/cross-selling/recalcular?ejercicio=${ejercicio}`)
    return res.data as { oportunidades: number; alertas: number }
  },

  getOportunidades: async (ejercicio: number, filters?: {
    ramo?: string
    score_min?: number
    sin_accionar?: boolean
  }) => {
    const params: any = { ejercicio }
    if (filters?.ramo) params.ramo = filters.ramo
    if (filters?.score_min !== undefined) params.score_min = filters.score_min
    if (filters?.sin_accionar !== undefined) params.sin_accionar = filters.sin_accionar
    const res = await api.get('/cross-selling/oportunidades', { params })
    return res.data as any[]
  },

  getAlertas: async (ejercicio: number, risk_min?: number) => {
    const params: any = { ejercicio }
    if (risk_min !== undefined) params.risk_min = risk_min
    const res = await api.get('/cross-selling/alertas', { params })
    return res.data as any[]
  },

  getEfectividad: async () => {
    const res = await api.get('/cross-selling/efectividad')
    return res.data
  },

  getClientes: async () => {
    const res = await api.get('/cross-selling/clientes')
    return res.data as any[]
  },

  uploadClientes: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const res = await api.post('/cross-selling/clientes/carga', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data as { insertados: number; actualizados: number }
  },

  createAccion: async (data: {
    tipo: string
    oportunidad_id?: string
    alerta_id?: string
    tomador: string
    ramo_objetivo?: string
    estado?: string
    notas?: string
    margen_conseguido?: number
  }) => {
    const res = await api.post('/cross-selling/acciones', data)
    return res.data
  },

  updateAccion: async (id: string, data: {
    estado?: string
    notas?: string
    margen_conseguido?: number
  }) => {
    const res = await api.patch(`/cross-selling/acciones/${id}`, data)
    return res.data
  },

  getClienteDetalle: async (tomador: string, ejercicio: number) => {
    const res = await api.get('/cross-selling/cliente-detalle', { params: { tomador, ejercicio } })
    return res.data
  },

  getAuxiliares: async (ejercicio?: number) => {
    const res = await api.get('/cross-selling/auxiliares', { params: ejercicio ? { ejercicio } : {} })
    return res.data as { auxiliar: string; participa: boolean; n_recibos: number; prima_total: number }[]
  },

  updateAuxiliarParticipacion: async (auxiliar: string, participa: boolean) => {
    const res = await api.patch('/cross-selling/auxiliares/participacion', { auxiliar, participa })
    return res.data
  },

  getRamoStats: async (ejercicio: number) => {
    const res = await api.get('/cross-selling/ramo-stats', { params: { ejercicio } })
    return res.data as { ramo: string; ramo_categoria: string | null; prima_media: number; margen_medio: number; n_clientes: number }[]
  },

  calcularRamoStats: async (ejercicio: number) => {
    const res = await api.post(`/cross-selling/ramo-stats/calcular?ejercicio=${ejercicio}`)
    return res.data as { ejercicio: number; ramos: any[] }
  },

  getOcurrencias: async (ejercicio: number) => {
    const res = await api.get('/cross-selling/ocurrencias', { params: { ejercicio } })
    return res.data as {
      por_ramo_recomendado: { ramo: string; n_clientes: number; prima_potencial: number; margen_potencial: number }[]
      por_combinacion: { combinacion: string; ramo_base: string; ramo_objetivo: string; n_clientes: number; prima_potencial: number }[]
    }
  },
}
