import * as XLSX from 'xlsx'
import {
  Card, Select, Space, Typography, Tag, Alert, Button,
  Popconfirm, message, Divider, Row, Col,
} from 'antd'
import {
  DownloadOutlined, LockOutlined, CheckCircleOutlined,
  RiseOutlined, FallOutlined, PlusOutlined, MinusOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { presupuestoApi } from '../../api/presupuesto'
import { apiError } from '../../utils/errorHandler'
import { useState, Fragment } from 'react'

const { Title, Text } = Typography
const { Option } = Select

// ─── Formateo ────────────────────────────────────────────────────────────────
const fmt = (v: number) =>
  (v ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
const fmtK = (v: number) => {
  const abs = Math.abs(v ?? 0)
  const sign = v < 0 ? '-' : ''
  if (abs >= 1_000_000) return sign + (abs / 1_000_000).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + 'M €'
  if (abs >= 1_000)     return sign + (abs / 1_000).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'k €'
  return fmt(v)
}
const fmtDev = (v: number) =>
  (v > 0 ? '+' : '') + (v ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
const fmtPct = (v: number) => (v > 0 ? '+' : '') + (v ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%'
const fmtPp  = (v: number) => (v > 0 ? '+' : '') + (v ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' pp'

// ─── Tipos de fila ────────────────────────────────────────────────────────────
type RowKind = 'section' | 'detail' | 'subtotal' | 'kpi' | 'resultado' | 'cost' | 'margen' | 'spacer'

interface PLRow {
  key: string
  concepto: string
  ppto: number | null        // importe ppto  (€ o %)
  base: number | null        // importe base  (€ o %)
  norm?: number | null       // importe base normalizado (€ o %)
  desviacion: number | null  // € o pp
  pct: number | null         // % o null
  kind: RowKind
  positiveIsGood?: boolean
  indent?: boolean
  isPct?: boolean            // true = la fila muestra % en lugar de €
  pct_ppto?: number | null   // % sobre total ingresos/gastos (ppto)
  pct_base?: number | null   // % sobre total ingresos/gastos (base)
}

// ─── Estilos ──────────────────────────────────────────────────────────────────
const S: Record<RowKind, React.CSSProperties> = {
  section:   { background: '#e6f4ff', fontWeight: 600, fontSize: 11, color: '#0958d9' },
  detail:    { background: '#ffffff', fontSize: 12,    color: '#595959' },
  subtotal:  { background: '#f5f5f5', fontWeight: 700, fontSize: 13, borderTop: '1px solid #d9d9d9' },
  kpi:       { background: '#fffbe6', fontWeight: 700, fontSize: 13, borderTop: '2px solid #d48806' },
  resultado: { background: '#f6ffed', fontWeight: 700, fontSize: 14, borderTop: '2px solid #389e0d' },
  cost:      { background: '#fff7e6', fontSize: 12,    color: '#873800', fontStyle: 'italic' },
  margen:    { background: '#f9f0ff', fontSize: 11,    color: '#531dab', fontStyle: 'italic' },
  spacer:    { background: '#fafafa' },
}

// ─── Constructor de filas ─────────────────────────────────────────────────────
function buildRows(data: any): PLRow[] {
  const rows: PLRow[] = []

  const add = (
    key: string, concepto: string, d: any,
    kind: RowKind, positiveIsGood = true, indent = false,
    normValue?: number | null,
  ): void => {
    rows.push({
      key, concepto,
      ppto: d?.ppto ?? null,
      base: d?.base ?? null,
      norm: normValue ?? null,
      desviacion: d?.desviacion ?? null,
      pct: d?.pct_desviacion ?? null,
      pct_ppto: d?.pct_ppto ?? null,
      pct_base: d?.pct_base ?? null,
      kind, positiveIsGood, indent,
    })
  }

  const addMargen = (key: string, concepto: string, d: any, normPct?: number | null): void => {
    rows.push({
      key, concepto,
      ppto: d?.ppto_pct ?? null,
      base: d?.base_pct ?? null,
      norm: normPct ?? null,
      desviacion: d?.delta_pp ?? null,
      pct: null,
      kind: 'margen',
      positiveIsGood: true,
      isPct: true,
    })
  }

  const spacer = (k: string) =>
    rows.push({ key: k, concepto: '', ppto: null, base: null, desviacion: null, pct: null, kind: 'spacer' })

  const nb = data.normalizado_base || {}

  // ── INGRESOS ─────────────────────────────────────────────────────────────
  rows.push({ key: 's-ing', concepto: 'INGRESOS DE EXPLOTACIÓN', ppto: null, base: null, desviacion: null, pct: null, kind: 'section' })
  for (const c of (data.ingresos_por_compania || [])) {
    add(`ing-${c.concepto}`, c.concepto, c, 'detail', true, true)
  }
  add('tot-ing', 'TOTAL INGRESOS', data.total_ingresos, 'subtotal', true)
  spacer('sp1')

  // ── GASTOS OPERATIVOS ─────────────────────────────────────────────────────
  rows.push({ key: 's-gto', concepto: 'GASTOS OPERATIVOS (excl. amortizaciones y gastos financieros)', ppto: null, base: null, desviacion: null, pct: null, kind: 'section' })
  for (const f of (data.gastos_operativos || [])) {
    const normV = f.concepto === 'Cesiones a auxiliares' ? (nb.cesion_normalizada ?? null) : null
    add(`gto-${f.concepto}`, f.concepto, f, 'detail', false, true, normV)
  }
  add('tot-gto', 'TOTAL GASTOS OPERATIVOS', data.total_gastos_operativos, 'subtotal', false)
  spacer('sp2')

  // ── EBITDA ────────────────────────────────────────────────────────────────
  add('ebitda', 'EBITDA', data.ebitda, 'kpi', true, false, nb.ebitda_normalizado ?? null)
  addMargen('m-ebitda', '   Margen EBITDA', data.margen_ebitda, nb.margen_ebitda_norm_pct ?? null)
  spacer('sp3')

  // ── AMORTIZACIONES → EBIT ─────────────────────────────────────────────────
  add('amort', '– Amortizaciones y dotaciones', data.amortizaciones, 'cost', false, true)
  add('ebit', 'EBIT (Resultado de explotación)', data.ebit, 'kpi', true)
  addMargen('m-ebit', '   Margen operativo (EBIT / Ingresos)', data.margen_operativo)
  spacer('sp4')

  // ── GASTOS FINANCIEROS → BAI ──────────────────────────────────────────────
  add('fin', '– Gastos financieros', data.gastos_financieros, 'cost', false, true)
  add('bai', 'BAI (Beneficio antes de impuestos)', data.bai, 'kpi', true)
  spacer('sp5')

  // ── IMPUESTO → RESULTADO ──────────────────────────────────────────────────
  add('imp', '– Impuesto de Sociedades (25% × BAI)', data.impuesto, 'cost', false, true)
  add('resultado', 'RESULTADO DEL EJERCICIO', data.resultado, 'resultado', true)
  addMargen('m-neto', '   Margen neto (Resultado / Ingresos)', data.margen_neto)
  spacer('sp6')

  // ── RATIO GASTOS ──────────────────────────────────────────────────────────
  addMargen('ratio-gto', 'Ratio gastos totales / Ingresos', data.ratio_gastos)

  return rows
}

// ─── Celda de desviación ──────────────────────────────────────────────────────
function DevCell({ row }: { row: PLRow }) {
  const { desviacion, pct, kind, positiveIsGood, isPct } = row
  if (desviacion === null) return <span />

  const good = positiveIsGood ? desviacion >= 0 : desviacion <= 0
  const color = desviacion === 0 ? '#8c8c8c' : good ? '#389e0d' : '#cf1322'
  const tagColor = desviacion === 0 ? 'default' : good ? 'green' : 'red'

  if (isPct) {
    // Fila de margen: desviación = delta puntos porcentuales
    return (
      <span style={{ color, fontWeight: kind !== 'detail' ? 600 : 400, fontSize: 12 }}>
        {fmtPp(desviacion)}
      </span>
    )
  }

  return (
    <span style={{ color, fontWeight: kind !== 'detail' ? 600 : 400 }}>
      {fmtDev(desviacion)}
      {pct !== null && (
        <Tag color={tagColor} style={{ fontSize: 10, marginLeft: 4 }}>
          {fmtPct(pct)}
        </Tag>
      )}
    </span>
  )
}

// ─── Componente principal ─────────────────────────────────────────────────────
export default function CuentaResultados() {
  const qc = useQueryClient()
  const [presupuestoId, setPresupuestoId] = useState<string | null>(null)
  const [cesionesExpanded, setCesionesExpanded] = useState(false)

  const { data: presupuestos = [] } = useQuery({
    queryKey: ['presupuestos'],
    queryFn: () => presupuestoApi.listar().then(r => r.data),
  })

  const cerrados  = (presupuestos as any[]).filter((p: any) => p.estado === 'cerrado')
  const cerrables = (presupuestos as any[]).filter((p: any) =>
    ['gastos_aprobados', 'tesoreria_aprobada', 'ingresos_aprobados'].includes(p.estado)
  )

  const { data: plData, isLoading } = useQuery({
    queryKey: ['cuenta-resultados', presupuestoId],
    queryFn: () => presupuestoApi.cuentaResultados(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const cerrar = useMutation({
    mutationFn: (id: string) => presupuestoApi.cerrarPresupuesto(id),
    onSuccess: () => {
      message.success('Presupuesto cerrado')
      qc.invalidateQueries({ queryKey: ['presupuestos'] })
    },
    onError: (e) => message.error(apiError(e, 'Error al cerrar')),
  })

  const anoPpto = plData?.ejercicio_ppto ?? new Date().getFullYear()
  const anoBase = plData?.ejercicio_base ?? (anoPpto - 1)
  const rows = plData ? buildRows(plData) : []

  // ─── Excel export ──────────────────────────────────────────────────────────
  const exportarExcel = () => {
    if (!plData) return
    const filas: any[] = []
    const col_p = `Ppto ${anoPpto} (€)`
    const col_b = `Real ${anoBase} (€)`

    const r = (concepto: string, d: any, isKpi = false) => {
      if (!d) return
      filas.push({
        Epígrafe: concepto,
        [col_p]: d.ppto ?? '',
        [col_b]: d.base ?? '',
        'Desviación (€)': d.desviacion ?? '',
        'Desviación (%)': d.pct_desviacion != null ? `${d.pct_desviacion}%` : '',
        KPI: isKpi ? 'Sí' : '',
      })
    }
    const rm = (concepto: string, d: any) => {
      if (!d) return
      filas.push({
        Epígrafe: concepto,
        [col_p]: d.ppto_pct != null ? `${d.ppto_pct}%` : '',
        [col_b]: d.base_pct != null ? `${d.base_pct}%` : '',
        'Desviación (€)': d.delta_pp != null ? `${d.delta_pp} pp` : '',
        'Desviación (%)': '',
        KPI: '',
      })
    }

    filas.push({ Epígrafe: 'INGRESOS DE EXPLOTACIÓN' })
    for (const c of plData.ingresos_por_compania || []) r(`  ${c.concepto}`, c)
    r('TOTAL INGRESOS', plData.total_ingresos, true)
    filas.push({ Epígrafe: '' })

    filas.push({ Epígrafe: 'GASTOS OPERATIVOS' })
    for (const f of plData.gastos_operativos || []) r(`  ${f.concepto}`, f)
    r('TOTAL GASTOS OPERATIVOS', plData.total_gastos_operativos, true)
    filas.push({ Epígrafe: '' })

    r('EBITDA', plData.ebitda, true)
    rm('  Margen EBITDA', plData.margen_ebitda)
    r('  – Amortizaciones', plData.amortizaciones)
    r('EBIT (Resultado explotación)', plData.ebit, true)
    rm('  Margen operativo', plData.margen_operativo)
    r('  – Gastos financieros', plData.gastos_financieros)
    r('BAI (Beneficio antes impuestos)', plData.bai, true)
    r('  – Impuesto Sociedades 25%', plData.impuesto)
    r('RESULTADO DEL EJERCICIO', plData.resultado, true)
    rm('  Margen neto', plData.margen_neto)
    filas.push({ Epígrafe: '' })
    rm('Ratio gastos totales / Ingresos', plData.ratio_gastos)

    const ws = XLSX.utils.json_to_sheet(filas)
    ws['!cols'] = [{ wch: 40 }, { wch: 18 }, { wch: 18 }, { wch: 16 }, { wch: 14 }, { wch: 5 }]
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, `P&L ${anoPpto}`)
    XLSX.writeFile(wb, `cuenta_resultados_${anoPpto}.xlsx`)
  }

  // ─── Cards de resumen ──────────────────────────────────────────────────────
  const renderResumen = () => {
    if (!plData) return null
    const items = [
      {
        title: `Ingresos ${anoPpto}`,
        value: plData.total_ingresos?.ppto,
        prev: plData.total_ingresos?.base,
        color: '#1677ff',
        suffix: '€',
      },
      {
        title: `EBITDA`,
        value: plData.ebitda?.ppto,
        prev: plData.ebitda?.base,
        pct: plData.margen_ebitda?.ppto_pct,
        pctPrev: plData.margen_ebitda?.base_pct,
        color: '#d48806',
        suffix: '€',
      },
      {
        title: 'Margen operativo (EBIT)',
        value: plData.ebit?.ppto,
        prev: plData.ebit?.base,
        pct: plData.margen_operativo?.ppto_pct,
        pctPrev: plData.margen_operativo?.base_pct,
        color: '#531dab',
        suffix: '€',
      },
      {
        title: 'Resultado neto',
        value: plData.resultado?.ppto,
        prev: plData.resultado?.base,
        pct: plData.margen_neto?.ppto_pct,
        pctPrev: plData.margen_neto?.base_pct,
        color: '#389e0d',
        suffix: '€',
      },
      {
        title: 'Ratio gastos / Ingresos',
        value: plData.ratio_gastos?.ppto_pct,
        prev: plData.ratio_gastos?.base_pct,
        color: '#cf1322',
        suffix: '%',
        lowerIsBetter: true,
      },
    ]

    return (
      <Card
        size="small"
        style={{ borderRadius: 10, boxShadow: '0 1px 6px rgba(0,0,0,0.07)', marginBottom: 0 }}
        bodyStyle={{ padding: '12px 16px' }}
      >
        <Row gutter={[16, 12]}>
          {items.map((item, idx) => {
            const delta = item.prev != null ? item.value - item.prev : null
            const isGood = delta == null ? null : (item.lowerIsBetter ? delta <= 0 : delta >= 0)
            return (
              <Col key={idx} xs={12} sm={8} md={item.suffix === '%' ? 4 : 5}>
                <div style={{
                  padding: '10px 14px',
                  borderRadius: 8,
                  background: '#fafafa',
                  border: '1px solid #f0f0f0',
                  height: '100%',
                }}>
                  <Text style={{ fontSize: 11, color: '#8c8c8c', display: 'block', marginBottom: 4 }}>
                    {item.title}
                  </Text>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                    <Text strong style={{ fontSize: 18, color: item.color }}>
                      {item.suffix === '%'
                        ? `${(item.value ?? 0).toFixed(1)}%`
                        : fmtK(item.value ?? 0)
                      }
                    </Text>
                    {item.pct != null && (
                      <Text style={{ fontSize: 11, color: item.color }}>
                        ({(item.pct ?? 0).toFixed(1)}%)
                      </Text>
                    )}
                  </div>
                  {item.prev != null && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 4 }}>
                      {isGood != null && (
                        isGood
                          ? <RiseOutlined style={{ color: '#389e0d', fontSize: 11 }} />
                          : <FallOutlined style={{ color: '#cf1322', fontSize: 11 }} />
                      )}
                      <Text style={{ fontSize: 10, color: '#8c8c8c' }}>
                        vs {anoBase}:{' '}
                        {item.suffix === '%'
                          ? `${(item.prev ?? 0).toFixed(1)}%`
                          : fmtK(item.prev)
                        }
                        {item.pctPrev != null && ` (${(item.pctPrev ?? 0).toFixed(1)}%)`}
                      </Text>
                    </div>
                  )}
                </div>
              </Col>
            )
          })}
        </Row>
      </Card>
    )
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {/* Cabecera */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <Title level={5} style={{ margin: 0 }}>Cuenta de Resultados</Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Presupuesto cerrado vs real del ejercicio base — EBITDA · EBIT · BAI · Resultado
          </Text>
        </div>
        <Space wrap size={4}>
          <Select
            placeholder="Selecciona presupuesto cerrado"
            style={{ width: 270 }}
            onChange={setPresupuestoId}
            value={presupuestoId}
            size="small"
            loading={isLoading}
          >
            {cerrados.map((p: any) => (
              <Option key={p.id} value={p.id}>
                Ejercicio {p.ejercicio}
                <Tag color="blue" style={{ fontSize: 10, marginLeft: 6 }}>cerrado</Tag>
              </Option>
            ))}
          </Select>
          {plData && (
            <Button size="small" icon={<DownloadOutlined />} onClick={exportarExcel}>
              Excel
            </Button>
          )}
        </Space>
      </div>

      {/* Aviso: hay presupuestos cerrables */}
      {cerrables.length > 0 && (
        <Alert
          type="info"
          showIcon
          message={`${cerrables.length} presupuesto(s) pendiente(s) de cerrar`}
          description={
            <Space size={[16, 8]} wrap>
              {cerrables.map((p: any) => (
                <Space key={p.id} size={6}>
                  <Text style={{ fontSize: 12 }}>Ejercicio {p.ejercicio} ({p.estado})</Text>
                  <Popconfirm
                    title={`¿Cerrar el presupuesto ${p.ejercicio}?`}
                    description="Una vez cerrado no se puede modificar."
                    onConfirm={() => cerrar.mutate(p.id)}
                    okText="Cerrar"
                    cancelText="Cancelar"
                  >
                    <Button size="small" icon={<LockOutlined />} loading={cerrar.isPending}>
                      Cerrar
                    </Button>
                  </Popconfirm>
                </Space>
              ))}
            </Space>
          }
        />
      )}

      {!presupuestoId && cerrados.length === 0 && cerrables.length === 0 && (
        <Alert type="info" showIcon message="No hay presupuestos disponibles. Aprueba y cierra un presupuesto para ver la cuenta de resultados." />
      )}

      {/* Cards resumen KPIs */}
      {renderResumen()}

      {/* Tabla P&L */}
      {rows.length > 0 && (
        <Card
          style={{ borderRadius: 10, boxShadow: '0 1px 6px rgba(0,0,0,0.07)' }}
          bodyStyle={{ padding: 0 }}
          title={
            <Space>
              <CheckCircleOutlined style={{ color: '#389e0d' }} />
              <span style={{ fontSize: 13 }}>
                P&L — Presupuesto {anoPpto} vs Real {anoBase}
              </span>
              <Tag color="blue" style={{ fontSize: 11 }}>Cerrado</Tag>
            </Space>
          }
        >
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
              <colgroup>
                <col style={{ width: '32%' }} />
                <col style={{ width: '15%' }} />
                <col style={{ width: '15%' }} />
                <col style={{ width: '15%' }} />
                <col style={{ width: '23%' }} />
              </colgroup>
              <thead>
                <tr style={{ background: '#fafafa', borderBottom: '2px solid #e8e8e8' }}>
                  <th style={{ padding: '10px 16px', textAlign: 'left',  fontSize: 11, color: '#8c8c8c', fontWeight: 500 }}>Epígrafe</th>
                  <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 12, color: '#531dab', fontWeight: 600 }}>Presupuesto {anoPpto}</th>
                  <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 12, color: '#1677ff', fontWeight: 600 }}>Real {anoBase}</th>
                  <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 12, color: '#722ed1', fontWeight: 600 }}>Real Norm. {anoBase}</th>
                  <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 12, color: '#595959', fontWeight: 600 }}>Desviación</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  if (row.kind === 'spacer') {
                    return <tr key={row.key}><td colSpan={5} style={{ height: 6, background: '#fafafa' }} /></tr>
                  }
                  const st = S[row.kind]
                  const isKpi = row.kind === 'kpi' || row.kind === 'resultado'
                  const isMrg = row.kind === 'margen'
                  const isCesiones = row.key === 'gto-Cesiones a auxiliares'
                  const auxData: any[] = plData?.cesiones_por_auxiliar ?? []

                  return (
                    <Fragment key={row.key}>
                      <tr style={{ borderBottom: '1px solid #f0f0f0', ...st }}>
                        {/* Concepto */}
                        <td style={{ padding: '8px 16px', ...(row.indent ? { paddingLeft: 36 } : {}) }}>
                          {isCesiones ? (
                            <Space size={4}>
                              <Button
                                size="small"
                                type="text"
                                icon={cesionesExpanded ? <MinusOutlined /> : <PlusOutlined />}
                                onClick={() => setCesionesExpanded(e => !e)}
                                style={{ color: '#873800', padding: '0 4px', height: 20, minWidth: 20 }}
                              />
                              <Text style={{ fontSize: 12 }}>{row.concepto}</Text>
                            </Space>
                          ) : row.kind === 'section'
                            ? <Text strong style={{ fontSize: 11, color: '#0958d9', letterSpacing: 0.3, textTransform: 'uppercase' }}>{row.concepto}</Text>
                            : row.kind === 'resultado'
                            ? <Text strong style={{ fontSize: 14, color: '#135200' }}>{row.concepto}</Text>
                            : row.kind === 'kpi'
                            ? <Text strong style={{ fontSize: 13, color: '#614700' }}>{row.concepto}</Text>
                            : row.kind === 'subtotal'
                            ? <Text strong style={{ fontSize: 13 }}>{row.concepto}</Text>
                            : row.kind === 'margen'
                            ? <Text style={{ fontSize: 11, color: '#531dab' }}>{row.concepto}</Text>
                            : <Text style={{ fontSize: 12 }}>{row.concepto}</Text>
                          }
                        </td>
                        {/* Ppto */}
                        <td style={{ padding: '8px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                          {row.ppto !== null && (
                            isMrg
                              ? <Text style={{ fontSize: 12, color: '#531dab', fontWeight: 600 }}>{(row.ppto).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%</Text>
                              : (
                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: 1.3 }}>
                                  <Text strong={isKpi} style={{ color: row.kind === 'resultado' ? '#135200' : row.kind === 'kpi' ? '#614700' : undefined }}>
                                    {fmt(row.ppto)}
                                  </Text>
                                  {row.pct_ppto != null && (
                                    <Text style={{ fontSize: 10, color: '#8c8c8c' }}>{row.pct_ppto.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% s/total</Text>
                                  )}
                                </div>
                              )
                          )}
                        </td>
                        {/* Base */}
                        <td style={{ padding: '8px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                          {row.base !== null && (
                            isMrg
                              ? <Text style={{ fontSize: 12, color: '#8c8c8c' }}>{(row.base).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%</Text>
                              : (
                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: 1.3 }}>
                                  <Text type="secondary" style={{ fontSize: 12 }}>{fmt(row.base)}</Text>
                                  {row.pct_base != null && (
                                    <Text style={{ fontSize: 10, color: '#bfbfbf' }}>{row.pct_base.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% s/total</Text>
                                  )}
                                </div>
                              )
                          )}
                        </td>
                        {/* Real Norm. */}
                        <td style={{ padding: '8px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                          {row.norm != null && (
                            isMrg
                              ? <Text style={{ fontSize: 12, color: '#722ed1', fontWeight: 600 }}>{row.norm.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%</Text>
                              : <Text style={{ color: '#722ed1', fontWeight: 600, fontSize: 12 }}>{fmt(row.norm)}</Text>
                          )}
                        </td>
                        {/* Desviación */}
                        <td style={{ padding: '8px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <DevCell row={row} />
                        </td>
                      </tr>

                      {/* Sub-filas por auxiliar (solo cuando cesiones expandido) */}
                      {isCesiones && cesionesExpanded && auxData.map((aux: any) => {
                        const dev = aux.ppto - aux.base
                        const pctDev = aux.base !== 0 ? (dev / Math.abs(aux.base)) * 100 : (aux.ppto > 0 ? 100 : -100)
                        const color = dev === 0 ? '#8c8c8c' : dev <= 0 ? '#389e0d' : '#cf1322'
                        const tagColor = dev === 0 ? 'default' : dev <= 0 ? 'green' : 'red'
                        return (
                          <tr key={`ces-${aux.auxiliar}`} style={{ background: '#fffbe6', borderBottom: '1px solid #f5e6c8' }}>
                            <td style={{ padding: '5px 16px 5px 52px', fontSize: 11, color: '#873800' }}>
                              {aux.auxiliar}
                            </td>
                            <td style={{ padding: '5px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: 1.3 }}>
                                <Text style={{ fontSize: 11 }}>{fmt(aux.ppto)}</Text>
                                <Text style={{ fontSize: 10, color: '#8c8c8c' }}>{aux.pct_ppto.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% s/total</Text>
                              </div>
                            </td>
                            <td style={{ padding: '5px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: 1.3 }}>
                                <Text type="secondary" style={{ fontSize: 11 }}>{fmt(aux.base)}</Text>
                                <Text style={{ fontSize: 10, color: '#bfbfbf' }}>{aux.pct_base.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% s/total</Text>
                              </div>
                            </td>
                            <td style={{ padding: '5px 16px', textAlign: 'right', whiteSpace: 'nowrap' }} />
                            <td style={{ padding: '5px 16px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                              <span style={{ color, fontSize: 12 }}>
                                {(dev > 0 ? '+' : '') + fmt(dev)}
                                <Tag color={tagColor} style={{ fontSize: 10, marginLeft: 4 }}>
                                  {(pctDev > 0 ? '+' : '') + pctDev.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%
                                </Tag>
                              </span>
                            </td>
                          </tr>
                        )
                      })}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>

          <Divider style={{ margin: '0' }} />
          <div style={{ padding: '8px 16px 10px', display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'center' }}>
            <Text style={{ fontSize: 11, color: '#8c8c8c' }}>
              <span style={{ color: '#389e0d', fontWeight: 600 }}>Verde</span> = favorable
            </Text>
            <Text style={{ fontSize: 11, color: '#8c8c8c' }}>
              <span style={{ color: '#cf1322', fontWeight: 600 }}>Rojo</span> = desfavorable
            </Text>
            <Text style={{ fontSize: 11, color: '#8c8c8c' }}>pp = puntos porcentuales</Text>
            <Text style={{ fontSize: 11, color: '#8c8c8c' }}>
              <span style={{ color: '#722ed1', fontWeight: 600 }}>Norm.</span> = cesión real 623 (recibos con auxiliar e ingreso en ejercicio) + estimada
            </Text>
            <Text style={{ fontSize: 11, color: '#8c8c8c' }}>
              Impuesto = 25% × BAI (ambos ejercicios)
            </Text>
          </div>
        </Card>
      )}
    </Space>
  )
}
