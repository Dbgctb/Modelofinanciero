import client from './client'

export const kpisApi = {
  calcular: (presupuestoId: string, hastaMes?: number) =>
    client.post(`/kpis/${presupuestoId}/calcular`, null, {
      params: hastaMes !== undefined ? { hasta_mes: hastaMes } : {},
    }),
  resultados: (presupuestoId: string, codigo?: string) =>
    client.get(`/kpis/${presupuestoId}/resultados`, { params: codigo ? { codigo } : {} }),
  alertas: (presupuestoId: string) =>
    client.get(`/kpis/${presupuestoId}/alertas`),
  umbrales: () => client.get('/kpis/umbrales'),
  actualizarUmbral: (kpiCodigo: string, data: { umbral_verde: number; umbral_amarillo: number }) =>
    client.put(`/kpis/umbrales/${kpiCodigo}`, data),
}
