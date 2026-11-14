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

export interface Apunte {
  id: number
  ejercicio: number
  fecha: string
  cuenta: string
  descripcion_cuenta: string | null
  concepto: string | null
  recibo_norm: string | null
  asiento_key: string | null
  debe: number
  haber: number
  neto: number
  reconciled: boolean
  recon_rule: string | null
  recon_group_id: string | null
  es_nuevo: boolean
  es_huerfano: boolean
}

export interface Paginado<T> {
  total: number
  page: number
  page_size: number
  filas: T[]
}

export interface Tarea {
  tipo: string
  estado: 'en_curso' | 'terminada' | 'error'
  mensaje: string
  paso: number | null
  total: number | null
  resultado: any
  error: string | null
  segundos?: number
}

export interface Regla {
  rule_code: string
  rule_name: string
  description: string | null
  active: boolean
  priority: number
  tolerance_amount: number
  implementada: boolean
}

export interface CuentaControl {
  id?: number
  tipo: 'C' | 'D' | 'K' | 'L'
  name: string
  cuenta: string
  min_mov: number | null
  max_mov: number | null
  tolerance_pct: number | null
  active: boolean
}

export interface FiltroManual {
  ejercicios: number[]
  cuenta?: string
  recibo?: string
  asiento?: string
  concepto?: string
  solo_pendientes: boolean
}

export interface Bloque {
  grupo: string
  regla: string
  num_lineas: number
  suma: number
  min_ej: number
  max_ej: number
  estado: string
}

export const cierresApi = {
  getResumen: () => apiClient.get<CierresResumen>('/cierres/resumen'),
  getTarea: (taskId: string) => apiClient.get<Tarea>(`/cierres/tareas/${taskId}`),
  descargarTarea: (taskId: string) =>
    apiClient.get(`/cierres/tareas/${taskId}/descarga`, { responseType: 'blob' }),

  // Importar diario
  importar: (form: FormData) =>
    apiClient.post<{ task_id: string }>('/cierres/importar', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  getApuntes: (params: { ejercicio: number; cuenta?: string; conciliado?: boolean; page: number; page_size: number }) =>
    apiClient.get<Paginado<Apunte>>('/cierres/apuntes', { params }),
  getDiferencias: (ejercicio: number) =>
    apiClient.get<{ nuevos: Apunte[]; huerfanos: Apunte[] }>('/cierres/importar/diferencias', { params: { ejercicio } }),
  eliminarHuerfanos: (ejercicio: number, ids: number[]) =>
    apiClient.post<{ borrados: number; ignorados: number }>('/cierres/importar/eliminar-huerfanos', { ejercicio, ids }),
  desconciliarEjercicio: (ejercicio: number) =>
    apiClient.post<{ desconciliados: number }>('/cierres/desconciliar-ejercicio', { ejercicio }),

  // Punteo automático
  getReglas: () => apiClient.get<Regla[]>('/cierres/reglas'),
  actualizarRegla: (codigo: string, cambios: Partial<Pick<Regla, 'active' | 'tolerance_amount' | 'description'>>) =>
    apiClient.put(`/cierres/reglas/${codigo}`, cambios),
  puntear: (body: { ejercicios: number[]; filtro_cuentas: string[]; controles: string[] }) =>
    apiClient.post<{ task_id: string }>('/cierres/punteo', body),
  getIncidencias: (ejercicio?: number) =>
    apiClient.get<{ ejercicio: number; control_type: string; severity: string; n: number; fecha: string }[]>(
      '/cierres/incidencias/resumen', { params: { ejercicio } }),
  getCuentasControl: () => apiClient.get<CuentaControl[]>('/cierres/cuentas-control'),
  crearCuentaControl: (c: CuentaControl) => apiClient.post('/cierres/cuentas-control', c),
  actualizarCuentaControl: (id: number, c: CuentaControl) => apiClient.put(`/cierres/cuentas-control/${id}`, c),
  borrarCuentaControl: (id: number) => apiClient.delete(`/cierres/cuentas-control/${id}`),

  // Punteo manual
  buscarManual: (f: FiltroManual & { page: number; page_size: number }) =>
    apiClient.post<Paginado<Apunte> & { suma_total: number }>('/cierres/manual/buscar', f),
  idsManual: (f: FiltroManual) => apiClient.post<{ ids: number[] }>('/cierres/manual/ids', f),
  resumenSeleccion: (ids: number[]) =>
    apiClient.post<{ n: number; suma: number; cuentas: string[]; punteados: number }>('/cierres/manual/resumen', { ids }),
  puntearManual: (ids: number[], tolerancia: number) =>
    apiClient.post<{ punteados: number; grupo: string; suma: number }>('/cierres/manual/puntear', { ids, tolerancia }),
  cambiarCuenta: (id: number, cuenta: string) => apiClient.put(`/cierres/apuntes/${id}/cuenta`, { cuenta }),
  excelManual: (ids: number[]) => apiClient.post('/cierres/manual/excel', { ids }, { responseType: 'blob' }),

  // Ver conciliados
  getReglasPunteo: () => apiClient.get<string[]>('/cierres/conciliados/reglas'),
  getBloques: (params: { ejercicio?: number; regla?: string; page: number; page_size: number; refrescar?: boolean }) =>
    apiClient.get<{ total: number; page: number; page_size: number; bloques: Bloque[] }>(
      '/cierres/conciliados/bloques', { params }),
  getBloque: (grupo: string) =>
    apiClient.get<{ grupo: string; filas: Apunte[]; suma: number }>('/cierres/conciliados/bloque', { params: { grupo } }),
  excelConciliados: (ejercicio?: number, regla?: string) =>
    apiClient.post<{ task_id: string }>('/cierres/conciliados/excel', null, { params: { ejercicio, regla } }),
}
