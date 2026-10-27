import apiClient from './client'

const _p = (ejercicio: number, tasa: number, extra?: Record<string, unknown>) =>
  ({ params: { ejercicio, tasa, ...extra } })

export const analiticoApi = {
  // MAP_CUENTAS
  getMapCuentas: () => apiClient.get('/analitico/map-cuentas'),
  saveMapCuenta: (data: { numero_cuenta: string; naturaleza: string; descripcion?: string }) =>
    apiClient.post('/analitico/map-cuentas', data),
  importarDesdeMapeo: () =>
    apiClient.post('/analitico/map-cuentas/importar-desde-mapeo'),
  deleteMapCuenta: (cuenta: string) => apiClient.delete(`/analitico/map-cuentas/${cuenta}`),

  // MAP_DRIVERS
  getMapDrivers: () => apiClient.get('/analitico/map-drivers'),
  saveMapDriver: (data: { naturaleza: string; driver: string }) =>
    apiClient.post('/analitico/map-drivers', data),

  // Listas de referencia
  getNaturalezas: () => apiClient.get('/analitico/naturalezas'),
  getDrivers: () => apiClient.get('/analitico/drivers'),
  getEjercicios: () => apiClient.get('/analitico/ejercicios'),
  // Tasa real de cesión del ejercicio (cesión 623 / comisión de recibos con auxiliar y cesión)
  getTasaCesionReal: (ejercicio: number) =>
    apiClient.get('/analitico/tasa-cesion-real', { params: { ejercicio } }),

  // Recálculo asíncrono
  recalcular: (ejercicio: number) =>
    apiClient.post(`/analitico/recalcular?ejercicio=${ejercicio}`),
  recalcularEstado: (taskId: string) =>
    apiClient.get(`/analitico/recalcular/estado?task_id=${taskId}`),

  // Dashboards — todos aceptan tasa (0–1, default 0.40)
  dashEjecutivo:       (ejercicio: number, tasa: number) =>
    apiClient.get('/analitico/dashboard/ejecutivo',       _p(ejercicio, tasa)),
  dashCompania:        (ejercicio: number, tasa: number) =>
    apiClient.get('/analitico/dashboard/compania',        _p(ejercicio, tasa)),
  dashAuxiliar:        (ejercicio: number, tasa: number) =>
    apiClient.get('/analitico/dashboard/auxiliar',        _p(ejercicio, tasa)),
  dashRamo:            (ejercicio: number, tasa: number) =>
    apiClient.get('/analitico/dashboard/ramo',            _p(ejercicio, tasa)),
  dashNuevaProduccion: (ejercicio: number, tasa: number) =>
    apiClient.get('/analitico/dashboard/nueva-produccion',_p(ejercicio, tasa)),
  dashOperaciones:     (ejercicio: number, tasa: number) =>
    apiClient.get('/analitico/dashboard/operaciones',     _p(ejercicio, tasa)),
  dashCostes:          (ejercicio: number, tasa: number) =>
    apiClient.get('/analitico/dashboard/costes',          _p(ejercicio, tasa)),
  dashSubramo:         (ejercicio: number, tasa: number, ramo?: string) =>
    apiClient.get('/analitico/dashboard/subramo',         _p(ejercicio, tasa, ramo ? { ramo } : {})),

  conciliacion: (ejercicio: number, tasa?: number) =>
    apiClient.get('/analitico/conciliacion', {
      params: { ejercicio, ...(tasa != null && { tasa }) },
    }),

  // Ajustes de coste por auxiliar
  listarAjustesCoste: (ejercicio: number) =>
    apiClient.get(`/analitico/ajustes-coste?ejercicio=${ejercicio}`),
  crearAjusteCoste: (data: {
    ejercicio: number; auxiliar: string; numero_cuenta: string;
    descripcion: string; importe_mensual: number;
  }) => apiClient.post('/analitico/ajustes-coste', data),
  actualizarAjusteCoste: (id: string, data: Partial<{
    auxiliar: string; numero_cuenta: string; descripcion: string;
    importe_mensual: number; activo: boolean;
  }>) => apiClient.patch(`/analitico/ajustes-coste/${id}`, data),
  eliminarAjusteCoste: (id: string) =>
    apiClient.delete(`/analitico/ajustes-coste/${id}`),

  // Valoración
  valoracion: (ejercicio: number, crecimiento?: number) =>
    apiClient.get(`/analitico/valoracion?ejercicio=${ejercicio}${crecimiento != null ? `&crecimiento=${crecimiento}` : ''}`),

  asignarAuxiliarCesion: (ejercicio: number, numero_cuenta: string, auxiliar: string) =>
    apiClient.post(`/analitico/cesion-sin-auxiliar/asignar?ejercicio=${ejercicio}&numero_cuenta=${encodeURIComponent(numero_cuenta)}&auxiliar=${encodeURIComponent(auxiliar)}`),
}
