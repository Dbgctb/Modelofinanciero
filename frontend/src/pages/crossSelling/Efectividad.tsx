import { Card, Col, Row, Statistic, Table, Tag, Typography } from 'antd'
import {
  TrophyOutlined, DollarOutlined, RiseOutlined,
  SafetyOutlined, TeamOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { crossSellingApi } from '../../api/crossSelling'

const { Title, Text } = Typography

const fmt = (v: number | null | undefined) =>
  v != null ? v.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' €' : '—'

export default function Efectividad() {
  const { data, isLoading } = useQuery({
    queryKey: ['cs-efectividad'],
    queryFn: crossSellingApi.getEfectividad,
  })

  const cs = data?.cross_selling
  const ret = data?.retencion
  const porRamo: any[] = data?.por_ramo || []

  const columns = [
    {
      title: 'Ramo',
      dataIndex: 'ramo',
      key: 'ramo',
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: 'Oportunidades',
      dataIndex: 'oportunidades',
      key: 'oportunidades',
      align: 'right' as const,
    },
    {
      title: 'Ganadas',
      dataIndex: 'ganadas',
      key: 'ganadas',
      align: 'right' as const,
      render: (v: number) => <Text style={{ color: '#52c41a', fontWeight: 600 }}>{v}</Text>,
    },
    {
      title: 'Tasa conversión',
      dataIndex: 'tasa',
      key: 'tasa',
      align: 'right' as const,
      sorter: (a: any, b: any) => a.tasa - b.tasa,
      render: (v: number) => (
        <Tag color={v >= 20 ? 'green' : v >= 10 ? 'orange' : 'red'}>{v.toFixed(1)}%</Tag>
      ),
    },
  ]

  return (
    <div>
      <Title level={4} style={{ marginBottom: 20 }}>
        <TrophyOutlined style={{ color: '#faad14', marginRight: 8 }} />
        Efectividad comercial
      </Title>

      <Title level={5} style={{ color: '#1677ff', marginBottom: 12 }}>Cross-selling</Title>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        {[
          { title: 'Oportunidades accionadas', value: cs?.accionadas ?? 0, color: '#1677ff', icon: <RiseOutlined /> },
          { title: 'Tasa de conversión', value: cs ? `${cs.tasa_conversion}%` : '—', color: '#52c41a', icon: <TrophyOutlined /> },
          { title: 'Margen incremental', value: fmt(cs?.margen_incremental), color: '#722ed1', icon: <DollarOutlined /> },
          { title: 'En curso', value: cs?.en_curso ?? 0, color: '#faad14', icon: <TeamOutlined /> },
        ].map((k, i) => (
          <Col key={i} xs={24} sm={12} xl={6}>
            <Card size="small" style={{ borderRadius: 10, borderLeft: `4px solid ${k.color}` }}>
              <Statistic
                title={k.title}
                value={k.value}
                prefix={<span style={{ color: k.color }}>{k.icon}</span>}
                valueStyle={{ fontSize: 20 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Title level={5} style={{ color: '#f5222d', marginBottom: 12 }}>Retención</Title>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        {[
          { title: 'Alertas accionadas', value: ret?.accionadas ?? 0, color: '#f5222d', icon: <SafetyOutlined /> },
          { title: 'Clientes retenidos', value: ret?.retenidas ?? 0, color: '#52c41a', icon: <SafetyOutlined /> },
          { title: 'Valor protegido recuperado', value: fmt(ret?.valor_protegido_recuperado), color: '#722ed1', icon: <DollarOutlined /> },
        ].map((k, i) => (
          <Col key={i} xs={24} sm={12} xl={8}>
            <Card size="small" style={{ borderRadius: 10, borderLeft: `4px solid ${k.color}` }}>
              <Statistic
                title={k.title}
                value={k.value}
                prefix={<span style={{ color: k.color }}>{k.icon}</span>}
                valueStyle={{ fontSize: 20 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card title="Conversión por ramo recomendado" style={{ borderRadius: 10 }}>
        {porRamo.length === 0 ? (
          <Text type="secondary">
            Aún no hay acciones registradas. Acciona oportunidades desde la pestaña de Oportunidades para ver métricas aquí.
          </Text>
        ) : (
          <Table
            rowKey="ramo"
            columns={columns}
            dataSource={porRamo}
            loading={isLoading}
            size="small"
            pagination={false}
          />
        )}
      </Card>
    </div>
  )
}
