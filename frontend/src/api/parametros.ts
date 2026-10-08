import api from './client'

export type TipoCuenta = 'ingreso' | 'gasto' | 'tesoreria_excluida'

export interface MapCuenta {
  id: string
  numero_cuenta: string
  tipo: TipoCuenta
  compania: string | null
  familia_gasto: string | null
  descripcion: string | null
  excluir_tesoreria: boolean
  activo: boolean
}

export interface MapCuentaInput {
  numero_cuenta: string
  tipo: TipoCuenta
  compania?: string
  familia_gasto?: string
  descripcion?: string
  excluir_tesoreria?: boolean
}

export const parametrosApi = {
  listarCuentas: (params?: { tipo?: string; activo?: boolean }) =>
    api.get<MapCuenta[]>('/parametros/cuentas', { params }),

  crearCuenta: (data: MapCuentaInput) =>
    api.post<MapCuenta>('/parametros/cuentas', data),

  actualizarCuenta: (id: string, data: Partial<MapCuentaInput> & { activo?: boolean }) =>
    api.patch<MapCuenta>(`/parametros/cuentas/${id}`, data),

  eliminarCuenta: (id: string) =>
    api.delete(`/parametros/cuentas/${id}`),

  importarLote: (cuentas: MapCuentaInput[]) =>
    api.post('/parametros/cuentas/importar-lote', cuentas),

  familias: () =>
    api.get<string[]>('/parametros/familias-gasto'),
}
