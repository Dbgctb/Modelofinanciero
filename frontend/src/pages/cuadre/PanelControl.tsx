import { useState } from 'react'
import {
  Row, Col, Card, Typography, Select, Spin, Alert, Tag, Tooltip,
  Table, Space, Progress,
} from 'antd'
import {
  CheckCircleFilled, WarningFilled, CloseCircleFilled,
  MinusOutlined, InfoCircleOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { cuadreApi } from '../../api/cuadre'

const { Title, Text } = Typography

// ── Formatters ────────────────────────────────────────────────────────────────
const fmtE = (v: number | null | undefined) => {
  if (v === null || v === undefined) return <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
  const abs = Math.round(Math.abs(v)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return (v < 0 ? '-' : '') + abs + ' €'
}
const fmtP = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : v.toFixed(1).replace('.', ',') + '%'
const fmtD = (v: number | null | undefined) => {
  if (v === null || v === undefined) return '—'
  const abs = Math.round(Math.abs(v)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  return (v > 0 ? '+' : v < 0 ? '-' : '') + abs + ' €'
}

// ── Semáforo ──────────────────────────────────────────────────────────────────
function Semaforo({ estado, size = 18 }: { estado: string; size?: number }) {
  if (estado === 'ok')      return <CheckCircleFilled style={{ color: '#52c41a', fontSize: size }} />
  if (estado === 'warning') return <WarningFilled     style={{ color: '#faad14', fontSize: size }} />
  if (estado === 'error')   return <CloseCircleFilled style={{ color: '#f5222d', fontSize: size }} />
  if (estado === 'info')    return <InfoCircleOutlined style={{ color: '#1890ff', fontSize: size }} />
  return <MinusOutlined style={{ color: '#d9d9d9', fontSize: size - 2 }} />
}

// ── Celda de valor ────────────────────────────────────────────────────────────
function Valor({ v, esPct, negativo, info }: {
  v: number | null | undefined; esPct?: boolean; negativo?: boolean; info?: boolean
}) {
  if (v === null || v === undefined)
    return <Text type="secondary" style={{ fontSize: 12 }}>—</Text>

  if (info) {
    const str = esPct ? fmtP(v) : `(${fmtE(v)})`
    return (
      <Tooltip title="Valor informativo — componente de cesión estimada pendiente de pago al auxiliar.">
        <Text style={{ fontStyle: 'italic', color: '#faad14', fontSize: 11 }}>{str}</Text>
      </Tooltip>
    )
  }

  if (esPct) {
    const color = v >= 20 ? '#52c41a' : v >= 10 ? '#1890ff' : v >= 0 ? '#faad14' : '#f5222d'
    return <Text strong style={{ color, fontSize: 13 }}>{fmtP(v)}</Text>
  }
  const color = negativo ? '#8c8c8c' : v > 0 ? '#262626' : '#f5222d'
  return (
    <Text style={{ color, fontWeight: negativo ? 400 : 600, fontSize: 13 }}>
      {fmtE(v)}
    </Text>
  )
}

// ── Delta (diferencia entre dos columnas) ─────────────────────────────────────
function Delta({ a, b, esPct, informativo }: {
  a: number | null | undefined; b: number | null | undefined; esPct?: boolean; informativo?: boolean
}) {
  if (a === null || a === undefined || b === null || b === undefined)
    return <Text type="secondary" style={{ fontSize: 11 }}>—</Text>
  const diff = b - a
  const abs  = Math.abs(diff)
  const color = informativo
    ? '#1890ff'
    : abs <= 1 ? '#52c41a' : abs <= 500 ? '#faad14' : '#f5222d'
  if (esPct) {
    const pp = diff.toFixed(1).replace('.', ',')
    return <Text style={{ color, fontSize: 11, fontWeight: 600 }}>{diff >= 0 ? '+' : ''}{pp} pp</Text>
  }
  return <Text style={{ color, fontSize: 11, fontWeight: 600 }}>{fmtD(diff)}</Text>
}

// ── Estilos por tipo de fila ──────────────────────────────────────────────────
function rowStyle(tipo: string) {
  if (tipo === 'subtotal') return { background: '#f0f5ff', fontWeight: 700 }
  if (tipo === 'info')     return { background: '#fffbe6' }
  return {}
}

export default function PanelControl() {
  const [ejercicio, setEjercicio] = useState<number>(2025)

  const { data, isLoading, error } = useQuery({
    queryKey: ['cuadre-panel', ejercicio],
    queryFn: () => cuadreApi.getPanel(ejercicio).then(r => r.data),
  })

  const ejercicioOpts = [2023, 2024, 2025, 2026].map(y => ({ value: y, label: String(y) }))
  const esPct = (row: any) => row.concepto.includes('%')

  // ── Columnas de la tabla P&L ─────────────────────────────────────────────
  const cols = [
    {
      title: <Text strong style={{ fontSize: 12 }}>Línea P&L</Text>,
      dataIndex: 'concepto', width: 220,
      render: (v: string, row: any) => {
        const isInfo = row.tipo === 'info'
        const isSub  = row.tipo === 'subtotal'
        return (
          <Text style={{
            fontSize: isInfo ? 11 : 13,
            fontStyle: isInfo ? 'italic' : undefined,
            fontWeight: isSub ? 700 : row.negativo ? 400 : undefined,
            color: isInfo ? '#8c8c8c' : undefined,
          }}>
            {v}
            {isInfo && (
              <Tooltip title="Línea informativa: componente de la cesión ya incluido en la fila Cesión auxiliar.">
                <InfoCircleOutlined style={{ marginLeft: 4, fontSize: 10 }} />
              </Tooltip>
            )}
          </Text>
        )
      },
    },
    // ── Col 1: Diario contable ────────────────────────────────────────────
    {
      title: (
        <Space direction="vertical" size={0}>
          <Tag color="default" style={{ margin: 0 }}>1 · Diario contable</Tag>
          <Text type="secondary" style={{ fontSize: 10 }}>
            Apuntes RAW · ejercicio {ejercicio}
          </Text>
          <Text type="secondary" style={{ fontSize: 9, color: '#bfbfbf' }}>
            cuentas 7* / 623* / 6x
          </Text>
        </Space>
      ),
      dataIndex: 'diario', align: 'right' as const,
      render: (v: number | null, row: any) =>
        row.tipo === 'info' ? null : <Valor v={v} esPct={esPct(row)} negativo={row.negativo} />,
    },
    // ── Col 2: Presupuesto → Cuenta de Resultados ─────────────────────────
    {
      title: (
        <Space direction="vertical" size={0}>
          <Tag color="purple" style={{ margin: 0 }}>2 · Presupuesto</Tag>
          <Text type="secondary" style={{ fontSize: 10 }}>
            Presupuestación › Cta. de Resultados
          </Text>
          <Text type="secondary" style={{ fontSize: 9, color: '#bfbfbf' }}>
            {data?.presupuesto_es_base
              ? `col. «Real ${ejercicio}» · del Ppto ${data.presupuesto_ppto}`
              : `col. «Presupuesto ${ejercicio}»${data?.presupuesto_base ? ` · base ${data.presupuesto_base}` : ''}`
            }
          </Text>
        </Space>
      ),
      dataIndex: 'presupuesto', align: 'right' as const,
      render: (v: number | null, row: any) =>
        row.tipo === 'info' ? null : <Valor v={v} esPct={esPct(row)} negativo={row.negativo} />,
    },
    // ── Col 3: Analítico → Cuenta de Resultados Normalizada ───────────────
    {
      title: (
        <Space direction="vertical" size={0}>
          <Tag color="blue" style={{ margin: 0 }}>3 · Analítico</Tag>
          <Text type="secondary" style={{ fontSize: 10 }}>
            Modelo Analítico › Cta. Resultados Norm.
          </Text>
          <Text type="secondary" style={{ fontSize: 9, color: '#bfbfbf' }}>
            ejercicio {ejercicio} · cesión real + estimada
          </Text>
        </Space>
      ),
      dataIndex: 'analitico', align: 'right' as const,
      render: (v: number | null, row: any) =>
        row.tipo === 'info' ? null : <Valor v={v} esPct={esPct(row)} negativo={row.negativo} />,
    },
    // ── Col 4: Analítico → Rentabilidad por Cliente ───────────────────────
    {
      title: (
        <Space direction="vertical" size={0}>
          <Tag color="green" style={{ margin: 0 }}>4 · Rentabilidad cliente</Tag>
          <Text type="secondary" style={{ fontSize: 10 }}>
            Modelo Analítico › Pestaña Rentabilidad
          </Text>
          <Text type="secondary" style={{ fontSize: 9, color: '#bfbfbf' }}>
            totales tabla clientes · {ejercicio} · cesión norm.
          </Text>
        </Space>
      ),
      dataIndex: 'rentabilidad', align: 'right' as const,
      render: (v: number | null, row: any) => (
        <Valor v={v} esPct={esPct(row)} negativo={row.negativo} info={row.tipo === 'info'} />
      ),
    },
    // ── Δ Diario ↔ Analítico ──────────────────────────────────────────────
    {
      title: (
        <Tooltip title="Diferencia EBITDA: Diario contable vs Analítico normalizado. Debe ser ≈ 0.">
          <Text style={{ fontSize: 10, color: '#8c8c8c' }}>Δ 1↔3</Text>
        </Tooltip>
      ),
      key: 'da', align: 'right' as const, width: 90,
      render: (_: any, row: any) =>
        row.tipo === 'info' ? null : (
          <Delta a={row.diario} b={row.analitico} esPct={esPct(row)} />
        ),
    },
    // ── Δ Analítico ↔ Rentabilidad ────────────────────────────────────────
    {
      title: (
        <Tooltip title="Diferencia: Analítico norm. vs Rentabilidad cliente. Debe ser ≈ 0.">
          <Text style={{ fontSize: 10, color: '#8c8c8c' }}>Δ 3↔4</Text>
        </Tooltip>
      ),
      key: 'ar', align: 'right' as const, width: 90,
      render: (_: any, row: any) =>
        row.tipo === 'info' ? null : (
          <Delta a={row.analitico} b={row.rentabilidad} esPct={esPct(row)} />
        ),
    },
    // ── Δ Diario ↔ Presupuesto (informativo) ─────────────────────────────
    {
      title: (
        <Tooltip title="Desviación real (diario) vs presupuesto. Informativo — no tiene que ser 0.">
          <Text style={{ fontSize: 10, color: '#1890ff' }}>Δ 1↔2</Text>
        </Tooltip>
      ),
      key: 'dp', align: 'right' as const, width: 90,
      render: (_: any, row: any) =>
        row.tipo === 'info' ? null : (
          <Delta a={row.diario} b={row.presupuesto} esPct={esPct(row)} informativo />
        ),
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>

      {/* ── Cabecera ──────────────────────────────────────────────────────── */}
      <Row align="middle" justify="space-between">
        <Col>
          <Title level={4} style={{ margin: 0 }}>Panel de control — Cuadre de módulos</Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Compara las 4 fuentes para el mismo ejercicio:{' '}
            <strong>Diario contable</strong> · <strong>Presupuesto (Cta. Resultados)</strong> · <strong>Analítico (Cta. Resultados Norm.)</strong> · <strong>Analítico (Rentabilidad por Cliente)</strong>
          </Text>
        </Col>
        <Col>
          <Select value={ejercicio} onChange={setEjercicio}
            style={{ width: 100 }} options={ejercicioOpts} />
        </Col>
      </Row>

      {isLoading && <Spin size="large" style={{ display: 'block', margin: '40px auto' }} />}
      {error && <Alert type="error" showIcon message="Error cargando datos del panel." />}

      {data && (
        <>
          {/* ── Semáforos + módulos ───────────────────────────────────────── */}
          <Row gutter={[12, 12]}>
            {/* Indicador global de cuadre */}
            <Col xs={24} md={5}>
              <Card size="small" styles={{ body: { padding: 14, textAlign: 'center' } }}>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>
                  CUADRE {ejercicio}
                </Text>
                {data.n_cuadres_total === 0 ? (
                  <MinusOutlined style={{ fontSize: 42, color: '#d9d9d9' }} />
                ) : data.n_cuadres_ok === data.n_cuadres_total ? (
                  <CheckCircleFilled style={{ fontSize: 42, color: '#52c41a' }} />
                ) : data.n_cuadres_ok >= Math.ceil(data.n_cuadres_total / 2) ? (
                  <WarningFilled style={{ fontSize: 42, color: '#faad14' }} />
                ) : (
                  <CloseCircleFilled style={{ fontSize: 42, color: '#f5222d' }} />
                )}
                <div style={{ marginTop: 6 }}>
                  <Text strong style={{ fontSize: 20 }}>
                    {data.n_cuadres_ok}/{data.n_cuadres_total}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                    verificaciones OK
                  </Text>
                </div>
                <Progress
                  percent={data.n_cuadres_total > 0
                    ? Math.round(data.n_cuadres_ok / data.n_cuadres_total * 100) : 0}
                  status={data.n_cuadres_ok === data.n_cuadres_total ? 'success' : 'normal'}
                  strokeColor={data.n_cuadres_ok === data.n_cuadres_total ? '#52c41a' : '#faad14'}
                  size="small" showInfo={false} style={{ marginTop: 8 }}
                />
              </Card>
            </Col>

            {/* Estado de cada módulo */}
            <Col xs={24} md={19}>
              <Card size="small" styles={{ body: { padding: 12 } }}>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 10 }}>
                  ESTADO DE MÓDULOS PARA {ejercicio}
                </Text>
                <Row gutter={[8, 8]}>
                  {[
                    { key: 'diario',       label: '1 · Diario contable',   sub: 'Apuntes RAW',                                                                     color: '#595959' },
                    { key: 'presupuesto',  label: '2 · Presupuesto',        sub: data.presupuesto_es_base ? `Real ${ejercicio} · Ppto ${data.presupuesto_ppto}` : 'Presupuestación › Cta. Resultados', color: '#722ed1' },
                    { key: 'analitico',    label: '3 · Analítico',          sub: 'Cta. Resultados Norm.',                                                           color: '#1890ff' },
                    { key: 'rentabilidad', label: '4 · Rentabilidad',       sub: 'Analítico › Pestaña Rentabilidad',                                                color: '#52c41a' },
                  ].map(({ key, label, sub, color }) => {
                    const ok = data.tiene_datos?.[key]
                    return (
                      <Col span={6} key={key}>
                        <div style={{
                          textAlign: 'center', padding: '10px 6px', borderRadius: 8,
                          border: `2px solid ${ok ? color : '#d9d9d9'}`,
                          background: ok ? '#fafafa' : '#f5f5f5',
                        }}>
                          <Text style={{ fontSize: 11, fontWeight: 600, color: ok ? color : '#bfbfbf', display: 'block' }}>
                            {label}
                          </Text>
                          <Text style={{ fontSize: 9, color: ok ? '#8c8c8c' : '#d9d9d9', display: 'block', marginTop: 1 }}>
                            {sub}
                          </Text>
                          <Tag color={ok ? 'success' : 'default'} style={{ marginTop: 4, fontSize: 10 }}>
                            {ok ? 'Con datos' : 'Sin datos'}
                          </Tag>
                        </div>
                      </Col>
                    )
                  })}
                </Row>
              </Card>
            </Col>
          </Row>

          {/* ── Cuadres de EBITDA ────────────────────────────────────────── */}
          {data.cuadres && data.cuadres.length > 0 && (
            <Card size="small" styles={{ body: { padding: '8px 16px' } }}>
              <Space size={24} wrap>
                {(data.cuadres as any[]).map((c, i) => (
                  <Space key={i} size={8} align="center">
                    <Semaforo estado={c.estado} size={16} />
                    <div>
                      <Text style={{ fontSize: 12, fontWeight: 600 }}>EBITDA: {c.label}</Text>
                      <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                        {c.estado === 'sin_datos'
                          ? 'Sin datos suficientes'
                          : c.estado === 'info'
                          ? c.diff != null ? `Desviación: ${fmtD(c.diff)}` : '—'
                          : c.diff === 0 ? '✓ Cuadra exacto'
                          : `Δ ${fmtD(c.diff)}`}
                      </Text>
                    </div>
                  </Space>
                ))}
              </Space>
            </Card>
          )}

          {/* ── Tabla P&L ─────────────────────────────────────────────────── */}
          <Card
            size="small"
            styles={{ body: { padding: 0 } }}
            title={
              <Row justify="space-between" align="middle">
                <Col>
                  <Text strong>Cuenta de resultados comparada — ejercicio {ejercicio}</Text>
                </Col>
                {(data.rent_n_estimados ?? 0) > 0 && (
                  <Col>
                    <Tag color="orange" style={{ fontSize: 11 }}>
                      {data.rent_n_estimados} clientes con cesión estimada incluida (cesión normalizada cols 3 y 4)
                    </Tag>
                  </Col>
                )}
              </Row>
            }
          >
            <Table
              dataSource={(data.pl || []).map((r: any, i: number) => ({ key: i, ...r }))}
              columns={cols}
              size="small"
              pagination={false}
              scroll={{ x: 960 }}
              bordered
              onRow={(row) => ({ style: rowStyle(row.tipo) })}
            />

            {data.costes_detalle && (
              <div style={{ padding: '8px 16px', background: '#fafafa', borderTop: '1px solid #f0f0f0', fontSize: 11 }}>
                <Text type="secondary">
                  Desglose costes (col 3 analítico) →{' '}
                  Operativos: <strong>{fmtE(data.costes_detalle.costes_op)}</strong>{' · '}
                  Marketing: <strong>{fmtE(data.costes_detalle.costes_mkt)}</strong>
                  {Math.abs(data.costes_detalle.ajustes_coste) > 1 && (
                    <Tooltip title="Cuentas sin naturaleza asignada o ajustes contables reclasificados.">
                      {' · '}Ajustes/Sin mapear: <strong style={{ color: '#faad14' }}>
                        {fmtE(data.costes_detalle.ajustes_coste)}
                      </strong> <InfoCircleOutlined />
                    </Tooltip>
                  )}
                  {' · '}Total: <strong>{fmtE(data.costes_detalle.total)}</strong>
                </Text>
              </div>
            )}
          </Card>

          {/* ── Por qué difieren las columnas ─────────────────────────────── */}
          <Card
            size="small"
            title={<Text strong>¿Por qué difieren las columnas?</Text>}
            styles={{ body: { padding: '12px 16px' } }}
          >
            <Row gutter={[16, 12]}>
              {/* ── Col 1 vs Col 2 ───────────────────────────────────────── */}
              <Col xs={24} md={12}>
                <div style={{ marginBottom: 12 }}>
                  <Space size={4} align="center" style={{ marginBottom: 4 }}>
                    <Tag color="default" style={{ fontSize: 10, margin: 0 }}>1 Diario contable</Tag>
                    <Text style={{ fontSize: 11 }}>vs</Text>
                    <Tag color="purple" style={{ fontSize: 10, margin: 0 }}>2 Presupuesto (Cta. Resultados)</Tag>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                    <strong>Desviación real vs plan.</strong> El diario refleja lo que realmente
                    ocurrió en el ejercicio; la columna 2 recoge la proyección de ingresos y
                    gastos que se introdujo en el módulo <em>Presupuestación › Cuenta de Resultados</em>.
                    Una diferencia positiva en ingresos (real &gt; plan) es favorable; en costes, lo
                    contrario. <strong>Esta diferencia no tiene por qué ser 0</strong> — es el
                    indicador de cumplimiento presupuestario.
                  </Text>
                </div>
              </Col>

              {/* ── Col 1 vs Col 3 ───────────────────────────────────────── */}
              <Col xs={24} md={12}>
                <div style={{ marginBottom: 12 }}>
                  <Space size={4} align="center" style={{ marginBottom: 4 }}>
                    <Tag color="default" style={{ fontSize: 10, margin: 0 }}>1 Diario contable</Tag>
                    <Text style={{ fontSize: 11 }}>vs</Text>
                    <Tag color="blue" style={{ fontSize: 10, margin: 0 }}>3 Analítico (Cta. Resultados Norm.)</Tag>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                    <strong>Normalización y enriquecimiento.</strong> La columna 3 muestra
                    exactamente los mismos valores que el <em>Dashboard Ejecutivo › Cuenta de
                    Resultados Normalizada</em>. La cesión normalizada filtra solo 623* de
                    recibos con auxiliar identificado y añade la cesión devengada estimada.
                    Pueden diferir si hay 623* sin auxiliar (ces_ajuste) o cuentas 6x sin
                    mapear en el analítico. <strong>Idealmente = 0.</strong>
                  </Text>
                </div>
              </Col>

              {/* ── Col 3 vs Col 4 ───────────────────────────────────────── */}
              <Col xs={24} md={12}>
                <div style={{ marginBottom: 12 }}>
                  <Space size={4} align="center" style={{ marginBottom: 4 }}>
                    <Tag color="blue" style={{ fontSize: 10, margin: 0 }}>3 Analítico</Tag>
                    <Text style={{ fontSize: 11 }}>vs</Text>
                    <Tag color="green" style={{ fontSize: 10, margin: 0 }}>4 Rentabilidad por cliente</Tag>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                    <strong>Misma fuente, distinto nivel de agregación.</strong> Ambas columnas leen
                    la misma tabla <code>fact_resultado_analitico</code>. La columna 4 es el
                    total que aparece en la fila de resumen de la pestaña{' '}
                    <em>Modelo Analítico › Rentabilidad por Cliente</em> (campos: comisión bruta,
                    cesión normalizada, costes imputados, EBITDA). La diferencia puede surgir por
                    apuntes 623* sin auxiliar (<em>ces_ajuste</em>) que el módulo de rentabilidad
                    no distribuye a clientes. <strong>Idealmente = 0.</strong>
                  </Text>
                </div>
              </Col>

              {/* ── Cesión estimada ───────────────────────────────────────── */}
              <Col xs={24} md={12}>
                <div>
                  <Space size={4} align="center" style={{ marginBottom: 4 }}>
                    <Tag color="orange" style={{ fontSize: 10, margin: 0 }}>Cesión estimada (línea informativa)</Tag>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                    Cuando un auxiliar tiene recibos en el ejercicio pero aún no se ha registrado
                    el apunte 623* en el diario, el modelo estima la cesión al{' '}
                    <strong>40% del ingreso del recibo</strong>. Esta estimación solo aparece en
                    las columnas 3 y 4 (analítico y rentabilidad), nunca en el diario ni en el
                    presupuesto. Se muestra en cursiva como línea informativa dentro de la cesión.
                  </Text>
                </div>
              </Col>
            </Row>
          </Card>
        </>
      )}
    </Space>
  )
}
