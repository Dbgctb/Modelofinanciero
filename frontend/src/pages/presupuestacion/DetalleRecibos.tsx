import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card, Row, Col, Typography, Space, Table, Tag, Select, Input,
  Button, Statistic, Descriptions, Spin, Alert,
} from 'antd'
import { ArrowLeftOutlined, SearchOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { cargaApi } from '../../api/carga'

const { Title, Text } = Typography
const { Option } = Select

const LABEL_TIPO: Record<string, string> = {
  cartera: 'Cartera',
  nueva_produccion: 'Nueva producción',
}

const COLOR_TIPO: Record<string, string> = {
  cartera: 'blue',
  nueva_produccion: 'green',
}

function fmt(n: number) {
  return new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

export default function DetalleRecibos() {
  const { cargaId } = useParams<{ cargaId: string }>()
  const navigate = useNavigate()

  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [filtroTipo, setFiltroTipo] = useState<string | undefined>()
  const [filtroRamo, setFiltroRamo] = useState<string | undefined>()
  const [filtroCompania, setFiltroCompania] = useState<string>('')
  const [busquedaCompania, setBusquedaCompania] = useState<string | undefined>()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['detalle-recibos', cargaId, page, pageSize, filtroTipo, filtroRamo, busquedaCompania],
    queryFn: () => cargaApi.detalleRecibos(cargaId!, {
      tipo_negocio: filtroTipo,
      ramo: filtroRamo,
      compania: busquedaCompania,
      page,
      page_size: pageSize,
    }).then(r => r.data),
    enabled: !!cargaId,
  })

  const carga = data?.carga
  const recibos = data?.recibos ?? []
  const total = data?.total ?? 0

  const sinTipo = recibos.filter((r: any) => !r.tipo_negocio).length
  const conTipo = recibos.filter((r: any) => r.tipo_negocio).length

  const columnas = [
    { title: 'Código', dataIndex: 'codigo', width: 85, fixed: 'left' as const },
    { title: 'Recibo Cía', dataIndex: 'recibo_cia', width: 130 },
    { title: 'Compañía', dataIndex: 'compania', width: 110, ellipsis: true },
    { title: 'Tomador', dataIndex: 'tomador', width: 160, ellipsis: true },
    { title: 'Producto', dataIndex: 'producto', width: 160, ellipsis: true },
    {
      title: 'Ramo',
      dataIndex: 'ramo',
      width: 120,
      render: (v: string) => v ? <Tag>{v}</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Tipo negocio',
      dataIndex: 'tipo_negocio',
      width: 145,
      fixed: 'right' as const,
      render: (v: string) => v
        ? <Tag color={COLOR_TIPO[v] ?? 'default'}>{LABEL_TIPO[v] ?? v}</Tag>
        : <Tag color="warning">Sin clasificar</Tag>,
    },
    {
      title: 'Pr. Total',
      dataIndex: 'pr_total',
      width: 115,
      align: 'right' as const,
      render: (v: number) => <span style={{ whiteSpace: 'nowrap' }}>{fmt(v)}</span>,
    },
    {
      title: 'Pr. Neto',
      dataIndex: 'pr_neto',
      width: 115,
      align: 'right' as const,
      render: (v: number) => <span style={{ whiteSpace: 'nowrap' }}>{fmt(v)}</span>,
    },
    { title: 'Desde', dataIndex: 'desde', width: 95 },
    { title: 'Hasta', dataIndex: 'hasta', width: 95 },
    { title: 'Cobro', dataIndex: 'cobro', width: 75 },
    {
      title: 'Estado',
      dataIndex: 'estado',
      width: 95,
      render: (v: string) => v ? <Tag>{v}</Tag> : '—',
    },
  ]

  if (isError) {
    return (
      <Alert
        type="error"
        message="No se pudo cargar el detalle de recibos"
        action={<Button onClick={() => navigate(-1)}>Volver</Button>}
      />
    )
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Space>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/presupuestacion/carga')}>
          Volver
        </Button>
        <Title level={4} style={{ margin: 0 }}>Detalle carga de recibos</Title>
      </Space>

      {carga && (
        <Card size="small">
          <Descriptions column={4} size="small">
            <Descriptions.Item label="Ejercicio">{carga.ejercicio}</Descriptions.Item>
            <Descriptions.Item label="Fichero">{carga.nombre_fichero}</Descriptions.Item>
            <Descriptions.Item label="Total recibos">
              <Text strong>{carga.total_registros?.toLocaleString('es-ES')}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Fecha carga">
              {carga.created_at ? new Date(carga.created_at).toLocaleString('es-ES') : '—'}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      )}

      <Row gutter={[16, 16]}>
        <Col span={8}>
          <Card size="small">
            <Statistic title="Total recibos" value={total} />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="Con tipo negocio (página actual)"
              value={conTipo}
              suffix={`/ ${recibos.length}`}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic
              title="Sin clasificar (página actual)"
              value={sinTipo}
              suffix={`/ ${recibos.length}`}
              valueStyle={{ color: sinTipo > 0 ? '#faad14' : '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title="Recibos"
        extra={
          <Space wrap>
            <Select
              placeholder="Tipo negocio"
              allowClear
              style={{ width: 170 }}
              value={filtroTipo}
              onChange={v => { setFiltroTipo(v); setPage(1) }}
            >
              <Option value="cartera">Cartera</Option>
              <Option value="nueva_produccion">Nueva producción</Option>
            </Select>
            <Select
              placeholder="Ramo"
              allowClear
              style={{ width: 150 }}
              value={filtroRamo}
              onChange={v => { setFiltroRamo(v); setPage(1) }}
            >
              {['Autos', 'Vida', 'Hogar', 'Salud', 'Diversos', 'Empresas', 'Transportes', 'Responsabilidad Civil', 'Decesos', 'Accidentes'].map(r => (
                <Option key={r} value={r}>{r}</Option>
              ))}
            </Select>
            <Input
              placeholder="Buscar compañía"
              prefix={<SearchOutlined />}
              style={{ width: 160 }}
              value={filtroCompania}
              onChange={e => {
                setFiltroCompania(e.target.value)
                if (!e.target.value) { setBusquedaCompania(undefined); setPage(1) }
              }}
              onPressEnter={() => { setBusquedaCompania(filtroCompania || undefined); setPage(1) }}
              allowClear
            />
          </Space>
        }
      >
        <Spin spinning={isLoading}>
          <Table
            dataSource={recibos}
            columns={columnas}
            rowKey="codigo"
            size="small"
            scroll={{ x: 1500 }}
            pagination={{
              current: page,
              pageSize,
              total,
              showTotal: (t) => `${t.toLocaleString('es-ES')} recibos`,
              onChange: (p) => setPage(p),
              showSizeChanger: false,
            }}
          />
        </Spin>
      </Card>
    </Space>
  )
}
