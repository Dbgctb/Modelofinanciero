import { useState } from 'react'
import {
  Card, Row, Col, Statistic, Table, Button, Tag, Space, Typography,
  Select, Alert, message, Tabs, Modal,
} from 'antd'
import {
  CheckCircleOutlined, ClockCircleOutlined, WarningOutlined,
  LockOutlined, UnlockOutlined, ArrowUpOutlined, ArrowDownOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { presupuestoApi } from '../../api/presupuesto'
import { realApi } from '../../api/tesoreria'
import { apiError } from '../../utils/errorHandler'
import {
  ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis,
  CartesianGrid, Tooltip as RTooltip, Legend,
} from 'recharts'

const { Title, Text } = Typography
const { Option } = Select

const fmt = (v: number) => v?.toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' €'
const fmtPct = (v: number) => (v >= 0 ? '+' : '') + v?.toFixed(2) + '%'

const ESTADO_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  no_cargado: { label: 'Sin datos', color: 'default', icon: <ClockCircleOutlined /> },
  cargado: { label: 'Cargado', color: 'processing', icon: <ClockCircleOutlined /> },
  con_incidencias: { label: 'Con incidencias', color: 'warning', icon: <WarningOutlined /> },
  validado: { label: 'Validado', color: 'cyan', icon: <CheckCircleOutlined /> },
  cerrado: { label: 'Cerrado', color: 'success', icon: <LockOutlined /> },
  reabierto: { label: 'Reabierto', color: 'orange', icon: <UnlockOutlined /> },
}

function TagEstadoMes({ estado }: { estado: string }) {
  const cfg = ESTADO_CONFIG[estado] || { label: estado, color: 'default', icon: null }
  return <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>
}

function DesvTag({ desv_abs, desv_pct, favorable }: { desv_abs: number; desv_pct: number; favorable: boolean }) {
  if (desv_abs === 0) return <Tag>Sin desviación</Tag>
  return (
    <Tag color={favorable ? 'success' : 'error'}
      icon={favorable ? <ArrowUpOutlined /> : <ArrowDownOutlined />}>
      {fmt(Math.abs(desv_abs))} ({fmtPct(Math.abs(desv_pct))})
    </Tag>
  )
}

export default function SeguimientoReal() {
  const qc = useQueryClient()
  const [presupuestoId, setPresupuestoId] = useState<string | null>(null)
  const [hastasMes, setHastasMes] = useState<number>(12)
  const [modalCerrar, setModalCerrar] = useState<number | null>(null)

  const { data: presupuestos = [] } = useQuery({
    queryKey: ['presupuestos'],
    queryFn: () => presupuestoApi.listar().then(r => r.data),
  })

  const { data: meses = [] } = useQuery({
    queryKey: ['meses-reales', presupuestoId],
    queryFn: () => realApi.getMeses(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: comparativaMensual = [] } = useQuery({
    queryKey: ['comparativa-mensual', presupuestoId],
    queryFn: () => realApi.comparativaMensual(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: acumulado } = useQuery({
    queryKey: ['acumulado', presupuestoId, hastasMes],
    queryFn: () => realApi.comparativaAcumulada(presupuestoId!, hastasMes).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const cerrarMes = useMutation({
    mutationFn: (mes: number) => realApi.cerrarMes(presupuestoId!, mes),
    onSuccess: () => {
      message.success('Mes cerrado. Desviaciones calculadas.')
      qc.invalidateQueries({ queryKey: ['meses-reales', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['comparativa-mensual', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['acumulado', presupuestoId] })
      setModalCerrar(null)
    },
    onError: (e) => message.error(apiError(e, 'Error al cerrar el mes')),
  })

  const reabrirMes = useMutation({
    mutationFn: (mes: number) => realApi.reabrirMes(presupuestoId!, mes),
    onSuccess: () => {
      message.success('Mes reabierto')
      qc.invalidateQueries({ queryKey: ['meses-reales', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al reabrir el mes')),
  })

  // Datos gráfico mensual (solo meses con datos)
  const datosGrafico = comparativaMensual
    .filter((m: any) => m.tiene_datos)
    .map((m: any) => ({
      mes: m.label,
      ing_real: m.ingresos.real,
      ing_presup: m.ingresos.presupuesto,
      gas_real: m.gastos.real,
      gas_presup: m.gastos.presupuesto,
      ebitda_real: m.ebitda_real,
      ebitda_presup: m.ebitda_presup,
    }))

  const colsMeses = [
    { title: 'Mes', dataIndex: 'label', width: 60 },
    { title: 'Estado', dataIndex: 'estado', render: (v: string) => <TagEstadoMes estado={v} /> },
    {
      title: '',
      render: (_: any, row: any) => (
        <Space>
          {(row.estado === 'cargado' || row.estado === 'validado' || row.estado === 'reabierto') && (
            <Button size="small" type="primary" ghost onClick={() => setModalCerrar(row.mes)}>
              Cerrar mes
            </Button>
          )}
          {row.estado === 'cerrado' && (
            <Button size="small" onClick={() => reabrirMes.mutate(row.mes)}>Reabrir</Button>
          )}
        </Space>
      ),
    },
  ]

  const colsComparativa = [
    { title: 'Mes', dataIndex: 'label', width: 60 },
    {
      title: 'Ingresos real', dataIndex: ['ingresos', 'real'],
      align: 'right' as const, render: (v: number) => fmt(v),
    },
    {
      title: 'Ingresos presup.', dataIndex: ['ingresos', 'presupuesto'],
      align: 'right' as const, render: (v: number) => <Text type="secondary">{fmt(v)}</Text>,
    },
    {
      title: 'Desv. ingresos',
      render: (_: any, row: any) => row.tiene_datos
        ? <DesvTag {...row.ingresos} />
        : <Text type="secondary">—</Text>,
    },
    {
      title: 'Gastos real', dataIndex: ['gastos', 'real'],
      align: 'right' as const, render: (v: number) => fmt(v),
    },
    {
      title: 'Desv. gastos',
      render: (_: any, row: any) => row.tiene_datos
        ? <DesvTag {...row.gastos} />
        : <Text type="secondary">—</Text>,
    },
    {
      title: 'EBITDA real',
      render: (_: any, row: any) => row.tiene_datos
        ? <Text strong style={{ color: row.ebitda_real >= 0 ? '#52c41a' : '#f5222d' }}>{fmt(row.ebitda_real)}</Text>
        : <Text type="secondary">—</Text>,
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Seguimiento real y comparativa</Title>
          <Text type="secondary">Real vs presupuesto mensual y acumulado</Text>
        </div>
        <Select placeholder="Selecciona ejercicio" style={{ width: 220 }} onChange={setPresupuestoId} value={presupuestoId}>
          {presupuestos.map((p: any) => <Option key={p.id} value={p.id}>Ejercicio {p.ejercicio}</Option>)}
        </Select>
      </div>

      {!presupuestoId && <Alert type="info" showIcon message="Selecciona un ejercicio para ver el seguimiento" />}

      {presupuestoId && (
        <Tabs defaultActiveKey="estado" items={[
          {
            key: 'estado',
            label: 'Estado de meses',
            children: (
              <Row gutter={24}>
                <Col span={8}>
                  <Card title="Control de meses">
                    <Table dataSource={meses} columns={colsMeses} rowKey="mes" size="small" pagination={false} />
                  </Card>
                </Col>
                <Col span={16}>
                  {/* Semáforo visual */}
                  <Card title="Vista anual de meses">
                    <Row gutter={[8, 8]}>
                      {meses.map((m: any) => {
                        const cfg = ESTADO_CONFIG[m.estado] || ESTADO_CONFIG.no_cargado
                        return (
                          <Col span={4} key={m.mes}>
                            <Card size="small" style={{ textAlign: 'center', borderColor: cfg.color === 'success' ? '#52c41a' : cfg.color === 'warning' ? '#faad14' : undefined }}>
                              <div style={{ fontSize: 12, color: '#999' }}>{m.label}</div>
                              <TagEstadoMes estado={m.estado} />
                            </Card>
                          </Col>
                        )
                      })}
                    </Row>
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: 'comparativa',
            label: 'Comparativa mensual',
            children: (
              <Space direction="vertical" size="large" style={{ width: '100%' }}>
                {datosGrafico.length > 0 && (
                  <Card title="Real vs Presupuesto">
                    <ResponsiveContainer width="100%" height={300}>
                      <ComposedChart data={datosGrafico}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="mes" />
                        <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                        <RTooltip formatter={(v: number) => fmt(v)} />
                        <Legend />
                        <Bar dataKey="ing_real" name="Ingresos real" fill="#52c41a" opacity={0.8} />
                        <Bar dataKey="ing_presup" name="Ingresos presup." fill="#b7eb8f" opacity={0.8} />
                        <Bar dataKey="gas_real" name="Gastos real" fill="#f5222d" opacity={0.8} />
                        <Bar dataKey="gas_presup" name="Gastos presup." fill="#ffccc7" opacity={0.8} />
                        <Line type="monotone" dataKey="ebitda_real" name="EBITDA real" stroke="#1890ff" strokeWidth={2} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </Card>
                )}
                <Card>
                  <Table dataSource={comparativaMensual} columns={colsComparativa} rowKey="mes" size="small" pagination={false} />
                </Card>
              </Space>
            ),
          },
          {
            key: 'acumulado',
            label: 'Acumulado',
            children: (
              <Space direction="vertical" size="large" style={{ width: '100%' }}>
                <Space>
                  <Text>Hasta el mes:</Text>
                  <Select value={hastasMes} onChange={setHastasMes} style={{ width: 120 }}>
                    {['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'].map((m, i) => (
                      <Option key={i + 1} value={i + 1}>{m}</Option>
                    ))}
                  </Select>
                </Space>
                {acumulado && (
                  <Row gutter={[16, 16]}>
                    <Col span={8}>
                      <Card title="Ingresos acumulados" style={{ borderTop: `3px solid #52c41a` }}>
                        <Statistic title="Real" value={acumulado.ingresos.real} suffix="€" precision={2} />
                        <Statistic title="Presupuesto" value={acumulado.ingresos.presupuesto} suffix="€" precision={2} valueStyle={{ fontSize: 14, color: '#999' }} />
                        <DesvTag desv_abs={acumulado.ingresos.desv_abs} desv_pct={acumulado.ingresos.desv_pct} favorable={acumulado.ingresos.favorable} />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card title="Gastos acumulados" style={{ borderTop: `3px solid #f5222d` }}>
                        <Statistic title="Real" value={acumulado.gastos.real} suffix="€" precision={2} />
                        <Statistic title="Presupuesto" value={acumulado.gastos.presupuesto} suffix="€" precision={2} valueStyle={{ fontSize: 14, color: '#999' }} />
                        <DesvTag desv_abs={acumulado.gastos.desv_abs} desv_pct={acumulado.gastos.desv_pct} favorable={acumulado.gastos.favorable} />
                      </Card>
                    </Col>
                    <Col span={8}>
                      <Card title="EBITDA acumulado" style={{ borderTop: `3px solid #1890ff` }}>
                        <Statistic title="Real" value={acumulado.ebitda.real} suffix="€" precision={2}
                          valueStyle={{ color: acumulado.ebitda.real >= 0 ? '#52c41a' : '#f5222d' }} />
                        <Statistic title="Presupuesto" value={acumulado.ebitda.presupuesto} suffix="€" precision={2} valueStyle={{ fontSize: 14, color: '#999' }} />
                        <DesvTag desv_abs={acumulado.ebitda.desv_abs} desv_pct={acumulado.ebitda.desv_pct} favorable={acumulado.ebitda.favorable} />
                      </Card>
                    </Col>
                  </Row>
                )}
              </Space>
            ),
          },
        ]} />
      )}

      <Modal
        title={`¿Cerrar el mes ${modalCerrar ? ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'][modalCerrar - 1] : ''}?`}
        open={!!modalCerrar}
        onOk={() => modalCerrar && cerrarMes.mutate(modalCerrar)}
        onCancel={() => setModalCerrar(null)}
        confirmLoading={cerrarMes.isPending}
        okText="Cerrar mes"
        cancelText="Cancelar"
      >
        <Alert type="info" showIcon message="Al cerrar el mes se calcularán automáticamente las desviaciones real vs presupuesto. Esta acción se puede deshacer reabriendo el mes." />
      </Modal>
    </Space>
  )
}
