import { useState, useEffect, useRef } from 'react'
import {
  Row, Col, Card, Statistic, Typography, Select, Button, Spin, Space,
  Table, Tag, Alert, Tabs, message, Divider, Progress,
  Tooltip, InputNumber,
} from 'antd'
import {
  SyncOutlined, CheckCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip as ChartTooltip, Legend, Cell, ReferenceLine,
} from 'recharts'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { analiticoApi } from '../../api/analitico'
import { apiError } from '../../utils/errorHandler'
import RentabilidadCliente from '../rentabilidad/RentabilidadCliente'

const { Title, Text } = Typography

// ── Formatters ────────────────────────────────────────────────────────────────
// Usa regex en vez de Intl.NumberFormat para garantizar punto de miles en cualquier
// entorno (algunos builds de Node/Vite no incluyen datos ICU completos para es-ES).
const _miles = (v: number) =>
  Math.round(Math.abs(v ?? 0)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.')
// Importes con 2 decimales, igual que la Cuenta de Resultados del presupuesto,
// para que las cifras de las dos pantallas se lean idénticas.
const _milesDec = (v: number) => {
  const [ent, dec] = Math.abs(v ?? 0).toFixed(2).split('.')
  return ent.replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ',' + dec
}
// Espacio no separable antes de "€": con los decimales la cifra es más ancha y en
// columnas estrechas no debe partirse en dos líneas.
const fmt  = (v: number) => ((v ?? 0) <= -0.005 ? '-' : '') + _milesDec(v) + ' €'
const fmtN = (v: number) => (v < 0 ? '-' : '') + _miles(v)
const pct  = (v: number) => (v != null ? v.toFixed(2).replace('.', ',') + '%' : '—')

const COLORS = ['#1890ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#13c2c2', '#fa8c16', '#eb2f96']

// Colores estándar para gráficos contable vs normalizado
const C_CONT_POS = '#4096ff'
const C_CONT_NEG = '#ff7875'
const C_NORM_POS = '#9254de'
const C_NORM_NEG = '#ff4d4f'

// Formateador dinámico del eje Y: usa k o M según magnitud
const tickFmtAuto = (v: number) => {
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000)     return `${(v / 1_000).toFixed(0)}k`
  return `${v}`
}

const NAT_COLOR: Record<string, string> = {
  'Personal': '#1890ff', 'Alquiler': '#fa8c16', 'Tecnología': '#13c2c2',
  'Marketing': '#722ed1', 'Financiero': '#2f54eb', 'Bancos': '#4096ff',
  'Servicios profesionales': '#d4b106', 'Comunicaciones': '#52c41a',
  'Viajes': '#389e0d', 'Impuestos': '#eb2f96', 'Seguros': '#c41d7f', 'Suministros': '#cf1322',
  'Cesión auxiliar': '#f5222d',
}

// ── Economía por póliza (vista normalizada) ──────────────────────────────────
// Una póliza deja beneficio si su comisión neta (tras cesión) supera su coste de
// gestión. Comisión mínima = coste por póliza / (1 − % cesión).
const fmtPol = (v: number | null | undefined) => (v == null ? '—' : fmt(v))
const colsPorPoliza = {
  title: (
    <Tooltip title="Economía por póliza (vista normalizada). Neta = comisión − cesión normalizada. Coste = costes operativos imputados. Mínima = coste / (1 − % cesión): la comisión por póliza por debajo de la cual cada póliza pierde dinero.">
      <span style={{ color: '#d46b08', fontWeight: 600 }}>Por póliza (normalizado)</span>
    </Tooltip>
  ),
  children: [
    { title: 'Pólizas', dataIndex: 'n_polizas', align: 'right' as const, width: 72,
      render: (v: number) => fmtN(v ?? 0), sorter: (a: any, b: any) => (a.n_polizas || 0) - (b.n_polizas || 0) },
    { title: 'Comisión', dataIndex: 'comision_por_poliza', align: 'right' as const, width: 85,
      render: (v: number | null, row: any) => {
        const bajo = v != null && row.comision_minima_poliza != null && v < row.comision_minima_poliza
        return <Text style={{ color: bajo ? '#f5222d' : undefined }}>{fmtPol(v)}</Text>
      },
      sorter: (a: any, b: any) => (a.comision_por_poliza || 0) - (b.comision_por_poliza || 0) },
    { title: 'Neta', dataIndex: 'neta_por_poliza', align: 'right' as const, width: 80,
      render: (v: number | null) => fmtPol(v), sorter: (a: any, b: any) => (a.neta_por_poliza || 0) - (b.neta_por_poliza || 0) },
    { title: 'Coste', dataIndex: 'coste_por_poliza', align: 'right' as const, width: 80,
      render: (v: number | null) => fmtPol(v), sorter: (a: any, b: any) => (a.coste_por_poliza || 0) - (b.coste_por_poliza || 0) },
    { title: 'Resultado', dataIndex: 'resultado_por_poliza', align: 'right' as const, width: 85,
      render: (v: number | null) => <Text style={{ color: v == null ? undefined : v >= 0 ? '#52c41a' : '#f5222d', fontWeight: 600 }}>{fmtPol(v)}</Text>,
      sorter: (a: any, b: any) => (a.resultado_por_poliza || 0) - (b.resultado_por_poliza || 0) },
    { title: <Tooltip title="Comisión por póliza necesaria para no perder dinero con su % de cesión: coste / (1 − % cesión). En rojo la comisión si no la alcanza."><span>Mínima</span></Tooltip>,
      dataIndex: 'comision_minima_poliza', align: 'right' as const, width: 80,
      render: (v: number | null) => <Text type="secondary">{fmtPol(v)}</Text>,
      sorter: (a: any, b: any) => (a.comision_minima_poliza || 0) - (b.comision_minima_poliza || 0) },
  ],
}

// Celdas de total del bloque "Por póliza" (desde el índice de columna start).
function porPolizaSummary(rows: any[], start: number) {
  const tPol   = rows.reduce((s, r) => s + (r.n_polizas || 0), 0)
  const tBruta = rows.reduce((s, r) => s + (r.comision_bruta || 0), 0)
  const tCesN  = rows.reduce((s, r) => s + (r.cesion_normalizada || 0), 0)
  const tEbN   = rows.reduce((s, r) => s + (r.ebitda_normalizado || 0), 0)
  const coste  = tBruta - tCesN - tEbN
  const pctCes = tBruta > 0 ? tCesN / tBruta : 0
  const porPol = (v: number) => (tPol > 0 ? fmt(v / tPol) : '—')
  return (
    <>
      <Table.Summary.Cell index={start} align="right">{fmtN(tPol)}</Table.Summary.Cell>
      <Table.Summary.Cell index={start + 1} align="right">{porPol(tBruta)}</Table.Summary.Cell>
      <Table.Summary.Cell index={start + 2} align="right">{porPol(tBruta - tCesN)}</Table.Summary.Cell>
      <Table.Summary.Cell index={start + 3} align="right">{porPol(coste)}</Table.Summary.Cell>
      <Table.Summary.Cell index={start + 4} align="right"><Text style={{ color: tEbN >= 0 ? '#52c41a' : '#f5222d' }}>{porPol(tEbN)}</Text></Table.Summary.Cell>
      <Table.Summary.Cell index={start + 5} align="right"><Text type="secondary">{tPol > 0 && pctCes < 1 ? fmt(coste / tPol / (1 - pctCes)) : '—'}</Text></Table.Summary.Cell>
    </>
  )
}

function KpiCard({
  title, value, suffix, color, tooltip,
}: { title: string; value: number; suffix?: string; color?: string; tooltip?: string }) {
  return (
    <Tooltip title={tooltip} placement="bottom">
      <Card size="small" style={{ height: '100%' }}>
        <Statistic
          title={title}
          value={value}
          formatter={v => fmt(Number(v))}
          valueStyle={{ color: color || '#333', fontSize: 20 }}
          suffix={suffix}
        />
      </Card>
    </Tooltip>
  )
}

// Benchmarks de mercado para corredurías pequeñas en España (INESE 2025-2026)
function BenchmarkCard({
  label, sub, value, display, colorFn, rangos, fuente,
}: {
  label: string
  sub?: string
  value: number
  display?: string
  colorFn: (v: number) => string
  rangos: [string, string, string]
  fuente: string
}) {
  const color = colorFn(value)
  const tagColor = color === '#52c41a' ? 'success' : color === '#faad14' ? 'warning' : 'error'
  const tagLabel = color === '#52c41a' ? 'Óptimo' : color === '#faad14' ? 'Bueno' : 'Alerta'
  return (
    <Card size="small" style={{ height: '100%' }}>
      <div style={{ marginBottom: 4 }}>
        <Text type="secondary" style={{ fontSize: 12 }}>{label}</Text>
        {sub && <Text type="secondary" style={{ fontSize: 10, display: 'block' }}>{sub}</Text>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <Text style={{ fontSize: 22, fontWeight: 700, color }}>{display ?? `${value.toFixed(2).replace('.', ',')}%`}</Text>
        <Tag color={tagColor}>{tagLabel}</Tag>
      </div>
      <div style={{ fontSize: 11, lineHeight: 1.8 }}>
        <span style={{ color: '#52c41a', marginRight: 8 }}>● {rangos[0]}</span>
        <span style={{ color: '#faad14', marginRight: 8 }}>● {rangos[1]}</span>
        <span style={{ color: '#f5222d' }}>● {rangos[2]}</span>
      </div>
      <Text type="secondary" style={{ fontSize: 10 }}>Fuente: {fuente}</Text>
    </Card>
  )
}

function HRankChart({ data, nameKey }: { data: any[], nameKey: string }) {
  const trunc18 = (v: string) => !v ? "-" : v.length > 18 ? v.substring(0, 18) + "..." : v
  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 24, right: 16, bottom: 80, left: 8 }} barCategoryGap="30%" barGap={3}>
        <CartesianGrid strokeDasharray="2 4" vertical={false} stroke="#e8e8e8" />
        <XAxis dataKey={nameKey} tick={{ fontSize: 10 }} interval={0} angle={-40} textAnchor="end" tickFormatter={trunc18} />
        <YAxis tickFormatter={tickFmtAuto} tick={{ fontSize: 10 }} width={52}
          domain={([dMin, dMax]: [number, number]) => { const pad = Math.max(Math.abs(dMin), Math.abs(dMax)) * 0.2; return [dMin < 0 ? dMin - pad : 0, dMax + pad] }} />
        <ChartTooltip
          formatter={(v: any, name: string, props: any) => {
            const row = props?.payload || {}
            const isNorm = name === "ebitda_normalizado"
            const mrg = isNorm ? (row.margen_pct_norm ?? 0) : (row.margen_pct ?? 0)
            return [fmt(Number(v)) + "  Mrg: " + pct(mrg), isNorm ? "EBITDA normalizado" : "EBITDA contable"]
          }}
        />
        <Legend formatter={(v: string) => v === "ebitda_normalizado" ? "EBITDA norm." : "EBITDA contable"} wrapperStyle={{ paddingTop: 4 }} />
        <ReferenceLine y={0} stroke="#595959" strokeWidth={1.5} />
        <Bar dataKey="ebitda" name="ebitda" radius={[3, 3, 0, 0]}>
          {data.map((d: any, i: number) => <Cell key={i} fill={(d.ebitda ?? 0) >= 0 ? C_CONT_POS : C_CONT_NEG} />)}
        </Bar>
        <Bar dataKey="ebitda_normalizado" name="ebitda_normalizado" radius={[3, 3, 0, 0]}>
          {data.map((d: any, i: number) => <Cell key={i} fill={(d.ebitda_normalizado ?? 0) >= 0 ? C_NORM_POS : C_NORM_NEG} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Dashboard 1 Ejecutivo ─────────────────────────────────────────────────────
function D1Ejecutivo({ ejercicio, tasaCesion }: { ejercicio: number; tasaCesion: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analitico-d1', ejercicio, tasaCesion],
    queryFn: () => analiticoApi.dashEjecutivo(ejercicio, tasaCesion / 100).then(r => r.data),
    enabled: !!ejercicio,
  })

  if (isLoading) return <Spin />
  if (!data || data.sin_datos) return <Alert type="info" message="Sin datos. Ejecuta el recálculo primero." />

  const r = data.resumen

  return (
    <div>
      {/* Fila contable */}
      <Row gutter={[12, 8]} style={{ marginBottom: 8 }}>
        <Col span={4}><KpiCard title="Comisiones brutas" value={r.comision_bruta} color="#1890ff"
          tooltip={`Ingresos brutos: ${fmt(r.comision_bruta)}`} /></Col>
        <Col span={4}><KpiCard title="Cesión auxiliar" value={r.comision_auxiliar} color="#fa8c16"
          tooltip={`SUM(-importe) cuentas 623* = ${fmt(r.comision_auxiliar)}`} /></Col>
        <Col span={4}><KpiCard title="Comisión neta" value={r.comision_neta} color="#52c41a"
          tooltip={`Bruta ${fmt(r.comision_bruta)} − Cesión ${fmt(r.comision_auxiliar)} = ${fmt(r.comision_neta)}`} /></Col>
        <Col span={4}><KpiCard title="Costes operativos" value={r.costes_op_contable ?? r.costes_operativos} color="#f5222d"
          tooltip={`Analítico ${fmt(r.costes_operativos)} + Ajuste coste ${fmt((r.costes_op_contable ?? r.costes_operativos) - r.costes_operativos)} = ${fmt(r.costes_op_contable ?? r.costes_operativos)}`} /></Col>
        <Col span={4}><KpiCard title="EBITDA contable" value={r.ebitda_contable ?? r.ebitda} color={(r.ebitda_contable ?? r.ebitda) >= 0 ? '#52c41a' : '#f5222d'}
          tooltip={`Bruta ${fmt(r.comision_bruta)} − Ces ${fmt(r.comision_auxiliar)} − COP ${fmt(r.costes_op_contable ?? r.costes_operativos)} − Capt ${fmt(r.costes_captacion)} − SinMap ${fmt(r.sin_mapear ?? 0)} = ${fmt(r.ebitda_contable ?? r.ebitda)}`} /></Col>
        <Col span={4}>
          <Tooltip title={`EBITDA ${fmt(r.ebitda_contable ?? r.ebitda)} / Bruta ${fmt(r.comision_bruta)} = ${(r.margen_pct_contable ?? r.margen_pct).toFixed(2).replace('.', ',')}%`} placement="bottom">
            <Card size="small" style={{ height: '100%' }}>
              <Statistic title="Margen EBITDA" value={r.margen_pct_contable ?? r.margen_pct} suffix="%" precision={2} decimalSeparator="," groupSeparator="."
                valueStyle={{ color: (r.margen_pct_contable ?? r.margen_pct) >= 15 ? '#52c41a' : (r.margen_pct_contable ?? r.margen_pct) >= 5 ? '#faad14' : '#f5222d', fontSize: 20 }} />
            </Card>
          </Tooltip>
        </Col>
      </Row>

      {/* Fila normalizada */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col span={24}>
          <div style={{ fontSize: 11, color: '#722ed1', fontWeight: 600, marginBottom: 4, paddingLeft: 2 }}>
            ★ Analítico normalizado — cesión real 623 + devengado estimado
          </div>
        </Col>
        <Col span={6}>
          <Tooltip title={`623 real ${fmt(r.cesion_directa ?? 0)} + Estimada ${fmt(r.cesion_estimada ?? 0)} = ${fmt(r.cesion_normalizada ?? 0)}`} placement="bottom">
            <Card size="small" style={{ borderTop: '2px solid #722ed1' }}>
              <Statistic title="Cesión normalizada" value={r.cesion_normalizada ?? 0}
                formatter={v => fmt(Number(v))}
                valueStyle={{ color: '#722ed1', fontSize: 18 }} />
            </Card>
          </Tooltip>
        </Col>
        <Col span={6}>
          <Tooltip title={`Bruta ${fmt(r.comision_bruta)} − Ces.norm ${fmt(r.cesion_normalizada ?? 0)} = ${fmt(r.comision_neta_norm ?? 0)}`} placement="bottom">
            <Card size="small" style={{ borderTop: '2px solid #13c2c2' }}>
              <Statistic title="Com. neta normalizada" value={r.comision_neta_norm ?? 0}
                formatter={v => fmt(Number(v))}
                valueStyle={{ color: '#13c2c2', fontSize: 18 }} />
            </Card>
          </Tooltip>
        </Col>
        <Col span={6}>
          <Tooltip title={`EBITDA cont. ${fmt(r.ebitda_contable ?? r.ebitda)} + AJ ${fmt(r.costes_op_contable != null ? (r.costes_op_contable - r.costes_operativos) : 0)} + ΔCes ${fmt((r.comision_auxiliar ?? 0) - (r.cesion_normalizada ?? 0))} = ${fmt(r.ebitda_normalizado ?? 0)}`} placement="bottom">
            <Card size="small" style={{ borderTop: '2px solid #52c41a' }}>
              <Statistic title="EBITDA normalizado" value={r.ebitda_normalizado ?? 0}
                formatter={v => fmt(Number(v))}
                valueStyle={{ color: (r.ebitda_normalizado ?? 0) >= 0 ? '#52c41a' : '#f5222d', fontSize: 18 }} />
            </Card>
          </Tooltip>
        </Col>
        <Col span={6}>
          <Tooltip title={`EBITDA norm. ${fmt(r.ebitda_normalizado ?? 0)} / Bruta ${fmt(r.comision_bruta)} = ${(r.margen_pct_norm ?? 0).toFixed(2).replace('.', ',')}%`} placement="bottom">
            <Card size="small" style={{ borderTop: '2px solid #9254de' }}>
              <Statistic title="Margen EBITDA norm." value={r.margen_pct_norm ?? 0} suffix="%" precision={2} decimalSeparator="," groupSeparator="."
                valueStyle={{ color: (r.margen_pct_norm ?? 0) >= 15 ? '#52c41a' : (r.margen_pct_norm ?? 0) >= 5 ? '#faad14' : '#f5222d', fontSize: 18 }} />
            </Card>
          </Tooltip>
        </Col>
      </Row>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col span={24}>
          <Card
            title="Cuenta de Resultados — Contable vs Normalizado"
            size="small"
            extra={
              <Text type="secondary" style={{ fontSize: 11 }}>
                Normalización: 623 real (recibos con auxiliar e ingreso en ejercicio) + estimada
              </Text>
            }
          >
            <Table
              size="small"
              pagination={false}
              showHeader
              dataSource={[
                { key: '1',  concepto: 'Comisión bruta',             contable: r.comision_bruta,         norm: r.comision_bruta,             tipo: 'bruta' },
                { key: '2',  concepto: 'Cesión auxiliar',            contable: r.comision_auxiliar,      norm: r.cesion_normalizada,         tipo: 'cesion' },
                { key: '2a', concepto: '  623 real (recibos año)',   contable: r.comision_auxiliar,                              norm: r.cesion_directa ?? 0,        tipo: 'sub' },
                { key: '2d', concepto: '  + Estimada (devengado)',   contable: null,                                             norm: r.cesion_estimada ?? 0,       tipo: 'sub-adj' },
                { key: '3',  concepto: 'Comisión neta',              contable: r.comision_neta,                                  norm: r.comision_neta_norm,         tipo: 'subtotal' },
                { key: '4',  concepto: 'Costes operativos',          contable: r.costes_op_contable ?? r.costes_operativos,      norm: r.costes_operativos,          tipo: 'coste' },
                { key: '4t', concepto: 'Total gastos',               contable: r.comision_auxiliar + (r.costes_op_contable ?? r.costes_operativos), norm: (r.cesion_normalizada ?? 0) + r.costes_operativos, tipo: 'subtotal' },
                { key: '5',  concepto: 'EBITDA',                     contable: r.ebitda_contable ?? r.ebitda,                    norm: r.ebitda_normalizado,         tipo: 'ebitda' },
                { key: '6',  concepto: '% Margen EBITDA',            contable: r.margen_pct_contable ?? r.margen_pct,            norm: r.margen_pct_norm ?? 0,       tipo: 'pct' },
              ]}
              columns={[
                {
                  title: 'Concepto', dataIndex: 'concepto', width: '34%',
                  render: (v: string, row: any) => {
                    const isSub = row.tipo === 'sub' || row.tipo === 'sub-adj'
                    return <Text
                      strong={row.tipo === 'ebitda' || row.tipo === 'subtotal'}
                      style={isSub ? { fontSize: 11, color: '#8c8c8c', fontStyle: 'italic' } : undefined}
                    >{v}</Text>
                  },
                },
                {
                  title: 'Contable (real)', dataIndex: 'contable', align: 'right' as const, width: '33%',
                  render: (v: number | null, row: any) => {
                    if (row.tipo === 'pct') return <Tag color={v as number >= 15 ? 'success' : (v as number) >= 5 ? 'warning' : 'error'}>{pct(v as number)}</Tag>
                    if (row.tipo === 'sub-adj') return <Text style={{ color: '#bfbfbf', fontSize: 11 }}>—</Text>
                    const isSub = row.tipo === 'sub'
                    const color = row.tipo === 'ebitda' ? ((v ?? 0) >= 0 ? '#52c41a' : '#f5222d') : isSub ? '#8c8c8c' : '#262626'
                    return <Text style={{ color, fontWeight: row.tipo === 'ebitda' || row.tipo === 'subtotal' ? 700 : 400, fontSize: isSub ? 11 : undefined }}>{fmt((v ?? 0))}</Text>
                  },
                },
                {
                  title: 'Normalizado (analítico)', dataIndex: 'norm', align: 'right' as const, width: '33%',
                  render: (v: number, row: any) => {
                    if (row.tipo === 'pct') return <Tag color={v >= 15 ? 'success' : v >= 5 ? 'warning' : 'error'} style={{ fontWeight: 700 }}>{pct(v)}</Tag>
                    const isSub = row.tipo === 'sub' || row.tipo === 'sub-adj'
                    const isAdj = row.tipo === 'sub-adj'
                    const color = row.tipo === 'ebitda' ? (v >= 0 ? '#52c41a' : '#f5222d') : row.tipo === 'cesion' ? '#722ed1' : isSub ? (isAdj ? (v >= 0 ? '#52c41a' : '#f5222d') : '#8c8c8c') : '#262626'
                    return <Text style={{ color, fontWeight: row.tipo === 'ebitda' || row.tipo === 'subtotal' ? 700 : row.tipo === 'cesion' ? 600 : 400, fontSize: isSub ? 11 : undefined }}>{fmt(v ?? 0)}</Text>
                  },
                },
              ]}
              rowClassName={(row: any) => row.tipo === 'ebitda' ? 'ant-table-row-selected' : ''}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title="P&L Contable vs Normalizado" size="small" style={{ height: 360 }}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart
                data={[
                  { name: 'Com. Bruta',  contable: r.comision_bruta || 0,          norm: r.comision_bruta || 0 },
                  { name: '− Cesión',    contable: -(r.comision_auxiliar || 0),     norm: -(r.cesion_normalizada || 0) },
                  { name: 'Com. Neta',   contable: r.comision_neta || 0,            norm: r.comision_neta_norm || 0 },
                  { name: '− Costes',    contable: -((r.costes_op_contable ?? r.costes_operativos) || 0), norm: -(r.costes_operativos || 0) },
                  { name: 'EBITDA',      contable: (r.ebitda_contable ?? r.ebitda) || 0,                  norm: r.ebitda_normalizado || 0 },
                ]}
                margin={{ top: 8, right: 16, bottom: 8, left: 12 }}
                barGap={3}
                barCategoryGap="28%"
              >
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={tickFmtAuto} tick={{ fontSize: 10 }} width={44} />
                <CartesianGrid strokeDasharray="2 4" vertical={false} stroke="#e8e8e8" />
                <ChartTooltip formatter={(v: any, name: string) => [fmt(v), name === 'contable' ? 'Contable' : 'Normalizado']} />
                <Legend formatter={v => v === 'contable' ? 'Contable' : 'Normalizado'} />
                <ReferenceLine y={0} stroke="#595959" strokeWidth={1.5} />
                <Bar dataKey="contable" name="contable" radius={[3, 3, 0, 0]}>
                  {[0,1,2,3,4].map(i => <Cell key={i} fill={[0,2].includes(i) ? C_CONT_POS : i === 4 ? ((r.ebitda_contable ?? r.ebitda) >= 0 ? C_CONT_POS : C_CONT_NEG) : C_CONT_NEG} />)}
                </Bar>
                <Bar dataKey="norm" name="norm" radius={[3, 3, 0, 0]}>
                  {[0,1,2,3,4].map(i => <Cell key={i} fill={[0,2].includes(i) ? C_NORM_POS : i === 4 ? ((r.ebitda_normalizado || 0) >= 0 ? C_NORM_POS : C_NORM_NEG) : C_NORM_NEG} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col span={12}>
          <Card title="Familias de costes — % sobre ingresos brutos" size="small" style={{ height: 360 }}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart
                data={(data.costes_naturaleza || []).slice(0, 10).map((e: any) => ({
                  ...e,
                  pct_ing: r.comision_bruta > 0 ? +(e.importe / r.comision_bruta * 100).toFixed(2) : 0,
                }))}
                layout="vertical"
                margin={{ left: 4, right: 54, top: 4, bottom: 4 }}
              >
                <XAxis type="number" tickFormatter={v => `${v.toFixed(0)}%`} tick={{ fontSize: 10 }} />
                <YAxis type="category" dataKey="naturaleza" width={145} tick={{ fontSize: 10 }} />
                <CartesianGrid strokeDasharray="2 4" horizontal={false} stroke="#e8e8e8" />
                <ChartTooltip
                  formatter={(v: any, _: any, props: any) =>
                    [`${Number(v).toFixed(2).replace('.', ',')}%  ·  ${fmt(props?.payload?.importe ?? 0)}`, '% s/ingresos']}
                />
                <Bar dataKey="pct_ing" name="% s/ingresos" radius={[0, 3, 3, 0]}
                  label={{ position: 'right', formatter: (v: number) => v > 0 ? `${v.toFixed(2).replace('.', ',')}%` : '', fontSize: 10, fill: '#595959' }}>
                  {(data.costes_naturaleza || []).slice(0, 10).map((entry: any, i: number) => (
                    <Cell key={i} fill={NAT_COLOR[entry.naturaleza] || COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>

      <Row gutter={[12, 12]}>
        <Col span={6}>
          <Tooltip title={`Ces.norm ${fmt(r.cesion_normalizada ?? 0)} / Bruta ${fmt(r.comision_bruta)} = ${pct(r.comision_bruta > 0 ? r.cesion_normalizada / r.comision_bruta * 100 : 0)}`} placement="top">
            <div><BenchmarkCard
              label="Ratio cesión normalizada"
              sub="Ces. normalizada / Com. bruta"
              value={r.comision_bruta > 0 ? +(r.cesion_normalizada / r.comision_bruta * 100).toFixed(2) : 0}
              colorFn={v => v <= 30 ? '#52c41a' : v <= 40 ? '#faad14' : '#f5222d'}
              rangos={['Óptimo < 30%', 'Bueno 30–40%', 'Alerta > 40%']}
              fuente="INESE 2025-2026"
            /></div>
          </Tooltip>
        </Col>
        <Col span={6}>
          <Tooltip title={`COP normalizado ${fmt(r.costes_operativos)} / Bruta ${fmt(r.comision_bruta)} = ${(r.ratio_costes_op_pct_norm ?? 0).toFixed(2).replace('.', ',')}%`} placement="top">
            <div><BenchmarkCard
              label="Costes op. / Ingresos"
              sub="Costes op. normalizados / Comisión bruta"
              value={r.ratio_costes_op_pct_norm ?? 0}
              colorFn={v => v <= 35 ? '#52c41a' : v <= 45 ? '#faad14' : '#f5222d'}
              rangos={['Óptimo < 35%', 'Bueno 35–45%', 'Alerta > 45%']}
              fuente="INESE 2025-2026"
            /></div>
          </Tooltip>
        </Col>
        <Col span={6}>
          <Tooltip title={`EBITDA norm. ${fmt(r.ebitda_normalizado ?? 0)} / Bruta ${fmt(r.comision_bruta)} = ${(r.margen_pct_norm ?? 0).toFixed(2).replace('.', ',')}%`} placement="top">
            <div><BenchmarkCard
              label="Margen EBITDA Normalizado"
              sub="EBITDA Norm. / Comisión bruta"
              value={r.margen_pct_norm ?? 0}
              colorFn={v => v >= 25 ? '#52c41a' : v >= 15 ? '#faad14' : '#f5222d'}
              rangos={['Óptimo > 25%', 'Bueno 15–25%', 'Alerta < 15%']}
              fuente="INESE 2025-2026"
            /></div>
          </Tooltip>
        </Col>
        <Col span={6}>
          <Tooltip title={`Ces.norm ${fmt(r.cesion_normalizada ?? 0)} + COP analít. ${fmt(r.costes_operativos)} = Total ${fmt(r.total_gastos_norm ?? 0)} / ${fmtN(r.n_recibos)} rec. = ${fmt(r.coste_por_recibo ?? 0)}`} placement="top">
            <div><BenchmarkCard
              label="Coste total / Recibo"
              sub={`${fmtN(r.n_recibos)} recibos en el ejercicio`}
              value={r.coste_por_recibo}
              display={`${fmt(r.coste_por_recibo ?? 0)}`}
              colorFn={v => v <= 15 ? '#52c41a' : v <= 25 ? '#faad14' : '#f5222d'}
              rangos={['Óptimo < 15 €', 'Bueno 15–25 €', 'Alerta > 25 €']}
              fuente="Estimación sectorial"
            /></div>
          </Tooltip>
        </Col>
      </Row>

      {/* ── Canal: Directo vs Intermediado ─────────────────────────── */}
      <Row gutter={[12, 12]} style={{ marginTop: 8, marginBottom: 8 }}>
        <Col span={18}>
          <Card size="small" title="Canal de negocio — Directo vs. Intermediado (peso sobre ingresos)">
            <Row gutter={[0, 0]} align="middle">
              <Col span={7} style={{ textAlign: 'center' }}>
                <Tooltip title={`Recibos SIN auxiliar: ${fmtN(r.rec_sin_auxiliar ?? 0)} · Ingresos ${fmt(r.ing_sin_auxiliar ?? 0)} / Bruta ${fmt(r.comision_bruta)} = ${(r.pct_sin_auxiliar ?? 0).toFixed(2).replace('.', ',')}%`} placement="bottom">
                  <div>
                    <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>Negocio directo (sin auxiliar)</Text>
                    <Text style={{ fontSize: 26, fontWeight: 700, color: '#1890ff' }}>
                      {(r.pct_sin_auxiliar ?? 0).toFixed(2).replace('.', ',')}%
                    </Text>
                    <Text style={{ fontSize: 13, display: 'block' }}>{fmt(r.ing_sin_auxiliar ?? 0)}</Text>
                    <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                      {fmtN(r.rec_sin_auxiliar ?? 0)} recibos
                    </Text>
                  </div>
                </Tooltip>
              </Col>
              <Col span={10} style={{ padding: '0 16px' }}>
                <div style={{ display: 'flex', height: 18, borderRadius: 4, overflow: 'hidden', margin: '6px 0' }}>
                  <div style={{ width: `${r.pct_sin_auxiliar ?? 0}%`, background: '#1890ff', transition: 'width 0.3s' }} />
                  <div style={{ width: `${r.pct_con_auxiliar ?? 0}%`, background: '#fa8c16', transition: 'width 0.3s' }} />
                </div>
                <Row justify="space-between">
                  <Text style={{ fontSize: 10, color: '#1890ff' }}>■ Directo {(r.pct_sin_auxiliar ?? 0).toFixed(2).replace('.', ',')}%</Text>
                  <Text style={{ fontSize: 10, color: '#fa8c16' }}>■ Auxiliar {(r.pct_con_auxiliar ?? 0).toFixed(2).replace('.', ',')}%</Text>
                </Row>
                <div style={{ marginTop: 6, textAlign: 'center' }}>
                  <Text type="secondary" style={{ fontSize: 10 }}>
                    {fmtN(r.n_recibos_canal ?? 0)} recibos con ingreso · Directo = sin cesión · Auxiliar = paga cesión
                  </Text>
                </div>
              </Col>
              <Col span={7} style={{ textAlign: 'center' }}>
                <Tooltip title={`Recibos CON auxiliar: ${fmtN(r.rec_con_auxiliar ?? 0)} · Ingresos ${fmt(r.ing_con_auxiliar ?? 0)} / Bruta ${fmt(r.comision_bruta)} = ${(r.pct_con_auxiliar ?? 0).toFixed(2).replace('.', ',')}%`} placement="bottom">
                  <div>
                    <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>Intermediado (con auxiliar)</Text>
                    <Text style={{ fontSize: 26, fontWeight: 700, color: '#fa8c16' }}>
                      {(r.pct_con_auxiliar ?? 0).toFixed(2).replace('.', ',')}%
                    </Text>
                    <Text style={{ fontSize: 13, display: 'block' }}>{fmt(r.ing_con_auxiliar ?? 0)}</Text>
                    <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                      {fmtN(r.rec_con_auxiliar ?? 0)} recibos
                    </Text>
                    <Tooltip title={`Cesión normalizada ${fmt(r.cesion_normalizada ?? 0)} / Ingresos intermediados ${fmt(r.ing_con_auxiliar ?? 0)}. Ratio de cesión = % intermediado × esta tasa. Tasa real contabilizada ${r.tasa_cesion_real?.ejercicio ?? ''}: ${pct(r.tasa_cesion_real?.tasa_pct ?? 0)} · aplicada a la estimada: ${pct(r.tasa_cesion_aplicada_pct ?? 0)}`}>
                      <Text strong style={{ fontSize: 12, display: 'block', marginTop: 4, color: '#d46b08' }}>
                        Cesión s/ intermediado: {pct(r.cesion_s_intermediado_pct ?? 0)}
                      </Text>
                    </Tooltip>
                  </div>
                </Tooltip>
              </Col>
            </Row>
          </Card>
        </Col>
        <Col span={6}>
          <Tooltip title={`Ing. sin auxiliar ${fmt(r.ing_sin_auxiliar ?? 0)} / Bruta ${fmt(r.comision_bruta)} = ${(r.pct_sin_auxiliar ?? 0).toFixed(2).replace('.', ',')}% · ${fmtN(r.rec_sin_auxiliar ?? 0)} recibos directos de ${fmtN(r.n_recibos_canal ?? 0)} totales`} placement="top">
            <div><BenchmarkCard
              label="% Negocio directo"
              sub="Ingresos sin auxiliar / Total ingresos"
              value={r.pct_sin_auxiliar ?? 0}
              colorFn={v => v >= 25 ? '#52c41a' : v >= 15 ? '#faad14' : '#f5222d'}
              rangos={['Óptimo > 25%', 'Bueno 15–25%', 'Alerta < 15%']}
              fuente="Recoletos 2026 / FECOR"
            /></div>
          </Tooltip>
        </Col>
      </Row>

      <Row style={{ marginTop: 8 }}>
        <Col span={24}>
          <Card
            size="small"
            style={{ background: '#f6ffed', borderColor: '#b7eb8f' }}
            bodyStyle={{ padding: '8px 12px' }}
          >
            <Space size={4}>
              <Text style={{ fontSize: 12, color: '#389e0d', fontWeight: 600 }}>
                Referencia sectorial — Margen neto (INESE 2026):
              </Text>
              <Tag color="success" style={{ margin: 0 }}>Óptimo 12–15 %</Tag>
              <Tag color="warning" style={{ margin: 0 }}>Bueno 8–12 %</Tag>
              <Tag color="error" style={{ margin: 0 }}>Alerta &lt; 8 %</Tag>
              <Text type="secondary" style={{ fontSize: 11 }}>
                · El modelo calcula EBITDA (previo a amortización, intereses e impuestos).
                Un EBITDA &gt; 25 % implica habitualmente un margen neto superior al 12 %.
              </Text>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

// ── Dashboard 2 Compañía ──────────────────────────────────────────────────────
function D2Compania({ ejercicio, tasaCesion }: { ejercicio: number; tasaCesion: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analitico-d2', ejercicio, tasaCesion],
    queryFn: () => analiticoApi.dashCompania(ejercicio, tasaCesion / 100).then(r => r.data),
    enabled: !!ejercicio,
  })

  if (isLoading) return <Spin />
  if (!data || !data.companias) return <Alert type="info" message="Sin datos. Ejecuta el recálculo primero." />

  const totalBruta = (data.companias as any[]).reduce((acc, c) => acc + (c.comision_bruta || 0), 0)
  const companiasSorted = [...(data.companias as any[])].sort((a, b) => (b.margen_pct_norm ?? b.margen_pct ?? 0) - (a.margen_pct_norm ?? a.margen_pct ?? 0))
  const top10cia = companiasSorted.slice(0, 10)

  const colsD2 = [
    { title: 'Compañía', dataIndex: 'compania', ellipsis: true, width: 160, fixed: 'left' as const,
      sorter: (a: any, b: any) => (a.compania || '').localeCompare(b.compania || '') },
    { title: 'Recibos', dataIndex: 'n_recibos', width: 70, align: 'right' as const,
      render: (v: number) => fmtN(v), sorter: (a: any, b: any) => a.n_recibos - b.n_recibos },
    {
      title: <span style={{ color: '#1890ff', fontWeight: 600 }}>Real (contable)</span>,
      children: [
        { title: 'Ingresos', dataIndex: 'comision_bruta', align: 'right' as const, width: 100,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_bruta - b.comision_bruta },
        { title: 'Peso%', key: 'peso', align: 'right' as const, width: 68,
          render: (_: any, row: any) => <Text type="secondary">{totalBruta > 0 ? (row.comision_bruta / totalBruta * 100).toFixed(2).replace('.', ',') + '%' : '—'}</Text> },
        { title: 'Cesión', dataIndex: 'comision_auxiliar', align: 'right' as const, width: 95,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_auxiliar - b.comision_auxiliar },
        { title: 'Com.Neta', dataIndex: 'comision_neta', align: 'right' as const, width: 95,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_neta - b.comision_neta },
        { title: 'Costes', dataIndex: 'costes_op_contable', align: 'right' as const, width: 90,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => (a.costes_op_contable||0) - (b.costes_op_contable||0) },
        { title: 'EBITDA', dataIndex: 'ebitda_contable', align: 'right' as const, width: 90,
          render: (v: number) => <Text style={{ color: v >= 0 ? '#52c41a' : '#f5222d' }}>{fmt(v)}</Text>,
          sorter: (a: any, b: any) => (a.ebitda_contable||0) - (b.ebitda_contable||0) },
        { title: 'Margen%', dataIndex: 'margen_pct_contable', align: 'center' as const, width: 80,
          render: (v: number) => <Tag color={v >= 15 ? 'success' : v >= 5 ? 'warning' : 'error'}>{pct(v)}</Tag>,
          sorter: (a: any, b: any) => (a.margen_pct_contable||0) - (b.margen_pct_contable||0) },
      ],
    },
    {
      title: <span style={{ color: '#722ed1', fontWeight: 600 }}>Analítico (normalizado)</span>,
      children: [
        { title: 'Ces.Norm.', dataIndex: 'cesion_normalizada', align: 'right' as const, width: 95,
          render: (v: number) => <Text style={{ color: '#722ed1', fontWeight: 600 }}>{fmt(v || 0)}</Text>,
          sorter: (a: any, b: any) => (a.cesion_normalizada || 0) - (b.cesion_normalizada || 0) },
        { title: 'EBITDA Norm.', dataIndex: 'ebitda_normalizado', align: 'right' as const, width: 100,render: (v: number) => <Text style={{ color: (v ?? 0) >= 0 ? '#52c41a' : '#f5222d', fontWeight: 700 }}>{fmt(v || 0)}</Text>,
          sorter: (a: any, b: any) => (a.ebitda_normalizado ?? 0) - (b.ebitda_normalizado ?? 0) },
        { title: 'Mrg.Norm%', dataIndex: 'margen_pct_norm', align: 'center' as const, width: 88,
          defaultSortOrder: 'descend' as const,
          render: (v: number) => <Tag color={(v ?? 0) >= 15 ? 'success' : (v ?? 0) >= 5 ? 'warning' : 'error'} style={{ fontWeight: 700 }}>{pct(v ?? 0)}</Tag>,
          sorter: (a: any, b: any) => (a.margen_pct_norm ?? 0) - (b.margen_pct_norm ?? 0) },
      ],
    },
    colsPorPoliza,
  ]

  return (
    <div>
      <Card title="Ranking compañías — EBITDA Normalizado vs Contable (top 10)" size="small" style={{ marginBottom: 16 }}>
        <HRankChart data={top10cia} nameKey="compania" />
      </Card>
      <Table
        dataSource={companiasSorted}
        columns={colsD2}
        rowKey="compania"
        size="small"
        pagination={false}
        scroll={{ x: 'max-content' }}
        bordered
        rowClassName={(r: any) => (r.ebitda_normalizado ?? r.ebitda_contable ?? r.ebitda) < 0 ? 'ant-table-row-danger' : ''}
        summary={pageData => {
          const rows = pageData as any[]
          const tBruta = rows.reduce((s, r) => s + (r.comision_bruta || 0), 0)
          const tCes   = rows.reduce((s, r) => s + (r.comision_auxiliar || 0), 0)
          const tCesN  = rows.reduce((s, r) => s + (r.cesion_normalizada || 0), 0)
          const tNeta  = rows.reduce((s, r) => s + (r.comision_neta || 0), 0)
          const tCost  = rows.reduce((s, r) => s + (r.costes_op_contable || 0), 0)
          const tEb    = rows.reduce((s, r) => s + (r.ebitda_contable ?? r.ebitda ?? 0), 0)
          const tEbN   = rows.reduce((s, r) => s + (r.ebitda_normalizado || 0), 0)
          const tRec   = rows.reduce((s, r) => s + (r.n_recibos || 0), 0)
          return (
            <Table.Summary.Row style={{ fontWeight: 600, background: '#fafafa' }}>
              <Table.Summary.Cell index={0}><Text strong>TOTAL</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={1} align="right">{fmtN(tRec)}</Table.Summary.Cell>
              <Table.Summary.Cell index={2} align="right">{fmt(tBruta)}</Table.Summary.Cell>
              <Table.Summary.Cell index={3} align="right"><Text type="secondary">100%</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={4} align="right">{fmt(tCes)}</Table.Summary.Cell>
              <Table.Summary.Cell index={5} align="right">{fmt(tNeta)}</Table.Summary.Cell>
              <Table.Summary.Cell index={6} align="right">{fmt(tCost)}</Table.Summary.Cell>
              <Table.Summary.Cell index={7} align="right"><Text style={{ color: tEb >= 0 ? '#52c41a' : '#f5222d' }}>{fmt(tEb)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={8} align="center">
                <Tag color={tBruta > 0 ? (tEb/tBruta*100 >= 15 ? 'success' : tEb/tBruta*100 >= 5 ? 'warning' : 'error') : 'default'}>
                  {tBruta > 0 ? pct(tEb / tBruta * 100) : '—'}
                </Tag>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={9} align="right"><Text style={{ color: '#722ed1', fontWeight: 600 }}>{fmt(tCesN)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={10} align="right"><Text style={{ color: tEbN >= 0 ? '#52c41a' : '#f5222d', fontWeight: 700 }}>{fmt(tEbN)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={11} align="center">
                <Tag color={tBruta > 0 ? (tEbN/tBruta*100 >= 15 ? 'success' : tEbN/tBruta*100 >= 5 ? 'warning' : 'error') : 'default'} style={{ fontWeight: 700 }}>
                  {tBruta > 0 ? pct(tEbN / tBruta * 100) : '—'}
                </Tag>
              </Table.Summary.Cell>
              {porPolizaSummary(rows, 12)}
            </Table.Summary.Row>
          )
        }}
      />
    </div>
  )
}

// ── Dashboard 3 Auxiliar ──────────────────────────────────────────────────────
function D3Auxiliar({ ejercicio, tasaCesion }: { ejercicio: number; tasaCesion: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analitico-d3', ejercicio, tasaCesion],
    queryFn: () => analiticoApi.dashAuxiliar(ejercicio, tasaCesion / 100).then(r => r.data),
    enabled: !!ejercicio,
  })

  if (isLoading) return <Spin />
  if (!data || !data.auxiliares) return <Alert type="info" message="Sin datos. Ejecuta el recálculo primero." />

  const totalBrutaD3 = (data.auxiliares as any[]).reduce((acc: number, a: any) => acc + (a.comision_bruta || 0), 0)

  const colsD3 = [
    { title: 'Auxiliar', dataIndex: 'auxiliar', ellipsis: true, width: 180, fixed: 'left' as const,
      sorter: (a: any, b: any) => (a.auxiliar || '').localeCompare(b.auxiliar || '') },
    { title: 'Recibos', dataIndex: 'n_recibos', width: 70, align: 'right' as const,
      render: (v: number) => fmtN(v), sorter: (a: any, b: any) => a.n_recibos - b.n_recibos },
    {
      title: <span style={{ color: '#1890ff', fontWeight: 600 }}>Real (contable)</span>,
      children: [
        { title: 'Ingresos', dataIndex: 'comision_bruta', align: 'right' as const, width: 95,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_bruta - b.comision_bruta },
        { title: 'Peso%', key: 'pesoD3', align: 'right' as const, width: 60,
          render: (_: any, row: any) => <Text type="secondary">{totalBrutaD3 > 0 ? (row.comision_bruta / totalBrutaD3 * 100).toFixed(2).replace('.', ',') + '%' : '—'}</Text> },
        { title: 'Cesión', dataIndex: 'comision_auxiliar', align: 'right' as const, width: 90,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_auxiliar - b.comision_auxiliar },
        { title: 'Com.Neta', dataIndex: 'comision_neta', align: 'right' as const, width: 90,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_neta - b.comision_neta },
        { title: 'Costes', dataIndex: 'costes_op_contable', align: 'right' as const, width: 85,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => (a.costes_op_contable||0) - (b.costes_op_contable||0) },
        { title: 'EBITDA', dataIndex: 'ebitda_contable', align: 'right' as const, width: 90,
          render: (v: number) => <Text style={{ color: v >= 0 ? '#52c41a' : '#f5222d' }}>{fmt(v)}</Text>,
          sorter: (a: any, b: any) => (a.ebitda_contable||0) - (b.ebitda_contable||0) },
        { title: 'Margen%', dataIndex: 'margen_pct_contable', align: 'center' as const, width: 78,
          render: (v: number) => <Tag color={v >= 15 ? 'success' : v >= 5 ? 'warning' : 'error'}>{pct(v)}</Tag>,
          sorter: (a: any, b: any) => (a.margen_pct_contable||0) - (b.margen_pct_contable||0) },
        { title: 'Ing./Rec.', dataIndex: 'comision_media_recibo', align: 'right' as const, width: 78,
          render: (v: number) => <Text type="secondary">{v ? fmt(v) : '—'}</Text>,
          sorter: (a: any, b: any) => (a.comision_media_recibo || 0) - (b.comision_media_recibo || 0) },
      ],
    },
    {
      title: <span style={{ color: '#722ed1', fontWeight: 600 }}>Analítico (normalizado)</span>,
      children: [
        { title: 'Ces.Norm.', dataIndex: 'cesion_normalizada', align: 'right' as const, width: 95,
          render: (v: number) => <Text style={{ color: '#722ed1', fontWeight: 600 }}>{fmt(v || 0)}</Text>,
          sorter: (a: any, b: any) => (a.cesion_normalizada || 0) - (b.cesion_normalizada || 0) },
        { title: 'EBITDA Norm.', dataIndex: 'ebitda_normalizado', align: 'right' as const, width: 100,render: (v: number) => <Text style={{ color: (v ?? 0) >= 0 ? '#52c41a' : '#f5222d', fontWeight: 700 }}>{fmt(v || 0)}</Text>,
          sorter: (a: any, b: any) => (a.ebitda_normalizado ?? 0) - (b.ebitda_normalizado ?? 0) },
        { title: 'Mrg.Norm%', dataIndex: 'margen_pct_norm', align: 'center' as const, width: 88,
          defaultSortOrder: 'descend' as const,
          render: (v: number) => <Tag color={(v ?? 0) >= 15 ? 'success' : (v ?? 0) >= 5 ? 'warning' : 'error'} style={{ fontWeight: 700 }}>{pct(v ?? 0)}</Tag>,
          sorter: (a: any, b: any) => (a.margen_pct_norm ?? 0) - (b.margen_pct_norm ?? 0) },
      ],
    },
    colsPorPoliza,
  ]

  const auxSorted = [...(data.auxiliares as any[])].sort((a, b) => (b.margen_pct_norm ?? b.margen_pct ?? 0) - (a.margen_pct_norm ?? a.margen_pct ?? 0))
  const top10aux = auxSorted.slice(0, 10)

  return (
    <div>
      <Card title="Ranking auxiliares — EBITDA Normalizado vs Contable (top 10)" size="small" style={{ marginBottom: 16 }}>
        <HRankChart data={top10aux} nameKey="auxiliar" />
      </Card>
      <Table
        dataSource={auxSorted}
        columns={colsD3}
        rowKey="auxiliar"
        size="small"
        pagination={false}
        scroll={{ x: 'max-content' }}
        bordered
        rowClassName={(r: any) => (r.ebitda_normalizado ?? r.ebitda_contable ?? r.ebitda) < 0 ? 'ant-table-row-danger' : ''}
        summary={pageData => {
          const rows = pageData as any[]
          const tBruta = rows.reduce((s, r) => s + (r.comision_bruta || 0), 0)
          const tCes   = rows.reduce((s, r) => s + (r.comision_auxiliar || 0), 0)
          const tCesN  = rows.reduce((s, r) => s + (r.cesion_normalizada || 0), 0)
          const tNeta  = rows.reduce((s, r) => s + (r.comision_neta || 0), 0)
          const tCost  = rows.reduce((s, r) => s + (r.costes_op_contable || 0), 0)
          const tEb    = rows.reduce((s, r) => s + (r.ebitda_contable ?? r.ebitda ?? 0), 0)
          const tEbN   = rows.reduce((s, r) => s + (r.ebitda_normalizado || 0), 0)
          const tRec   = rows.reduce((s, r) => s + (r.n_recibos || 0), 0)
          return (
            <Table.Summary.Row style={{ fontWeight: 600, background: '#fafafa' }}>
              <Table.Summary.Cell index={0}><Text strong>TOTAL</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={1} align="right">{fmtN(tRec)}</Table.Summary.Cell>
              <Table.Summary.Cell index={2} align="right">{fmt(tBruta)}</Table.Summary.Cell>
              <Table.Summary.Cell index={3} align="right"><Text type="secondary">100%</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={4} align="right">{fmt(tCes)}</Table.Summary.Cell>
              <Table.Summary.Cell index={5} align="right">{fmt(tNeta)}</Table.Summary.Cell>
              <Table.Summary.Cell index={6} align="right">{fmt(tCost)}</Table.Summary.Cell>
              <Table.Summary.Cell index={7} align="right"><Text style={{ color: tEb >= 0 ? '#52c41a' : '#f5222d' }}>{fmt(tEb)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={8} align="center">
                <Tag color={tBruta > 0 ? (tEb/tBruta*100 >= 15 ? 'success' : tEb/tBruta*100 >= 5 ? 'warning' : 'error') : 'default'}>{tBruta > 0 ? pct(tEb/tBruta*100) : '—'}</Tag>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={9} />
              <Table.Summary.Cell index={10} align="right"><Text style={{ color: '#722ed1', fontWeight: 600 }}>{fmt(tCesN)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={11} align="right"><Text style={{ color: tEbN >= 0 ? '#52c41a' : '#f5222d', fontWeight: 700 }}>{fmt(tEbN)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={12} align="center">
                <Tag color={tBruta > 0 ? (tEbN/tBruta*100 >= 15 ? 'success' : tEbN/tBruta*100 >= 5 ? 'warning' : 'error') : 'default'} style={{ fontWeight: 700 }}>{tBruta > 0 ? pct(tEbN/tBruta*100) : '—'}</Tag>
              </Table.Summary.Cell>
              {porPolizaSummary(rows, 13)}
            </Table.Summary.Row>
          )
        }}
      />
    </div>
  )
}

// ── Dashboard 4 Ramo ──────────────────────────────────────────────────────────
function D4Ramo({ ejercicio, tasaCesion }: { ejercicio: number; tasaCesion: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analitico-d4', ejercicio, tasaCesion],
    queryFn: () => analiticoApi.dashRamo(ejercicio, tasaCesion / 100).then(r => r.data),
    enabled: !!ejercicio,
  })

  if (isLoading) return <Spin />
  if (!data || !data.ramos) return <Alert type="info" message="Sin datos. Ejecuta el recálculo primero." />

  const totalBrutaD4 = (data.ramos as any[]).reduce((acc: number, r: any) => acc + (r.comision_bruta || 0), 0)
  const ramosSorted  = [...(data.ramos as any[])].sort((a, b) => (b.margen_pct_norm ?? b.margen_pct ?? 0) - (a.margen_pct_norm ?? a.margen_pct ?? 0))
  const top10ramo    = ramosSorted.slice(0, 10)

  const colsD4 = [
    { title: 'Ramo', dataIndex: 'ramo', ellipsis: true, width: 160, fixed: 'left' as const,
      sorter: (a: any, b: any) => (a.ramo || '').localeCompare(b.ramo || '') },
    { title: 'Recibos', dataIndex: 'n_recibos', width: 70, align: 'right' as const,
      render: (v: number) => fmtN(v), sorter: (a: any, b: any) => a.n_recibos - b.n_recibos },
    {
      title: <span style={{ color: '#1890ff', fontWeight: 600 }}>Real (contable)</span>,
      children: [
        { title: 'Ingresos', dataIndex: 'comision_bruta', align: 'right' as const, width: 95,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_bruta - b.comision_bruta },
        { title: 'Peso%', key: 'pesoD4', align: 'right' as const, width: 60,
          render: (_: any, row: any) => <Text type="secondary">{totalBrutaD4 > 0 ? (row.comision_bruta / totalBrutaD4 * 100).toFixed(2).replace('.', ',') + '%' : '—'}</Text> },
        { title: 'Cesión', dataIndex: 'comision_auxiliar', align: 'right' as const, width: 90,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_auxiliar - b.comision_auxiliar },
        { title: 'Com.Neta', dataIndex: 'comision_neta', align: 'right' as const, width: 90,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_neta - b.comision_neta },
        { title: 'Costes', dataIndex: 'costes_op_contable', align: 'right' as const, width: 85,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => (a.costes_op_contable||0) - (b.costes_op_contable||0) },
        { title: 'EBITDA', dataIndex: 'ebitda_contable', align: 'right' as const, width: 90,
          render: (v: number) => <Text style={{ color: v >= 0 ? '#52c41a' : '#f5222d' }}>{fmt(v)}</Text>,
          sorter: (a: any, b: any) => (a.ebitda_contable||0) - (b.ebitda_contable||0) },
        { title: 'Margen%', dataIndex: 'margen_pct_contable', align: 'center' as const, width: 78,
          render: (v: number) => <Tag color={v >= 15 ? 'success' : v >= 5 ? 'warning' : 'error'}>{pct(v)}</Tag>,
          sorter: (a: any, b: any) => (a.margen_pct_contable||0) - (b.margen_pct_contable||0) },
      ],
    },
    {
      title: <span style={{ color: '#722ed1', fontWeight: 600 }}>Analítico (normalizado)</span>,
      children: [
        { title: 'Ces.Norm.', dataIndex: 'cesion_normalizada', align: 'right' as const, width: 95,
          render: (v: number) => <Text style={{ color: '#722ed1', fontWeight: 600 }}>{fmt(v || 0)}</Text>,
          sorter: (a: any, b: any) => (a.cesion_normalizada || 0) - (b.cesion_normalizada || 0) },
        { title: 'EBITDA Norm.', dataIndex: 'ebitda_normalizado', align: 'right' as const, width: 100,render: (v: number) => <Text style={{ color: (v ?? 0) >= 0 ? '#52c41a' : '#f5222d', fontWeight: 700 }}>{fmt(v || 0)}</Text>,
          sorter: (a: any, b: any) => (a.ebitda_normalizado ?? 0) - (b.ebitda_normalizado ?? 0) },
        { title: 'Mrg.Norm%', dataIndex: 'margen_pct_norm', align: 'center' as const, width: 88,
          defaultSortOrder: 'descend' as const,
          render: (v: number) => <Tag color={(v ?? 0) >= 15 ? 'success' : (v ?? 0) >= 5 ? 'warning' : 'error'} style={{ fontWeight: 700 }}>{pct(v ?? 0)}</Tag>,
          sorter: (a: any, b: any) => (a.margen_pct_norm ?? 0) - (b.margen_pct_norm ?? 0) },
      ],
    },
    colsPorPoliza,
  ]

  return (
    <div>
      <Card title="Ranking ramos — EBITDA Normalizado vs Contable (top 10)" size="small" style={{ marginBottom: 16 }}>
        <HRankChart data={top10ramo} nameKey="ramo" />
      </Card>
      <Table
        dataSource={ramosSorted}
        columns={colsD4}
        rowKey="ramo"
        size="small"
        pagination={false}
        scroll={{ x: 'max-content' }}
        bordered
        rowClassName={(r: any) => (r.ebitda_normalizado ?? r.ebitda_contable ?? r.ebitda) < 0 ? 'ant-table-row-danger' : ''}
        summary={pageData => {
          const rows = pageData as any[]
          const tBruta = rows.reduce((s, r) => s + (r.comision_bruta || 0), 0)
          const tCes   = rows.reduce((s, r) => s + (r.comision_auxiliar || 0), 0)
          const tCesN  = rows.reduce((s, r) => s + (r.cesion_normalizada || 0), 0)
          const tNeta  = rows.reduce((s, r) => s + (r.comision_neta || 0), 0)
          const tCost  = rows.reduce((s, r) => s + (r.costes_op_contable || 0), 0)
          const tEb    = rows.reduce((s, r) => s + (r.ebitda_contable ?? r.ebitda ?? 0), 0)
          const tEbN   = rows.reduce((s, r) => s + (r.ebitda_normalizado || 0), 0)
          const tRec   = rows.reduce((s, r) => s + (r.n_recibos || 0), 0)
          return (
            <Table.Summary.Row style={{ fontWeight: 600, background: '#fafafa' }}>
              <Table.Summary.Cell index={0}><Text strong>TOTAL</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={1} align="right">{fmtN(tRec)}</Table.Summary.Cell>
              <Table.Summary.Cell index={2} align="right">{fmt(tBruta)}</Table.Summary.Cell>
              <Table.Summary.Cell index={3} align="right"><Text type="secondary">100%</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={4} align="right">{fmt(tCes)}</Table.Summary.Cell>
              <Table.Summary.Cell index={5} align="right">{fmt(tNeta)}</Table.Summary.Cell>
              <Table.Summary.Cell index={6} align="right">{fmt(tCost)}</Table.Summary.Cell>
              <Table.Summary.Cell index={7} align="right"><Text style={{ color: tEb >= 0 ? '#52c41a' : '#f5222d' }}>{fmt(tEb)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={8} align="center">
                <Tag color={tBruta > 0 ? (tEb/tBruta*100 >= 15 ? 'success' : tEb/tBruta*100 >= 5 ? 'warning' : 'error') : 'default'}>{tBruta > 0 ? pct(tEb/tBruta*100) : '—'}</Tag>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={9} align="right"><Text style={{ color: '#722ed1', fontWeight: 600 }}>{fmt(tCesN)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={10} align="right"><Text style={{ color: tEbN >= 0 ? '#52c41a' : '#f5222d', fontWeight: 700 }}>{fmt(tEbN)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={11} align="center">
                <Tag color={tBruta > 0 ? (tEbN/tBruta*100 >= 15 ? 'success' : tEbN/tBruta*100 >= 5 ? 'warning' : 'error') : 'default'} style={{ fontWeight: 700 }}>{tBruta > 0 ? pct(tEbN/tBruta*100) : '—'}</Tag>
              </Table.Summary.Cell>
              {porPolizaSummary(rows, 12)}
            </Table.Summary.Row>
          )
        }}
      />
    </div>
  )
}

// ── Dashboard 5 Nueva Producción ──────────────────────────────────────────────
const PAYBACK_SECTOR_MIN = 12
const PAYBACK_SECTOR_MAX = 18

function CdrSegmento({ pl, titulo, color }: { pl: any; titulo: string; color: string }) {
  const ebitdaCont = pl.ebitda_contable ?? pl.ebitda ?? 0
  const ebitdaNorm = pl.ebitda_normalizado ?? 0
  const copCont    = pl.costes_op_contable ?? pl.costes_operativos ?? 0
  const copAnal    = pl.costes_operativos ?? 0
  const cesNorm    = pl.cesion_normalizada ?? 0
  const bruta      = pl.comision_bruta ?? 0

  const renderVal = (v: number | null, tipo: string, isNorm = false) => {
    if (v === null) return <Text style={{ color: '#bfbfbf', fontSize: 11 }}>—</Text>
    if (tipo === 'pct') return <Tag color={(v ?? 0) >= 15 ? 'success' : (v ?? 0) >= 5 ? 'warning' : 'error'} style={{ fontWeight: isNorm ? 700 : 400 }}>{pct(v ?? 0)}</Tag>
    const col = tipo === 'ebitda' ? ((v ?? 0) >= 0 ? '#52c41a' : '#f5222d') : tipo === 'cesion' && isNorm ? '#722ed1' : tipo === 'subtotal' ? '#262626' : '#262626'
    return <Text style={{ color: col, fontWeight: tipo === 'ebitda' || tipo === 'subtotal' ? 700 : isNorm && tipo === 'cesion' ? 600 : 400, fontSize: 13 }}>{fmt(v ?? 0)}</Text>
  }

  const rows = [
    { k: '1',  label: 'Comisión bruta',    cont: bruta,                               norm: bruta,                          tipo: 'bruta',    ttCont: `Ingresos brutos: ${fmt(bruta)}`, ttNorm: `Ingresos brutos: ${fmt(bruta)}` },
    { k: '2',  label: 'Cesión auxiliar',   cont: pl.comision_auxiliar ?? 0,           norm: cesNorm,                        tipo: 'cesion',   ttCont: `SUM(-importe) cuentas 623*: ${fmt(pl.comision_auxiliar ?? 0)}`, ttNorm: `Directa ${fmt(pl.cesion_directa ?? (cesNorm - (pl.cesion_estimada ?? 0)))} + Estimada ${fmt(pl.cesion_estimada ?? 0)} = ${fmt(cesNorm)}` },
    { k: '3',  label: 'Comisión neta',     cont: pl.comision_neta ?? 0,              norm: pl.comision_neta_norm ?? 0,     tipo: 'subtotal', ttCont: `Bruta ${fmt(bruta)} − Ces. ${fmt(pl.comision_auxiliar ?? 0)} = ${fmt(pl.comision_neta ?? 0)}`, ttNorm: `Bruta ${fmt(bruta)} − Ces.norm ${fmt(cesNorm)} = ${fmt(pl.comision_neta_norm ?? 0)}` },
    { k: '4',  label: 'Costes operativos', cont: copCont,                             norm: copAnal,                        tipo: 'coste',    ttCont: `COP analítico ${fmt(copAnal)} + Ajuste ${fmt(copCont - copAnal)} = ${fmt(copCont)}`, ttNorm: `COP analítico (pool ya reducido por ajuste): ${fmt(copAnal)}` },
    { k: '4t', label: 'Total gastos',      cont: (pl.comision_auxiliar ?? 0) + copCont, norm: cesNorm + copAnal,            tipo: 'subtotal', ttCont: `Ces. ${fmt(pl.comision_auxiliar ?? 0)} + COP ${fmt(copCont)} = ${fmt((pl.comision_auxiliar ?? 0) + copCont)}`, ttNorm: `Ces.norm ${fmt(cesNorm)} + COP ${fmt(copAnal)} = ${fmt(cesNorm + copAnal)}` },
    { k: '5',  label: 'EBITDA',            cont: ebitdaCont,                          norm: ebitdaNorm,                     tipo: 'ebitda',   ttCont: `Bruta − Ces − COP.cont − Capt ${fmt(pl.costes_captacion ?? 0)} − SinMap ${fmt(pl.sin_mapear ?? 0)} = ${fmt(ebitdaCont)}`, ttNorm: `Bruta − Ces.norm − COP.anal − Capt − SinMap = ${fmt(ebitdaNorm)}` },
    { k: '6',  label: '% Margen EBITDA',   cont: pl.margen_pct_contable ?? pl.margen_pct ?? 0, norm: pl.margen_pct_norm ?? 0, tipo: 'pct', ttCont: `EBITDA cont. ${fmt(ebitdaCont)} / Bruta ${fmt(bruta)} = ${(pl.margen_pct_contable ?? pl.margen_pct ?? 0).toFixed(2).replace('.', ',')}%`, ttNorm: `EBITDA norm. ${fmt(ebitdaNorm)} / Bruta ${fmt(bruta)} = ${(pl.margen_pct_norm ?? 0).toFixed(2).replace('.', ',')}%` },
  ]

  return (
    <Card title={titulo} size="small" style={{ borderTop: `3px solid ${color}` }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #f0f0f0' }}>
            <th style={{ textAlign: 'left', padding: '3px 6px', color: '#8c8c8c', fontWeight: 500, fontSize: 11, width: '36%' }}>Concepto</th>
            <th style={{ textAlign: 'right', padding: '3px 6px', color: '#1890ff', fontWeight: 600, fontSize: 11, width: '32%' }}>Contable</th>
            <th style={{ textAlign: 'right', padding: '3px 6px', color: '#722ed1', fontWeight: 600, fontSize: 11, width: '32%' }}>Normalizado</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.k} style={{ borderBottom: '1px solid #fafafa', background: row.tipo === 'ebitda' ? '#f6ffed' : row.tipo === 'subtotal' ? '#fafafa' : 'transparent' }}>
              <td style={{ padding: '4px 6px', fontWeight: row.tipo === 'ebitda' || row.tipo === 'subtotal' ? 600 : 400 }}>{row.label}</td>
              <td style={{ padding: '4px 6px', textAlign: 'right' }}>
                <Tooltip title={row.ttCont} placement="left">{renderVal(row.cont, row.tipo, false)}</Tooltip>
              </td>
              <td style={{ padding: '4px 6px', textAlign: 'right' }}>
                <Tooltip title={row.ttNorm} placement="right">{renderVal(row.norm, row.tipo, true)}</Tooltip>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function BridgeSegmento({ pl, titulo }: { pl: any; titulo: string }) {
  const ebitdaNorm = pl.ebitda_normalizado ?? pl.ebitda ?? 0
  const cesNorm    = pl.cesion_normalizada ?? pl.comision_auxiliar ?? 0
  const netaNorm   = pl.comision_neta_norm ?? pl.comision_neta ?? 0
  const bridge = [
    { name: 'Com. Brutas',  value: pl.comision_bruta    ?? 0,  fill: '#1890ff' },
    { name: 'Ces. Norm.',   value: -(cesNorm),                  fill: '#f5222d' },
    { name: 'Com. Neta',    value: netaNorm,                    fill: '#13c2c2' },
    { name: 'COP analít.',  value: -(pl.costes_operativos ?? 0), fill: '#fa8c16' },
    ...(pl.costes_captacion > 0 ? [{ name: 'Captación', value: -(pl.costes_captacion ?? 0), fill: '#722ed1' }] : []),
    { name: 'EBITDA',       value: ebitdaNorm,                  fill: ebitdaNorm >= 0 ? '#52c41a' : '#f5222d' },
  ]
  return (
    <Card title={titulo} size="small" style={{ height: 300 }}>
      <ResponsiveContainer width="100%" height={248}>
        <BarChart data={bridge} margin={{ top: 4, right: 16, bottom: 4, left: 8 }} barCategoryGap="28%">
          <XAxis dataKey="name" tick={{ fontSize: 10 }} />
          <YAxis tickFormatter={tickFmtAuto} tick={{ fontSize: 10 }} width={48} />
          <CartesianGrid strokeDasharray="2 4" vertical={false} stroke="#e8e8e8" />
          <ChartTooltip formatter={(v: any) => [fmt(Number(v)), 'Importe']} />
          <ReferenceLine y={0} stroke="#595959" strokeWidth={1.5} />
          <Bar dataKey="value" name="Importe" radius={[3, 3, 0, 0]}>
            {bridge.map((e, i) => <Cell key={i} fill={e.fill} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  )
}

function D5NuevaProduccion({ ejercicio, tasaCesion }: { ejercicio: number; tasaCesion: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analitico-d5', ejercicio, tasaCesion],
    queryFn: () => analiticoApi.dashNuevaProduccion(ejercicio, tasaCesion / 100).then(r => r.data),
    enabled: !!ejercicio,
  })

  if (isLoading) return <Spin />
  if (!data) return <Alert type="info" message="Sin datos. Ejecuta el recálculo primero." />

  const np   = data.nueva_produccion || {}
  const cart = data.cartera          || {}

  const npEbitdaNorm   = np.ebitda_normalizado   ?? np.ebitda   ?? 0
  const cartEbitdaNorm = cart.ebitda_normalizado  ?? cart.ebitda ?? 0
  const npMrgNorm      = np.margen_pct_norm       ?? 0
  const cartMrgNorm    = cart.margen_pct_norm     ?? 0
  const npCesNormPct   = np.comision_bruta   > 0 ? +((np.cesion_normalizada   ?? 0) / np.comision_bruta   * 100).toFixed(2) : 0
  const cartCesNormPct = cart.comision_bruta > 0 ? +((cart.cesion_normalizada ?? 0) / cart.comision_bruta * 100).toFixed(2) : 0

  const costeCaptacion = data.coste_captacion || 0
  const paybackMeses   = npEbitdaNorm > 0 && costeCaptacion > 0
    ? Math.round((costeCaptacion / npEbitdaNorm) * 12)
    : null

  return (
    <div>
      {/* CdR NP + Cartera */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col span={12}><CdrSegmento pl={np}   titulo="Nueva Producción" color="#1890ff" /></Col>
        <Col span={12}><CdrSegmento pl={cart} titulo="Cartera"          color="#52c41a" /></Col>
      </Row>

      {/* Benchmarks (todos sobre valores normalizados) */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col span={6}>
          <Tooltip title={`Ces.norm ${fmt(np.cesion_normalizada ?? 0)} / Bruta ${fmt(np.comision_bruta ?? 0)} = ${npCesNormPct.toFixed(2).replace('.', ',')}%`} placement="top">
            <div><BenchmarkCard label="Ratio cesión NP (norm.)" sub="Ces. normalizada NP / Ingresos NP"
              value={npCesNormPct}
              colorFn={v => v <= 40 ? '#52c41a' : v <= 50 ? '#faad14' : '#f5222d'}
              rangos={['Óptimo < 40%', 'Bueno 40–50%', 'Alerta > 50%']}
              fuente="INESE 2025-2026" /></div>
          </Tooltip>
        </Col>
        <Col span={6}>
          <Tooltip title={`EBITDA norm NP ${fmt(npEbitdaNorm)} / Bruta ${fmt(np.comision_bruta ?? 0)} = ${npMrgNorm.toFixed(2).replace('.', ',')}%`} placement="top">
            <div><BenchmarkCard label="Margen EBITDA NP (norm.)" sub="EBITDA norm. NP / Ingresos NP"
              value={npMrgNorm}
              colorFn={v => v >= 15 ? '#52c41a' : v >= 5 ? '#faad14' : '#f5222d'}
              rangos={['Óptimo > 15%', 'Bueno 5–15%', 'Alerta < 5%']}
              fuente="INESE 2025-2026" /></div>
          </Tooltip>
        </Col>
        <Col span={6}>
          <Tooltip title={`Ces.norm ${fmt(cart.cesion_normalizada ?? 0)} / Bruta ${fmt(cart.comision_bruta ?? 0)} = ${cartCesNormPct.toFixed(2).replace('.', ',')}%`} placement="top">
            <div><BenchmarkCard label="Ratio cesión Cartera (norm.)" sub="Ces. normalizada Cartera / Ingresos Cartera"
              value={cartCesNormPct}
              colorFn={v => v <= 30 ? '#52c41a' : v <= 40 ? '#faad14' : '#f5222d'}
              rangos={['Óptimo < 30%', 'Bueno 30–40%', 'Alerta > 40%']}
              fuente="INESE 2025-2026" /></div>
          </Tooltip>
        </Col>
        <Col span={6}>
          <Tooltip title={`EBITDA norm Cartera ${fmt(cartEbitdaNorm)} / Bruta ${fmt(cart.comision_bruta ?? 0)} = ${cartMrgNorm.toFixed(2).replace('.', ',')}%`} placement="top">
            <div><BenchmarkCard label="Margen EBITDA Cartera (norm.)" sub="EBITDA norm. Cartera / Ingresos Cartera"
              value={cartMrgNorm}
              colorFn={v => v >= 20 ? '#52c41a' : v >= 10 ? '#faad14' : '#f5222d'}
              rangos={['Óptimo > 20%', 'Bueno 10–20%', 'Alerta < 10%']}
              fuente="INESE 2025-2026" /></div>
          </Tooltip>
        </Col>
      </Row>

      {/* Payback */}
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
        <Col span={24}>
          <Tooltip title={`Coste captación ${fmt(costeCaptacion)} / EBITDA norm NP ${fmt(npEbitdaNorm)} × 12 = ${paybackMeses ?? '—'} meses`} placement="top">
            <Card size="small" style={{ background: paybackMeses !== null ? '#f6ffed' : '#fff7e6', borderColor: paybackMeses !== null ? '#b7eb8f' : '#ffd591' }}>
              <Space size={24} align="center">
                <div>
                  <Text strong>Payback captación (normalizado)</Text>
                  <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>Coste captación / EBITDA norm NP × 12</Text>
                </div>
                {paybackMeses !== null ? (
                  <Space align="center" size={12}>
                    <Text style={{ fontSize: 26, fontWeight: 700, color: paybackMeses <= PAYBACK_SECTOR_MAX ? '#52c41a' : '#f5222d' }}>
                      {paybackMeses} meses
                    </Text>
                    <Tag color={paybackMeses <= PAYBACK_SECTOR_MAX ? 'success' : 'error'}>{paybackMeses <= PAYBACK_SECTOR_MAX ? 'Óptimo' : 'Largo'}</Tag>
                    <Text type="secondary" style={{ fontSize: 11 }}>Sector: {PAYBACK_SECTOR_MIN}–{PAYBACK_SECTOR_MAX} m. · Recoletos 2026</Text>
                  </Space>
                ) : (
                  <Text type="warning" strong>No calculable — EBITDA NP normalizado negativo</Text>
                )}
              </Space>
            </Card>
          </Tooltip>
        </Col>
      </Row>

      {/* Bridges NP y Cartera */}
      <Row gutter={[12, 12]}>
        <Col span={12}><BridgeSegmento pl={np}   titulo="Bridge P&L normalizado — Nueva Producción" /></Col>
        <Col span={12}><BridgeSegmento pl={cart} titulo="Bridge P&L normalizado — Cartera" /></Col>
      </Row>
    </div>
  )
}

// ── Dashboard Subramo ────────────────────────────────────────────────────────
const RAMOS_CON_SUBRAMO = ['Multirriesgos', 'Autos', 'Asistencia Sanitaria', 'Vida', 'Decesos']

function DSubramo({ ejercicio, tasaCesion }: { ejercicio: number; tasaCesion: number }) {
  const [ramoFiltro, setRamoFiltro] = useState<string>('')

  const { data, isLoading } = useQuery({
    queryKey: ['analitico-subramo', ejercicio, tasaCesion, ramoFiltro],
    queryFn: () => analiticoApi.dashSubramo(ejercicio, tasaCesion / 100, ramoFiltro || undefined).then(r => r.data),
    enabled: !!ejercicio,
  })

  if (isLoading) return <Spin />
  if (!data || data.sin_datos) return <Alert type="info" message="Sin datos. Ejecuta el recálculo primero." />

  const subramos: any[] = data.subramos || []
  const totalBrutaSR = subramos.reduce((s, r) => s + (r.comision_bruta || 0), 0)
  const subSorted = [...subramos].sort((a, b) => (b.margen_pct_norm ?? b.margen_pct ?? 0) - (a.margen_pct_norm ?? a.margen_pct ?? 0))
  const verTodos = !ramoFiltro

  const colsSR = [
    ...(verTodos ? [{ title: 'Ramo', dataIndex: 'ramo', width: 140, fixed: 'left' as const,
      sorter: (a: any, b: any) => (a.ramo || '').localeCompare(b.ramo || '') }] : []),
    { title: 'Subramo', dataIndex: 'subramo', width: 160, fixed: 'left' as const,
      sorter: (a: any, b: any) => (a.subramo || '').localeCompare(b.subramo || '') },
    { title: 'Recibos', dataIndex: 'n_recibos', width: 68, align: 'right' as const,
      render: (v: number) => fmtN(v), sorter: (a: any, b: any) => a.n_recibos - b.n_recibos },
    {
      title: <span style={{ color: '#1890ff', fontWeight: 600 }}>Real (contable)</span>,
      children: [
        { title: 'Ingresos', dataIndex: 'comision_bruta', align: 'right' as const, width: 90,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_bruta - b.comision_bruta },
        { title: 'Peso%', key: 'pesoSR', align: 'right' as const, width: 60,
          render: (_: any, row: any) => <Text type="secondary">{totalBrutaSR > 0 ? (row.comision_bruta / totalBrutaSR * 100).toFixed(2).replace('.', ',') + '%' : '—'}</Text> },
        { title: 'Cesión', dataIndex: 'comision_auxiliar', align: 'right' as const, width: 88,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_auxiliar - b.comision_auxiliar },
        { title: 'Com.Neta', dataIndex: 'comision_neta', align: 'right' as const, width: 88,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => a.comision_neta - b.comision_neta },
        { title: 'Costes', dataIndex: 'costes_op_contable', align: 'right' as const, width: 85,
          render: (v: number) => fmt(v), sorter: (a: any, b: any) => (a.costes_op_contable||0) - (b.costes_op_contable||0) },
        { title: 'EBITDA', dataIndex: 'ebitda_contable', align: 'right' as const, width: 88,
          render: (v: number) => <Text style={{ color: v >= 0 ? '#52c41a' : '#f5222d' }}>{fmt(v)}</Text>,
          sorter: (a: any, b: any) => (a.ebitda_contable||0) - (b.ebitda_contable||0) },
        { title: 'Margen%', dataIndex: 'margen_pct_contable', align: 'center' as const, width: 76,
          render: (v: number) => <Tag color={v >= 15 ? 'success' : v >= 5 ? 'warning' : 'error'}>{pct(v)}</Tag>,
          sorter: (a: any, b: any) => (a.margen_pct_contable||0) - (b.margen_pct_contable||0) },
      ],
    },
    {
      title: <span style={{ color: '#722ed1', fontWeight: 600 }}>Analítico (normalizado)</span>,
      children: [
        { title: 'Ces.Norm.', dataIndex: 'cesion_normalizada', align: 'right' as const, width: 90,
          render: (v: number) => <Text style={{ color: '#722ed1', fontWeight: 600 }}>{fmt(v || 0)}</Text>,
          sorter: (a: any, b: any) => (a.cesion_normalizada || 0) - (b.cesion_normalizada || 0) },
        { title: 'EBITDA Norm.', dataIndex: 'ebitda_normalizado', align: 'right' as const, width: 100,render: (v: number) => <Text style={{ color: (v ?? 0) >= 0 ? '#52c41a' : '#f5222d', fontWeight: 700 }}>{fmt(v || 0)}</Text>,
          sorter: (a: any, b: any) => (a.ebitda_normalizado ?? 0) - (b.ebitda_normalizado ?? 0) },
        { title: 'Mrg.Norm%', dataIndex: 'margen_pct_norm', align: 'center' as const, width: 88,
          defaultSortOrder: 'descend' as const,
          render: (v: number) => <Tag color={(v ?? 0) >= 15 ? 'success' : (v ?? 0) >= 5 ? 'warning' : 'error'} style={{ fontWeight: 700 }}>{pct(v ?? 0)}</Tag>,
          sorter: (a: any, b: any) => (a.margen_pct_norm ?? 0) - (b.margen_pct_norm ?? 0) },
      ],
    },
  ]

  const chartDataSR = [...subramos]
    .sort((a, b) => (b.margen_pct_norm ?? b.margen_pct ?? 0) - (a.margen_pct_norm ?? a.margen_pct ?? 0))
    .slice(0, 20)
    .map((d: any) => ({ ...d, _label: verTodos ? `${d.ramo} · ${d.subramo}` : d.subramo }))

  return (
    <div>
      <Row align="middle" gutter={12} style={{ marginBottom: 12 }}>
        <Col>
          <Text strong>Ramo:</Text>
        </Col>
        <Col>
          <Select
            value={ramoFiltro}
            onChange={setRamoFiltro}
            style={{ width: 220 }}
            options={[
              { value: '', label: 'Todos los ramos' },
              ...RAMOS_CON_SUBRAMO.map(r => ({ value: r, label: r })),
            ]}
          />
        </Col>
      </Row>

      <Alert type="info" showIcon style={{ marginBottom: 8, padding: "4px 12px", fontSize: 12 }} message="(Sin subramo): recibos cuya linea de negocio no tiene subcategoria asignada en BD. Es negocio real, no un error de datos." />
      <Card title={verTodos ? 'Todos los ramos — EBITDA Normalizado vs Contable (top 20)' : `Subramos de ${ramoFiltro} — EBITDA Normalizado vs Contable`} size="small" style={{ marginBottom: 12 }}>
        <HRankChart data={chartDataSR} nameKey="_label" />
      </Card>

      <Table
        dataSource={subSorted}
        columns={colsSR}
        rowKey={(r: any) => (r.ramo || '') + '::' + (r.subramo || '')}
        size="small"
        pagination={false}
        scroll={{ x: 'max-content' }}
        bordered
        rowClassName={(r: any) => (r.ebitda_normalizado ?? r.ebitda_contable ?? r.ebitda) < 0 ? 'ant-table-row-danger' : ''}
        summary={pageData => {
          const tot  = pageData as any[]
          const tRec = tot.reduce((s, r) => s + (r.n_recibos || 0), 0)
          // Cuando verTodos, usamos los totales D1 del backend (incluyen filas ramo=NULL)
          const T = (verTodos && data?.totales) ? data.totales : null
          const tIng  = T ? T.comision_bruta     : tot.reduce((s, r) => s + (r.comision_bruta || 0), 0)
          const tCes  = T ? T.comision_auxiliar   : tot.reduce((s, r) => s + (r.comision_auxiliar || 0), 0)
          const tNeta = T ? (tIng - tCes)         : tot.reduce((s, r) => s + (r.comision_neta || 0), 0)
          const tCost = T ? T.costes_op_contable  : tot.reduce((s, r) => s + (r.costes_op_contable || 0), 0)
          const tEb   = T ? T.ebitda_contable     : tot.reduce((s, r) => s + (r.ebitda_contable ?? r.ebitda ?? 0), 0)
          const tMrgCont = T ? T.margen_pct_contable : (tIng > 0 ? tEb / tIng * 100 : 0)
          const tCesN = T ? T.cesion_normalizada  : tot.reduce((s, r) => s + (r.cesion_normalizada || 0), 0)
          const tEbN  = T ? T.ebitda_normalizado  : tot.reduce((s, r) => s + (r.ebitda_normalizado || 0), 0)
          const tMrgN = T ? T.margen_pct_norm     : (tIng > 0 ? tEbN / tIng * 100 : 0)
          const o = verTodos ? 1 : 0
          return (
            <Table.Summary.Row style={{ fontWeight: 600, background: '#fafafa' }}>
              <Table.Summary.Cell index={0}><Text strong>TOTAL</Text></Table.Summary.Cell>
              {verTodos && <Table.Summary.Cell index={1} />}
              <Table.Summary.Cell index={1+o} align="right">{fmtN(tRec)}</Table.Summary.Cell>
              <Table.Summary.Cell index={2+o} align="right">{fmt(tIng)}</Table.Summary.Cell>
              <Table.Summary.Cell index={3+o} align="right"><Text type="secondary">100%</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={4+o} align="right">{fmt(tCes)}</Table.Summary.Cell>
              <Table.Summary.Cell index={5+o} align="right">{fmt(tNeta)}</Table.Summary.Cell>
              <Table.Summary.Cell index={6+o} align="right">{fmt(tCost)}</Table.Summary.Cell>
              <Table.Summary.Cell index={7+o} align="right"><Text style={{ color: tEb >= 0 ? '#52c41a' : '#f5222d' }}>{fmt(tEb)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={8+o} align="center">
                <Tag color={tMrgCont >= 15 ? 'success' : tMrgCont >= 5 ? 'warning' : 'error'}>{pct(tMrgCont)}</Tag>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={9+o} align="right"><Text style={{ color: '#722ed1', fontWeight: 600 }}>{fmt(tCesN)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={10+o} align="right"><Text style={{ color: tEbN >= 0 ? '#52c41a' : '#f5222d', fontWeight: 700 }}>{fmt(tEbN)}</Text></Table.Summary.Cell>
              <Table.Summary.Cell index={11+o} align="center">
                <Tag color={tMrgN >= 15 ? 'success' : tMrgN >= 5 ? 'warning' : 'error'} style={{ fontWeight: 700 }}>{pct(tMrgN)}</Tag>
              </Table.Summary.Cell>
            </Table.Summary.Row>
          )
        }}
      />
    </div>
  )
}


// ── Dashboard 7 Costes ───────────────────────────────────────────────────────
const COST_TARGETS: Record<string, { target: number; fuente: string }> = {
  'Personal':               { target: 22, fuente: 'INESE 2025' },
  'Cesión auxiliar':        { target: 16, fuente: 'INESE 2025' },
  'Tecnología':             { target: 4,  fuente: 'Recoletos 2025' },
  'Servicios profesionales':{ target: 3,  fuente: 'Recoletos 2025' },
  'Alquiler':               { target: 3,  fuente: 'INESE 2025' },
  'Marketing':              { target: 2,  fuente: 'Sector medio' },
  'Financiero':             { target: 2,  fuente: 'Sector medio' },
  'Bancos':                 { target: 1,  fuente: 'Sector medio' },
  'Comunicaciones':         { target: 1,  fuente: 'Sector medio' },
  'Viajes':                 { target: 1,  fuente: 'Sector medio' },
  'Impuestos':              { target: 1,  fuente: 'Sector medio' },
  'Suministros':            { target: 1,  fuente: 'Sector medio' },
}

function D7Costes({ ejercicio, tasaCesion }: { ejercicio: number; tasaCesion: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['analitico-d7', ejercicio, tasaCesion],
    queryFn: () => analiticoApi.dashCostes(ejercicio, tasaCesion / 100).then(r => r.data),
    enabled: !!ejercicio,
  })

  if (isLoading) return <Spin />
  if (!data || data.sin_datos) return <Alert type="info" message="Sin datos. Ejecuta el recálculo primero." />

  const r       = data.resumen || {}
  const detalle: any[] = data.detalle || []

  const bridgeData = [
    ...detalle.map((d: any) => ({
      ...d,
      importe:     d.importe_norm ?? d.importe,
      pct_ingreso: d.pct_ingreso_norm ?? d.pct_ingreso,
    })),
    {
      naturaleza: 'TOTAL',
      importe:     r.total_costes_norm ?? r.total_costes,
      pct_ingreso: r.ratio_total_pct_norm ?? r.ratio_total_pct,
    },
  ]

  const cols = [
    { title: 'Naturaleza', dataIndex: 'naturaleza', width: 200,
      render: (v: string) => <Text strong style={{ color: NAT_COLOR[v] ?? '#595959' }}>{v}</Text> },
    { title: 'Importe (norm.)', key: 'importe_norm', align: 'right' as const, width: 130,
      render: (_: any, row: any) => fmt(row.importe_norm ?? row.importe) },
    { title: '% s/ingresos (norm.)', key: 'pct_ingreso_norm', align: 'right' as const, width: 140,
      render: (_: any, row: any) => {
        const v = row.pct_ingreso_norm ?? row.pct_ingreso ?? 0
        const t = COST_TARGETS[row.naturaleza]
        const color = !t ? '#333' : v <= t.target ? '#52c41a' : v <= t.target * 1.2 ? '#faad14' : '#f5222d'
        return <Text style={{ color, fontWeight: 600 }}>{v.toFixed(2).replace('.', ',')}%</Text>
      } },
    { title: '% s/costes (norm.)', key: 'pct_norm', align: 'right' as const, width: 130,
      render: (_: any, row: any) => `${(row.pct_norm ?? row.pct ?? 0).toFixed(2).replace('.', ',')}%` },
    { title: 'Gap vs mercado (pp)', key: 'gap', align: 'center' as const, width: 140,
      render: (_: any, row: any) => {
        const t = COST_TARGETS[row.naturaleza]
        const v = row.pct_ingreso_norm ?? row.pct_ingreso
        if (!t || v == null) return null
        const gap = parseFloat((v - t.target).toFixed(2))
        if (gap <= 0) return <Tag color="success">-{Math.abs(gap).toFixed(2).replace('.', ',')} pp</Tag>
        return <Tag color={gap > 5 ? 'error' : 'warning'}>+{gap.toFixed(2).replace('.', ',')} pp</Tag>
      } },
    { title: 'Referencia', key: 'fuente', width: 130,
      render: (_: any, row: any) => {
        const t = COST_TARGETS[row.naturaleza]
        return t ? <><Text type="secondary" style={{ fontSize: 10 }}>{t.fuente}</Text><Text type="secondary" style={{ fontSize: 10, display: 'block' }}>Target: {t.target}%</Text></> : null
      } },
  ]

  return (
    <div>
      <Row gutter={[12, 8]} style={{ marginBottom: 12 }}>
        <Col span={6}>
          <KpiCard
            title="Total Gastos Norm."
            value={r.total_costes_norm ?? 0}
            tooltip={`Ces.norm ${fmt(r.cesion_normalizada ?? 0)} + COP analítico ${fmt(r.costes_operativos ?? 0)} = ${fmt(r.total_costes_norm ?? 0)}`}
          />
        </Col>
        <Col span={6}>
          <Tooltip title={`Total gastos norm. ${fmt(r.total_costes_norm ?? 0)} / Ingresos ${fmt(r.comision_bruta ?? 0)} = ${(r.ratio_total_pct_norm ?? 0).toFixed(2).replace('.', ',')}%`} placement="bottom">
            <Card size="small" style={{ height: '100%' }}>
              <Statistic
                title="% Gastos / Ingresos (norm.)"
                value={r.ratio_total_pct_norm ?? 0}
                precision={2} decimalSeparator="," groupSeparator="."
                suffix="%"
                valueStyle={{ color: (r.ratio_total_pct_norm ?? 0) <= 80 ? '#52c41a' : '#f5222d', fontSize: 20 }}
              />
            </Card>
          </Tooltip>
        </Col>
        <Col span={6}>
          <Tooltip title={`Total gastos norm. ${fmt(r.total_costes_norm ?? 0)} / ${(r.n_recibos ?? 0).toLocaleString()} recibos = ${fmt(r.coste_por_recibo_norm ?? 0)}/recibo`} placement="bottom">
            <Card size="small" style={{ height: '100%' }}>
              <Statistic
                title="Coste / Recibo (norm.)"
                value={r.coste_por_recibo_norm ?? 0}
                precision={2} decimalSeparator="," groupSeparator="."
                suffix="€"
                valueStyle={{ fontSize: 20 }}
              />
            </Card>
          </Tooltip>
        </Col>
        <Col span={6}>
          <Tooltip title={`COP analítico ${fmt(r.costes_operativos ?? 0)} / Ingresos ${fmt(r.comision_bruta ?? 0)} = ${(r.ratio_costes_pct_norm ?? 0).toFixed(2).replace('.', ',')}%`} placement="bottom">
            <Card size="small" style={{ height: '100%' }}>
              <Statistic
                title="% COP / Ingresos (norm.)"
                value={r.ratio_costes_pct_norm ?? 0}
                precision={2} decimalSeparator="," groupSeparator="."
                suffix="%"
                valueStyle={{ color: (r.ratio_costes_pct_norm ?? 0) <= 30 ? '#52c41a' : (r.ratio_costes_pct_norm ?? 0) <= 50 ? '#faad14' : '#f5222d', fontSize: 20 }}
              />
            </Card>
          </Tooltip>
        </Col>
      </Row>

      <Card title="Desglose de costes normalizados — % sobre ingresos" size="small" style={{ marginBottom: 12 }}>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={bridgeData} margin={{ top: 8, right: 16, bottom: 60, left: 8 }} barCategoryGap="35%">
            <CartesianGrid strokeDasharray="2 4" vertical={false} stroke="#e8e8e8" />
            <XAxis dataKey="naturaleza" tick={{ fontSize: 10 }} interval={0} angle={-35} textAnchor="end" />
            <YAxis tickFormatter={tickFmtAuto} tick={{ fontSize: 10 }} width={52} />
            <ChartTooltip formatter={(v: any, _: string, props: any) => {
              const row = props?.payload || {}
              return [`${fmt(Number(v))}  (${(row.pct_ingreso ?? 0).toFixed(2).replace('.', ',')}% / ingresos)`, 'Importe norm.']
            }} />
            <Bar dataKey="importe" name="importe" radius={[3, 3, 0, 0]}>
              {bridgeData.map((d: any, i: number) => (
                <Cell key={i} fill={d.naturaleza === 'TOTAL' ? '#262626' : (NAT_COLOR[d.naturaleza] ?? COLORS[i % COLORS.length])} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <Table
        dataSource={detalle}
        columns={cols}
        rowKey="naturaleza"
        size="small"
        pagination={false}
        rowClassName={(row: any) => {
          const t = COST_TARGETS[row.naturaleza]
          const v = row.pct_ingreso_norm ?? row.pct_ingreso
          return t && v > t.target * 1.2 ? 'ant-table-row-danger' : ''
        }}
      />
      <div style={{ marginTop: 8, fontSize: 10, color: '#bfbfbf' }}>
        Valores normalizados: cesión al {pct(tasaCesion)} estimada + cesión real 623*. Gap positivo = por encima del target sectorial.
      </div>
    </div>
  )
}


// ── Página principal ──────────────────────────────────────────────────────────
export default function DashboardsAnalitico() {
  const qc = useQueryClient()
  const [ejercicio, setEjercicio] = useState<number | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState<any>(null)
  // Tasa de cesión estimada: por defecto la REAL del ejercicio; el selector permite
  // simular otra (tasaManual) y se vuelve a la real al cambiar de ejercicio.
  const [tasaManual, setTasaManual] = useState<number | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const { data: ejercicios = [] } = useQuery({
    queryKey: ['analitico-ejercicios'],
    queryFn: () => analiticoApi.getEjercicios().then(r => r.data),
  })

  const { data: tasaReal } = useQuery({
    queryKey: ['analitico-tasa-real', ejercicio],
    queryFn: () => analiticoApi.getTasaCesionReal(ejercicio!).then(r => r.data),
    enabled: !!ejercicio,
  })
  useEffect(() => { setTasaManual(null) }, [ejercicio])
  const tasaCesion: number | null = tasaManual ?? (tasaReal?.tasa_pct ?? null)

  useEffect(() => {
    if (ejercicios.length > 0 && !ejercicio) setEjercicio(ejercicios[0])
  }, [ejercicios, ejercicio])

  // Polling del estado de la tarea
  useEffect(() => {
    if (!taskId) return
    pollRef.current = setInterval(async () => {
      try {
        const res = await analiticoApi.recalcularEstado(taskId)
        const s = res.data
        setTaskStatus(s)
        if (s.done) {
          clearInterval(pollRef.current!)
          pollRef.current = null
          if (s.error) {
            message.error(`Error: ${s.error}`, 8)
          } else {
            message.success(s.mensaje)
            ;['d1','d2','d3','d4','d5','d7'].forEach(k =>
              qc.invalidateQueries({ queryKey: [`analitico-${k}`, ejercicio] })
            )
            qc.invalidateQueries({ queryKey: ['analitico-conciliacion', ejercicio] })
            qc.invalidateQueries({ queryKey: ['analitico-subramo', ejercicio] })
          }
          setTimeout(() => { setTaskId(null); setTaskStatus(null) }, 3000)
        }
      } catch {}
    }, 800)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [taskId, ejercicio, qc])

  const recalcular = useMutation({
    mutationFn: () => analiticoApi.recalcular(ejercicio!),
    onSuccess: (res) => {
      setTaskId(res.data.task_id)
      setTaskStatus({ step: 0, total: 6, pct: 0, mensaje: 'Iniciando…', done: false })
    },
    onError: (e: any) => message.error(apiError(e, 'Error al lanzar el recálculo')),
  })

  const calculando = !!taskId && !taskStatus?.done

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>Modelo Analítico de Rentabilidad</Title>
        </Col>
        <Col>
          <Space>
            <Text>Ejercicio:</Text>
            <Select
              value={ejercicio}
              onChange={setEjercicio}
              style={{ width: 100 }}
              options={ejercicios.map((e: number) => ({ value: e, label: String(e) }))}
              placeholder="Ejercicio"
              disabled={calculando}
            />
            <Divider type="vertical" />
            <Tooltip title={tasaReal
              ? `Tasa real ${ejercicio}: ${pct(tasaReal.tasa_pct)} (cesión ${fmt(tasaReal.cesion_recibos)} / comisión ${fmt(tasaReal.ingreso_recibos)} de ${fmtN(tasaReal.n_recibos)} recibos con auxiliar y cesión 623). Cada auxiliar se estima con SU tasa real; si no tiene cesión contabilizada, con su % del catálogo de Administración → Auxiliares. Esta tasa solo se aplica a los que no están en ninguno de los dos.`
              : 'Tasa de cesión estimada'}>
              <Text style={{ fontSize: 12 }}>Cesión est.:</Text>
            </Tooltip>
            <InputNumber
              min={0} max={100} step={0.01} precision={2}
              value={tasaCesion ?? undefined}
              onChange={v => setTasaManual(v ?? null)}
              formatter={v => `${String(v).replace('.', ',')}%`}
              parser={v => Number(String(v).replace('%', '').replace(',', '.'))}
              style={{ width: 84 }}
              size="small"
              disabled={calculando}
            />
            {tasaManual != null && tasaReal && (
              <Button size="small" type="link" onClick={() => setTasaManual(null)} style={{ padding: 0 }}>
                Usar real ({pct(tasaReal.tasa_pct)})
              </Button>
            )}
            <Button
              icon={<SyncOutlined />}
              onClick={() => {
                ;['d1','d2','d3','d4','d5','d7'].forEach(k =>
                  qc.invalidateQueries({ queryKey: [`analitico-${k}`, ejercicio] })
                )
                qc.invalidateQueries({ queryKey: ['analitico-conciliacion', ejercicio] })
                qc.invalidateQueries({ queryKey: ['analitico-subramo', ejercicio] })
                message.success('Datos refrescados')
              }}
              disabled={!ejercicio || calculando}
            >
              Refrescar todo
            </Button>
            <Button
              type="primary"
              icon={<SyncOutlined spin={calculando} />}
              loading={recalcular.isPending}
              onClick={() => recalcular.mutate()}
              disabled={!ejercicio || calculando}
            >
              {calculando ? 'Calculando…' : 'Recalcular modelo'}
            </Button>
          </Space>
        </Col>
      </Row>

      {/* Barra de progreso */}
      {taskStatus && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Space style={{ width: '100%' }} direction="vertical" size={4}>
            <Row justify="space-between">
              <Text strong>
                {taskStatus.done && !taskStatus.error && <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 6 }} />}
                {taskStatus.error && <CloseCircleOutlined style={{ color: '#f5222d', marginRight: 6 }} />}
                {taskStatus.mensaje}
              </Text>
              <Text type="secondary">Paso {taskStatus.step}/{taskStatus.total}</Text>
            </Row>
            <Progress
              percent={taskStatus.pct}
              status={taskStatus.error ? 'exception' : taskStatus.done ? 'success' : 'active'}
              strokeColor={taskStatus.done && !taskStatus.error ? '#52c41a' : undefined}
            />
          </Space>
        </Card>
      )}

      {!ejercicio ? (
        <Alert type="warning" message="Selecciona un ejercicio y pulsa 'Recalcular modelo' para generar los datos analíticos." />
      ) : tasaCesion == null ? (
        <Spin style={{ display: 'block', margin: '40px auto' }} />
      ) : (
        <Tabs
          type="card"
          items={[
            { key: 'd1', label: 'Ejecutivo',     children: <D1Ejecutivo ejercicio={ejercicio} tasaCesion={tasaCesion} /> },
            { key: 'd2', label: 'Compañía',      children: <D2Compania  ejercicio={ejercicio} tasaCesion={tasaCesion} /> },
            { key: 'd3', label: 'Auxiliar',      children: <D3Auxiliar  ejercicio={ejercicio} tasaCesion={tasaCesion} /> },
            { key: 'd4', label: 'Ramo',          children: <D4Ramo      ejercicio={ejercicio} tasaCesion={tasaCesion} /> },
            { key: 'd_sub', label: 'Subramo',    children: <DSubramo    ejercicio={ejercicio} tasaCesion={tasaCesion} /> },
            { key: 'd5', label: 'NP vs Cartera', children: <D5NuevaProduccion ejercicio={ejercicio} tasaCesion={tasaCesion} /> },
            { key: 'd7', label: 'Costes',        children: <D7Costes    ejercicio={ejercicio} tasaCesion={tasaCesion} /> },
            { key: 'd_rent', label: 'Rentabilidad cliente', children: <RentabilidadCliente /> },
          ]}
        />
      )}
    </div>
  )
}