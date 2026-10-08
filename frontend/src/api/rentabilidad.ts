import apiClient from './client'

export const rentabilidadApi = {
  getEjercicios: () =>
    apiClient.get('/rentabilidad/ejercicios'),

  getClientes: (ejercicio: number, minComision?: number, tasaCesionEstimada?: number) =>
    apiClient.get('/rentabilidad/clientes', {
      params: {
        ejercicio,
        ...(minComision != null && { min_comision: minComision }),
        ...(tasaCesionEstimada != null && { tasa_cesion_estimada: tasaCesionEstimada }),
      },
    }),

  getSinTomador: (ejercicio: number) =>
    apiClient.get('/rentabilidad/sin-tomador', { params: { ejercicio } }),

  getRecibosCliente: (ejercicio: number, tomador: string) =>
    apiClient.get('/rentabilidad/recibos-cliente', { params: { ejercicio, tomador } }),
}
