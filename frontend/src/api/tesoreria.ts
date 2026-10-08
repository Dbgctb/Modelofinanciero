import api from './client'

export const tesoreriaApi = {
  getConfig: (id: string) => api.get(`/tesoreria/${id}/config`),
  upsertConfig: (id: string, data: object) => api.post(`/tesoreria/${id}/config`, data),
  getApuntes: (id: string) => api.get(`/tesoreria/${id}/apuntes`),
  crearApunte: (id: string, data: object) => api.post(`/tesoreria/${id}/apuntes`, data),
  eliminarApunte: (id: string, apunteId: string) => api.delete(`/tesoreria/${id}/apuntes/${apunteId}`),
  calcular: (id: string, caja_inicial: number, caja_minima?: number) =>
    api.post(`/tesoreria/${id}/calcular`, { caja_inicial, caja_minima }),
  getResultado: (id: string) => api.get(`/tesoreria/${id}/resultado`),
  aprobar: (id: string) => api.post(`/tesoreria/${id}/aprobar`),
  // Empleados
  getEmpleados: (id: string) => api.get(`/tesoreria/${id}/empleados`),
  generarEmpleados: (id: string) => api.post(`/tesoreria/${id}/empleados/generar`),
  actualizarEmpleado: (id: string, empId: string, data: object) =>
    api.patch(`/tesoreria/${id}/empleados/${empId}`, data),
}

export const realApi = {
  getMeses: (id: string) => api.get(`/real/${id}/meses`),
  vincularCarga: (id: string, mes: number, carga_id: string) =>
    api.post(`/real/${id}/meses/${mes}/vincular-carga`, { carga_id }),
  cerrarMes: (id: string, mes: number) => api.post(`/real/${id}/meses/${mes}/cerrar`),
  reabrirMes: (id: string, mes: number) => api.post(`/real/${id}/meses/${mes}/reabrir`),
  comparativaMensual: (id: string) => api.get(`/real/${id}/comparativa/mensual`),
  comparativaAcumulada: (id: string, hasta_mes: number) =>
    api.get(`/real/${id}/comparativa/acumulado`, { params: { hasta_mes } }),
  detalleIngresos: (id: string, params?: object) =>
    api.get(`/real/${id}/comparativa/ingresos-detalle`, { params }),
  detalleGastos: (id: string, params?: object) =>
    api.get(`/real/${id}/comparativa/gastos-detalle`, { params }),
}
