import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, App as AntApp } from 'antd'
import esES from 'antd/locale/es_ES'
import { QueryClient, QueryClientProvider, QueryCache, MutationCache } from '@tanstack/react-query'
import AppLayout from './components/layout/AppLayout'
import ProtectedRoute from './components/common/ProtectedRoute'
import Login from './pages/auth/Login'
import Dashboard from './pages/dashboard/Dashboard'
import CargaDatos from './pages/presupuestacion/CargaDatos'
import DetalleRecibos from './pages/presupuestacion/DetalleRecibos'
import DetalleDiario from './pages/presupuestacion/DetalleDiario'
import PresupuestoIngresos from './pages/presupuestacion/PresupuestoIngresos'
import PresupuestoGastos from './pages/presupuestacion/PresupuestoGastos'
import Tesoreria from './pages/presupuestacion/Tesoreria'
import SeguimientoReal from './pages/presupuestacion/SeguimientoReal'
import MapeoCuentas from './pages/admin/Mapeo'
import Usuarios from './pages/admin/Usuarios'
import TasasMercado from './pages/admin/TasasMercado'
import ResetDatos from './pages/admin/ResetDatos'
import KPIs from './pages/presupuestacion/KPIs'
import CuentaResultados from './pages/presupuestacion/CuentaResultados'
import ConfiguracionAnalitico from './pages/analitico/ConfiguracionAnalitico'
import DashboardsAnalitico from './pages/analitico/DashboardsAnalitico'
import AjustesCoste from './pages/analitico/AjustesCoste'
import Valoracion from './pages/analitico/Valoracion'
import RentabilidadCliente from './pages/rentabilidad/RentabilidadCliente'
import PanelControl from './pages/cuadre/PanelControl'
import Oportunidades from './pages/crossSelling/Oportunidades'
import FugaAlertas from './pages/crossSelling/FugaAlertas'
import Efectividad from './pages/crossSelling/Efectividad'
import CrossSellingConfiguracion from './pages/crossSelling/Configuracion'

// Ref global que AppErrorConfig rellena con el contexto de notificaciones antd
let _notify: ((msg: string, type?: 'error' | 'warning' | 'info') => void) | null = null

function msgFromError(error: any): string {
  const status = error?.response?.status
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.length < 200) return detail
  if (status === 403) return 'No tienes permisos para esta acción.'
  if (status === 404) return 'Recurso no encontrado.'
  if (status && status >= 500) return 'Error del servidor. Inténtalo de nuevo más tarde.'
  return 'Error inesperado. Comprueba la consola para más detalles.'
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error: any) => {
      const status = error?.response?.status
      if (!status || status === 401) return  // 401 lo gestiona el interceptor de axios
      _notify?.(msgFromError(error), status >= 500 ? 'error' : 'warning')
    },
  }),
  mutationCache: new MutationCache({
    onError: (error: any) => {
      const status = error?.response?.status
      if (!status || status === 401) return
      _notify?.(msgFromError(error))
    },
  }),
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

// Monta dentro de AntApp para acceder al contexto de mensaje
function AppErrorConfig() {
  const { message } = AntApp.useApp()
  useEffect(() => {
    _notify = (msg, type = 'error') => message[type](msg, 4)
    return () => { _notify = null }
  }, [message])
  return null
}

const theme = {
  token: {
    colorPrimary: '#1890ff',
    borderRadius: 8,
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider locale={esES} theme={theme}>
        <AntApp>
          <AppErrorConfig />
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<Dashboard />} />
                {/* Módulo de Presupuestación */}
                <Route path="presupuestacion/carga" element={<CargaDatos />} />
                <Route path="presupuestacion/carga/recibos/:cargaId" element={<DetalleRecibos />} />
                <Route path="presupuestacion/carga/diario/:cargaId" element={<DetalleDiario />} />
                <Route path="presupuestacion/ingresos" element={<PresupuestoIngresos />} />
                <Route path="presupuestacion/gastos" element={<PresupuestoGastos />} />
                <Route path="presupuestacion/tesoreria" element={<Tesoreria />} />
                <Route path="presupuestacion/real" element={<SeguimientoReal />} />
                <Route path="presupuestacion/kpis" element={<KPIs />} />
                <Route path="presupuestacion/cuenta-resultados" element={<CuentaResultados />} />

                {/* Panel de control — cuadre */}
                <Route path="panel-control" element={<PanelControl />} />

                {/* Rentabilidad por cliente */}
                <Route path="rentabilidad/clientes" element={<RentabilidadCliente />} />

                {/* Cross-selling y Fuga */}
                <Route path="cross-selling/oportunidades" element={<Oportunidades />} />
                <Route path="cross-selling/alertas" element={<FugaAlertas />} />
                <Route path="cross-selling/efectividad" element={<Efectividad />} />
                <Route path="cross-selling/configuracion" element={<CrossSellingConfiguracion />} />

                {/* Módulo Analítico */}
                <Route path="analitico/dashboards" element={<DashboardsAnalitico />} />
                <Route path="analitico/configuracion" element={<ConfiguracionAnalitico />} />
                <Route path="analitico/ajustes-coste" element={<AjustesCoste />} />
                <Route path="analitico/valoracion" element={<Valoracion />} />

                {/* Administración — solo admin */}
                <Route
                  path="admin/mapeo-cuentas"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <MapeoCuentas />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="usuarios"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <Usuarios />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="admin/tasas-mercado"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <TasasMercado />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="admin/reset-datos"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <ResetDatos />
                    </ProtectedRoute>
                  }
                />
              </Route>
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </BrowserRouter>
        </AntApp>
      </ConfigProvider>
    </QueryClientProvider>
  )
}
