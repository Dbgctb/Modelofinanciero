import { useState, useEffect } from 'react'
import {
  Row, Col, Card, Typography, Select, Table, Tag, Tabs,
  Switch, Button, Statistic, Space, message, Tooltip, Badge, Alert,
} from 'antd'
import {
  TeamOutlined, CalculatorOutlined, BulbOutlined,
  DollarOutlined, BarChartOutlined, FilterOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { crossSellingApi } from '../../api/crossSelling'

const { Title, Text } = Typography

const RAMO_COLORS: Record<string, string> = {
  AUTO: 'blue', HOGAR: 'green', SALUD: 'red', VIDA: 'purple',
  DECESOS: 'default', ACCIDENTES: 'orange', RC: 'cyan',
  MULTIRRIESGO: 'geekblue', CIBER: 'magenta', FLOTILLAS: 'volcano', BAJAS: 'gold',
}

const fmt = (v: number | null | undefined) =>
  v != null ? v.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' €' : '—'

const pct = (v: number | null | undefined) =>
  v != null ? (v * 100).toFixed(1) + '%' : '—'

export default function CrossSellingConfiguracion() {
  const qc = useQueryClient()
  const [ejercicio, setEjercicio] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState('auxiliares')
  const [catFiltro, setCatFiltro] = useState<string>('')

  const { data: ejercicios = [] } = useQuery<number[]>({
    queryKey: ['cs-ejercicios'],
    queryFn: crossSellingApi.getEjercicios,
  })

  useEffect(() => {
    if (ejercicios.length && !ejercicio) setEjercicio(ejercicios[0])
  }, [ejercicios])

  // ── Auxiliares ──────────────────────────────────────────────────────────────
  const { data: auxiliares = [], isLoading: loadingAux } = useQuery({
    queryKey: ['cs-auxiliares', ejercicio],
    queryFn: () => crossSellingApi.getAuxiliares(ejercicio!),
    enabled: !!ejercicio,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ auxiliar, participa }: { auxiliar: string; participa: boolean }) =>
      crossSellingApi.updateAuxiliarParticipacion(auxiliar, participa),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cs-auxiliares'] }),
    onError: () => message.error('Error al actualizar participación'),
  })

  // ── Ramo stats ──────────────────────────────────────────────────────────────
  const { data: ramoStats = [], isLoading: loadingStats } = useQuery({
    queryKey: ['cs-ramo-stats', ejercicio],
    queryFn: () => crossSellingApi.getRamoStats(ejercicio!),
    enabled: !!ejercicio,
  })

  const calcularMutation = useMutation({
    mutationFn: () => crossSellingApi.calcularRamoStats(ejercicio!),
    onSuccess: (data) => {
      message.success(`Stats calculados: ${data.ramos.length} sub-ramos`)
      qc.invalidateQueries({ queryKey: ['cs-ramo-stats'] })
    },
    onError: () => message.error('Error al calcular estadísticas'),
  })

  // ── Ocurrencias ─────────────────────────────────────────────────────────────
  const { data: ocurrencias, isLoading: loadingOcurr } = useQuery({
    queryKey: ['cs-ocurrencias', ejercicio],
    queryFn: () => crossSellingApi.getOcurrencias(ejercicio!),
    enabled: !!ejercicio && activeTab === 'ocurrencias',
  })

  const nParticipan = auxiliares.filter(a => a.participa).length
  const primaParticipan = auxiliares.filter(a => a.participa).reduce((s, a) => s + a.prima_total, 0)

  // ── Filtro de categorías ─────────────────────────────────────────────────────
  const categorias = Array.from(
    new Set(ramoStats.map((r: any) => r.ramo_categoria).filter(Boolean))
  ).sort() as string[]

  const statsFiltered = catFiltro
    ? ramoStats.filter((r: any) => r.ramo_categoria === catFiltro)
    : ramoStats

  const verTodas = !catFiltro

  // ── Columnas auxiliares ─────────────────────────────────────────────────────
  const colsAux = [
    {
      title: 'Auxiliar',
      dataIndex: 'auxiliar',
      key: 'auxiliar',
      render: (v: string) => <Text strong style={{ fontSize: 13 }}>{v}</Text>,
    },
    {
      title: 'Prima total',
      dataIndex: 'prima_total',
      key: 'prima',
      align: 'right' as const,
      sorter: (a: any, b: any) => a.prima_total - b.prima_total,
      defaultSortOrder: 'descend' as const,
      render: (v: number) => <Text style={{ fontSize: 12 }}>{fmt(v)}</Text>,
    },
    {
      title: 'Recibos',
      dataIndex: 'n_recibos',
      key: 'n_recibos',
      align: 'right' as const,
      render: (v: number) => <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: 'Participa',
      dataIndex: 'participa',
      key: 'participa',
      align: 'center' as const,
      render: (v: boolean, record: any) => (
        <Switch
          checked={v}
          size="small"
          loading={toggleMutation.isPending}
          onChange={(checked) => toggleMutation.mutate({ auxiliar: record.auxiliar, participa: checked })}
          checkedChildren="Sí"
          unCheckedChildren="No"
        />
      ),
    },
  ]

  // ── Columnas ramo stats (dinámicas según filtro) ────────────────────────────
  const colsStats = [
    ...(verTodas ? [{
      title: 'Categoría',
      dataIndex: 'ramo_categoria',
      key: 'ramo_categoria',
      width: 120,
      sorter: (a: any, b: any) => (a.ramo_categoria || '').localeCompare(b.ramo_categoria || ''),
      render: (v: string) => v
        ? <Tag color={RAMO_COLORS[v] || 'default'} style={{ fontSize: 11 }}>{v}</Tag>
        : <Text type="secondary" style={{ fontSize: 11 }}>—</Text>,
    }] : []),
    {
      title: 'Sub-ramo',
      dataIndex: 'ramo',
      key: 'ramo',
      sorter: (a: any, b: any) => (a.ramo || '').localeCompare(b.ramo || ''),
      render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: 'Clientes',
      dataIndex: 'n_clientes',
      key: 'n_clientes',
      align: 'center' as const,
      width: 75,
      sorter: (a: any, b: any) => (a.n_clientes || 0) - (b.n_clientes || 0),
      render: (v: number) => <Text type="secondary">{v ?? '—'}</Text>,
    },
    {
      title: 'Prima media',
      dataIndex: 'prima_media',
      key: 'prima_media',
      align: 'right' as const,
      sorter: (a: any, b: any) => a.prima_media - b.prima_media,
      render: (v: number) => (
        <Tooltip title="Prima media anual por cliente en este sub-ramo (se usa en oportunidades)">
          <Text strong style={{ color: '#1677ff' }}>{fmt(v)}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Margen %',
      dataIndex: 'margen_medio',
      key: 'margen_medio',
      align: 'right' as const,
      width: 85,
      sorter: (a: any, b: any) => a.margen_medio - b.margen_medio,
      render: (v: number) => (
        <Text strong style={{ color: '#52c41a' }}>{pct(v)}</Text>
      ),
    },
    {
      title: 'Margen €',
      key: 'margen_eur',
      align: 'right' as const,
      width: 90,
      render: (_: any, r: any) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {fmt(r.prima_media != null && r.margen_medio != null ? r.prima_media * r.margen_medio : null)}
        </Text>
      ),
    },
  ]

  // ── Columnas ocurrencias por ramo ───────────────────────────────────────────
  const colsOcurrRamo = [
    {
      title: 'Ramo recomendado',
      dataIndex: 'ramo',
      key: 'ramo',
      render: (v: string) => <Tag color={RAMO_COLORS[v] || 'default'} style={{ fontSize: 13 }}>{v}</Tag>,
    },
    {
      title: 'Clientes',
      dataIndex: 'n_clientes',
      key: 'n_clientes',
      align: 'center' as const,
      sorter: (a: any, b: any) => a.n_clientes - b.n_clientes,
      defaultSortOrder: 'descend' as const,
      render: (v: number) => <Badge count={v} color="#1677ff" overflowCount={9999} />,
    },
    {
      title: 'Prima potencial',
      dataIndex: 'prima_potencial',
      key: 'prima_potencial',
      align: 'right' as const,
      render: (v: number) => <Text style={{ color: '#1677ff' }}>{fmt(v)}</Text>,
    },
    {
      title: 'Margen potencial',
      dataIndex: 'margen_potencial',
      key: 'margen_potencial',
      align: 'right' as const,
      render: (v: number) => <Text strong style={{ color: '#52c41a' }}>{fmt(v)}</Text>,
    },
  ]

  // ── Columnas ocurrencias por combinación ────────────────────────────────────
  const colsOcurrComb = [
    {
      title: 'Tiene',
      dataIndex: 'ramo_base',
      key: 'ramo_base',
      render: (v: string) => <Tag color={RAMO_COLORS[v] || 'default'} style={{ fontSize: 12 }}>{v}</Tag>,
    },
    {
      title: 'Se recomienda',
      dataIndex: 'ramo_objetivo',
      key: 'ramo_objetivo',
      render: (v: string) => <Tag color={RAMO_COLORS[v] || 'default'} style={{ fontSize: 12 }}>{v}</Tag>,
    },
    {
      title: 'Clientes',
      dataIndex: 'n_clientes',
      key: 'n_clientes',
      align: 'center' as const,
      sorter: (a: any, b: any) => a.n_clientes - b.n_clientes,
      defaultSortOrder: 'descend' as const,
      render: (v: number) => <Badge count={v} color="#722ed1" overflowCount={9999} />,
    },
    {
      title: 'Prima potencial',
      dataIndex: 'prima_potencial',
      key: 'prima_potencial',
      align: 'right' as const,
      render: (v: number) => <Text style={{ color: '#1677ff', fontSize: 12 }}>{fmt(v)}</Text>,
    },
  ]

  const tabItems = [
    {
      key: 'auxiliares',
      label: <span><TeamOutlined /> Auxiliares y Ramos</span>,
      children: (
        <>
          {/* KPIs resumen */}
          <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
            {[
              { title: 'Auxiliares participantes', value: nParticipan, total: auxiliares.length, color: '#52c41a', icon: <TeamOutlined /> },
              { title: 'Prima en oportunidades', value: fmt(primaParticipan), color: '#1677ff', icon: <DollarOutlined /> },
              { title: 'Sub-ramos configurados', value: ramoStats.length, color: '#722ed1', icon: <BarChartOutlined /> },
            ].map((k, i) => (
              <Col key={i} xs={24} sm={8}>
                <Card size="small" style={{ borderLeft: `4px solid ${k.color}`, borderRadius: 10 }}>
                  <Statistic
                    title={<Text type="secondary" style={{ fontSize: 12 }}>{k.title}</Text>}
                    value={k.value}
                    suffix={'total' in k ? <Text type="secondary" style={{ fontSize: 13 }}>/ {k.total}</Text> : undefined}
                    prefix={<span style={{ color: k.color }}>{k.icon}</span>}
                    valueStyle={{ fontSize: 20, fontWeight: 700 }}
                  />
                </Card>
              </Col>
            ))}
          </Row>

          {/* Auxiliares */}
          <Card
            size="small"
            title={<><TeamOutlined style={{ color: '#1677ff' }} /> Auxiliares</>}
            style={{ borderRadius: 10, marginBottom: 20 }}
          >
            <Table
              rowKey="auxiliar"
              columns={colsAux}
              dataSource={auxiliares}
              loading={loadingAux}
              size="small"
              pagination={{ pageSize: 10, showSizeChanger: false }}
              scroll={{ x: 480 }}
            />
          </Card>

          {/* Ramo stats */}
          <Card
            size="small"
            title={
              <Space>
                <BarChartOutlined style={{ color: '#722ed1' }} />
                <span>Prima y margen por sub-ramo</span>
                {catFiltro && (
                  <Tag color={RAMO_COLORS[catFiltro] || 'default'}>{catFiltro}</Tag>
                )}
              </Space>
            }
            extra={
              <Space>
                <FilterOutlined style={{ color: '#8c8c8c' }} />
                <Select
                  value={catFiltro || undefined}
                  placeholder="Todas las categorías"
                  allowClear
                  onChange={v => setCatFiltro(v || '')}
                  style={{ width: 200 }}
                  options={categorias.map(c => ({
                    value: c,
                    label: (
                      <Space size={4}>
                        <Tag color={RAMO_COLORS[c] || 'default'} style={{ margin: 0 }}>{c}</Tag>
                      </Space>
                    ),
                  }))}
                />
                <Button
                  size="small"
                  type="primary"
                  icon={<CalculatorOutlined />}
                  loading={calcularMutation.isPending}
                  onClick={() => ejercicio && calcularMutation.mutate()}
                >
                  Calcular {ejercicio}
                </Button>
              </Space>
            }
            style={{ borderRadius: 10 }}
          >
            {ramoStats.length === 0 && !loadingStats && (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 12 }}
                message='Sin datos — pulsa "Calcular" para generar las estadísticas del año seleccionado.'
                description="Las primas y márgenes calculados aquí son los que se usarán en el recálculo de oportunidades."
              />
            )}
            {ramoStats.length > 0 && (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 8, padding: '4px 12px', fontSize: 12 }}
                message='Sub-ramo vacío "(sin subramo)" indica recibos sin asignación en Ramo2.xlsx — es negocio real, no un error de datos.'
              />
            )}
            <Table
              rowKey={(r: any) => (r.ramo_categoria || '') + '::' + (r.ramo || '')}
              columns={colsStats}
              dataSource={statsFiltered}
              loading={loadingStats}
              size="small"
              pagination={{ pageSize: 20, showSizeChanger: false }}
              scroll={{ x: 'max-content' }}
              bordered
            />
          </Card>
        </>
      ),
    },
    {
      key: 'ocurrencias',
      label: <span><BulbOutlined /> Ocurrencias</span>,
      children: (
        <>
          <Row gutter={[20, 20]}>
            <Col xs={24} lg={10}>
              <Card
                size="small"
                title="Por ramo recomendado"
                style={{ borderRadius: 10 }}
              >
                <Table
                  rowKey="ramo"
                  columns={colsOcurrRamo}
                  dataSource={ocurrencias?.por_ramo_recomendado || []}
                  loading={loadingOcurr}
                  size="small"
                  pagination={false}
                  scroll={{ x: 380 }}
                />
              </Card>
            </Col>
            <Col xs={24} lg={14}>
              <Card
                size="small"
                title="Por combinación tiene → se recomienda"
                extra={<Text type="secondary" style={{ fontSize: 11 }}>Top 40 combinaciones</Text>}
                style={{ borderRadius: 10 }}
              >
                <Table
                  rowKey="combinacion"
                  columns={colsOcurrComb}
                  dataSource={ocurrencias?.por_combinacion || []}
                  loading={loadingOcurr}
                  size="small"
                  pagination={{ pageSize: 15, showSizeChanger: false }}
                  scroll={{ x: 420 }}
                />
              </Card>
            </Col>
          </Row>
        </>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <Title level={4} style={{ margin: 0 }}>
          <BarChartOutlined style={{ color: '#722ed1' }} /> Configuración Cross-Selling
        </Title>
        <Select
          value={ejercicio}
          onChange={setEjercicio}
          options={ejercicios.map((e: number) => ({ value: e, label: String(e) }))}
          style={{ width: 100 }}
          placeholder="Año"
        />
        <Text type="secondary" style={{ fontSize: 12 }}>
          Selecciona el año, calcula stats y marca auxiliares antes de recalcular oportunidades.
        </Text>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        style={{ background: 'transparent' }}
      />
    </div>
  )
}
