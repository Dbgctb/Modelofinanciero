import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card, Row, Col, Typography, Space, Table, Tag, Select, Button,
  Statistic, Descriptions, Spin, Alert, Tabs, Badge, Modal, Input, message,
  Divider, Popconfirm,
} from 'antd'
import {
  ArrowLeftOutlined, CheckCircleOutlined, WarningOutlined,
  RiseOutlined, FallOutlined, LockOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cargaApi } from '../../api/carga'
import { apiError } from '../../utils/errorHandler'

const { Title, Text } = Typography
const { Option } = Select

const LABEL_TIPO_NEGOCIO: Record<string, string> = {
  cartera: 'Cartera',
  nueva_produccion: 'Nueva producción',
}

const LABEL_TIPO_INCIDENCIA: Record<string, string> = {
  cuenta_sin_mapear: 'Cuenta sin mapear',
  compania_no_identificada: 'Compañía no identificada',
  recibo_no_extraido: 'Recibo no extraíble',
  recibo_no_encontrado: 'Recibo no encontrado',
  recibo_sin_ramo: 'Recibo sin ramo',
  recibo_sin_cartera: 'Sin cartera/nueva producción',
  gasto_sin_familia: 'Gasto sin familia',
  periodo_incorrecto: 'Periodo incorrecto',
  posible_duplicado: 'Posible duplicado',
}

const LABEL_TIPO_CUENTA: Record<string, string> = {
  ingreso: 'Ingreso',
  gasto: 'Gasto',
  tesoreria_excluida: 'Tesorería excluida',
  no_clasificada: 'No clasificada',
}

const COLOR_TIPO_CUENTA: Record<string, string> = {
  ingreso: 'blue',
  gasto: 'orange',
  tesoreria_excluida: 'default',
  no_clasificada: 'error',
}

function fmt(n: number) {
  return new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

export default function DetalleDiario() {
  const { cargaId } = useParams<{ cargaId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  // Apuntes
  const [pageApuntes, setPageApuntes] = useState(1)
  const [filtroEstado, setFiltroEstado] = useState<string | undefined>()
  const [filtroTipoCuenta, setFiltroTipoCuenta] = useState<string | undefined>()
  const [filtroMes, setFiltroMes] = useState<number | undefined>()

  // Incidencias
  const [modalVisible, setModalVisible] = useState(false)
  const [incidenciaActiva, setIncidenciaActiva] = useState<any>(null)
  const [resolucion, setResolucion] = useState('')

  const { data: dataApuntes, isLoading: cargandoApuntes, isError } = useQuery({
    queryKey: ['detalle-apuntes', cargaId, pageApuntes, filtroEstado, filtroTipoCuenta, filtroMes],
    queryFn: () => cargaApi.detalleApuntes(cargaId!, {
      estado: filtroEstado,
      tipo_cuenta: filtroTipoCuenta,
      mes: filtroMes,
      page: pageApuntes,
      page_size: 50,
    }).then(r => r.data),
    enabled: !!cargaId,
  })

  const { data: incidencias, isLoading: cargandoInc } = useQuery({
    queryKey: ['incidencias', cargaId],
    queryFn: () => cargaApi.incidencias(cargaId!).then(r => r.data),
    enabled: !!cargaId,
  })

  const cerrarCarga = useMutation({
    mutationFn: () => cargaApi.cerrarCarga(cargaId!),
    onSuccess: () => {
      message.success('Carga cerrada. Ya puedes iniciar el presupuesto.')
      qc.invalidateQueries({ queryKey: ['detalle-apuntes', cargaId] })
      qc.invalidateQueries({ queryKey: ['historial-cargas'] })
    },
    onError: (e) => message.error(apiError(e, 'Error al cerrar la carga')),
  })

  const resolverInc = useMutation({
    mutationFn: () => cargaApi.resolverIncidencia(cargaId!, incidenciaActiva.id, resolucion),
    onSuccess: () => {
      message.success('Incidencia resuelta')
      qc.invalidateQueries({ queryKey: ['incidencias', cargaId] })
      setModalVisible(false)
      setResolucion('')
    },
    onError: (e) => message.error(apiError(e, 'Error al resolver la incidencia')),
  })

  const carga = dataApuntes?.carga
  const apuntes = dataApuntes?.apuntes ?? []
  const totalApuntes = dataApuntes?.total ?? 0
  const incPendientes = (incidencias ?? []).filter((i: any) => i.estado === 'pendiente').length
  const incCriticasPendientes = (incidencias ?? []).filter((i: any) => i.estado === 'pendiente' && i.es_critica === 'si').length

  const colsApuntes = [
    { title: 'Línea', dataIndex: 'linea', width: 65, fixed: 'left' as const },
    { title: 'Fecha', dataIndex: 'fecha', width: 95 },
    { title: 'Cuenta', dataIndex: 'numero_cuenta', width: 105 },
    { title: 'Descripción', dataIndex: 'descripcion_cuenta', width: 170, ellipsis: true },
    { title: 'Concepto', dataIndex: 'concepto', width: 220, ellipsis: true },
    {
      title: 'Debe',
      dataIndex: 'debe',
      width: 115,
      align: 'right' as const,
      render: (v: number) => <span style={{ whiteSpace: 'nowrap' }}>{v > 0 ? fmt(v) : '—'}</span>,
    },
    {
      title: 'Haber',
      dataIndex: 'haber',
      width: 115,
      align: 'right' as const,
      render: (v: number) => <span style={{ whiteSpace: 'nowrap' }}>{v > 0 ? fmt(v) : '—'}</span>,
    },
    {
      title: 'Tipo cuenta',
      dataIndex: 'tipo_cuenta',
      width: 125,
      render: (v: string) => v
        ? <Tag color={COLOR_TIPO_CUENTA[v] ?? 'default'}>{LABEL_TIPO_CUENTA[v] ?? v}</Tag>
        : '—',
    },
    {
      title: 'Ramo',
      dataIndex: 'ramo',
      width: 110,
      render: (v: string) => v ?? '—',
    },
    {
      title: 'Tipo negocio',
      dataIndex: 'tipo_negocio',
      width: 145,
      render: (v: string) => v
        ? <Tag color={v === 'cartera' ? 'blue' : 'green'}>{LABEL_TIPO_NEGOCIO[v] ?? v}</Tag>
        : '—',
    },
    {
      title: 'Estado',
      dataIndex: 'estado',
      width: 125,
      fixed: 'right' as const,
      render: (v: string) => v === 'correcto'
        ? <Tag icon={<CheckCircleOutlined />} color="success">Correcto</Tag>
        : v === 'con_incidencia'
          ? <Tag icon={<WarningOutlined />} color="warning">Incidencia</Tag>
          : <Tag>{v}</Tag>,
    },
  ]

  const colsIncidencias = [
    {
      title: 'Tipo',
      dataIndex: 'tipo',
      render: (v: string) => LABEL_TIPO_INCIDENCIA[v] || v,
    },
    {
      title: 'Crítica',
      dataIndex: 'es_critica',
      width: 90,
      render: (v: string) => (
        <Tag color={v === 'si' ? 'error' : 'warning'}>{v === 'si' ? 'Crítica' : 'Menor'}</Tag>
      ),
    },
    { title: 'Descripción', dataIndex: 'descripcion', ellipsis: true },
    {
      title: 'Cuenta',
      render: (_: any, row: any) => row.apunte?.numero_cuenta || '—',
      width: 110,
    },
    {
      title: 'Concepto',
      render: (_: any, row: any) => row.apunte?.concepto || '—',
      ellipsis: true,
    },
    {
      title: 'Estado',
      dataIndex: 'estado',
      width: 110,
      render: (v: string) =>
        v === 'resuelta'
          ? <Tag color="success">Resuelta</Tag>
          : v === 'excluida'
            ? <Tag color="default">Excluida</Tag>
            : <Tag color="warning">Pendiente</Tag>,
    },
    {
      title: '',
      width: 100,
      render: (_: any, row: any) => row.estado === 'pendiente' ? (
        <Button
          size="small"
          type="primary"
          ghost
          onClick={() => { setIncidenciaActiva(row); setModalVisible(true) }}
        >
          Resolver
        </Button>
      ) : null,
    },
  ]

  if (isError) {
    return (
      <Alert
        type="error"
        message="No se pudo cargar el detalle del diario"
        action={<Button onClick={() => navigate(-1)}>Volver</Button>}
      />
    )
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/presupuestacion/carga')}>
            Volver
          </Button>
          <Title level={4} style={{ margin: 0 }}>Detalle carga de diario</Title>
          {carga?.estado === 'cerrado' && (
            <Tag icon={<LockOutlined />} color="blue">Cerrada (definitiva)</Tag>
          )}
        </Space>
        {carga?.tipo_carga === 'base_presupuestaria' && carga?.estado !== 'cerrado' && (
          <Popconfirm
            title="¿Cerrar esta carga como definitiva?"
            description={
              <span>
                Una vez cerrada servirá de base para el presupuesto de ingresos y gastos.<br />
                Esta acción no se puede deshacer.
              </span>
            }
            onConfirm={() => cerrarCarga.mutate()}
            okText="Cerrar definitivamente"
            cancelText="Cancelar"
            okButtonProps={{ danger: true }}
          >
            <Button
              type="primary"
              icon={<LockOutlined />}
              loading={cerrarCarga.isPending}
              disabled={incCriticasPendientes > 0}
              title={incCriticasPendientes > 0 ? `Hay ${incCriticasPendientes} incidencias críticas pendientes` : ''}
            >
              Cerrar carga
            </Button>
          </Popconfirm>
        )}
      </div>

      {carga && (
        <Card size="small">
          <Descriptions column={4} size="small">
            <Descriptions.Item label="Ejercicio">{carga.ejercicio}</Descriptions.Item>
            <Descriptions.Item label="Tipo">
              {carga.tipo_carga === 'base_presupuestaria' ? 'Base presupuestaria' : 'Real mensual'}
            </Descriptions.Item>
            <Descriptions.Item label="Fichero">{carga.nombre_fichero}</Descriptions.Item>
            <Descriptions.Item label="Fecha carga">
              {carga.created_at ? new Date(carga.created_at).toLocaleString('es-ES') : '—'}
            </Descriptions.Item>
          </Descriptions>
          <Divider style={{ margin: '12px 0' }} />
          <Row gutter={[24, 12]}>
            <Col xs={8} md={4}>
              <Statistic title="Total registros" value={carga.total_registros} />
            </Col>
            <Col xs={8} md={4}>
              <Statistic title="Correctos" value={carga.registros_correctos} valueStyle={{ color: '#52c41a' }} />
            </Col>
            <Col xs={8} md={4}>
              <Statistic
                title="Con incidencias"
                value={carga.registros_con_incidencia}
                valueStyle={{ color: carga.registros_con_incidencia > 0 ? '#faad14' : '#52c41a' }}
              />
            </Col>
            <Col xs={12} md={6}>
              <Space direction="vertical" size={2}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  <RiseOutlined style={{ color: '#1677ff' }} /> Debe total
                </Text>
                <Text strong style={{ whiteSpace: 'nowrap', fontSize: 16 }}>
                  {fmt(carga.importe_debe_total)} €
                </Text>
              </Space>
            </Col>
            <Col xs={12} md={6}>
              <Space direction="vertical" size={2}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  <FallOutlined style={{ color: '#722ed1' }} /> Haber total
                </Text>
                <Text strong style={{ whiteSpace: 'nowrap', fontSize: 16 }}>
                  {fmt(carga.importe_haber_total)} €
                </Text>
              </Space>
            </Col>
          </Row>
        </Card>
      )}

      <Tabs
        items={[
          {
            key: 'apuntes',
            label: `Apuntes (${totalApuntes.toLocaleString('es-ES')})`,
            children: (
              <Card>
                <Space wrap style={{ marginBottom: 16 }}>
                  <Select
                    placeholder="Estado"
                    allowClear
                    style={{ width: 160 }}
                    value={filtroEstado}
                    onChange={v => { setFiltroEstado(v); setPageApuntes(1) }}
                  >
                    <Option value="correcto">Correcto</Option>
                    <Option value="con_incidencia">Con incidencia</Option>
                  </Select>
                  <Select
                    placeholder="Tipo cuenta"
                    allowClear
                    style={{ width: 170 }}
                    value={filtroTipoCuenta}
                    onChange={v => { setFiltroTipoCuenta(v); setPageApuntes(1) }}
                  >
                    <Option value="ingreso">Ingreso</Option>
                    <Option value="gasto">Gasto</Option>
                    <Option value="no_clasificada">No clasificada</Option>
                  </Select>
                  <Select
                    placeholder="Mes"
                    allowClear
                    style={{ width: 120 }}
                    value={filtroMes}
                    onChange={v => { setFiltroMes(v); setPageApuntes(1) }}
                  >
                    {MESES.map((m, i) => (
                      <Option key={i + 1} value={i + 1}>{m}</Option>
                    ))}
                  </Select>
                </Space>
                <Spin spinning={cargandoApuntes}>
                  <Table
                    dataSource={apuntes}
                    columns={colsApuntes}
                    rowKey="id"
                    size="small"
                    scroll={{ x: 1490 }}
                    rowClassName={(row: any) => row.estado === 'con_incidencia' ? 'ant-table-row-warning' : ''}
                    pagination={{
                      current: pageApuntes,
                      pageSize: 50,
                      total: totalApuntes,
                      showTotal: (t) => `${t.toLocaleString('es-ES')} apuntes`,
                      onChange: (p) => setPageApuntes(p),
                      showSizeChanger: false,
                    }}
                  />
                </Spin>
              </Card>
            ),
          },
          {
            key: 'incidencias',
            label: (
              <Badge count={incPendientes} size="small" offset={[6, 0]}>
                Incidencias
              </Badge>
            ),
            children: (
              <Card>
                <Spin spinning={cargandoInc}>
                  <Table
                    dataSource={incidencias ?? []}
                    columns={colsIncidencias}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 20 }}
                    rowClassName={(row: any) =>
                      row.es_critica === 'si' && row.estado === 'pendiente' ? 'ant-table-row-danger' : ''
                    }
                  />
                </Spin>
              </Card>
            ),
          },
        ]}
      />

      <Modal
        title="Resolver incidencia"
        open={modalVisible}
        onOk={() => resolverInc.mutate()}
        onCancel={() => { setModalVisible(false); setResolucion('') }}
        confirmLoading={resolverInc.isPending}
        okText="Resolver"
        cancelText="Cancelar"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text strong>{incidenciaActiva?.descripcion}</Text>
          <Input.TextArea
            value={resolucion}
            onChange={e => setResolucion(e.target.value)}
            placeholder="Describe cómo se ha resuelto esta incidencia..."
            rows={3}
          />
        </Space>
      </Modal>
    </Space>
  )
}
