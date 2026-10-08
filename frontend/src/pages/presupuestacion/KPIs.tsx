import { useState } from 'react'
import {
  Card, Row, Col, Select, Button, Space, Typography, Tag, Alert,
  Table, Badge, Drawer, InputNumber, Form, message, Tabs, Statistic,
} from 'antd'
import {
  ThunderboltOutlined, SettingOutlined, BellOutlined,
  CheckCircleFilled, ExclamationCircleFilled, CloseCircleFilled,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { presupuestoApi } from '../../api/presupuesto'
import { kpisApi } from '../../api/kpis'
import { apiError } from '../../utils/errorHandler'

const { Title, Text } = Typography
const { Option } = Select

const SEMAFORO_CONFIG = {
  verde:    { color: '#52c41a', bg: '#f6ffed', border: '#b7eb8f', icon: <CheckCircleFilled style={{ color: '#52c41a' }} /> },
  amarillo: { color: '#faad14', bg: '#fffbe6', border: '#ffe58f', icon: <ExclamationCircleFilled style={{ color: '#faad14' }} /> },
  rojo:     { color: '#f5222d', bg: '#fff2f0', border: '#ffccc7', icon: <CloseCircleFilled style={{ color: '#f5222d' }} /> },
}

// KPIs donde MENOR es mejor
const KPI_INVERTIDOS = new Set(['KPI-06', 'KPI-08', 'KPI-10'])

// Umbrales por defecto (espejo del backend) para cuando el usuario no los ha configurado en BD
const UMBRALES_DEFAULT_FRONT: Record<string, { verde: number; amarillo: number }> = {
  'KPI-01': { verde: 95.0,  amarillo: 85.0   },
  'KPI-02': { verde: 0.0,   amarillo: -5000.0 },
  'KPI-04': { verde: 20.0,  amarillo: 12.0   },
  'KPI-05': { verde: 60.0,  amarillo: 40.0   },
  'KPI-06': { verde: 0.0,   amarillo: 30.0   },
  'KPI-08': { verde: 0.0,   amarillo: 5.0    },
  'KPI-10': { verde: 70.0,  amarillo: 85.0   },
  'KPI-11': { verde: 0.0,   amarillo: -5000.0 },
  'KPI-12': { verde: 15.0,  amarillo: 5.0    },
}

function SemaforoTag({ valor }: { valor: string }) {
  const cfg = SEMAFORO_CONFIG[valor as keyof typeof SEMAFORO_CONFIG]
  if (!cfg) return null
  return <Tag color={valor === 'verde' ? 'success' : valor === 'amarillo' ? 'warning' : 'error'} icon={cfg.icon}>
    {valor.charAt(0).toUpperCase() + valor.slice(1)}
  </Tag>
}

function KpiCard({ kpi, umbralesMap }: { kpi: any; umbralesMap: Map<string, any> }) {
  const sem = kpi.semaforo as keyof typeof SEMAFORO_CONFIG
  const cfg = SEMAFORO_CONFIG[sem] || SEMAFORO_CONFIG.verde

  // Detectar unidad desde el nombre (KPI-01/08 cambian en modo presupuesto)
  const isEur = kpi.nombre.includes('(€)') || kpi.nombre.endsWith('€)')
  const fmtVal = (v: number) => isEur
    ? v.toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' €'
    : v.toFixed(2) + '%'

  const val = kpi.valor !== null && kpi.valor !== undefined ? fmtVal(kpi.valor) : '—'

  // Meta y desviación
  const dbUmbral = umbralesMap.get(kpi.codigo)
  const defUmbral = UMBRALES_DEFAULT_FRONT[kpi.codigo]
  const umbral = dbUmbral || defUmbral

  // KPIs puramente informativos (montos absolutos €) no tienen meta significativa
  const esInformativo = kpi.nombre.toLowerCase().includes('presupuestados') ||
                        kpi.nombre.toLowerCase().includes('propios presupuestados')

  // Para invertidos: la meta visible es el límite amarillo (no exceder)
  // Para normales: la meta es el umbral verde (alcanzar o superar)
  const metaRaw: number | null = (!esInformativo && umbral)
    ? (KPI_INVERTIDOS.has(kpi.codigo) ? umbral.umbral_amarillo ?? defUmbral?.amarillo : umbral.umbral_verde ?? defUmbral?.verde)
    : null

  // desviación positiva = bueno, negativa = malo (mismo criterio para todos)
  const desv: number | null = metaRaw !== null && kpi.valor !== null
    ? (KPI_INVERTIDOS.has(kpi.codigo)
        ? parseFloat((metaRaw - kpi.valor).toFixed(2))   // inverted: meta - valor (positivo = bajo el límite)
        : parseFloat((kpi.valor - metaRaw).toFixed(2)))  // normal: valor - meta (positivo = sobre el objetivo)
    : null

  const dsvColor = desv === null ? '#666' : desv >= 0 ? '#52c41a' : '#f5222d'
  const dsvPrefix = desv !== null && desv > 0 ? '+' : ''
  const dsvLabel = desv !== null
    ? `${dsvPrefix}${isEur ? desv.toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' €' : desv.toFixed(2) + ' pp'}`
    : null

  return (
    <Card
      size="small"
      style={{ borderTop: `3px solid ${cfg.color}`, background: cfg.bg, borderColor: cfg.border, height: '100%' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
        <Text style={{ fontSize: 11, color: '#666', fontWeight: 600 }}>{kpi.codigo}</Text>
        {cfg.icon}
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, color: cfg.color, marginBottom: 2 }}>{val}</div>
      <Text style={{ fontSize: 12, color: '#555' }}>{kpi.nombre}</Text>

      {metaRaw !== null && (
        <div style={{ marginTop: 8, paddingTop: 6, borderTop: '1px solid #e8e8e8' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 2 }}>
            <Text type="secondary">Meta{KPI_INVERTIDOS.has(kpi.codigo) ? ' (límite)' : ' (objetivo)'}:</Text>
            <Text style={{ fontWeight: 600 }}>
              {isEur
                ? metaRaw.toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' €'
                : metaRaw.toFixed(2) + '%'}
            </Text>
          </div>
          {dsvLabel !== null && (
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <Text type="secondary">Desviación:</Text>
              <Text style={{ fontWeight: 700, color: dsvColor }}>{dsvLabel}</Text>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

export default function KPIs() {
  const qc = useQueryClient()
  const [presupuestoId, setPresupuestoId] = useState<string | null>(null)
  const [hastaMes, setHastaMes] = useState<number>(12)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [form] = Form.useForm()

  const { data: presupuestos = [] } = useQuery({
    queryKey: ['presupuestos'],
    queryFn: () => presupuestoApi.listar().then(r => r.data),
  })

  const { data: kpisData = [], isLoading } = useQuery({
    queryKey: ['kpis-resultados', presupuestoId],
    queryFn: () => kpisApi.resultados(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: alertas = [] } = useQuery({
    queryKey: ['kpis-alertas', presupuestoId],
    queryFn: () => kpisApi.alertas(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: umbrales = [] } = useQuery({
    queryKey: ['kpis-umbrales'],
    queryFn: () => kpisApi.umbrales().then(r => r.data),
  })

  const calcular = useMutation({
    mutationFn: () => kpisApi.calcular(presupuestoId!, hastaMes),
    onSuccess: () => {
      message.success('KPIs calculados correctamente')
      qc.invalidateQueries({ queryKey: ['kpis-resultados', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['kpis-alertas', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al calcular los KPIs')),
  })

  const actualizarUmbral = useMutation({
    mutationFn: ({ codigo, verde, amarillo }: { codigo: string; verde: number; amarillo: number }) =>
      kpisApi.actualizarUmbral(codigo, { umbral_verde: verde, umbral_amarillo: amarillo }),
    onSuccess: () => {
      message.success('Umbral actualizado')
      qc.invalidateQueries({ queryKey: ['kpis-umbrales'] })
    },
  })

  // KPIs sin dimensión → tarjetas; con dimensión → tablas
  const kpisSimples = kpisData.filter((k: any) => k.dimension === null || k.dimension === undefined)
  // Mapa de umbrales de BD (tiene prioridad sobre los defaults del frontend)
  const umbralesMap = new Map<string, any>(umbrales.map((u: any) => [u.kpi_codigo as string, u]))
  const kpi07 = kpisData.filter((k: any) => k.codigo === 'KPI-07')
  const kpi09 = kpisData.filter((k: any) => k.codigo === 'KPI-09')
  const kpi13 = kpisData.filter((k: any) => k.codigo === 'KPI-13')
  const kpi14 = kpisData.filter((k: any) => k.codigo === 'KPI-14')
  const kpi15 = kpisData.filter((k: any) => k.codigo === 'KPI-15')

  const colsDim = (unidad: string) => [
    { title: 'Dimensión', dataIndex: 'dimension', ellipsis: true },
    {
      title: 'Valor', dataIndex: 'valor', align: 'right' as const,
      render: (v: number) => unidad === '%' ? `${v?.toFixed(2)}%` : v?.toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' €',
    },
    { title: 'Semáforo', dataIndex: 'semaforo', render: (v: string) => <SemaforoTag valor={v} /> },
  ]

  // Columnas para dependencia: incluye % acumulado
  const colsDep = (datos: any[]) => {
    let acum = 0
    const withAcum = datos.map((r: any) => { acum += r.valor; return { ...r, _acum: Math.min(acum, 100) } })
    return {
      dataSource: withAcum,
      columns: [
        { title: 'Dimensión', dataIndex: 'dimension', ellipsis: true },
        { title: '%', dataIndex: 'valor', align: 'right' as const, width: 70,
          render: (v: number) => `${v?.toFixed(2)}%` },
        { title: '% Acum.', dataIndex: '_acum', align: 'right' as const, width: 80,
          render: (v: number) => <span style={{ color: v >= 80 ? '#f5222d' : v >= 60 ? '#faad14' : '#666' }}>{v?.toFixed(1)}%</span> },
        { title: 'Semáforo', dataIndex: 'semaforo', width: 90, render: (v: string) => <SemaforoTag valor={v} /> },
      ],
    }
  }

  // KPI-09: unidad dinámica según nombre (% en modo presupuesto, € en modo real)
  const kpi09Unit = kpi09.length > 0 && (kpi09[0] as any).nombre?.includes('(%)') ? '%' : '€'
  const kpi09Label = kpi09Unit === '%' ? 'Distribución gastos por familia' : 'Desv. gastos por familia'

  const dep13 = colsDep(kpi13)
  const dep14 = colsDep(kpi14)

  const colsUmbrales = [
    { title: 'KPI', dataIndex: 'kpi_codigo', width: 100 },
    { title: 'Umbral verde (≥)', dataIndex: 'umbral_verde', align: 'right' as const, render: (v: number) => v?.toFixed(2) },
    { title: 'Umbral amarillo (≥)', dataIndex: 'umbral_amarillo', align: 'right' as const, render: (v: number) => v?.toFixed(2) },
    {
      title: '',
      render: (_: any, row: any) => (
        <Button size="small" onClick={() => {
          form.setFieldsValue({ codigo: row.kpi_codigo, verde: row.umbral_verde, amarillo: row.umbral_amarillo })
          setDrawerOpen(true)
        }}>Editar</Button>
      ),
    },
  ]

  const totalRojo = kpisSimples.filter((k: any) => k.semaforo === 'rojo').length
  const totalAmarillo = kpisSimples.filter((k: any) => k.semaforo === 'amarillo').length

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Panel de KPIs</Title>
          <Text type="secondary">Indicadores clave de rendimiento presupuestario</Text>
        </div>
        <Space>
          <Select placeholder="Ejercicio" style={{ width: 200 }} onChange={setPresupuestoId} value={presupuestoId}>
            {presupuestos.map((p: any) => <Option key={p.id} value={p.id}>Ejercicio {p.ejercicio}</Option>)}
          </Select>
          <Select value={hastaMes} onChange={setHastaMes} style={{ width: 100 }}>
            {['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'].map((m, i) => (
              <Option key={i + 1} value={i + 1}>Hasta {m}</Option>
            ))}
          </Select>
          <Button
            type="primary" icon={<ThunderboltOutlined />}
            loading={calcular.isPending}
            disabled={!presupuestoId}
            onClick={() => calcular.mutate()}
          >
            Calcular KPIs
          </Button>
          <Button icon={<SettingOutlined />} onClick={() => setDrawerOpen(true)}>
            Umbrales
          </Button>
        </Space>
      </div>

      {!presupuestoId && <Alert type="info" showIcon message="Selecciona un ejercicio para ver los KPIs" />}

      {presupuestoId && kpisData.length === 0 && !isLoading && (
        <Alert type="warning" showIcon message="No hay KPIs calculados. Pulsa 'Calcular KPIs' para generarlos." />
      )}

      {/* Alertas de gestión */}
      {alertas.length > 0 && (
        <Card
          title={<Space><BellOutlined style={{ color: '#f5222d' }} /><span>Alertas de gestión</span><Badge count={alertas.length} /></Space>}
          style={{ borderTop: '3px solid #f5222d' }}
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            {alertas.map((a: any) => (
              <Alert
                key={a.codigo}
                type={a.nivel === 'rojo' ? 'error' : 'warning'}
                showIcon
                message={a.titulo}
                description={`${a.descripcion} — Valor actual: ${a.valor}`}
              />
            ))}
          </Space>
        </Card>
      )}

      {/* Resumen semáforos */}
      {kpisSimples.length > 0 && (
        <Row gutter={16}>
          <Col span={8}>
            <Card style={{ textAlign: 'center', borderTop: '3px solid #52c41a' }}>
              <Statistic title="KPIs en Verde" value={kpisSimples.filter((k: any) => k.semaforo === 'verde').length}
                valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleFilled />} />
            </Card>
          </Col>
          <Col span={8}>
            <Card style={{ textAlign: 'center', borderTop: '3px solid #faad14' }}>
              <Statistic title="KPIs en Amarillo" value={totalAmarillo}
                valueStyle={{ color: '#faad14' }} prefix={<ExclamationCircleFilled />} />
            </Card>
          </Col>
          <Col span={8}>
            <Card style={{ textAlign: 'center', borderTop: '3px solid #f5222d' }}>
              <Statistic title="KPIs en Rojo" value={totalRojo}
                valueStyle={{ color: '#f5222d' }} prefix={<CloseCircleFilled />} />
            </Card>
          </Col>
        </Row>
      )}

      {kpisSimples.length > 0 && (
        <Tabs items={[
          {
            key: 'principales',
            label: 'KPIs principales',
            children: (
              <Row gutter={[12, 12]}>
                {kpisSimples.map((k: any) => (
                  <Col key={k.codigo} xs={24} sm={12} md={8} lg={6}>
                    <KpiCard kpi={k} umbralesMap={umbralesMap} />
                  </Col>
                ))}
              </Row>
            ),
          },
          {
            key: 'kpi07',
            label: 'Ingreso neto por auxiliar',
            children: (
              <Table dataSource={kpi07} columns={colsDim('€')} rowKey="dimension" size="small" pagination={false} />
            ),
          },
          {
            key: 'kpi09',
            label: kpi09Label,
            children: (
              <Table dataSource={kpi09} columns={colsDim(kpi09Unit)} rowKey="dimension" size="small" pagination={false} />
            ),
          },
          {
            key: 'kpi13',
            label: 'Dependencia compañía',
            children: (
              <Table dataSource={dep13.dataSource} columns={dep13.columns} rowKey="dimension" size="small" pagination={{ pageSize: 20 }} />
            ),
          },
          {
            key: 'kpi14',
            label: 'Dependencia auxiliar',
            children: (
              <Table dataSource={dep14.dataSource} columns={dep14.columns} rowKey="dimension" size="small" pagination={{ pageSize: 20 }} />
            ),
          },
          {
            key: 'kpi15',
            label: 'Mix de ramos',
            children: (
              <Table dataSource={kpi15} columns={colsDim('%')} rowKey="dimension" size="small" pagination={false} />
            ),
          },
        ]} />
      )}

      <Drawer
        title="Configurar umbrales de semáforo"
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); form.resetFields() }}
        width={480}
      >
        <Table
          dataSource={umbrales}
          columns={colsUmbrales}
          rowKey="kpi_codigo"
          size="small"
          pagination={false}
          style={{ marginBottom: 24 }}
        />
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => {
            actualizarUmbral.mutate({ codigo: values.codigo, verde: values.verde, amarillo: values.amarillo })
            form.resetFields()
          }}
        >
          <Form.Item name="codigo" label="Código KPI" rules={[{ required: true }]}>
            <Select placeholder="Selecciona KPI">
              {['KPI-01','KPI-02','KPI-04','KPI-05','KPI-06','KPI-08','KPI-10','KPI-11','KPI-12'].map(c => (
                <Option key={c} value={c}>{c}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="verde" label="Umbral verde" rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="amarillo" label="Umbral amarillo" rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={actualizarUmbral.isPending} block>
            Guardar umbral
          </Button>
        </Form>
      </Drawer>
    </Space>
  )
}
