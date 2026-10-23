import client from './client'

export const costesApi = {
  clasificar: (ejercicio: number, mes: number) =>
    client.post(`/costes/${ejercicio}/clasificar`, null, { params: { mes } }),
  listarLineas: (ejercicio: number, params?: { mes?: number; familia?: string; estado?: string }) =>
    client.get(`/costes/${ejercicio}/lineas`, { params }),
  actualizarLinea: (ejercicio: number, lineaId: string, data: any) =>
    client.patch(`/costes/${ejercicio}/lineas/${lineaId}`, data),
  imputar: (ejercicio: number, meses: number[]) =>
    client.post(`/costes/${ejercicio}/imputar`, null, { params: { meses } }),
  comparativa: (ejercicio: number, meses: number[]) =>
    client.get(`/costes/${ejercicio}/comparativa`, { params: { meses } }),
  kpis: (ejercicio: number, meses: number[]) =>
    client.get(`/costes/${ejercicio}/kpis`, { params: { meses } }),
  anyosDisponibles: () =>
    client.get('/costes/anyos-disponibles'),
  familiasClasificacion: () =>
    client.get('/costes/familias-clasificacion'),
}
