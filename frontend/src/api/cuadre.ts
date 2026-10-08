import apiClient from './client'

export const cuadreApi = {
  getPanel: (ejercicio: number) =>
    apiClient.get('/cuadre/panel', { params: { ejercicio } }),
}
