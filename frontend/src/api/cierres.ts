import apiClient from './client'

export interface CierresResumenApuntes {
  ejercicio: number
  total: number
  punteados: number
}

export interface CierresResumenExtractos {
  ejercicio: number
  total: number
  conciliados: number
}

export interface CierresResumen {
  apuntes: CierresResumenApuntes[]
  extractos: CierresResumenExtractos[]
}

export const cierresApi = {
  getResumen: () => apiClient.get<CierresResumen>('/cierres/resumen'),
}
