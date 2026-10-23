import api from './client'

export const presupuestoApi = {
  listar: () => api.get('/presupuesto/'),
  iniciar: (ejercicio: number) => api.post('/presupuesto/iniciar', { ejercicio }),
  detalle: (id: string) => api.get(`/presupuesto/${id}`),

  // Ingresos
  generarIngresos: (id: string, coeficiente_prudencia: number) =>
    api.post(`/presupuesto/${id}/ingresos/generar`, { coeficiente_prudencia }),
  listarIngresos: (id: string) => api.get(`/presupuesto/${id}/ingresos`),
  actualizarIngreso: (presupuestoId: string, lineaId: string, datos: object) =>
    api.patch(`/presupuesto/${presupuestoId}/ingresos/${lineaId}`, datos),
  aprobarIngresos: (id: string) => api.post(`/presupuesto/${id}/ingresos/aprobar`),
  reabrirIngresos: (id: string) => api.post(`/presupuesto/${id}/ingresos/reabrir`),
  resumenIngresos: (id: string) => api.get(`/presupuesto/${id}/ingresos/resumen`),
  aplicarCoeficiente: (id: string, body: {
    coeficiente_prudencia: number;
    compania?: string;
    ramo?: string;
    actualizar_mercado?: boolean;
    tasa_caida_cartera?: number;
    tasa_caida_nueva_produccion?: number;
  }) => api.post(`/presupuesto/${id}/ingresos/aplicar-coeficiente`, body),
  mercadoReferencia: (id: string) => api.get(`/presupuesto/${id}/ingresos/mercado-referencia`),
  metodologia: (id: string) => api.get(`/presupuesto/${id}/ingresos/metodologia`),
  diagnosticoIngresos: (id: string, compania?: string) =>
    api.get(`/presupuesto/${id}/ingresos/diagnostico`, { params: compania ? { compania } : {} }),
  atipicosLinea: (presupuestoId: string, lineaId: string) =>
    api.get(`/presupuesto/${presupuestoId}/ingresos/${lineaId}/atipicos`),
  importarIngresos: (id: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post(`/presupuesto/${id}/ingresos/importar`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  // Gastos
  generarGastos: (id: string) => api.post(`/presupuesto/${id}/gastos/generar`),
  listarGastos: (id: string, familia?: string) =>
    api.get(`/presupuesto/${id}/gastos`, { params: familia ? { familia } : {} }),
  actualizarReglaGasto: (presupuestoId: string, lineaId: string, datos: object) =>
    api.patch(`/presupuesto/${presupuestoId}/gastos/${lineaId}/regla`, datos),
  ajusteManualGasto: (presupuestoId: string, lineaId: string, datos: object) =>
    api.patch(`/presupuesto/${presupuestoId}/gastos/${lineaId}/ajuste-manual`, datos),
  nuevoGasto: (presupuestoId: string, datos: object) =>
    api.post(`/presupuesto/${presupuestoId}/gastos/nuevo`, datos),
  aprobarGastos: (id: string) => api.post(`/presupuesto/${id}/gastos/aprobar`),
  reabrirGastos: (id: string) => api.post(`/presupuesto/${id}/gastos/reabrir`),
  resumenGastos: (id: string) => api.get(`/presupuesto/${id}/gastos/resumen`),

  // Cierre y Cuenta de Resultados
  cerrarPresupuesto: (id: string) => api.post(`/presupuesto/${id}/cerrar`),
  cuentaResultados: (id: string) => api.get(`/presupuesto/${id}/cuenta-resultados`),

  // Cesiones de auxiliares
  generarCesiones: (id: string) => api.post(`/presupuesto/${id}/gastos/cesiones/generar`),
  listarCesiones: (id: string) => api.get(`/presupuesto/${id}/gastos/cesiones`),
  actualizarCesion: (presupuestoId: string, cesionId: string, datos: object) =>
    api.patch(`/presupuesto/${presupuestoId}/gastos/cesiones/${cesionId}`, datos),
  importarCesiones: (id: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post(`/presupuesto/${id}/gastos/cesiones/importar`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}
