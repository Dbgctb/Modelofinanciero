import { useState } from 'react'
import {
  Card, Row, Col, Table, Button, Tag, Space, Typography,
  InputNumber, Select, Modal, Form, Alert, Popconfirm, message,
  Tooltip, Badge,
} from 'antd'
import {
  CalculatorOutlined, CheckCircleOutlined, WarningOutlined,
  PlusOutlined, DeleteOutlined, TeamOutlined, ClockCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { presupuestoApi } from '../../api/presupuesto'
import { tesoreriaApi } from '../../api/tesoreria'
import { apiError } from '../../utils/errorHandler'
import {
  ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis,
  CartesianGrid, Tooltip as RTooltip, Legend, ReferenceLine,
} from 'recharts'

const { Title, Text } = Typography
const { Option } = Select

const fmt = (v: number) =>
  (v ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

const TIPO_APUNTE_LABELS: Record<string, string> = {
  prestamo: 'Préstamo', disposicion_poliza: 'Disposición póliza',
  amortizacion_deuda: 'Amortización deuda', intereses: 'Intereses financieros',
  aportacion_socios: 'Aportación socios', retirada_socios: 'Retirada socios',
  inversion: 'Inversión', regularizacion: 'Regularización', otro: 'Otro',
}

const REGLA_LABELS: Record<string, string> = {
  mismo_mes: 'Inmediato (mismo mes)',
  mes_siguiente: 'Mes siguiente',
  dias_30: '30 días',
  dias_60: '60 días',
}

// Sentinels que usa el backend para configs globales
const KEY_COBROS_GLOBAL = '__cobros__'
const KEY_PAGOS_DEFAULT = '__pagos__'
const KEY_CESIONES      = 'Cesiones a auxiliares'

// SS empleado 2026: contingencias 4,70 + desempleo 1,55 + FP 0,10 + MEI 0,12
const SS_INFO = 'SS empleado 2026: contingencias 4,70% + desempleo 1,55% + FP 0,10% + MEI 0,12% = 6,47%'

export default function Tesoreria() {
  const qc = useQueryClient()
  const [presupuestoId, setPresupuestoId] = useState<string | null>(null)
  const [cajaInicial, setCajaInicial] = useState<number>(0)
  const [cajaMinima, setCajaMinima] = useState<number | undefined>()
  const [modalApunte, setModalApunte] = useState(false)
  const [formApunte] = Form.useForm()

  const { data: presupuestos = [] } = useQuery({
    queryKey: ['presupuestos'],
    queryFn: () => presupuestoApi.listar().then(r => r.data),
  })

  const { data: resultado } = useQuery({
    queryKey: ['tesoreria-resultado', presupuestoId],
    queryFn: () => tesoreriaApi.getResultado(presupuestoId!).then(r => r.data).catch(() => null),
    enabled: !!presupuestoId,
  })

  const { data: apuntes = [] } = useQuery({
    queryKey: ['tesoreria-apuntes', presupuestoId],
    queryFn: () => tesoreriaApi.getApuntes(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: configs = [] } = useQuery({
    queryKey: ['tesoreria-config', presupuestoId],
    queryFn: () => tesoreriaApi.getConfig(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: empleados = [] } = useQuery({
    queryKey: ['tesoreria-empleados', presupuestoId],
    queryFn: () => tesoreriaApi.getEmpleados(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  // ── Helpers para leer configs ────────────────────────────────────────────
  const getReglaCobros = () => {
    const c = (configs as any[]).find(x => x.familia_gasto === KEY_COBROS_GLOBAL)
    return c?.regla_cobro ?? 'dias_30'
  }
  const getReglaPagoDefault = () => {
    const c = (configs as any[]).find(x => x.familia_gasto === KEY_PAGOS_DEFAULT)
    return c?.regla_pago ?? 'mismo_mes'
  }
  const getReglaCesiones = () => {
    const c = (configs as any[]).find(x => x.familia_gasto === KEY_CESIONES)
    return c?.regla_pago ?? 'dias_30'
  }

  // ── Mutations ────────────────────────────────────────────────────────────
  const upsertConfig = useMutation({
    mutationFn: (data: object) => tesoreriaApi.upsertConfig(presupuestoId!, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tesoreria-config', presupuestoId] }),
    onError: (e) => message.error(apiError(e, 'Error al guardar configuración')),
  })

  const calcular = useMutation({
    mutationFn: () => tesoreriaApi.calcular(presupuestoId!, cajaInicial, cajaMinima),
    onSuccess: () => {
      message.success('Tesorería calculada')
      qc.invalidateQueries({ queryKey: ['tesoreria-resultado', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['tesoreria-config', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al calcular la tesorería')),
  })

  const crearApunte = useMutation({
    mutationFn: (datos: object) => tesoreriaApi.crearApunte(presupuestoId!, datos),
    onSuccess: () => {
      message.success('Apunte añadido')
      qc.invalidateQueries({ queryKey: ['tesoreria-apuntes', presupuestoId] })
      setModalApunte(false)
      formApunte.resetFields()
    },
    onError: (e) => message.error(apiError(e, 'Error al añadir el apunte')),
  })

  const eliminarApunte = useMutation({
    mutationFn: (id: string) => tesoreriaApi.eliminarApunte(presupuestoId!, id),
    onSuccess: () => {
      message.success('Apunte eliminado')
      qc.invalidateQueries({ queryKey: ['tesoreria-apuntes', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al eliminar el apunte')),
  })

  const aprobar = useMutation({
    mutationFn: () => tesoreriaApi.aprobar(presupuestoId!),
    onSuccess: () => {
      message.success('Tesorería aprobada')
      qc.invalidateQueries({ queryKey: ['presupuestos'] })
      qc.invalidateQueries({ queryKey: ['tesoreria-resultado', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al aprobar la tesorería')),
  })

  const generarEmpleados = useMutation({
    mutationFn: () => tesoreriaApi.generarEmpleados(presupuestoId!),
    onSuccess: (r) => {
      message.success(`${r.data.count} empleados generados desde contabilidad 640*`)
      qc.invalidateQueries({ queryKey: ['tesoreria-empleados', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al generar empleados')),
  })

  const actualizarEmpleado = useMutation({
    mutationFn: ({ id, data }: { id: string; data: object }) =>
      tesoreriaApi.actualizarEmpleado(presupuestoId!, id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tesoreria-empleados', presupuestoId] }),
    onError: (e) => message.error(apiError(e, 'Error al actualizar empleado')),
  })

  // ── Gráfico: empieza con caja inicial como punto 0 ───────────────────────
  // cobros/pagos ya incluyen timing aplicado por el backend
  // apilamos manuales para mostrar los totales reales de entrada/salida de caja
  const datosGrafico = resultado ? [
    {
      mes: 'Inicio',
      cobros: 0, entradas: 0,
      pagos: 0, salidas: 0,
      flujo: 0, caja: resultado.caja_inicial,
    },
    ...(resultado.meses || []).map((m: any) => ({
      mes: m.label,
      cobros: m.cobros,
      entradas: m.entradas_manuales || 0,
      pagos: -(m.pagos || 0),
      salidas: -(m.salidas_manuales || 0),
      flujo: m.flujo,
      caja: m.caja_final,
      alerta: m.alerta,
    })),
  ] : []

  // ── Columnas apuntes manuales ─────────────────────────────────────────────
  const colsApuntes = [
    { title: 'Mes', dataIndex: 'mes', width: 55, render: (v: number) => MESES[v - 1] },
    { title: 'Tipo', dataIndex: 'tipo', render: (v: string) => TIPO_APUNTE_LABELS[v] || v },
    { title: 'Concepto', dataIndex: 'concepto', ellipsis: true },
    { title: 'Entrada (€)', dataIndex: 'importe_haber', align: 'right' as const,
      render: (v: number) => v > 0 ? <Text style={{ color: '#52c41a' }}>+{fmt(v)}</Text> : '—' },
    { title: 'Salida (€)', dataIndex: 'importe_debe', align: 'right' as const,
      render: (v: number) => v > 0 ? <Text type="danger">−{fmt(v)}</Text> : '—' },
    { title: '', width: 50,
      render: (_: any, row: any) => (
        <Popconfirm title="¿Eliminar apunte?" onConfirm={() => eliminarApunte.mutate(row.id)}
          okButtonProps={{ danger: true }}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ) },
  ]

  // ── Columnas tabla mensual ────────────────────────────────────────────────
  const colsMeses = [
    { title: 'Mes', dataIndex: 'label', width: 60,
      render: (v: string, row: any) => row._esInicio
        ? <Text strong style={{ color: '#1677ff' }}>{v}</Text>
        : v },
    { title: 'Cobros', dataIndex: 'cobros', align: 'right' as const,
      render: (v: number, row: any) => row._esInicio ? '—' : fmt(v) },
    { title: 'Pagos', dataIndex: 'pagos', align: 'right' as const,
      render: (v: number, row: any) => row._esInicio ? '—' : <Text type="danger">{fmt(v)}</Text> },
    { title: 'Ent. manual', dataIndex: 'entradas_manuales', align: 'right' as const,
      render: (v: number, row: any) => row._esInicio ? '—' : (v > 0 ? fmt(v) : '—') },
    { title: 'Sal. manual', dataIndex: 'salidas_manuales', align: 'right' as const,
      render: (v: number, row: any) => row._esInicio ? '—' : (v > 0 ? <Text type="danger">{fmt(v)}</Text> : '—') },
    { title: 'Flujo neto', dataIndex: 'flujo', align: 'right' as const,
      render: (v: number, row: any) => row._esInicio ? '—'
        : <Text style={{ color: v >= 0 ? '#52c41a' : '#f5222d', fontWeight: 600 }}>{fmt(v)}</Text> },
    { title: 'Caja', dataIndex: 'caja_final', align: 'right' as const,
      render: (v: number, row: any) => (
        <Space>
          <Text strong style={{ color: row._esInicio ? '#1677ff' : row.alerta ? '#f5222d' : '#333' }}>{fmt(v)}</Text>
          {row.alerta && <Tooltip title="Caja por debajo del mínimo"><WarningOutlined style={{ color: '#f5222d' }} /></Tooltip>}
        </Space>
      ) },
  ]

  // ── Columnas empleados ────────────────────────────────────────────────────
  const colsEmpleados = [
    { title: 'Empleado', dataIndex: 'nombre', ellipsis: true,
      render: (v: string, row: any) => (
        <Space size={6}>
          <Text style={{ fontSize: 12 }}>{v}</Text>
          {row.es_autonomo && <Tag color="purple" style={{ fontSize: 10 }}>Autónomo</Tag>}
        </Space>
      ) },
    { title: 'Cuenta', dataIndex: 'numero_cuenta', width: 110,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 11 }}>{v}</Text> },
    {
      title: 'Bruto anual', dataIndex: 'salario_bruto_anual', align: 'right' as const, width: 140,
      render: (v: number, row: any) => (
        <InputNumber
          size="small"
          value={v}
          min={0}
          step={100}
          precision={2}
          decimalSeparator=","
          style={{ width: 125 }}
          formatter={(val) => {
            if (val == null) return ''
            const s = String(val); if (!s) return ''
            const [intPart, decPart] = s.split('.')
            const intFmt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
            return decPart !== undefined ? `${intFmt},${decPart}` : intFmt
          }}
          parser={(val) => Number(String(val || '').replace(/\./g, '').replace(',', '.')) || 0}
          onChange={(val) => actualizarEmpleado.mutate({ id: row.id, data: { salario_bruto_anual: val ?? 0 } })}
        />
      ),
    },
    {
      title: <Tooltip title={SS_INFO}>% SS empleado ⓘ</Tooltip>,
      dataIndex: 'pct_ss', align: 'center' as const, width: 120,
      render: (v: number, row: any) => (
        <InputNumber
          size="small"
          min={0} max={20} step={0.01}
          precision={2}
          decimalSeparator=","
          value={v}
          disabled={row.es_autonomo}
          style={{ width: 80 }}
          formatter={(val) => val !== undefined && val !== null
            ? String(val).replace('.', ',')
            : ''
          }
          parser={(val) => Number(String(val || '').replace(',', '.')) || 0}
          onChange={(val) => actualizarEmpleado.mutate({ id: row.id, data: { pct_ss: val ?? 0 } })}
        />
      ),
    },
    {
      title: '% IRPF',
      dataIndex: 'pct_irpf', align: 'center' as const, width: 100,
      render: (v: number, row: any) => (
        <InputNumber
          size="small"
          min={0} max={50} step={0.5}
          precision={2}
          decimalSeparator=","
          value={v}
          style={{ width: 75 }}
          formatter={(val) => val !== undefined && val !== null
            ? String(val).replace('.', ',')
            : ''
          }
          parser={(val) => Number(String(val || '').replace(',', '.')) || 0}
          onChange={(val) => actualizarEmpleado.mutate({ id: row.id, data: { pct_irpf: val ?? 0 } })}
        />
      ),
    },
    {
      title: 'Pagas',
      dataIndex: 'num_pagas', align: 'center' as const, width: 80,
      render: (v: number, row: any) => (
        <Select
          size="small"
          value={v ?? 14}
          style={{ width: 64 }}
          onChange={(val) => actualizarEmpleado.mutate({ id: row.id, data: { num_pagas: val } })}
        >
          <Option value={12}>12</Option>
          <Option value={14}>14</Option>
        </Select>
      ),
    },
    {
      title: 'Neto/paga',
      align: 'right' as const, width: 120,
      render: (_: any, row: any) => {
        const pagas = row.num_pagas || 14
        const neto = (row.salario_bruto_anual / pagas) * (1 - row.pct_ss / 100 - row.pct_irpf / 100)
        return <Text strong style={{ fontSize: 12, color: '#389e0d' }}>{fmt(neto)}</Text>
      },
    },
    {
      title: 'SS+IRPF ret./paga',
      align: 'right' as const, width: 120,
      render: (_: any, row: any) => {
        const pagas = row.num_pagas || 14
        const ret = (row.salario_bruto_anual / pagas) * (row.pct_ss / 100 + row.pct_irpf / 100)
        return <Text type="secondary" style={{ fontSize: 11 }}>{fmt(ret)}</Text>
      },
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* Cabecera */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Tesorería presupuestada</Title>
          <Text type="secondary">Flujo de caja mensual proyectado desde ingresos y gastos aprobados</Text>
        </div>
        <Select placeholder="Selecciona ejercicio" style={{ width: 220 }}
          onChange={(v) => { setPresupuestoId(v); setCajaInicial(0); setCajaMinima(undefined) }}
          value={presupuestoId}>
          {(presupuestos as any[]).map((p: any) => (
            <Option key={p.id} value={p.id}>Ejercicio {p.ejercicio}</Option>
          ))}
        </Select>
      </div>

      {!presupuestoId && <Alert type="info" showIcon message="Selecciona un ejercicio presupuestario" />}

      {presupuestoId && (
        <>
          {/* ── Parámetros de cálculo ─────────────────────────────────────── */}
          <Card title="Parámetros de cálculo" size="small">
            <Row gutter={[24, 12]} align="middle">
              <Col span={6}>
                <Text style={{ display: 'block', marginBottom: 4 }}>Caja inicial (€)</Text>
                <InputNumber
                  style={{ width: '100%' }}
                  value={cajaInicial}
                  onChange={(v) => setCajaInicial(v ?? 0)}
                  step={1000}
                  precision={2}
                  decimalSeparator=","
                  formatter={(val) => {
                    if (val == null) return ''
                    const s = String(val); if (!s) return ''
                    const [intPart, decPart] = s.split('.')
                    const intFmt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
                    return decPart !== undefined ? `${intFmt},${decPart}` : intFmt
                  }}
                  parser={(val) => Number(String(val || '').replace(/\./g, '').replace(',', '.')) || 0}
                />
              </Col>
              <Col span={6}>
                <Text style={{ display: 'block', marginBottom: 4 }}>Caja mínima (€) — opcional</Text>
                <InputNumber
                  style={{ width: '100%' }}
                  value={cajaMinima}
                  onChange={(v) => setCajaMinima(v ?? undefined)}
                  step={1000}
                  precision={2}
                  decimalSeparator=","
                  formatter={(val) => {
                    if (val == null) return ''
                    const s = String(val); if (!s) return ''
                    const [intPart, decPart] = s.split('.')
                    const intFmt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
                    return decPart !== undefined ? `${intFmt},${decPart}` : intFmt
                  }}
                  parser={(val) => Number(String(val || '').replace(/\./g, '').replace(',', '.')) || 0}
                />
              </Col>
              <Col span={6}>
                <Button type="primary" icon={<CalculatorOutlined />} onClick={() => calcular.mutate()}
                  loading={calcular.isPending} style={{ marginTop: 24 }}>
                  Calcular tesorería
                </Button>
              </Col>
              {resultado && !resultado.aprobado && (
                <Col span={6}>
                  <Popconfirm title="¿Aprobar la tesorería presupuestada?"
                    onConfirm={() => aprobar.mutate()} okText="Aprobar">
                    <Button icon={<CheckCircleOutlined />} style={{ marginTop: 24 }}>
                      Aprobar tesorería
                    </Button>
                  </Popconfirm>
                </Col>
              )}
              {resultado?.aprobado && (
                <Col span={6}>
                  <Tag color="blue" style={{ marginTop: 24 }}>
                    <CheckCircleOutlined /> Aprobada
                  </Tag>
                </Col>
              )}
            </Row>
          </Card>

          {/* ── Configuración de timing ───────────────────────────────────── */}
          <Card
            size="small"
            title={<Space><ClockCircleOutlined /> Timing de cobros y pagos</Space>}
          >
            <Row gutter={[24, 8]} align="middle">
              <Col span={8}>
                <Text style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                  Cobros (todos los ingresos)
                </Text>
                <Select
                  size="small" style={{ width: '100%' }}
                  value={getReglaCobros()}
                  onChange={(v) => upsertConfig.mutate({ familia_gasto: KEY_COBROS_GLOBAL, regla_cobro: v })}
                >
                  {Object.entries(REGLA_LABELS).map(([k, lab]) => (
                    <Option key={k} value={k}>{lab}</Option>
                  ))}
                </Select>
              </Col>
              <Col span={8}>
                <Text style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                  Pagos — Cesiones a auxiliares
                </Text>
                <Select
                  size="small" style={{ width: '100%' }}
                  value={getReglaCesiones()}
                  onChange={(v) => upsertConfig.mutate({ familia_gasto: KEY_CESIONES, regla_pago: v })}
                >
                  {Object.entries(REGLA_LABELS).map(([k, lab]) => (
                    <Option key={k} value={k}>{lab}</Option>
                  ))}
                </Select>
              </Col>
              <Col span={8}>
                <Text style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                  Pagos — Resto de gastos (por defecto)
                </Text>
                <Select
                  size="small" style={{ width: '100%' }}
                  value={getReglaPagoDefault()}
                  onChange={(v) => upsertConfig.mutate({ familia_gasto: KEY_PAGOS_DEFAULT, regla_pago: v })}
                >
                  {Object.entries(REGLA_LABELS).map(([k, lab]) => (
                    <Option key={k} value={k}>{lab}</Option>
                  ))}
                </Select>
              </Col>
            </Row>
          </Card>

          {/* ── Empleados: SS e IRPF ─────────────────────────────────────── */}
          <Card
            size="small"
            title={<Space><TeamOutlined /> Empleados — SS e IRPF (pagos netos)</Space>}
            extra={
              <Popconfirm
                title="¿Regenerar empleados desde contabilidad 640*?"
                description="Se sobreescribirán los datos actuales."
                onConfirm={() => generarEmpleados.mutate()}
                okText="Generar"
              >
                <Button size="small" icon={<SyncOutlined />} loading={generarEmpleados.isPending}>
                  Generar desde 640*
                </Button>
              </Popconfirm>
            }
          >
            {(empleados as any[]).length === 0 ? (
              <Alert type="info" showIcon
                message="Sin empleados cargados. Pulsa «Generar desde 640*» para auto-poblar."
              />
            ) : (
              <>
                <Alert
                  type="info" showIcon style={{ marginBottom: 8 }}
                  message={<Text style={{ fontSize: 11 }}>{SS_INFO}. Autónomos (Cristina y Marta): SS = 0%, solo IRPF.</Text>}
                />
                <Table
                  dataSource={empleados as any[]}
                  columns={colsEmpleados}
                  rowKey="id"
                  size="small"
                  pagination={false}
                  summary={(data) => {
                    const brutoBruto = data.reduce((s, e) => s + (e.salario_bruto_anual || 0), 0)
                    const netoAnual = data.reduce((s, e) => {
                      const pagas = e.num_pagas || 14
                      return s + (e.salario_bruto_anual || 0) * (1 - (e.pct_ss || 0) / 100 - (e.pct_irpf || 0) / 100) * pagas / pagas
                    }, 0)
                    const retAnual = brutoBruto - netoAnual
                    return (
                      <Table.Summary.Row style={{ background: '#f0f7ff', fontWeight: 700 }}>
                        <Table.Summary.Cell index={0} colSpan={2}>
                          <Text strong style={{ fontSize: 11 }}>TOTAL ANUAL</Text>
                        </Table.Summary.Cell>
                        <Table.Summary.Cell index={2} align="right">
                          <Text strong style={{ fontSize: 12 }}>{fmt(brutoBruto)}</Text>
                        </Table.Summary.Cell>
                        <Table.Summary.Cell index={3} />
                        <Table.Summary.Cell index={4} />
                        <Table.Summary.Cell index={5} />
                        <Table.Summary.Cell index={6} align="right">
                          <Text strong style={{ fontSize: 12, color: '#389e0d' }}>{fmt(netoAnual)}/año</Text>
                        </Table.Summary.Cell>
                        <Table.Summary.Cell index={7} align="right">
                          <Text style={{ fontSize: 11, color: '#8c8c8c' }}>{fmt(retAnual)}/año</Text>
                        </Table.Summary.Cell>
                      </Table.Summary.Row>
                    )
                  }}
                />
              </>
            )}
          </Card>

          {/* ── Apuntes manuales ─────────────────────────────────────────── */}
          <Card
            size="small"
            title={<span>Apuntes manuales <Badge count={(apuntes as any[]).length} /></span>}
            extra={<Button size="small" icon={<PlusOutlined />} onClick={() => setModalApunte(true)}>Añadir apunte</Button>}
          >
            <Table dataSource={apuntes as any[]} columns={colsApuntes} rowKey="id"
              size="small" pagination={false} />
          </Card>

          {/* ── Resultado ─────────────────────────────────────────────────── */}
          {resultado && (
            <>
              {resultado.alertas?.length > 0 && (
                <Alert type="error" showIcon
                  message={`Alerta: caja por debajo del mínimo en ${resultado.alertas.length} mes/es`}
                  description={resultado.alertas.map((a: any) =>
                    `${MESES[a.mes - 1]}: ${fmt(a.caja_final)} (mínimo: ${fmt(a.caja_minima)})`
                  ).join(' | ')}
                />
              )}

              <Row gutter={[16, 16]}>
                {[
                  { title: 'Caja inicial',       value: resultado.caja_inicial,                  color: '#333'    },
                  { title: 'Cobros totales',      value: resultado.totales.cobros,                color: '#52c41a' },
                  { title: 'Pagos totales',       value: resultado.totales.pagos,                 color: '#f5222d' },
                  { title: 'Caja final diciembre',value: resultado.totales.caja_final_diciembre,  color: resultado.totales.caja_final_diciembre >= 0 ? '#1890ff' : '#f5222d' },
                ].map((item) => (
                  <Col span={6} key={item.title}>
                    <Card size="small">
                      <Text style={{ fontSize: 12, color: '#8c8c8c', display: 'block', marginBottom: 4 }}>
                        {item.title}
                      </Text>
                      <Text strong style={{ fontSize: 18, color: item.color }}>
                        {fmt(item.value)}
                      </Text>
                    </Card>
                  </Col>
                ))}
              </Row>

              <Card title="Evolución de caja mensual">
                <ResponsiveContainer width="100%" height={360}>
                  <ComposedChart data={datosGrafico} stackOffset="sign">
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="mes" />
                    {/* Eje izquierdo: flujos mensuales (barras) */}
                    <YAxis
                      yAxisId="flujos"
                      orientation="left"
                      tickFormatter={(v) => `${(v / 1000).toLocaleString('es-ES', { maximumFractionDigits: 0 })}k`}
                      label={{ value: 'Flujo (€)', angle: -90, position: 'insideLeft', offset: 10, style: { fontSize: 11 } }}
                    />
                    {/* Eje derecho: caja acumulada (línea) — escala independiente */}
                    <YAxis
                      yAxisId="caja"
                      orientation="right"
                      tickFormatter={(v) => `${(v / 1000).toLocaleString('es-ES', { maximumFractionDigits: 0 })}k`}
                      label={{ value: 'Caja (€)', angle: 90, position: 'insideRight', offset: 10, style: { fontSize: 11 } }}
                    />
                    <RTooltip
                      formatter={(v: number, name: string) =>
                        name === 'Caja acumulada' ? [fmt(v), name] : [fmt(Math.abs(v)), name]
                      }
                      labelFormatter={(label) => `Mes: ${label}`}
                    />
                    <Legend />
                    <Bar yAxisId="flujos" dataKey="cobros" name="Cobros (con timing)" stackId="inflow" fill="#52c41a" opacity={0.85} />
                    <Bar yAxisId="flujos" dataKey="entradas" name="Entradas manuales" stackId="inflow" fill="#95de64" opacity={0.85} />
                    <Bar yAxisId="flujos" dataKey="pagos" name="Pagos (con timing)" stackId="outflow" fill="#f5222d" opacity={0.85} />
                    <Bar yAxisId="flujos" dataKey="salidas" name="Salidas manuales" stackId="outflow" fill="#ff7875" opacity={0.85} />
                    <Line yAxisId="caja" type="monotone" dataKey="caja" name="Caja acumulada"
                      stroke="#1890ff" strokeWidth={2.5} dot={{ r: 4 }} />
                    <ReferenceLine yAxisId="flujos" y={0} stroke="#555" strokeWidth={1} />
                    {resultado.caja_minima != null && (
                      <ReferenceLine yAxisId="caja" y={resultado.caja_minima} stroke="#faad14"
                        strokeDasharray="5 5" label={{ value: 'Mínimo', position: 'insideTopRight', fontSize: 11 }} />
                    )}
                  </ComposedChart>
                </ResponsiveContainer>
              </Card>

              {/* ── Mod-111: IRPF trimestral a Hacienda ─────────────────── */}
              {(resultado.irpf_trimestral || []).length > 0 && (
                <Card
                  size="small"
                  title={
                    <Space>
                      <WarningOutlined style={{ color: '#faad14' }} />
                      Modelo 111 — IRPF trimestral a Hacienda
                    </Space>
                  }
                >
                  <Table
                    size="small"
                    pagination={false}
                    rowKey="trimestre"
                    dataSource={resultado.irpf_trimestral}
                    rowClassName={(row: any) => row.mes_pago === null ? 'ant-table-row-warning' : ''}
                    columns={[
                      {
                        title: 'Periodo', dataIndex: 'label', width: 140,
                        render: (v: string, row: any) => (
                          <Space size={4}>
                            <Text strong>{v}</Text>
                            {row.es_estimado && (
                              <Tooltip title="Se usa el 4T del ejercicio presupuestado como estimación del 4T del año anterior, que se paga en enero.">
                                <Tag color="gold" style={{ fontSize: 10 }}>est.</Tag>
                              </Tooltip>
                            )}
                          </Space>
                        ),
                      },
                      {
                        title: 'Mes de pago', dataIndex: 'mes_pago', width: 110,
                        render: (v: number) => <Tag color="orange">{MESES[v - 1]}</Tag>,
                      },
                      {
                        title: 'IRPF nómina', dataIndex: 'nomina', align: 'right' as const,
                        render: (v: number) => fmt(v),
                      },
                      {
                        title: 'IRPF cesiones', dataIndex: 'cesiones', align: 'right' as const,
                        render: (v: number) => fmt(v),
                      },
                      {
                        title: 'Total Hacienda', dataIndex: 'total', align: 'right' as const,
                        render: (v: number) => (
                          <Text strong style={{ color: '#f5222d' }}>{fmt(v)}</Text>
                        ),
                      },
                    ]}
                    summary={(data) => {
                      const totalHacienda = data.reduce((s, r) => s + (r.total || 0), 0)
                      return (
                        <Table.Summary.Row style={{ background: '#fff7e6' }}>
                          <Table.Summary.Cell index={0} colSpan={2}>
                            <Text strong style={{ fontSize: 11 }}>TOTAL EN FLUJO</Text>
                          </Table.Summary.Cell>
                          <Table.Summary.Cell index={2} align="right">
                            <Text strong>{fmt(data.reduce((s, r) => s + (r.nomina || 0), 0))}</Text>
                          </Table.Summary.Cell>
                          <Table.Summary.Cell index={3} align="right">
                            <Text strong>{fmt(data.reduce((s, r) => s + (r.cesiones || 0), 0))}</Text>
                          </Table.Summary.Cell>
                          <Table.Summary.Cell index={4} align="right">
                            <Text strong style={{ color: '#f5222d' }}>{fmt(totalHacienda)}</Text>
                          </Table.Summary.Cell>
                        </Table.Summary.Row>
                      )
                    }}
                  />
                </Card>
              )}

              <Card title="Detalle mensual">
                <Table
                  dataSource={[
                    {
                      mes: 0, label: 'Inicio',
                      cobros: 0, pagos: 0,
                      entradas_manuales: 0, salidas_manuales: 0,
                      flujo: 0, caja_final: resultado.caja_inicial,
                      alerta: false, _esInicio: true,
                    },
                    ...(resultado.meses || []),
                  ]}
                  columns={colsMeses}
                  rowKey="mes"
                  size="small"
                  pagination={false}
                  rowClassName={(row: any) =>
                    row._esInicio ? 'ant-table-row-selected' : row.alerta ? 'ant-table-row-danger' : ''
                  }
                />
              </Card>
            </>
          )}
        </>
      )}

      {/* ── Modal apunte manual ───────────────────────────────────────────── */}
      <Modal title="Nuevo apunte manual de tesorería" open={modalApunte}
        onOk={() => formApunte.validateFields().then(v => crearApunte.mutate(v))}
        onCancel={() => { setModalApunte(false); formApunte.resetFields() }}
        confirmLoading={crearApunte.isPending} okText="Añadir" cancelText="Cancelar">
        <Form form={formApunte} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="tipo" label="Tipo de apunte" rules={[{ required: true }]}>
            <Select>
              {Object.entries(TIPO_APUNTE_LABELS).map(([k, v]) => (
                <Option key={k} value={k}>{v}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="concepto" label="Concepto" rules={[{ required: true }]}>
            <input className="ant-input" placeholder="Ej: Préstamo ICO enero" />
          </Form.Item>
          <Form.Item name="mes" label="Mes" rules={[{ required: true }]}>
            <Select>{MESES.map((m, i) => <Option key={i + 1} value={i + 1}>{m}</Option>)}</Select>
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="importe_haber" label="Entrada de caja (€)" initialValue={0}>
                <InputNumber style={{ width: '100%' }} min={0} step={100} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="importe_debe" label="Salida de caja (€)" initialValue={0}>
                <InputNumber style={{ width: '100%' }} min={0} step={100} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="notas" label="Notas">
            <input className="ant-input" placeholder="Descripción adicional..." />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
