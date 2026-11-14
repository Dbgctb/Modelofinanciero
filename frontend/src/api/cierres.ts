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

// ── Conciliación bancaria ────────────────────────────────────────────────────

export interface BancoCC {
  id?: number
  nombre: string
  cuenta_572: string
  iban: string
  entidad: string
  activo: boolean
  movimientos?: number
}

export interface ConfigBanco {
  dias_nivel2: number
  tol_nivel8: number
  tol_nivel9: number
}

export interface MovimientoBanco {
  id: number
  fecha_operacion: string
  fecha_valor: string | null
  concepto: string | null
  referencia: string | null
  importe: number
  saldo?: number | null
  reconciled?: boolean
  recon_level?: string | null
}

export interface ApunteBanco {
  id: number
  fecha: string
  cuenta: string
  asiento_key: string | null
  concepto: string | null
  neto: number
}

export interface Conciliado {
  id: number
  fecha_operacion: string
  concepto: string | null
  importe: number
  recon_level: string | null
  recon_difference: number | null
  recon_timestamp: string | null
  recon_group_id: string | null
  recon_journal_id: number | null
  asiento_key: string | null
  concepto_diario: string | null
  neto: number | null
  apuntes_grupo: number
}

export interface PropuestaAsiento {
  id: number
  fecha: string
  concepto: string
  importe: number
  tipo: string
  lineas: { cuenta: string; nombre: string; debe: number; haber: number }[]
}

const B = '/cierres/banco'

export const bancoApi = {
  getBancos: () => apiClient.get<BancoCC[]>(`${B}/bancos`),
  crearBanco: (b: BancoCC) => apiClient.post(`${B}/bancos`, b),
  actualizarBanco: (id: number, b: BancoCC) => apiClient.put(`${B}/bancos/${id}`, b),
  borrarBanco: (id: number) => apiClient.delete(`${B}/bancos/${id}`),
  getConfig: (bancoId: number) => apiClient.get<ConfigBanco>(`${B}/${bancoId}/config`),
  guardarConfig: (bancoId: number, c: ConfigBanco) => apiClient.put(`${B}/${bancoId}/config`, c),
  columnas: (form: FormData) =>
    apiClient.post<{ columnas: string[]; muestra: Record<string, string>[] }>(`${B}/columnas`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  importar: (bancoId: number, form: FormData) =>
    apiClient.post<any>(`${B}/${bancoId}/importar`, form, { headers: { 'Content-Type': 'multipart/form-data' } }),
  getExtractos: (bancoId: number, ejercicio: number, page: number, page_size: number) =>
    apiClient.get<{ total: number; filas: MovimientoBanco[] }>(`${B}/${bancoId}/extractos`, {
      params: { ejercicio, page, page_size },
    }),
  conciliar: (bancoId: number, ejercicio: number) =>
    apiClient.post<{ task_id: string }>(`${B}/${bancoId}/conciliar`, { ejercicio }),
  getPendientes: (bancoId: number, ejercicio: number) =>
    apiClient.get<{ cuenta_572: string; banco: MovimientoBanco[]; diario: ApunteBanco[]; total_banco: number; total_diario: number }>(
      `${B}/${bancoId}/pendientes`, { params: { ejercicio } }),
  manual1a1: (bancoId: number, ejercicio: number, id_banco: number, id_diario: number) =>
    apiClient.post<{ diferencia: number }>(`${B}/${bancoId}/manual-1a1`, { ejercicio, id_banco, id_diario }),
  manualNN: (bancoId: number, ejercicio: number, ids_banco: number[], ids_diario: number[]) =>
    apiClient.post<{ grupo: string; diferencia: number }>(`${B}/${bancoId}/manual-nn`, { ejercicio, ids_banco, ids_diario }),
  propuesta: (bancoId: number, ids_banco: number[]) =>
    apiClient.post<PropuestaAsiento[]>(`${B}/${bancoId}/propuesta-asientos`, { ids_banco }),
  getConciliados: (bancoId: number, ejercicio: number, nivel: string | undefined, page: number, page_size: number) =>
    apiClient.get<{ total: number; por_nivel: Record<string, number>; filas: Conciliado[] }>(
      `${B}/${bancoId}/conciliados`, { params: { ejercicio, nivel, page, page_size } }),
  desconciliar: (bancoId: number, ids_banco: number[]) =>
    apiClient.post<{ movimientos: number; apuntes: number }>(`${B}/${bancoId}/desconciliar`, { ids_banco }),
  excelConciliados: (bancoId: number, ejercicio: number) =>
    apiClient.get(`${B}/${bancoId}/conciliados/excel`, { params: { ejercicio }, responseType: 'blob' }),
}
