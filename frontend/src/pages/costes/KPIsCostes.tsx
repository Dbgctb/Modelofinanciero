import { useState } from 'react'
import {
  Card, Row, Col, Select, Space, Typography, Alert, Table,
} from 'antd'
import { useQuery } from '@tanstack/react-query'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip as RTooltip,
} from 'recharts'
import { costesApi } from '../../api/costes'

const { Title, Text } = Typography
const { Option } = Select

const MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
const fmt = (v: number) => v?.toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' €'
const fmtPct = (v: number) => v?.toFixed(2) + '%'

export default function KPIsCostes() {
  const [ejercicio, setEjercicio] = useState<number | null>(null)
  const [mesesSel, setMesesSel] = useState<number[]>([1, 2, 3, 4, 5, 6])

  const { data: anyos = [] } = useQuery({
    queryKey: ['costes-anyos'],
    queryFn: () => costesApi.anyosDisponibles().then(r => r.data),
  })

  const { data: kpis = [], isLoading } = useQuery({
    queryKey: ['costes-kpis', ejercicio, mesesSel],
    queryFn: () => costesApi.kpis(ejercicio!, mesesSel).then(r => r.data),
    enabled: !!ejercicio && mesesSel.length > 0,
  })

  // KPIs principales (CK-01 a CK-06)
  const kpisPrincipales = kpis.filter((k: any) => ['CK-01','CK-02','CK-03','CK-04','CK-05','CK-06'].includes(k.codigo))
  const kpisFamilia = kpis.filter((k: any) => k.codigo.startsWith('CK-F'))

  const radarData = kpisFamilia.slice(0, 8).map((k: any) => ({
    subject: k.nombre.replace('Coste ', '').replace(' (€)', ''),
    valor: k.valor,
  }))

  const colsKpis = [
    { title: 'Código', dataIndex: 'codigo', width: 80 },
    { title: 'Indicador', dataIndex: 'nombre', ellipsis: true },
    {
      title: 'Valor', dataIndex: 'valor', align: 'right' as const,
      render: (v: number, r: any) =>
        r.nombre.includes('%') ? <Text strong>{fmtPct(v)}</Text> : <Text strong>{fmt(v)}</Text>,
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>KPIs y márgenes de costes</Title>
          <Text type="secondary">Indicadores de eficiencia y estructura de costes</Text>
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

      {!ejercicio && <Alert type="info" showIcon message="Selecciona un ejercicio para ver los KPIs de costes" />}

      {ejercicio && kpis.length === 0 && !isLoading && (
        <Alert type="warning" showIcon
          message="Sin datos de costes. Asegúrate de que hay líneas clasificadas e imputadas para los meses seleccionados." />
      )}

      {kpisPrincipales.length > 0 && (
        <>
          <Row gutter={[16, 16]}>
            {kpisPrincipales.map((k: any) => (
              <Col key={k.codigo} xs={24} sm={12} md={8}>
                <Card size="small" style={{ textAlign: 'center' }}>
                  <Text style={{ fontSize: 11, color: '#888', fontWeight: 600 }}>{k.codigo}</Text>
                  <div style={{ fontSize: 22, fontWeight: 700, color: '#1890ff', marginTop: 4 }}>
                    {k.nombre.includes('%') ? fmtPct(k.valor) : fmt(k.valor)}
                  </div>
                  <Text style={{ fontSize: 12, color: '#555' }}>{k.nombre}</Text>
                </Card>
              </Col>
            ))}
          </Row>

          {radarData.length >= 3 && (
            <Card title="Distribución de costes por familia">
              <ResponsiveContainer width="100%" height={300}>
                <RadarChart data={radarData}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="subject" tick={{ fontSize: 11 }} />
                  <PolarRadiusAxis angle={30} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                  <Radar name="Coste (€)" dataKey="valor" stroke="#1890ff" fill="#1890ff" fillOpacity={0.3} />
                  <RTooltip formatter={(v: number) => fmt(v)} />
                </RadarChart>
              </ResponsiveContainer>
            </Card>
          )}

          {kpisFamilia.length > 0 && (
            <Card title="Coste por familia de gasto">
              <Table
                dataSource={kpisFamilia}
                columns={colsKpis}
                rowKey="codigo"
                size="small"
                pagination={false}
                loading={isLoading}
              />
            </Card>
          )}
        </>
      )}
    </Space>
  )
}
