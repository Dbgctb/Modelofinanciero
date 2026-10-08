import { useState, useEffect } from 'react'
import {
  Row, Col, Card, Typography, Select, Table, Tag, Tooltip,
  Button, Modal, Form, Input, Statistic, Switch,
  InputNumber, Progress, Space, Alert, message, Drawer,
  Badge, Divider, Spin,
} from 'antd'
import {
  BulbOutlined, ThunderboltOutlined, ReloadOutlined,
  DollarOutlined, BellOutlined, UploadOutlined,
  TeamOutlined, UserOutlined, FireOutlined, SafetyOutlined,
  EyeOutlined,
  BankOutlined, HomeOutlined, CarOutlined, HeartOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { crossSellingApi } from '../../api/crossSelling'

const { Title, Text } = Typography

const RAMO_COLORS: Record<string, string> = {
  AUTO: 'blue', HOGAR: 'green', SALUD: 'red', VIDA: 'purple',
  DECESOS: 'default', ACCIDENTES: 'orange', RC: 'cyan',
  MULTIRRIESGO: 'geekblue', CIBER: 'magenta', FLOTILLAS: 'volcano', BAJAS: 'gold',
}

const RAMO_ICONS: Record<string, React.ReactNode> = {
  AUTO: <CarOutlined />, HOGAR: <HomeOutlined />, SALUD: <HeartOutlined />,
  VIDA: <SafetyOutlined />, RC: <BankOutlined />,
}

const ESTADO_OPTIONS = [
  { value: 'contactado', label: 'Contactado' },
  { value: 'propuesta', label: 'Propuesta enviada' },
  { value: 'ganado', label: '✓ Ganado' },
  { value: 'perdido', label: 'Perdido' },
  { value: 'no_interesado', label: 'No interesado' },
]

const fmt = (v: number | null | undefined) =>
  v != null ? v.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' €' : '—'

const pct = (v: number | null | undefined) =>
  v != null ? v.toFixed(1) + '%' : '—'

const scoreColor = (s: number) => s >= 70 ? '#52c41a' : s >= 50 ? '#faad14' : '#ff4d4f'
const scoreLabel = (s: number) => s >= 70 ? 'Alto' : s >= 50 ? 'Medio' : 'Bajo'

export default function Oportunidades() {
  const qc = useQueryClient()
  const [ejercicio, setEjercicio] = useState<number | null>(null)
  const [ramoFiltro, setRamoFiltro] = useState<string | undefined>()
  const [scoreMin, setScoreMin] = useState(0)
  const [sinAccionar, setSinAccionar] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [clienteDetalle, setClienteDetalle] = useState<any>(null)
  const [loadingDetalle, setLoadingDetalle] = useState(false)
  const [form] = Form.useForm()
  const [showGanado, setShowGanado] = useState(false)
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)

  const { data: ejercicios = [] } = useQuery<number[]>({
    queryKey: ['cs-ejercicios'],
    queryFn: crossSellingApi.getEjercicios,
  })

  useEffect(() => {
    if (ejercicios.length && !ejercicio) setEjercicio(ejercicios[0])
  }, [ejercicios])

  const { data: clientes = [] } = useQuery({
    queryKey: ['cs-clientes'],
    queryFn: crossSellingApi.getClientes,
  })

  const { data: oportunidades = [], isLoading } = useQuery({
    queryKey: ['cs-oportunidades', ejercicio, ramoFiltro, scoreMin, sinAccionar],
    queryFn: () => crossSellingApi.getOportunidades(ejercicio!, {
      ramo: ramoFiltro, score_min: scoreMin, sin_accionar: sinAccionar,
    }),
    enabled: !!ejercicio,
  })

  const recalcularMutation = useMutation({
    mutationFn: () => crossSellingApi.recalcular(ejercicio!),
    onSuccess: (data: any) => {
      message.success(`Scoring actualizado: ${data.oportunidades} oportunidades, ${data.alertas} alertas de fuga`)
      qc.invalidateQueries({ queryKey: ['cs-oportunidades'] })
    },
    onError: () => message.error('Error al recalcular el scoring'),
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => crossSellingApi.uploadClientes(file),
    onSuccess: (data: any) => {
      message.success(`${data.insertados} clientes nuevos, ${data.actualizados} actualizados`)
      setUploadModalOpen(false)
      setUploadFile(null)
      qc.invalidateQueries({ queryKey: ['cs-clientes'] })
    },
    onError: () => message.error('Error al cargar el fichero de clientes'),
  })

  const accionMutation = useMutation({
    mutationFn: (payload: any) => crossSellingApi.createAccion(payload),
    onSuccess: () => {
      message.success('Acción registrada correctamente')
      setModalOpen(false)
      form.resetFields()
      qc.invalidateQueries({ queryKey: ['cs-oportunidades'] })
    },
    onError: () => message.error('Error al registrar la acción'),
  })

  const handleVerCliente = async (record: any) => {
    setSelected(record)
    setDrawerOpen(true)
    setLoadingDetalle(true)
    setClienteDetalle(null)
    try {
      const detalle = await crossSellingApi.getClienteDetalle(record.tomador, ejercicio!)
      setClienteDetalle(detalle)
    } catch {
      message.error('Error cargando detalle del cliente')
    } finally {
      setLoadingDetalle(false)
    }
  }

  const totalMargenEsp = oportunidades.reduce((s: number, o: any) => s + (o.margen_esperado || 0), 0)
  const scoreMedio = oportunidades.length
    ? oportunidades.reduce((s: number, o: any) => s + o.score, 0) / oportunidades.length
    : 0
  const pendientes = oportunidades.filter((o: any) => !o.tiene_accion_activa).length
  const ramosDisponibles = Array.from(new Set(oportunidades.map((o: any) => o.ramo_recomendado))).sort() as string[]

  const expandedRowRender = (record: any) => (
    <div style={{ padding: '10px 16px 10px 40px', background: '#fafafa', borderBottom: '1px solid #f0f0f0' }}>
      <Row gutter={24}>
        <Col xs={24} md={10}>
          <Text type="secondary" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Cartera vigente
          </Text>
          <div style={{ marginTop: 6 }}>
            {(record.ramos_actuales || []).map((r: string) => (
              <div key={r} style={{ marginBottom: 6 }}>
                <Tag color={RAMO_COLORS[r] || 'default'} style={{ fontSize: 11 }}>{r}</Tag>
                {(record.subramos_vigentes?.[r] || []).map((s: string) => (
                  <div key={s} style={{ fontSize: 10, color: '#595959', paddingLeft: 8, lineHeight: 1.7 }}>• {s}</div>
                ))}
              </div>
            ))}
          </div>
        </Col>
        <Col xs={12} md={6}>
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: '#8c8c8c' }}>Prima actual del cliente</div>
            <div style={{ fontSize: 15, fontWeight: 700 }}>{fmt(record.prima_total_activa)}</div>
          </div>
          <div>
            <Tooltip title="Media ponderada de prima por sub-ramo de la categoría recomendada en la cartera real">
              <div style={{ fontSize: 11, color: '#8c8c8c' }}>Prima esperada</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: '#1677ff' }}>
                {record.prima_esperada ? fmt(record.prima_esperada) : '—'}
              </div>
            </Tooltip>
          </div>
        </Col>
        <Col xs={12} md={8}>
          <Text type="secondary" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Motivo
          </Text>
          <div style={{ fontSize: 12, color: '#595959', marginTop: 4, lineHeight: 1.6 }}>
            {record.motivo}
          </div>
        </Col>
      </Row>
    </div>
  )

  const columns = [
    {
      title: 'Cliente',
      dataIndex: 'tomador',
      key: 'tomador',
      width: 215,
      render: (v: string, record: any) => (
        <div>
          <Button
            type="link"
            style={{ padding: 0, fontWeight: 600, fontSize: 13, textAlign: 'left', height: 'auto', whiteSpace: 'normal', lineHeight: 1.3 }}
            onClick={() => handleVerCliente(record)}
            icon={<EyeOutlined style={{ fontSize: 11 }} />}
          >
            {v}
          </Button>
          <div style={{ marginTop: 3, display: 'flex', flexWrap: 'wrap', gap: 3, alignItems: 'center' }}>
            {record.tipo_cliente === 'juridico' && (
              <Tag style={{ fontSize: 10, margin: 0, lineHeight: '16px' }} color="geekblue">Empresa</Tag>
            )}
            {record.antiguedad_anos > 0 && (
              <Text type="secondary" style={{ fontSize: 10 }}>{record.antiguedad_anos.toFixed(0)}a</Text>
            )}
            {record.auxiliar && (
              <Text type="secondary" style={{ fontSize: 10 }}>· {record.auxiliar}</Text>
            )}
          </div>
        </div>
      ),
    },
    {
      title: 'Recomendar',
      dataIndex: 'ramo_recomendado',
      key: 'ramo',
      width: 185,
      render: (v: string, record: any) => {
        const subs = record.subramos_recomendados || []
        return (
          <div>
            <Tag color={RAMO_COLORS[v] || 'default'} icon={RAMO_ICONS[v]} style={{ fontSize: 12, padding: '2px 8px', marginBottom: 2 }}>
              {v}
            </Tag>
            {subs.slice(0, 2).map((s: string) => (
              <div key={s} style={{ fontSize: 10, color: '#595959', lineHeight: 1.4, paddingLeft: 2 }}>• {s}</div>
            ))}
            {subs.length > 2 && (
              <Tooltip title={subs.slice(2).join(' · ')}>
                <div style={{ fontSize: 10, color: '#1677ff', paddingLeft: 2, cursor: 'help' }}>
                  +{subs.length - 2} más
                </div>
              </Tooltip>
            )}
          </div>
        )
      },
    },
    {
      title: 'Score',
      dataIndex: 'score',
      key: 'score',
      width: 130,
      sorter: (a: any, b: any) => a.score - b.score,
      defaultSortOrder: 'descend' as const,
      render: (v: number, row: any) => (
        <Tooltip
          title={
            <div style={{ fontSize: 12 }}>
              <div>Afinidad de mercado: <b>{row.score_afinidad?.toFixed(0)}</b></div>
              <div>Similitud cartera: <b>{row.score_propension?.toFixed(0)}</b></div>
              <div>Valor cliente: <b>{row.score_valor?.toFixed(0)}</b></div>
              <div>Momento: <b>{row.score_timing?.toFixed(0)}</b></div>
            </div>
          }
        >
          <div style={{ cursor: 'help' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <Text strong style={{ color: scoreColor(v), fontSize: 18 }}>{v.toFixed(0)}</Text>
              <Text style={{ fontSize: 11, color: scoreColor(v) }}>{scoreLabel(v)}</Text>
            </div>
            <Progress percent={v} showInfo={false} size="small" strokeColor={scoreColor(v)} style={{ marginTop: 1, marginBottom: 0 }} />
          </div>
        </Tooltip>
      ),
    },
    {
      title: 'Cartera vigente',
      dataIndex: 'ramos_actuales',
      key: 'ramos',
      width: 170,
      render: (v: string[]) => (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
          {(v || []).map((r: string) => (
            <Tag key={r} color={RAMO_COLORS[r] || 'default'} style={{ fontSize: 10, margin: '1px 0', padding: '0 6px' }}>
              {r}
            </Tag>
          ))}
        </div>
      ),
    },
    {
      title: 'Margen esp.',
      dataIndex: 'margen_esperado',
      key: 'margen',
      width: 105,
      align: 'right' as const,
      sorter: (a: any, b: any) => (a.margen_esperado || 0) - (b.margen_esperado || 0),
      render: (v: number) => (
        <Tooltip title="Prima esperada × margen medio ponderado de los sub-ramos de la categoría">
          <Text strong style={{ color: '#52c41a', fontSize: 13 }}>{v ? fmt(v) : '—'}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Acción',
      key: 'acciones',
      width: 155,
      render: (_: any, record: any) => (
        <Space direction="vertical" size={2}>
          <Tag color={record.tiene_accion_activa ? 'processing' : 'default'} style={{ fontSize: 11 }}>
            {record.accion_sugerida}
          </Tag>
          <Button
            type={record.tiene_accion_activa ? 'default' : 'primary'}
            size="small"
            icon={<ThunderboltOutlined />}
            onClick={() => {
              setSelected(record)
              form.resetFields()
              setShowGanado(false)
              setModalOpen(true)
            }}
            style={{ fontSize: 11 }}
          >
            {record.tiene_accion_activa ? 'Actualizar' : 'Accionar'}
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <Title level={4} style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <BulbOutlined style={{ color: '#1677ff' }} />
          Oportunidades Cross-selling
        </Title>
        <Select
          value={ejercicio}
          onChange={setEjercicio}
          options={ejercicios.map((e: number) => ({ value: e, label: String(e) }))}
          style={{ width: 100 }}
          placeholder="Año"
        />
        <Button
          type="primary"
          icon={<ReloadOutlined />}
          loading={recalcularMutation.isPending}
          onClick={() => ejercicio && Modal.confirm({
            title: 'Recalcular scoring de oportunidades',
            content: `Se analizarán los recibos vigentes del ejercicio ${ejercicio} y se recalcularán todos los scores.`,
            okText: 'Recalcular',
            onOk: () => recalcularMutation.mutate(),
          })}
        >
          Recalcular
        </Button>
        <Button icon={<UploadOutlined />} onClick={() => setUploadModalOpen(true)}>
          Cargar clientes
        </Button>
        <Tag icon={<TeamOutlined />} color="blue">{clientes.length} clientes</Tag>
      </div>

      {/* KPIs */}
      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        {[
          { title: 'Oportunidades', value: oportunidades.length, color: '#1677ff', icon: <BulbOutlined /> },
          { title: 'Score medio', value: scoreMedio.toFixed(0), color: '#722ed1', icon: <FireOutlined />, suffix: '/100' },
          { title: 'Margen esperado total', value: fmt(totalMargenEsp), color: '#52c41a', icon: <DollarOutlined /> },
          { title: 'Sin accionar', value: pendientes, color: '#faad14', icon: <BellOutlined /> },
        ].map((k, i) => (
          <Col key={i} xs={24} sm={12} xl={6}>
            <Card
              size="small"
              style={{ borderRadius: 12, borderLeft: `4px solid ${k.color}`, boxShadow: '0 2px 8px rgba(0,0,0,0.07)' }}
              styles={{ body: { padding: '16px 20px' } }}
            >
              <Statistic
                title={<Text type="secondary" style={{ fontSize: 12 }}>{k.title}</Text>}
                value={k.value}
                suffix={'suffix' in k ? k.suffix : undefined}
                prefix={<span style={{ color: k.color }}>{k.icon}</span>}
                valueStyle={{ fontSize: 22, fontWeight: 700, color: '#262626' }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* Filtros */}
      <Card
        size="small"
        style={{ marginBottom: 16, borderRadius: 10, background: '#fafafa' }}
        styles={{ body: { padding: '10px 16px' } }}
      >
        <Space size={20} wrap>
          <Space size={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>Producto a vender:</Text>
            <Select
              allowClear value={ramoFiltro} onChange={setRamoFiltro}
              options={ramosDisponibles.map(r => ({ value: r, label: r }))}
              style={{ width: 150 }} placeholder="Todos los ramos"
            />
          </Space>
          <Space size={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>Score mínimo:</Text>
            <Select
              value={scoreMin} onChange={setScoreMin}
              options={[
                { value: 0, label: 'Todos' },
                { value: 35, label: '≥ 35' },
                { value: 50, label: '≥ 50 (Medio)' },
                { value: 70, label: '≥ 70 (Alto)' },
              ]}
              style={{ width: 160 }}
            />
          </Space>
          <Space size={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>Solo pendientes:</Text>
            <Switch checked={sinAccionar} onChange={setSinAccionar} size="small" />
          </Space>
        </Space>
      </Card>

      {/* Tabla */}
      <Card
        style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}
        styles={{ body: { padding: 0 } }}
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={oportunidades}
          loading={isLoading}
          size="small"
          pagination={{ pageSize: 15, showTotal: (t) => `${t} oportunidades`, showSizeChanger: false }}
          scroll={{ x: 960 }}
          expandable={{
            expandedRowRender,
            rowExpandable: () => true,
            expandRowByClick: false,
          }}
          style={{ borderRadius: 12, overflow: 'hidden' }}
        />
      </Card>

      {/* Drawer detalle cliente */}
      <Drawer
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <UserOutlined style={{ color: '#1677ff' }} />
            <span style={{ fontWeight: 600 }}>{selected?.tomador}</span>
            {selected?.tipo_cliente === 'juridico' && (
              <Tag color="geekblue" style={{ fontSize: 11 }}>Empresa</Tag>
            )}
          </div>
        }
        width={640}
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); setClienteDetalle(null) }}
        styles={{ body: { padding: '16px 20px' } }}
      >
        {loadingDetalle ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" />
          </div>
        ) : clienteDetalle ? (
          <>
            {/* Resumen financiero */}
            <Row gutter={12} style={{ marginBottom: 16 }}>
              {[
                { label: 'Prima vigente', value: fmt(clienteDetalle.resumen.prima_vigente), color: '#1677ff' },
                { label: 'Margen real', value: pct(clienteDetalle.resumen.margen_pct), color: '#52c41a' },
                { label: 'Pólizas vigentes', value: clienteDetalle.resumen.n_recibos_vigentes, color: '#722ed1' },
              ].map((k, i) => (
                <Col key={i} span={8}>
                  <Card
                    size="small"
                    style={{ borderRadius: 8, textAlign: 'center', borderTop: `3px solid ${k.color}` }}
                    styles={{ body: { padding: '10px 8px' } }}
                  >
                    <div style={{ fontSize: 18, fontWeight: 700, color: k.color }}>{k.value}</div>
                    <div style={{ fontSize: 11, color: '#8c8c8c' }}>{k.label}</div>
                  </Card>
                </Col>
              ))}
            </Row>

            {/* Alerta de fuga */}
            {clienteDetalle.alerta_fuga && (
              <Alert
                type="warning"
                style={{ marginBottom: 16, borderRadius: 8 }}
                message={
                  <Space>
                    <Text strong>Riesgo de fuga detectado</Text>
                    <Badge
                      count={`${clienteDetalle.alerta_fuga.risk_score.toFixed(0)}/100`}
                      color="#faad14"
                    />
                  </Space>
                }
                description={
                  <div style={{ fontSize: 12, marginTop: 4 }}>
                    {(clienteDetalle.alerta_fuga.senales || []).map((s: any, i: number) => (
                      <div key={i}>• {s.desc}</div>
                    ))}
                  </div>
                }
              />
            )}

            {/* Oportunidades de venta para este cliente */}
            {clienteDetalle.oportunidades_score.length > 0 && (
              <>
                <Divider orientation="left" style={{ fontSize: 13, color: '#1677ff', margin: '12px 0' }}>
                  <BulbOutlined /> Oportunidades de venta
                </Divider>
                <Space wrap style={{ marginBottom: 16 }}>
                  {clienteDetalle.oportunidades_score.map((o: any) => (
                    <Tooltip key={o.ramo} title={o.motivo}>
                      <Tag
                        color={RAMO_COLORS[o.ramo] || 'default'}
                        style={{ padding: '4px 10px', cursor: 'help', fontSize: 13 }}
                      >
                        {o.ramo}{' '}
                        <Text style={{ color: 'inherit', opacity: 0.8, fontSize: 11 }}>
                          ({o.score.toFixed(0)})
                        </Text>
                      </Tag>
                    </Tooltip>
                  ))}
                </Space>
              </>
            )}

            {/* Pólizas vigentes */}
            <Divider orientation="left" style={{ fontSize: 13, margin: '12px 0' }}>
              <SafetyOutlined /> Pólizas vigentes ({clienteDetalle.resumen.n_recibos_vigentes})
            </Divider>
            <Table
              rowKey={(r: any) => r.codigo || r.numero_poliza || Math.random()}
              size="small"
              dataSource={clienteDetalle.recibos.filter((r: any) => r.vigente)}
              pagination={false}
              scroll={{ x: 520 }}
              style={{ marginBottom: 16 }}
              columns={[
                {
                  title: 'Ramo',
                  dataIndex: 'ramo_norm',
                  width: 110,
                  render: (v: string) => (
                    <Tag color={RAMO_COLORS[v] || 'default'} style={{ fontSize: 11 }}>{v}</Tag>
                  ),
                },
                {
                  title: 'Compañía',
                  dataIndex: 'compania',
                  width: 130,
                  render: (v: string) => <Text style={{ fontSize: 12 }}>{v || '—'}</Text>,
                },
                {
                  title: 'Auxiliar',
                  dataIndex: 'auxiliar',
                  width: 120,
                  render: (v: string) => <Text style={{ fontSize: 12 }}>{v || '—'}</Text>,
                },
                {
                  title: 'Prima',
                  dataIndex: 'pr_total',
                  align: 'right' as const,
                  render: (v: number) => <Text style={{ fontSize: 12 }}>{fmt(v)}</Text>,
                },
                {
                  title: 'Hasta',
                  dataIndex: 'hasta',
                  width: 90,
                  render: (v: string) => (
                    <Text style={{ fontSize: 11, color: '#595959' }}>{v ? v.slice(0, 10) : '—'}</Text>
                  ),
                },
              ]}
            />

            {/* Recibos vencidos en el ejercicio */}
            {clienteDetalle.recibos.filter((r: any) => !r.vigente).length > 0 && (
              <>
                <Divider orientation="left" style={{ fontSize: 12, color: '#8c8c8c', margin: '8px 0' }}>
                  Vencidos en el ejercicio ({clienteDetalle.recibos.filter((r: any) => !r.vigente).length})
                </Divider>
                <Table
                  rowKey={(r: any) => r.codigo || r.numero_poliza || Math.random()}
                  size="small"
                  dataSource={clienteDetalle.recibos.filter((r: any) => !r.vigente)}
                  pagination={false}
                  scroll={{ x: 420 }}
                  style={{ opacity: 0.6, marginBottom: 8 }}
                  columns={[
                    {
                      title: 'Ramo',
                      dataIndex: 'ramo_norm',
                      width: 110,
                      render: (v: string) => (
                        <Tag color="default" style={{ fontSize: 11 }}>{v}</Tag>
                      ),
                    },
                    {
                      title: 'Compañía',
                      dataIndex: 'compania',
                      width: 130,
                      render: (v: string) => <Text style={{ fontSize: 12 }}>{v || '—'}</Text>,
                    },
                    {
                      title: 'Prima',
                      dataIndex: 'pr_total',
                      align: 'right' as const,
                      render: (v: number) => <Text style={{ fontSize: 12 }}>{fmt(v)}</Text>,
                    },
                    {
                      title: 'Hasta',
                      dataIndex: 'hasta',
                      width: 90,
                      render: (v: string) => (
                        <Text style={{ fontSize: 11, color: '#ff4d4f' }}>{v ? v.slice(0, 10) : '—'}</Text>
                      ),
                    },
                  ]}
                />
              </>
            )}
          </>
        ) : null}
      </Drawer>

      {/* Modal cargar clientes */}
      <Modal
        open={uploadModalOpen}
        title="Cargar fichero de clientes"
        onOk={() => { if (uploadFile) uploadMutation.mutate(uploadFile) }}
        onCancel={() => { setUploadModalOpen(false); setUploadFile(null) }}
        okText="Cargar"
        cancelText="Cancelar"
        okButtonProps={{ disabled: !uploadFile }}
        confirmLoading={uploadMutation.isPending}
        width={480}
        destroyOnClose
      >
        <Alert
          type="info"
          style={{ marginBottom: 12 }}
          message="Columnas obligatorias: Código (o codigo_cliente), Nombre"
          description={
            <span>
              Opcionales: F.Alta, F.Nacimie, Fis/Jur (F o J), T. Fijo, T. Móvil, E-Mail
              <br />
              <span style={{ color: '#8c8c8c', fontSize: 11 }}>
                También acepta nombres estándar: fecha_alta, fecha_nacimiento, tipo, telefono_fijo, telefono_movil, email
              </span>
            </span>
          }
        />
        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          onChange={e => setUploadFile(e.target.files?.[0] ?? null)}
          style={{ width: '100%' }}
        />
        {uploadFile && (
          <div style={{ marginTop: 8, color: '#1677ff', fontSize: 12 }}>
            Fichero: <b>{uploadFile.name}</b> ({(uploadFile.size / 1024).toFixed(0)} KB)
          </div>
        )}
      </Modal>

      {/* Modal registrar acción */}
      <Modal
        open={modalOpen}
        title={selected ? `Registrar acción — ${selected.tomador}` : ''}
        onOk={async () => {
          const values = await form.validateFields()
          accionMutation.mutate({
            tipo: 'cross_selling',
            oportunidad_id: selected.id,
            tomador: selected.tomador,
            ramo_objetivo: selected.ramo_recomendado,
            ...values,
          })
        }}
        onCancel={() => { setModalOpen(false); form.resetFields() }}
        okText="Guardar"
        cancelText="Cancelar"
        confirmLoading={accionMutation.isPending}
        width={480}
        destroyOnClose
      >
        {selected && (
          <Alert
            type="info"
            style={{ marginBottom: 16 }}
            message={
              <span>
                Vender{' '}
                <Tag color={RAMO_COLORS[selected.ramo_recomendado] || 'default'}>
                  {selected.ramo_recomendado}
                </Tag>
                · Score <b>{selected.score?.toFixed(0)}</b> · {selected.accion_sugerida}
              </span>
            }
          />
        )}
        <Form form={form} layout="vertical">
          <Form.Item name="estado" label="Estado" rules={[{ required: true }]} initialValue="contactado">
            <Select options={ESTADO_OPTIONS} onChange={v => setShowGanado(v === 'ganado')} />
          </Form.Item>
          {showGanado && (
            <Form.Item name="margen_conseguido" label="Margen conseguido (€)">
              <InputNumber min={0} style={{ width: '100%' }} placeholder="Margen real obtenido" />
            </Form.Item>
          )}
          <Form.Item name="notas" label="Notas">
            <Input.TextArea rows={3} placeholder="Resultado del contacto, próximos pasos..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
