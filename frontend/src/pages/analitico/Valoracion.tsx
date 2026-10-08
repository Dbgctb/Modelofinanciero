import { useState } from 'react'
import {
  Row, Col, Card, Typography, Space, Select, InputNumber, Button,
  Tag, Divider, Tooltip, Table, Alert, Progress, Statistic,
} from 'antd'
import {
  InfoCircleOutlined, ReloadOutlined, RiseOutlined, FallOutlined,
  MinusOutlined, StarFilled, StarOutlined,
} from '@ant-design/icons'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as ChartTooltip, ReferenceLine, Cell, LineChart, Line, Legend,
} from 'recharts'
import { useQuery } from '@tanstack/react-query'
import { analiticoApi } from '../../api/analitico'

const { Title, Text } = Typography

const _miles = (v: number) =>
  Math.round(Math.abs(v ?? 0)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.')
const fmt  = (v: number) => (v < 0 ? '-' : '') + _miles(v) + ' €'
const fmtP = (v: number) => (v != null ? (v * 100).toFixed(1).replace('.', ',') + '%' : '—')
const pct  = (v: number) => v.toFixed(1).replace('.', ',') + '%'

const SCENARIO_COLORS = {
  pesimista:  '#f5222d',
  base:       '#1890ff',
  optimista:  '#52c41a',
}

function AdjBar({ label, value, desc }: { label: string; value: number; desc: string }) {
  const icon = value > 0 ? <RiseOutlined /> : value < 0 ? <FallOutlined /> : <MinusOutlined />
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '6px 0', borderBottom: '1px solid #f0f0f0' }}>
      <div>
        <Text style={{ fontSize: 12 }}>{label}</Text>
        <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>{desc}</Text>
      </div>
      <Tag color={value > 0 ? 'success' : value < 0 ? 'error' : 'default'}
           icon={icon} style={{ fontSize: 12, minWidth: 64, textAlign: 'right' }}>
        {value > 0 ? '+' : ''}{value.toFixed(2)}×
      </Tag>
    </div>
  )
}

function ValCard({ escenario, data, method }: {
  escenario: 'pesimista' | 'base' | 'optimista'
  data: any
  method: 'comisiones' | 'ebitda'
}) {
  if (!data) return (
    <Card size="small" style={{ opacity: 0.5, textAlign: 'center' }}>
      <Text type="secondary" style={{ fontSize: 11 }}>
        {method === 'ebitda' ? 'EBITDA negativo — método no aplicable' : 'Sin datos'}
      </Text>
    </Card>
  )
  const labels = { pesimista: 'Pesimista', base: 'Base', optimista: 'Optimista' }
  const color  = SCENARIO_COLORS[escenario]
  return (
    <Card size="small" style={{ borderTop: `3px solid ${color}`, textAlign: 'center' }}>
      <Tag color={escenario === 'base' ? 'blue' : escenario === 'optimista' ? 'success' : 'error'}
           style={{ marginBottom: 6 }}>
        {labels[escenario]}
      </Tag>
      <div style={{ fontSize: 26, fontWeight: 800, color }}>{fmt(data.valor)}</div>
      <div style={{ fontSize: 11, color: '#8c8c8c', marginTop: 4 }}>
        {data.multiplo_final.toFixed(2)}× {method === 'comisiones' ? 'comisiones' : 'EBITDA'}
        {data.ajuste_aplicado !== 0 && (
          <span style={{ color: data.ajuste_aplicado > 0 ? '#52c41a' : '#f5222d' }}>
            {' '}({data.ajuste_aplicado > 0 ? '+' : ''}{data.ajuste_aplicado.toFixed(2)} ajuste)
          </span>
        )}
      </div>
    </Card>
  )
}

export default function Valoracion() {
  const [ejercicio, setEjercicio] = useState<number>(2025)
  const [crecimientoManual, setCrecimientoManual] = useState<number | null>(null)
  const [usarManual, setUsarManual] = useState(false)

  const { data: ejercicios = [] } = useQuery({
    queryKey: ['analitico-ejercicios'],
    queryFn: () => analiticoApi.getEjercicios().then(r => r.data),
  })

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['valoracion', ejercicio, usarManual ? crecimientoManual : null],
    queryFn: () => analiticoApi.valoracion(
      ejercicio,
      usarManual && crecimientoManual != null ? crecimientoManual / 100 : undefined,
    ).then(r => r.data),
    enabled: !!ejercicio,
  })

  if (!data || data.sin_datos) {
    return (
      <Alert type="info" showIcon
        message="Sin datos analíticos"
        description="Selecciona un ejercicio y ejecuta el recálculo del modelo analítico primero." />
    )
  }

  const f  = data.financiero
  const p  = data.perfil
  const cr = data.crecimiento
  const aj = data.ajustes
  const v  = data.valoracion
  const m  = data.mercado

  // Datos para gráfico de escenarios (ambos métodos)
  const escenarios = ['pesimista', 'base', 'optimista']
  const chartBar = escenarios.map(e => ({
    escenario: e === 'pesimista' ? 'Pesimista' : e === 'base' ? 'Base' : 'Optimista',
    comisiones: v.comisiones[e]?.valor ?? 0,
    ebitda: v.ebitda[e]?.valor ?? 0,
  }))

  // Histórico de ingresos
  const historico = (cr.historico || []).map((h: any) => ({
    año: String(h.ejercicio),
    ingresos: h.ingresos,
  }))

  const cagrUsado   = cr.cagr_usado
  const cagrPeriodo = cr.cagr_periodo ?? '—'
  const cagrLabel   = cagrUsado != null ? fmtP(cagrUsado) : '—'
  const cagr5Label  = cr.cagr_5y != null ? fmtP(cr.cagr_5y) : '—'
  const cagr3Label  = cr.cagr_3y != null ? fmtP(cr.cagr_3y) : '—'

  // Auxiliares: combina MAKONTA + JOSE LUIS SOBRINO como grupo relacionado
  const auxDetailAgrupado: { auxiliar: string; ingreso: number; pct: number; grupo?: string }[] = (() => {
    const raw: { auxiliar: string; ingreso: number; pct: number }[] = p.aux_detail || []
    const esMakonta  = (n: string) => n.toUpperCase().includes('MAKONTA')
    const esJoseLuis = (n: string) => n.toUpperCase().includes('JOSE LUIS') || n.toUpperCase().includes('SOBRINO')
    const grupo = raw.filter(a => esMakonta(a.auxiliar) || esJoseLuis(a.auxiliar))
    if (grupo.length <= 1) return raw  // sin agrupación necesaria
    const ingresoGrupo = grupo.reduce((s, a) => s + a.ingreso, 0)
    const pctGrupo = f.comision_bruta > 0 ? Math.round(ingresoGrupo / f.comision_bruta * 1000) / 10 : 0
    const combinado = {
      auxiliar: grupo.map(a => a.auxiliar).join(' + '),
      ingreso: Math.round(ingresoGrupo * 100) / 100,
      pct: pctGrupo,
      grupo: 'combinado',
    }
    const resto = raw.filter(a => !esMakonta(a.auxiliar) && !esJoseLuis(a.auxiliar))
    return [...resto, combinado].sort((a, b) => b.ingreso - a.ingreso)
  })()

  // Rango de valor recomendado (promedio de base comisiones + base ebitda si aplica)
  const baseComVal = v.comisiones.base?.valor ?? 0
  const rangoBajo  = v.comisiones.pesimista?.valor ?? 0
  const rangoAlto  = v.comisiones.optimista?.valor ?? 0
  const valRef     = v.combinado ?? baseComVal

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>

      {/* Cabecera */}
      <Row align="middle" justify="space-between">
        <Col>
          <Title level={4} style={{ margin: 0 }}>Valoración de la correduría</Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Referencia interna · SegurosNews / Recoletos Consultores 2025
          </Text>
        </Col>
        <Col>
          <Space>
            <Select value={ejercicio} onChange={setEjercicio} style={{ width: 100 }}
              options={(ejercicios as number[]).map(e => ({ value: e, label: String(e) }))} />
            <Tooltip title={`CAGR 5A: ${cagr5Label} · CAGR 3A: ${cagr3Label} · Usado: ${cagrLabel} (${cagrPeriodo})`}>
              <InputNumber
                style={{ width: 160 }}
                placeholder={`CAGR auto (${cagrLabel} ${cagrPeriodo})`}
                min={-50} max={50} precision={1} suffix="%"
                value={usarManual ? crecimientoManual : null}
                onChange={v => { setCrecimientoManual(v); setUsarManual(v != null) }}
              />
            </Tooltip>
            <Button icon={<ReloadOutlined />} onClick={() => refetch()} loading={isLoading}>
              Calcular
            </Button>
          </Space>
        </Col>
      </Row>

      {/* Valor de referencia destacado */}
      <Card style={{ background: 'linear-gradient(135deg, #e6f4ff 0%, #f0f9ff 100%)',
                    border: '1px solid #91caff', textAlign: 'center' }}>
        <Text style={{ fontSize: 13, color: '#0958d9', display: 'block', marginBottom: 4 }}>
          Valor de referencia (fórmula combinada mercado español)
        </Text>
        <Text style={{ fontSize: 42, fontWeight: 900, color: '#0958d9' }}>
          {fmt(valRef)}
        </Text>
        <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 12 }}>
          Rango estimado: <strong>{fmt(rangoBajo)}</strong> — <strong>{fmt(rangoAlto)}</strong>
          {v.combinado && (
            <span> · Fórmula: (2 × comisiones + 5 × EBITDA) / 2</span>
          )}
        </Text>
      </Card>

      <Row gutter={[16, 16]}>
        {/* Columna izquierda: escenarios + gráfico */}
        <Col xs={24} lg={14}>

          {/* Método 1: Múltiplo comisiones */}
          <Card title={
            <Space>
              <Text strong>Método 1 — Múltiplo sobre comisiones brutas</Text>
              <Tooltip title="El método más usado en España para corredurías < 600k€. Multiplica las comisiones anuales por un factor según la calidad de la cartera.">
                <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
              </Tooltip>
            </Space>
          } size="small" style={{ marginBottom: 12 }}>
            <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 10 }}>
              Base mercado: {m.multiples_comisiones.pesimista}× — {m.multiples_comisiones.base}× — {m.multiples_comisiones.optimista}×
              {' '}· Ajuste calidad: {aj.total > 0 ? '+' : ''}{aj.total.toFixed(2)}×
            </Text>
            <Row gutter={[8, 8]}>
              {escenarios.map(e => (
                <Col span={8} key={e}>
                  <ValCard escenario={e as any} data={v.comisiones[e]} method="comisiones" />
                </Col>
              ))}
            </Row>
          </Card>

          {/* Método 2: Múltiplo EBITDA */}
          <Card title={
            <Space>
              <Text strong>Método 2 — Múltiplo sobre EBITDA</Text>
              <Tooltip title="Más usado en corredurías medianas/grandes. Requiere EBITDA positivo. Con EBITDA bajo, la valoración por este método es conservadora.">
                <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
              </Tooltip>
            </Space>
          } size="small" style={{ marginBottom: 12 }}>
            {f.ebitda <= 0 ? (
              <Alert type="warning" showIcon
                message="EBITDA negativo o cero: este método no es aplicable"
                description="El múltiplo sobre comisiones es el indicador relevante para esta correduría." />
            ) : (
              <>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 10 }}>
                  Base mercado: {m.multiples_ebitda.pesimista}× — {m.multiples_ebitda.base}× — {m.multiples_ebitda.optimista}×
                  {' '}· EBITDA: {fmt(f.ebitda)} ({pct(f.margen_pct)} margen)
                </Text>
                <Row gutter={[8, 8]}>
                  {escenarios.map(e => (
                    <Col span={8} key={e}>
                      <ValCard escenario={e as any} data={v.ebitda[e]} method="ebitda" />
                    </Col>
                  ))}
                </Row>
              </>
            )}
          </Card>

          {/* Gráfico comparativo */}
          <Card title="Comparativa de escenarios" size="small" style={{ height: 280 }}>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartBar} margin={{ top: 8, right: 12, bottom: 8, left: 8 }}>
                <XAxis dataKey="escenario" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={v => `${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 10 }} />
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <ChartTooltip formatter={(v: any) => fmt(v)} />
                <Legend />
                <Bar dataKey="comisiones" name="× Comisiones" fill="#1890ff"
                  label={{ position: 'top', formatter: (v: number) => `${(v/1000).toFixed(0)}k`, fontSize: 9 }}>
                  {chartBar.map((_, i) => (
                    <Cell key={i} fill={Object.values(SCENARIO_COLORS)[i]} />
                  ))}
                </Bar>
                {f.ebitda > 0 && (
                  <Bar dataKey="ebitda" name="× EBITDA" fill="#52c41a" opacity={0.6}
                    label={{ position: 'top', formatter: (v: number) => `${(v/1000).toFixed(0)}k`, fontSize: 9 }} />
                )}
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>

        {/* Columna derecha: factores de ajuste + perfil */}
        <Col xs={24} lg={10}>

          {/* Factores de ajuste */}
          <Card title="Factores de ajuste sobre el múltiplo" size="small" style={{ marginBottom: 12 }}>
            <AdjBar label="Calidad de cartera" value={aj.cartera.valor} desc={aj.cartera.referencia} />
            <AdjBar label="Concentración auxiliares" value={aj.concentracion.valor} desc={aj.concentracion.referencia} />
            <AdjBar label="Mix de ramos premium" value={aj.ramos.valor} desc={aj.ramos.referencia} />
            <AdjBar label="Tendencia de crecimiento" value={aj.crecimiento.valor} desc={aj.crecimiento.referencia} />
            <Divider style={{ margin: '8px 0' }} />
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text strong>Ajuste total</Text>
              <Tag color={aj.total > 0 ? 'success' : aj.total < 0 ? 'error' : 'default'}
                   style={{ fontSize: 13, fontWeight: 700 }}>
                {aj.total > 0 ? '+' : ''}{aj.total.toFixed(3)}×
              </Tag>
            </div>
          </Card>

          {/* Perfil de cartera */}
          <Card title="Perfil de la cartera" size="small" style={{ marginBottom: 12 }}>
            <Row gutter={[8, 8]}>
              <Col span={12}>
                <div style={{ fontSize: 11, color: '#8c8c8c' }}>Cartera recurrente</div>
                <Progress percent={p.cartera_pct} size="small"
                  strokeColor={p.cartera_pct >= 70 ? '#52c41a' : '#faad14'} showInfo={false} />
                <Text style={{ fontSize: 13, fontWeight: 700 }}>{pct(p.cartera_pct)}</Text>
              </Col>
              <Col span={12}>
                <div style={{ fontSize: 11, color: '#8c8c8c' }}>Ramos premium</div>
                <Progress percent={p.ramo_premium_pct} size="small"
                  strokeColor={p.ramo_premium_pct >= 50 ? '#52c41a' : '#faad14'} showInfo={false} />
                <Text style={{ fontSize: 13, fontWeight: 700 }}>{pct(p.ramo_premium_pct)}</Text>
              </Col>
              <Col span={12}>
                <div style={{ fontSize: 11, color: '#8c8c8c' }}>Concentración aux. (top 3 / top 4)</div>
                <Progress percent={p.top3_aux_pct} size="small"
                  strokeColor={p.top3_aux_pct <= 40 ? '#52c41a' : p.top3_aux_pct <= 60 ? '#faad14' : '#f5222d'}
                  showInfo={false} />
                <Text style={{ fontSize: 13, fontWeight: 700 }}>{pct(p.top3_aux_pct)}</Text>
                {p.top4_aux_pct != null && (
                  <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                    Top 4: {pct(p.top4_aux_pct)}
                  </Text>
                )}
              </Col>
              <Col span={12}>
                <div style={{ fontSize: 11, color: '#8c8c8c' }}>
                  CAGR {cr.manual ? '(manual)' : `(${cagrPeriodo})`}
                </div>
                <div style={{ marginTop: 2 }}>
                  <Tag color={cagrUsado >= 0.05 ? 'success' : cagrUsado >= 0.02 ? 'warning' : 'error'}
                       style={{ fontSize: 13, fontWeight: 700 }}>
                    {cagrLabel}
                  </Tag>
                </div>
                {!cr.manual && (
                  <div style={{ fontSize: 10, color: '#8c8c8c', marginTop: 2 }}>
                    5A: {cagr5Label} · 3A: {cagr3Label}
                  </div>
                )}
              </Col>
            </Row>
            <Divider style={{ margin: '8px 0' }} />
            <Row gutter={[8, 4]}>
              <Col span={12}><Text style={{ fontSize: 11, color: '#8c8c8c' }}>Auxiliares activos</Text>
                <Text strong style={{ display: 'block' }}>{p.n_auxiliares}</Text></Col>
              <Col span={12}><Text style={{ fontSize: 11, color: '#8c8c8c' }}>Compañías</Text>
                <Text strong style={{ display: 'block' }}>{p.n_companias}</Text></Col>
              <Col span={12}><Text style={{ fontSize: 11, color: '#8c8c8c' }}>Comisión/recibo</Text>
                <Text strong style={{ display: 'block' }}>{f.comision_por_recibo.toFixed(2)} €</Text></Col>
              <Col span={12}><Text style={{ fontSize: 11, color: '#8c8c8c' }}>Margen EBITDA</Text>
                <Text strong style={{ display: 'block' }}>{pct(f.margen_pct)}</Text></Col>
            </Row>
          </Card>

          {/* Evolución histórica */}
          {historico.length > 1 && (
            <Card title="Evolución de ingresos" size="small" style={{ height: 200 }}>
              <ResponsiveContainer width="100%" height={150}>
                <LineChart data={historico} margin={{ top: 4, right: 12, bottom: 4, left: 8 }}>
                  <XAxis dataKey="año" tick={{ fontSize: 10 }} />
                  <YAxis tickFormatter={v => `${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 10 }} />
                  <CartesianGrid strokeDasharray="3 3" />
                  <ChartTooltip formatter={(v: any) => fmt(v)} />
                  <Line type="monotone" dataKey="ingresos" name="Ingresos"
                    stroke="#1890ff" strokeWidth={2} dot={{ r: 3 }} />
                  <ReferenceLine y={f.comision_bruta} stroke="#52c41a" strokeDasharray="4 4" />
                </LineChart>
              </ResponsiveContainer>
            </Card>
          )}
        </Col>
      </Row>

      {/* Top auxiliares con importes */}
      <Card
        title={
          <Space>
            <span>Riesgo de concentración — Auxiliares por ingreso</span>
            <Tooltip title="El ajuste de concentración usa el Top 3. El Top 4 se muestra para valorar si un auxiliar adicional entra en zona de riesgo.">
              <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
            </Tooltip>
          </Space>
        }
        size="small"
      >
        <Alert type="warning" showIcon style={{ marginBottom: 8 }}
          message={
            `Top 3: ${pct(p.top3_aux_pct)} de los ingresos` +
            (p.top4_aux_pct ? ` · Top 4: ${pct(p.top4_aux_pct)}` : '') +
            '. Una salida de cualquiera de los principales reduciría el valor estimado.'
          } />
        <Table
          dataSource={auxDetailAgrupado.slice(0, 5).map((a, i) => ({
            key: i,
            pos: i + 1,
            nombre: a.auxiliar,
            ingreso: a.ingreso,
            pct: a.pct,
            enTop3: i < 3,
            enTop4: i < 4,
            esGrupo: !!(a as any).grupo,
          }))}
          columns={[
            {
              title: '#', dataIndex: 'pos', width: 36,
              render: (v: number, row: any) => (
                <Tag color={row.enTop3 ? 'error' : row.enTop4 ? 'warning' : 'default'}
                     style={{ margin: 0, minWidth: 24, textAlign: 'center' }}>
                  {v}
                </Tag>
              ),
            },
            {
              title: 'Auxiliar', dataIndex: 'nombre', ellipsis: true,
              render: (v: string, row: any) => row.esGrupo
                ? <span><Tag color="purple" style={{ margin: '0 4px 0 0', fontSize: 10 }}>GRUPO</Tag>{v}</span>
                : v,
            },
            {
              title: 'Ingreso', dataIndex: 'ingreso', width: 110, align: 'right' as const,
              render: (v: number) => <span style={{ fontWeight: 600 }}>{fmt(v)}</span>,
            },
            {
              title: '%', dataIndex: 'pct', width: 60, align: 'right' as const,
              render: (v: number, row: any) => (
                <Tag color={row.enTop3 ? 'error' : row.enTop4 ? 'warning' : 'default'}
                     style={{ margin: 0 }}>
                  {pct(v)}
                </Tag>
              ),
            },
          ]}
          size="small" pagination={false}
        />
      </Card>

      {/* Ramos premium */}
      <Card
        title={
          <Space>
            <span>Ramos premium — Mix y camino al siguiente nivel</span>
            <Tooltip title={`Ramos premium: ${['Multirriesgos','Responsabilidad Civil','Accidentes','Transporte','Ingeniería','Crédito'].join(', ')}. Umbral actual: <30%→ -0.10×, 30-50%→ 0×, 50-70%→ +0.10×, >70%→ +0.20×`}>
              <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
            </Tooltip>
          </Space>
        }
        size="small"
      >
        <Row gutter={[16, 12]} style={{ marginBottom: 12 }}>
          <Col span={8}>
            <Statistic
              title="Ingreso premium actual"
              value={p.ingreso_premium_actual ?? 0}
              suffix="€"
              valueStyle={{ fontSize: 18, fontWeight: 700 }}
              formatter={(v: any) => fmt(Number(v))}
            />
          </Col>
          <Col span={8}>
            <Statistic
              title="% sobre ingresos"
              value={pct(p.ramo_premium_pct)}
              valueStyle={{
                fontSize: 18, fontWeight: 700,
                color: p.ramo_premium_pct >= 70 ? '#52c41a' : p.ramo_premium_pct >= 50 ? '#1890ff' : p.ramo_premium_pct >= 30 ? '#faad14' : '#f5222d',
              }}
            />
          </Col>
          <Col span={8}>
            {p.umbral_premium_siguiente != null ? (
              <Statistic
                title={`Falta para ${pct(p.umbral_premium_siguiente)} (+${p.umbral_premium_siguiente <= 30 ? '0.00' : p.umbral_premium_siguiente <= 50 ? '0.10' : '0.20'}×)`}
                value={p.ingreso_premium_faltante ?? 0}
                suffix="€"
                valueStyle={{ fontSize: 18, fontWeight: 700, color: '#faad14' }}
                formatter={(v: any) => fmt(Number(v))}
              />
            ) : (
              <div style={{ paddingTop: 8 }}>
                <Tag color="success" style={{ fontSize: 13 }}>Nivel máximo (+0.20×)</Tag>
              </div>
            )}
          </Col>
        </Row>
        <Progress
          percent={Math.min(p.ramo_premium_pct, 100)}
          success={{ percent: 0 }}
          strokeColor={p.ramo_premium_pct >= 70 ? '#52c41a' : p.ramo_premium_pct >= 50 ? '#1890ff' : p.ramo_premium_pct >= 30 ? '#faad14' : '#f5222d'}
          format={() => pct(p.ramo_premium_pct)}
          style={{ marginBottom: 12 }}
        />
        <Table
          dataSource={(p.ramos_detail || []).map((r: any, i: number) => ({ key: i, ...r }))}
          columns={[
            {
              title: '', dataIndex: 'es_premium', width: 28,
              render: (v: boolean) => v
                ? <StarFilled style={{ color: '#faad14', fontSize: 13 }} />
                : <StarOutlined style={{ color: '#d9d9d9', fontSize: 13 }} />,
            },
            { title: 'Ramo', dataIndex: 'ramo', ellipsis: true },
            {
              title: 'Ingreso', dataIndex: 'ingreso', width: 110, align: 'right' as const,
              render: (v: number, row: any) => (
                <span style={{ fontWeight: row.es_premium ? 700 : 400 }}>{fmt(v)}</span>
              ),
            },
            {
              title: '%', dataIndex: 'pct', width: 60, align: 'right' as const,
              render: (v: number, row: any) => (
                <Tag color={row.es_premium ? 'gold' : 'default'} style={{ margin: 0 }}>
                  {pct(v)}
                </Tag>
              ),
            },
          ]}
          size="small" pagination={false}
          onRow={(row: any) => ({ style: row.es_premium ? { background: '#fffbe6' } : {} })}
        />
      </Card>

      {/* Nota metodológica */}
      <Card size="small" style={{ background: '#fafafa' }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          <strong>Metodología:</strong> Valoración para uso interno de referencia.
          Múltiplos base: {m.multiples_comisiones.pesimista}×–{m.multiples_comisiones.optimista}× sobre comisiones brutas anuales;
          {m.multiples_ebitda.pesimista}×–{m.multiples_ebitda.optimista}× sobre EBITDA.
          Fuente: {m.fuente}. {m.nota}
          Los ajustes automáticos son estimaciones basadas en los datos del modelo analítico.
          Para una valoración vinculante, se recomienda tasación por experto independiente.
        </Text>
      </Card>

    </Space>
  )
}
