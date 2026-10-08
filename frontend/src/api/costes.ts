import client from './client'

export const costesApi = {
  clasificar: (presupuestoId: string, mes: number, ejercicio: number) =>
    client.post(`/costes/${presupuestoId}/clasificar`, null, { params: { mes, ejercicio } }),
  listarLineas: (presupuestoId: string, params?: { mes?: number; familia?: string; estado?: string }) =>
    client.get(`/costes/${presupuestoId}/lineas`, { params }),
  actualizarLinea: (presupuestoId: string, lineaId: string, data: any) =>
    client.patch(`/costes/${presupuestoId}/lineas/${lineaId}`, data),
  imputar: (presupuestoId: string, meses: number[]) =>
    client.post(`/costes/${presupuestoId}/imputar`, null, { params: { meses } }),
  comparativa: (presupuestoId: string, meses: number[]) =>
    client.get(`/costes/${presupuestoId}/comparativa`, { params: { meses } }),
  kpis: (presupuestoId: string, meses: number[]) =>
    client.get(`/costes/${presupuestoId}/kpis`, { params: { meses } }),
  familiasClasificacion: () =>
    client.get('/costes/familias-clasificacion'),
}
