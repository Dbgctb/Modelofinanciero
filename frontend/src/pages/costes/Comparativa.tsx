import { useState } from 'react'
import {
  Card, Row, Col, Select, Space, Typography, Tag, Alert,
  Table, Statistic,
} from 'antd'
import { ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip,
  Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { costesApi } from '../../api/costes'

const { Title, Text } = Typography
const { Option } = Select

const MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
const fmt = (v: number) => v?.toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' €'
const fmtPct = (v: number) => (v >= 0 ? '+' : '') + v?.toFixed(2) + '%'

function DesvTag({ desv, desv_pct }: { desv: number; desv_pct: number }) {
  if (desv === 0) return <Tag>Sin desviación</Tag>
  const favorable = desv <= 0  // en costes, menor real es favorable
  return (
    <Tag color={favorable ? 'success' : 'error'}
      icon={favorable ? <ArrowDownOutlined /> : <ArrowUpOutlined />}>
      {fmt(Math.abs(desv))} ({fmtPct(Math.abs(desv_pct))})
    </Tag>
  )
}

export default function Comparativa() {
  const [ejercicio, setEjercicio] = useState<number | null>(null)
  const [mesesSel, setMesesSel] = useState<number[]>([1, 2, 3, 4, 5, 6])

  const { data: anyos = [] } = useQuery({
    queryKey: ['costes-anyos'],
    queryFn: () => costesApi.anyosDisponibles().then(r => r.data),
  })

  const { data: comparativa, isLoading } = useQuery({
    queryKey: ['costes-comparativa', ejercicio, mesesSel],
    queryFn: () => costesApi.comparativa(ejercicio!, mesesSel).then(r => r.data),
    enabled: !!ejercicio && mesesSel.length > 0,
  })

  const familias: any[] = comparativa?.familias || []
  const totales: any = comparativa?.totales || {}

  const datosGrafico = familias.map((f: any) => ({
    familia: f.familia.length > 20 ? f.familia.slice(0, 18) + '…' : f.familia,
    real: f.real,
    presupuesto: f.presupuesto,
    desviacion: f.desviacion,
  }))

  const cols = [
    { title: 'Familia de gasto', dataIndex: 'familia' },
    {
      title: 'Tipo',
      render: (_: any, r: any) => r.tipo_coste
        ? <Tag color={r.tipo_coste === 'fijo' ? 'geekblue' : 'purple'}>{r.tipo_coste}</Tag>
        : '—',
    },
    {
      title: 'Tratamiento',
      render: (_: any, r: any) => {
        const colors: Record<string, string> = { directo: 'green', indirecto: 'blue', excluido: 'orange' }
        return r.tratamiento ? <Tag color={colors[r.tratamiento]}>{r.tratamiento}</Tag> : '—'
      },
    },
    {
      title: 'Real', dataIndex: 'real', align: 'right' as const,
      render: (v: number) => <Text strong>{fmt(v)}</Text>,
    },
    {
      title: 'Presupuesto', dataIndex: 'presupuesto', align: 'right' as const,
      render: (v: number) => <Text type="secondary">{fmt(v)}</Text>,
    },
    {
      title: 'Desviación',
      render: (_: any, r: any) => <DesvTag desv={r.desviacion} desv_pct={r.desv_pct} />,
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Real vs Presupuesto — Costes</Title>
          <Text type="secondary">Comparativa de costes reales frente al presupuesto por familia</Text>
        </div>
        <Space>
          <Select placeholder="Ejercicio" style={{ width: 150 }} onChange={setEjercicio} value={ejercicio}>
            {anyos.map((a: number) => <Option key={a} value={a}>Ejercicio {a}</Option>)}
          </Select>
          <Select
            mode="multiple"
            placeholder="Meses"
            style={{ width: 240 }}
            value={mesesSel}
            onChange={setMesesSel}
            maxTagCount="responsive"
          >
            {MESES.map((m, i) => <Option key={i + 1} value={i + 1}>{m}</Option>)}
          </Select>
        </Space>
      </div>

      {!ejercicio && <Alert type="info" showIcon message="Selecciona un ejercicio para ver la comparativa de costes" />}

      {ejercicio && comparativa && (
        <>
          <Row gutter={16}>
            <Col span={8}>
              <Card style={{ borderTop: '3px solid #f5222d', textAlign: 'center' }}>
                <Statistic title="Coste real total" value={totales.real} precision={2} suffix="€"
                  valueStyle={{ color: '#f5222d' }} />
              </Card>
            </Col>
            <Col span={8}>
              <Card style={{ borderTop: '3px solid #999', textAlign: 'center' }}>
                <Statistic title="Coste presupuestado" value={totales.presupuesto} precision={2} suffix="€"
                  valueStyle={{ color: '#999' }} />
              </Card>
            </Col>
            <Col span={8}>
              <Card style={{ borderTop: `3px solid ${totales.desviacion <= 0 ? '#52c41a' : '#f5222d'}`, textAlign: 'center' }}>
                <Statistic
                  title="Desviación total"
                  value={Math.abs(totales.desviacion)}
                  precision={2}
                  suffix="€"
                  prefix={totales.desviacion <= 0 ? <ArrowDownOutlined /> : <ArrowUpOutlined />}
                  valueStyle={{ color: totales.desviacion <= 0 ? '#52c41a' : '#f5222d' }}
                />
              </Card>
            </Col>
          </Row>

          {datosGrafico.length > 0 && (
            <Card title="Costes real vs presupuesto por familia">
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={datosGrafico} margin={{ bottom: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="familia" angle={-30} textAnchor="end" interval={0} height={70} tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                  <RTooltip formatter={(v: number) => fmt(v)} />
                  <Legend />
                  <Bar dataKey="real" name="Real" fill="#f5222d" opacity={0.85} />
                  <Bar dataKey="presupuesto" name="Presupuesto" fill="#ffccc7" opacity={0.85} />
                  <ReferenceLine y={0} stroke="#333" />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          )}

          <Card>
            <Table
              dataSource={familias}
              columns={cols}
              rowKey="familia"
              size="small"
              loading={isLoading}
              pagination={false}
              summary={() => (
                <Table.Summary.Row style={{ fontWeight: 700 }}>
                  <Table.Summary.Cell index={0} colSpan={3}>TOTAL</Table.Summary.Cell>
                  <Table.Summary.Cell index={1} align="right">{fmt(totales.real || 0)}</Table.Summary.Cell>
                  <Table.Summary.Cell index={2} align="right">{fmt(totales.presupuesto || 0)}</Table.Summary.Cell>
                  <Table.Summary.Cell index={3}>
                    <DesvTag desv={totales.desviacion || 0} desv_pct={
                      totales.presupuesto ? Math.round((totales.desviacion / totales.presupuesto) * 10000) / 100 : 0
                    } />
                  </Table.Summary.Cell>
                </Table.Summary.Row>
              )}
            />
          </Card>
        </>
      )}
    </Space>
  )
}
