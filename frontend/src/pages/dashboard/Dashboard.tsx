import { useEffect, useState } from 'react'
import {
  Row, Col, Card, Tag, Typography, Space, Select, Spin, Divider, Table,
  Statistic, Progress, Avatar,
} from 'antd'
import {
  ArrowUpOutlined, ArrowDownOutlined,
  CheckCircleFilled, WarningFilled, CloseCircleFilled,
  RiseOutlined,
  BarChartOutlined, TeamOutlined, BankOutlined, LineChartOutlined,
} from '@ant-design/icons'
import { useQuery, useQueries } from '@tanstack/react-query'
import { useAuthStore } from '../../store/authStore'
import { presupuestoApi } from '../../api/presupuesto'
import { realApi } from '../../api/tesoreria'
import { kpisApi } from '../../api/kpis'
import { analiticoApi } from '../../api/analitico'
import { rentabilidadApi } from '../../api/rentabilidad'

const { Title, Text } = Typography

// ── Formatters ─────────────────────────────────────────────────────────────
const _miles = (v: number) =>
  Math.round(Math.abs(v ?? 0)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.')
const fmt  = (v: number) => (v < 0 ? '-' : '') + _miles(v) + ' €'
const fmtK = (v: number) => {
  const abs = Math.abs(v ?? 0)
  if (abs >= 1_000_000) return (v < 0 ? '-' : '') + (abs / 1_000_000).toFixed(2).replace('.', ',') + ' M€'
  if (abs >= 1_000)     return (v < 0 ? '-' : '') + (abs / 1_000).toFixed(1).replace('.', ',') + ' k€'
  return fmt(v)
}
const fmtP  = (v: number | null | undefined) =>
  v == null ? '—' : v.toFixed(1).replace('.', ',') + '%'
const fmtPp = (v: number) => (v >= 0 ? '+' : '') + v.toFixed(1).replace('.', ',') + 'pp'

const MESES_LABELS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

// ── Paleta ─────────────────────────────────────────────────────────────────
const C = {
  blue:   '#1677ff',
  green:  '#52c41a',
  red:    '#f5222d',
  purple: '#722ed1',
  orange: '#d46b08',
  gold:   '#d48806',
  text:   '#595959',
  sub:    '#8c8c8c',
  border: '#f0f0f0',
}

// ── Card base styles ────────────────────────────────────────────────────────
const CARD = {
  style: { borderRadius: 12, boxShadow: '0 2px 10px rgba(0,0,0,0.07)', border: '1px solid #f0f0f0' },
  styles: { body: { padding: '20px 24px' } },
}

// ── KPI metas ──────────────────────────────────────────────────────────────
const KPI_META: Record<string, { target: string; desc: string }> = {
  'KPI-04': { target: '≥ 20%',  desc: 'Peso Nueva Producción' },
  'KPI-05': { target: '≥ 60%',  desc: 'Peso Cartera' },
  'KPI-06': { target: '≤ 30%',  desc: 'Ratio Cesión' },
  'KPI-12': { target: '≥ 15%',  desc: 'Margen EBITDA' },
  'KPI-11': { target: '> 0 €',  desc: 'EBITDA presupuestado' },
  'KPI-03': { target: 'máximo', desc: 'Ingreso neto' },
}
const KPI_SHOW_ORDER = ['KPI-04', 'KPI-05', 'KPI-06', 'KPI-12', 'KPI-11', 'KPI-03']

// ── Helpers UI ─────────────────────────────────────────────────────────────

function SemaforoIcon({ estado }: { estado: string }) {
  const s = (estado || '').toLowerCase()
  if (s === 'verde')    return <CheckCircleFilled style={{ color: C.green }} />
  if (s === 'amarillo') return <WarningFilled     style={{ color: C.gold }} />
  return <CloseCircleFilled style={{ color: C.red }} />
}

function KpiSemaforo({ kpi }: { kpi: any }) {
  const s     = (kpi.semaforo || '').toLowerCase()
  const color = s === 'verde' ? C.green : s === 'amarillo' ? C.gold : C.red
  const tc    = s === 'verde' ? 'success' : s === 'amarillo' ? 'warning' : 'error'
  const isPct = kpi.nombre?.includes('(%)')
  const disp  = kpi.valor != null ? (isPct ? fmtP(kpi.valor) : fmt(kpi.valor)) : '—'
  const meta  = KPI_META[kpi.codigo]
  return (
    <Card
      size="small"
      style={{ borderLeft: `4px solid ${color}`, borderRadius: 8, boxShadow: 'none' }}
      styles={{ body: { padding: '10px 12px' } }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
        <Text style={{ fontSize: 11, color: C.sub, lineHeight: 1.3 }}>
          {meta?.desc ?? kpi.nombre?.replace(/\s*\(.*?\)/g, '').trim()}
        </Text>
        <Tag color={tc} icon={<SemaforoIcon estado={kpi.semaforo ?? ''} />} style={{ fontSize: 10, margin: 0, marginLeft: 6 }}>
          {s === 'verde' ? 'OK' : s === 'amarillo' ? 'Atención' : 'Alerta'}
        </Tag>
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, color }}>{disp}</div>
      {meta?.target && meta.target !== 'máximo' && (
        <Text style={{ fontSize: 10, color: C.sub }}>Target {meta.target}</Text>
      )}
    </Card>
  )
}

function DesvBadge({ real, ppto, favorable }: { real: number; ppto: number; favorable?: boolean }) {
  if (!ppto) return null
  const desv = ((real - ppto) / Math.abs(ppto)) * 100
  const ok   = favorable ?? desv >= 0
  const Icon = desv >= 0 ? ArrowUpOutlined : ArrowDownOutlined
  return (
    <Text style={{ fontSize: 11, color: ok ? C.green : C.red }}>
      <Icon /> {(desv >= 0 ? '+' : '')}{desv.toFixed(1).replace('.', ',')}% vs ppto
    </Text>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Sección 1 — Presupuesto
// ─────────────────────────────────────────────────────────────────────────────

function SeccionPresupuesto({ presupuestoId }: { presupuestoId: string | null }) {
  const { data: cr, isLoading: cargandoCR } = useQuery({
    queryKey: ['dash-cr', presupuestoId],
    queryFn: () => presupuestoApi.cuentaResultados(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: meses = [] } = useQuery({
    queryKey: ['dash-meses', presupuestoId],
    queryFn: () => realApi.getMeses(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: kpisData = [] } = useQuery({
    queryKey: ['dash-kpis', presupuestoId],
    queryFn: () => kpisApi.resultados(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const mesesCerrados = (meses as any[]).filter(m => m.estado === 'cerrado')
  const ultimoMes: any = mesesCerrados[mesesCerrados.length - 1]

  const { data: acumulado } = useQuery({
    queryKey: ['dash-acumulado', presupuestoId, ultimoMes?.mes],
    queryFn: () => realApi.comparativaAcumulada(presupuestoId!, ultimoMes!.mes).then(r => r.data),
    enabled: !!presupuestoId && !!ultimoMes,
  })

  const kpisByCode: Record<string, any> = (kpisData as any[])
    .filter(k => !k.dimension)
    .reduce((acc: any, k: any) => {
      if (!acc[k.codigo] || (k.mes ?? 0) > (acc[k.codigo].mes ?? 0)) acc[k.codigo] = k
      return acc
    }, {})

  const kpisToShow = KPI_SHOW_ORDER.map(c => kpisByCode[c]).filter(Boolean)

  const ing_ppto    = kpisByCode['KPI-01']?.valor ?? cr?.total_ingresos?.ppto ?? 0
  const ebitda_ppto = kpisByCode['KPI-11']?.valor ?? cr?.ebitda?.ppto ?? 0
  const margen_ppto = kpisByCode['KPI-12']?.valor ?? 0
  const ces_ppto    = kpisByCode['KPI-06']?.valor ?? 0

  if (!presupuestoId) {
    return <Text type="secondary">Sin presupuesto seleccionado.</Text>
  }

  return (
    <Spin spinning={cargandoCR}>
      {/* 4 KPIs principales */}
      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col span={6}>
          <Card size="small" style={{ background: 'linear-gradient(135deg, #e6f4ff 0%, #bae0ff 100%)', border: 'none', borderRadius: 10 }} styles={{ body: { padding: 16 } }}>
            <Statistic
              title={<Text style={{ fontSize: 11, color: '#0958d9' }}>Ingresos presupuestados</Text>}
              value={ing_ppto}
              suffix="€"
              precision={0}
              valueStyle={{ color: '#0958d9', fontSize: 22, fontWeight: 700 }}
              formatter={(v) => _miles(Number(v))}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ background: ebitda_ppto >= 0 ? 'linear-gradient(135deg, #f6ffed 0%, #d9f7be 100%)' : 'linear-gradient(135deg, #fff1f0 0%, #ffccc7 100%)', border: 'none', borderRadius: 10 }} styles={{ body: { padding: 16 } }}>
            <Statistic
              title={<Text style={{ fontSize: 11, color: ebitda_ppto >= 0 ? '#237804' : C.red }}>EBITDA presupuestado</Text>}
              value={ebitda_ppto}
              suffix="€"
              precision={0}
              valueStyle={{ color: ebitda_ppto >= 0 ? '#237804' : C.red, fontSize: 22, fontWeight: 700 }}
              formatter={(v) => _miles(Number(v))}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ background: 'linear-gradient(135deg, #f9f0ff 0%, #efdbff 100%)', border: 'none', borderRadius: 10 }} styles={{ body: { padding: 16 } }}>
            <Statistic
              title={<Text style={{ fontSize: 11, color: C.purple }}>Margen EBITDA</Text>}
              value={margen_ppto}
              suffix="%"
              precision={1}
              valueStyle={{ color: C.purple, fontSize: 22, fontWeight: 700 }}
            />
            <Text style={{ fontSize: 10, color: C.sub }}>Target ≥ 15%</Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ background: 'linear-gradient(135deg, #fff7e6 0%, #ffe7ba 100%)', border: 'none', borderRadius: 10 }} styles={{ body: { padding: 16 } }}>
            <Statistic
              title={<Text style={{ fontSize: 11, color: C.orange }}>Ratio cesión ppto</Text>}
              value={ces_ppto}
              suffix="%"
              precision={1}
              valueStyle={{ color: ces_ppto <= 30 ? '#237804' : ces_ppto <= 40 ? C.gold : C.red, fontSize: 22, fontWeight: 700 }}
            />
            <Text style={{ fontSize: 10, color: C.sub }}>Target ≤ 30%</Text>
          </Card>
        </Col>
      </Row>

      {/* Seguimiento real */}
      {acumulado && ultimoMes && (
        <>
          <Divider style={{ margin: '12px 0' }}>
            <Text style={{ fontSize: 11, color: C.sub }}>
              Seguimiento real hasta {MESES_LABELS[ultimoMes.mes - 1]} · {mesesCerrados.length} mes(es) cerrado(s)
            </Text>
          </Divider>
          <Row gutter={[16, 12]} style={{ marginBottom: 20 }}>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 8 }} styles={{ body: { padding: 12 } }}>
                <Text style={{ fontSize: 11, color: C.sub, display: 'block', marginBottom: 4 }}>Ingresos reales</Text>
                <div style={{ fontSize: 18, fontWeight: 700, color: C.blue }}>{fmt(acumulado.ingresos?.real ?? 0)}</div>
                <DesvBadge real={acumulado.ingresos?.real ?? 0} ppto={acumulado.ingresos?.presupuesto ?? 0} favorable={acumulado.ingresos?.favorable} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 8 }} styles={{ body: { padding: 12 } }}>
                <Text style={{ fontSize: 11, color: C.sub, display: 'block', marginBottom: 4 }}>EBITDA real</Text>
                <div style={{ fontSize: 18, fontWeight: 700, color: (acumulado.ebitda?.real ?? 0) >= 0 ? C.green : C.red }}>{fmt(acumulado.ebitda?.real ?? 0)}</div>
                <DesvBadge real={acumulado.ebitda?.real ?? 0} ppto={acumulado.ebitda?.presupuesto ?? 0} favorable={acumulado.ebitda?.favorable} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 8 }} styles={{ body: { padding: 12 } }}>
                <Text style={{ fontSize: 11, color: C.sub, display: 'block', marginBottom: 4 }}>Avance s/ ingresos ppto</Text>
                <div style={{ fontSize: 18, fontWeight: 700, color: C.blue }}>
                  {ing_ppto > 0 ? fmtP((acumulado.ingresos?.real ?? 0) / ing_ppto * 100) : '—'}
                </div>
                <Progress
                  percent={ing_ppto > 0 ? Math.min(100, Math.round((acumulado.ingresos?.real ?? 0) / ing_ppto * 100)) : 0}
                  size="small" showInfo={false}
                  strokeColor={C.blue} style={{ marginTop: 4 }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ borderRadius: 8 }} styles={{ body: { padding: 12 } }}>
                <Text style={{ fontSize: 11, color: C.sub, display: 'block', marginBottom: 4 }}>Avance s/ EBITDA ppto</Text>
                <div style={{ fontSize: 18, fontWeight: 700, color: C.green }}>
                  {ebitda_ppto > 0 ? fmtP((acumulado.ebitda?.real ?? 0) / ebitda_ppto * 100) : '—'}
                </div>
                <Progress
                  percent={ebitda_ppto > 0 ? Math.min(100, Math.round((acumulado.ebitda?.real ?? 0) / ebitda_ppto * 100)) : 0}
                  size="small" showInfo={false}
                  strokeColor={C.green} style={{ marginTop: 4 }}
                />
              </Card>
            </Col>
          </Row>
        </>
      )}

      {/* KPIs semáforo */}
      {kpisToShow.length > 0 && (
        <>
          <Divider style={{ margin: '12px 0' }}>
            <Text style={{ fontSize: 11, color: C.sub }}>KPIs del presupuesto</Text>
          </Divider>
          <Row gutter={[12, 12]}>
            {kpisToShow.map((k: any) => (
              <Col span={8} key={k.codigo}>
                <KpiSemaforo kpi={k} />
              </Col>
            ))}
          </Row>
        </>
      )}
    </Spin>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Sección 2 — Analítica contable vs normalizada
// ─────────────────────────────────────────────────────────────────────────────

function SeccionAnalitica({ ejercicio }: { ejercicio: number | null }) {
  const { data: analitico, isLoading } = useQuery({
    queryKey: ['dash-d1', ejercicio],
    queryFn: () => analiticoApi.dashEjecutivo(ejercicio!, 0.40).then(r => r.data),
    enabled: !!ejercicio,
  })

  if (!ejercicio) return null
  if (isLoading) return <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>
  if (!analitico || analitico.sin_datos) {
    return (
      <div style={{ padding: '32px 0', textAlign: 'center' }}>
        <Text type="secondary">Sin datos analíticos para {ejercicio}. Recalcula el modelo analítico.</Text>
      </div>
    )
  }

  const r = analitico.resumen

  const StatVal = ({ label, value, color, note }: { label: string; value: number; color: string; note?: string }) => (
    <div style={{ padding: '10px 0', borderBottom: `1px solid ${C.border}` }}>
      <Text style={{ fontSize: 11, color: C.sub, display: 'block', marginBottom: 2 }}>{label}</Text>
      <div style={{ fontSize: 20, fontWeight: 700, color }}>{fmtK(value)}</div>
      {note && <Text style={{ fontSize: 10, color: C.sub }}>{note}</Text>}
    </div>
  )

  return (
    <>
      <Row gutter={[20, 0]} style={{ marginBottom: 20 }}>
        {/* Contable */}
        <Col span={12}>
          <div style={{ background: '#f8f9fa', border: `1px solid #dee2e6`, borderRadius: 10, padding: '16px 20px', height: '100%' }}>
            <Text style={{ fontSize: 13, fontWeight: 600, color: C.text, display: 'block', marginBottom: 12 }}>
              Contable · datos del diario
            </Text>
            <StatVal label="Comisión bruta" value={r.comision_bruta ?? 0} color={C.blue} />
            <StatVal label="Cesión contable (623*)" value={r.comision_auxiliar ?? 0} color={C.red} />
            <StatVal label="EBITDA contable" value={r.ebitda_contable ?? r.ebitda ?? 0} color={(r.ebitda_contable ?? r.ebitda ?? 0) >= 0 ? '#237804' : C.red} />
            <div style={{ padding: '10px 0' }}>
              <Text style={{ fontSize: 11, color: C.sub, display: 'block', marginBottom: 2 }}>Margen contable</Text>
              <div style={{ fontSize: 20, fontWeight: 700, color: C.purple }}>{fmtP(r.margen_pct_contable ?? r.margen_pct ?? 0)}</div>
            </div>
          </div>
        </Col>

        {/* Normalizado */}
        <Col span={12}>
          <div style={{ background: 'linear-gradient(135deg, #f9f0ff 0%, #efdbff 100%)', border: `2px solid ${C.purple}`, borderRadius: 10, padding: '16px 20px', height: '100%' }}>
            <Text style={{ fontSize: 13, fontWeight: 600, color: C.purple, display: 'block', marginBottom: 12 }}>
              ★ Normalizado · analítico
            </Text>
            <StatVal
              label="Cesión normalizada"
              value={r.cesion_normalizada ?? 0}
              color={C.purple}
              note={r.tiene_estimada ? `incluye estimada ${fmtK(r.cesion_estimada ?? 0)}` : undefined}
            />
            <StatVal label="Comisión neta normalizada" value={r.comision_neta_norm ?? 0} color="#08979c" />
            <StatVal label="EBITDA normalizado" value={r.ebitda_normalizado ?? 0} color={(r.ebitda_normalizado ?? 0) >= 0 ? '#237804' : C.red} />
            <div style={{ padding: '10px 0' }}>
              <Text style={{ fontSize: 11, color: C.sub, display: 'block', marginBottom: 2 }}>Margen normalizado</Text>
              <div style={{ fontSize: 20, fontWeight: 700, color: C.purple }}>{fmtP(r.margen_pct_norm ?? 0)}</div>
            </div>
          </div>
        </Col>
      </Row>

      {/* Benchmarks */}
      <Divider style={{ margin: '4px 0 16px' }}>
        <Text style={{ fontSize: 11, color: C.sub }}>Benchmarks sectoriales INESE 2025-26</Text>
      </Divider>
      <Row gutter={[12, 12]}>
        {[
          {
            label: 'Ratio cesión',
            value: r.ratio_cesion_pct ?? 0,
            target: '< 35%',
            max: 60,
            colorFn: (v: number) => v <= 30 ? C.green : v <= 40 ? C.gold : C.red,
            desc: 'Cesión / Comisión bruta',
          },
          {
            label: 'Costes op. / Ingresos',
            value: r.ratio_costes_op_pct ?? 0,
            target: '< 35%',
            max: 70,
            colorFn: (v: number) => v <= 35 ? C.green : v <= 45 ? C.gold : C.red,
            desc: 'Costes operativos / Ingresos',
          },
          {
            label: 'Margen EBITDA norm.',
            value: r.margen_pct_norm ?? 0,
            target: '≥ 15%',
            max: 40,
            colorFn: (v: number) => v >= 20 ? C.green : v >= 10 ? C.blue : v >= 0 ? C.gold : C.red,
            desc: 'EBITDA normalizado / Ingresos',
          },
          {
            label: 'Coste por recibo',
            value: Math.min(r.coste_por_recibo ?? 0, 50),
            target: '< 15 €',
            max: 50,
            colorFn: (v: number) => v <= 15 ? C.green : v <= 25 ? C.gold : C.red,
            desc: `${fmtP(r.coste_por_recibo ?? 0).replace('%','')} € / recibo · target < 15 €`,
            rawValue: r.coste_por_recibo ?? 0,
            isEuro: true,
          },
        ].map(b => {
          const color = b.colorFn(b.isEuro ? (b.rawValue ?? b.value) : b.value)
          const pct   = Math.min(100, Math.max(0, (b.value / b.max) * 100))
          return (
            <Col span={6} key={b.label}>
              <Card size="small" style={{ borderRadius: 10, textAlign: 'center', border: `1px solid ${color}22` }} styles={{ body: { padding: '14px 10px' } }}>
                <Text style={{ fontSize: 11, color: C.sub, display: 'block', marginBottom: 8 }}>{b.label}</Text>
                <Progress
                  type="circle"
                  percent={pct}
                  size={64}
                  strokeColor={color}
                  format={() => (
                    <span style={{ fontSize: 12, fontWeight: 700, color }}>
                      {b.isEuro ? `${(b.rawValue ?? b.value).toFixed(1)}€` : fmtP(b.value)}
                    </span>
                  )}
                />
                <div style={{ marginTop: 8 }}>
                  <Tag color={color === C.green ? 'success' : color === C.gold ? 'warning' : color === C.blue ? 'processing' : 'error'} style={{ fontSize: 10 }}>
                    Target {b.target}
                  </Tag>
                </div>
                <Text style={{ fontSize: 10, color: C.sub, display: 'block', marginTop: 4 }}>{b.desc}</Text>
              </Card>
            </Col>
          )
        })}
      </Row>
    </>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Sección 3 — Auxiliares y Clientes
// ─────────────────────────────────────────────────────────────────────────────

function SeccionAuxiliares({ ejercicio }: { ejercicio: number | null }) {
  const { data: auxData, isLoading: loadAux } = useQuery({
    queryKey: ['dash-aux', ejercicio],
    queryFn: () => analiticoApi.dashAuxiliar(ejercicio!, 0.40).then(r => r.data),
    enabled: !!ejercicio,
  })

  const { data: d1Data } = useQuery({
    queryKey: ['dash-d1', ejercicio],
    queryFn: () => analiticoApi.dashEjecutivo(ejercicio!, 0.40).then(r => r.data),
    enabled: !!ejercicio,
  })

  const { data: rentData, isLoading: loadRent } = useQuery({
    queryKey: ['dash-clientes', ejercicio],
    queryFn: () => rentabilidadApi.getClientes(ejercicio!).then(r => r.data),
    enabled: !!ejercicio,
  })

  if (!ejercicio) return null
  if (loadAux || loadRent) return <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /></div>

  const totalBruto: number = d1Data?.resumen?.comision_bruta ?? 1

  // Cesión efectiva por auxiliar = directa (623*) + estimada
  const cesionAux = (a: any) =>
    (a.cesion_directa ?? a.comision_auxiliar ?? 0) + (a.cesion_estimada ?? 0)

  // Agrupar Sobrino (José Luis + Irene) + Makonta en una sola fila
  const isGrupo = (name: string) => {
    const u = name.toUpperCase()
    return u.includes('SOBRINO') || u.includes('MAKONTA')
  }
  const auxiliares: any[] = auxData?.auxiliares ?? []
  const grupoAux  = auxiliares.filter(a => isGrupo(a.auxiliar))
  const restoAux  = auxiliares.filter(a => !isGrupo(a.auxiliar))
  const grupoCesion = grupoAux.reduce((s, a) => s + cesionAux(a), 0)
  const grupoEntry = grupoAux.length > 0
    ? { auxiliar: 'Grupo Sobrino / Makonta', cesionTotal: grupoCesion, isGrupo: true,
        members: grupoAux.map(a => a.auxiliar).join(' · ') }
    : null

  const allEntries = [
    ...restoAux.map(a => ({ auxiliar: a.auxiliar, cesionTotal: cesionAux(a), isGrupo: false, members: '' })),
    ...(grupoEntry ? [grupoEntry] : []),
  ].sort((a, b) => b.cesionTotal - a.cesionTotal)

  const top5Aux = allEntries.slice(0, 5).map((a, i) => ({
    key: a.auxiliar,
    rank: i + 1,
    name: a.auxiliar,
    cesion: a.cesionTotal,
    pctIng: totalBruto > 0 ? (a.cesionTotal / totalBruto * 100) : 0,
    isGrupo: a.isGrupo,
    members: a.members,
  }))

  // Top 3 clientes por margen neto efectivo DESC
  const clientes: any[] = (rentData?.clientes ?? []).filter((c: any) => c.tomador !== '__SIN_CLIENTE__')
  const top3Cli = [...clientes]
    .sort((a: any, b: any) => {
      const mA = a.tiene_cesion_estimada ? (a.margen_neto_estimado ?? a.margen_neto ?? 0) : (a.margen_neto ?? 0)
      const mB = b.tiene_cesion_estimada ? (b.margen_neto_estimado ?? b.margen_neto ?? 0) : (b.margen_neto ?? 0)
      return mB - mA
    })
    .slice(0, 3)
    .map((c: any, i: number) => ({
      key: c.tomador,
      rank: i + 1,
      name: c.tomador,
      margen: c.tiene_cesion_estimada ? (c.margen_neto_estimado ?? c.margen_neto ?? 0) : (c.margen_neto ?? 0),
      pctMrg: c.tiene_cesion_estimada ? (c.margen_pct_estimado ?? c.margen_pct ?? 0) : (c.margen_pct ?? 0),
    }))

  const rankColor = (r: number) => r === 1 ? '#d48806' : r === 2 ? '#8c8c8c' : r === 3 ? '#873800' : C.sub

  const auxCols = [
    {
      title: '#',
      dataIndex: 'rank',
      width: 36,
      render: (v: number) => (
        <Avatar size={22} style={{ background: rankColor(v), fontSize: 11, fontWeight: 700 }}>{v}</Avatar>
      ),
    },
    {
      title: 'Auxiliar',
      dataIndex: 'name',
      render: (v: string, row: any) => row.isGrupo
        ? <span>
            <Tag color="purple" style={{ fontSize: 10, marginRight: 6 }}>GRUPO</Tag>
            <Text style={{ fontSize: 12, fontWeight: 600 }} title={row.members}>{v}</Text>
          </span>
        : <Text style={{ fontSize: 13, fontWeight: 500 }}>{v}</Text>,
    },
    {
      title: 'Cesión recibida (real + estimada)',
      dataIndex: 'cesion',
      align: 'right' as const,
      render: (v: number) => <Text style={{ fontWeight: 700, color: C.purple, fontSize: 13 }}>{fmtK(v)}</Text>,
    },
    {
      title: '% s/ ingresos',
      dataIndex: 'pctIng',
      align: 'right' as const,
      width: 100,
      render: (v: number) => <Tag color="purple" style={{ fontSize: 11 }}>{fmtP(v)}</Tag>,
    },
  ]

  const cliCols = [
    {
      title: '#',
      dataIndex: 'rank',
      width: 36,
      render: (v: number) => (
        <Avatar size={22} style={{ background: rankColor(v), fontSize: 11, fontWeight: 700 }}>{v}</Avatar>
      ),
    },
    {
      title: 'Agrupación',
      dataIndex: 'name',
      render: (v: string) => <Text style={{ fontSize: 13, fontWeight: 500 }}>{v}</Text>,
    },
    {
      title: 'Margen neto',
      dataIndex: 'margen',
      align: 'right' as const,
      render: (v: number) => (
        <Text style={{ fontWeight: 700, color: v >= 0 ? '#237804' : C.red, fontSize: 13 }}>{fmtK(v)}</Text>
      ),
    },
    {
      title: '% Margen',
      dataIndex: 'pctMrg',
      align: 'right' as const,
      width: 90,
      render: (v: number) => (
        <Tag color={v >= 20 ? 'success' : v >= 10 ? 'processing' : v >= 0 ? 'warning' : 'error'} style={{ fontSize: 11 }}>
          {fmtP(v)}
        </Tag>
      ),
    },
  ]

  return (
    <Row gutter={[20, 0]}>
      <Col span={13}>
        <div style={{ marginBottom: 6 }}>
          <Text strong style={{ fontSize: 13 }}>Top 5 Auxiliares por cesión recibida</Text>
        </div>
        <Text style={{ fontSize: 11, color: C.sub, display: 'block', marginBottom: 12 }}>
          Importe de cesión normalizada recibida por cada auxiliar en el ejercicio
        </Text>
        {top5Aux.length === 0
          ? <Text type="secondary" style={{ fontSize: 12 }}>Sin datos de auxiliares.</Text>
          : (
            <Table
              dataSource={top5Aux}
              columns={auxCols}
              size="small"
              pagination={false}
              showHeader
              style={{ fontSize: 12 }}
              rowClassName={(_, i) => i % 2 === 1 ? 'ant-table-row-alt' : ''}
            />
          )
        }
      </Col>

      <Col span={11}>
        <div style={{ marginBottom: 6 }}>
          <Text strong style={{ fontSize: 13 }}>Top 3 Clientes por margen aportado</Text>
        </div>
        <Text style={{ fontSize: 11, color: C.sub, display: 'block', marginBottom: 12 }}>
          Margen neto aportado por cada cliente tras cesión y costes imputados
        </Text>
        {top3Cli.length === 0
          ? <Text type="secondary" style={{ fontSize: 12 }}>Sin datos de clientes.</Text>
          : (
            <Table
              dataSource={top3Cli}
              columns={cliCols}
              size="small"
              pagination={false}
              showHeader
              style={{ fontSize: 12 }}
            />
          )
        }
      </Col>
    </Row>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Sección 4 — Valoración multi-ejercicio
// ─────────────────────────────────────────────────────────────────────────────

function SeccionValoracion({ ejList }: { ejList: number[] }) {
  const d1Results = useQueries({
    queries: ejList.map(ej => ({
      queryKey: ['dash-val-d1', ej] as const,
      queryFn: () => analiticoApi.dashEjecutivo(ej, 0.40).then(r => r.data),
      enabled: ejList.length > 0,
    })),
  })

  const valResults = useQueries({
    queries: ejList.map(ej => ({
      queryKey: ['dash-val-val', ej] as const,
      queryFn: () => analiticoApi.valoracion(ej).then(r => r.data),
      enabled: ejList.length > 0,
    })),
  })

  const allRows = ejList.map((ej, i) => {
    const d1  = d1Results[i]?.data
    const val = valResults[i]?.data
    const r   = d1?.resumen
    return {
      key:    ej,
      ej,
      bruta:  r?.comision_bruta     ?? null as number | null,
      ebitda: r?.ebitda_normalizado ?? null as number | null,
      margen: r?.margen_pct_norm    ?? null as number | null,
      valCom:  (!val || val.sin_datos) ? null as number | null : (val.valoracion?.comisiones?.base?.valor ?? null),
      valEb:   (!val || val.sin_datos) ? null as number | null : (val.valoracion?.ebitda?.base?.valor   ?? null),
      valProp: (!val || val.sin_datos) ? null as number | null : (val.valoracion?.combinado ?? val.valoracion?.comisiones?.base?.valor ?? null),
    }
  })

  const rows = allRows.filter(r => r.bruta != null)
  const loading = d1Results.some(q => q.isLoading) || valResults.some(q => q.isLoading)

  const cols = [
    {
      title: 'Ejercicio',
      dataIndex: 'ej',
      width: 90,
      render: (v: number) => <Text strong style={{ fontSize: 14 }}>{v}</Text>,
    },
    {
      title: 'Comisión bruta',
      dataIndex: 'bruta',
      align: 'right' as const,
      render: (v: number | null) => v != null ? <Text style={{ color: C.blue }}>{fmtK(v)}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: 'EBITDA norm.',
      dataIndex: 'ebitda',
      align: 'right' as const,
      render: (v: number | null) =>
        v != null
          ? <Text style={{ color: v >= 0 ? '#237804' : C.red, fontWeight: 600 }}>{fmtK(v)}</Text>
          : <Text type="secondary">—</Text>,
    },
    {
      title: '% Margen',
      dataIndex: 'margen',
      align: 'right' as const,
      render: (v: number | null) =>
        v != null
          ? <Tag color={v >= 15 ? 'success' : v >= 0 ? 'warning' : 'error'} style={{ fontSize: 11 }}>{fmtP(v)}</Tag>
          : <Text type="secondary">—</Text>,
    },
    {
      title: 'Val. Comisiones',
      dataIndex: 'valCom',
      align: 'right' as const,
      render: (v: number | null) =>
        v != null
          ? <Text style={{ color: C.blue }}>{fmtK(v)}</Text>
          : <Text type="secondary">—</Text>,
    },
    {
      title: 'Val. EBITDA',
      dataIndex: 'valEb',
      align: 'right' as const,
      render: (v: number | null) =>
        v != null
          ? <Text style={{ color: '#237804' }}>{fmtK(v)}</Text>
          : <Text type="secondary">—</Text>,
    },
    {
      title: 'Valoración propuesta',
      dataIndex: 'valProp',
      align: 'right' as const,
      render: (v: number | null) =>
        v != null
          ? <Text style={{ fontWeight: 800, color: C.blue, fontSize: 16 }}>{fmtK(v)}</Text>
          : <Text type="secondary">—</Text>,
    },
  ]

  if (!loading && rows.length === 0) {
    return <Text type="secondary">Sin datos de valoración disponibles.</Text>
  }

  return (
    <Spin spinning={loading}>
      <Table
        dataSource={rows}
        columns={cols}
        size="small"
        pagination={false}
        bordered={false}
        style={{ fontSize: 12 }}
        rowClassName={(_, i) => i % 2 === 1 ? 'ant-table-row-alt' : ''}
      />
    </Spin>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Sección 5 — Conclusiones
// ─────────────────────────────────────────────────────────────────────────────

function SeccionConclusiones({
  analitico,
  auxData,
  kpisByCode,
  acumulado,
  clientes,
  totalBruto,
}: {
  analitico: any
  auxData: any
  kpisByCode: Record<string, any>
  acumulado: any
  clientes: any[]
  totalBruto: number
}) {
  if (!analitico || analitico.sin_datos) {
    return <Text type="secondary">Sin datos analíticos para generar conclusiones.</Text>
  }

  const r         = analitico.resumen
  const mrg       = r.margen_pct_norm ?? 0
  const ces       = r.ratio_cesion_pct ?? 0
  const ing       = r.comision_bruta ?? 0
  const ebitda_n  = r.ebitda_normalizado ?? 0
  const cesTotal  = r.cesion_normalizada ?? 0

  const cliFiltrados = clientes.filter((c: any) => c.tomador !== '__SIN_CLIENTE__')
  const top3Cli = [...cliFiltrados]
    .sort((a: any, b: any) => b.ingreso_bruto - a.ingreso_bruto)
    .slice(0, 3)
  const top3Ing  = totalBruto > 0
    ? top3Cli.reduce((s: number, c: any) => s + (c.ingreso_bruto ?? 0), 0) / totalBruto * 100
    : 0
  const top1Name = top3Cli[0]?.tomador ?? '—'
  const top1Pct  = totalBruto > 0 ? ((top3Cli[0]?.ingreso_bruto ?? 0) / totalBruto * 100) : 0

  const auxiliares: any[] = auxData?.auxiliares ?? []
  const top1Aux    = [...auxiliares].sort((a, b) => ((b.cesion_normalizada ?? 0) - (a.cesion_normalizada ?? 0)))[0]
  const top1AuxPct = cesTotal > 0 && top1Aux ? ((top1Aux.cesion_normalizada ?? 0) / cesTotal * 100) : 0

  const kpisRojo = KPI_SHOW_ORDER.map(c => kpisByCode[c]).filter(k => k && (k.semaforo || '').toLowerCase() === 'rojo')
  const kpisOk   = KPI_SHOW_ORDER.map(c => kpisByCode[c]).filter(k => k && (k.semaforo || '').toLowerCase() === 'verde')
  const tieneKpis = kpisRojo.length + kpisOk.length > 0

  // Textos
  const gapMrg = mrg - 15
  const ebitdaNeed = ing > 0 ? ing * 0.15 - ebitda_n : 0

  const txtRent =
    mrg >= 15
      ? `EBITDA normalizado de ${fmtK(ebitda_n)} con margen del ${fmtP(mrg)}. Gap positivo de ${fmtPp(gapMrg)} sobre el mínimo sectorial del 15%. La correduría genera valor por encima del umbral de rentabilidad.`
      : mrg >= 0
      ? `Margen del ${fmtP(mrg)}, ${fmtPp(gapMrg)} por debajo del objetivo del 15%. Para alcanzar el target se necesitan ${fmtK(ebitdaNeed)} adicionales de EBITDA. Palancas: reducir cesión o optimizar costes operativos.`
      : `EBITDA normalizado negativo: ${fmtK(ebitda_n)}. La correduría no cubre sus costes totales. Palancas prioritarias: reducción del ratio de cesión (${fmtP(ces)}) y revisión de la estructura de costes operativos.`

  const ahorroSi30 = ing > 0 ? (ces / 100 - 0.30) * ing : 0
  const txtCes =
    ces <= 30
      ? `Ratio de cesión en rango óptimo: ${fmtP(ces)} (target interno ≤ 30%, benchmark INESE ≤ 35%). Buena gestión de condiciones con auxiliares.${r.tiene_estimada ? ' Existe cesión estimada pendiente de identificar — su correcta asignación podría ajustar este ratio.' : ''}`
      : ces <= 35
      ? `Ratio de cesión del ${fmtP(ces)}, dentro del benchmark sectorial (≤ 35%) pero por encima del objetivo interno (≤ 30%). Reducir al 30% supondría una mejora de EBITDA de aprox. ${fmtK(ahorroSi30)}.${r.tiene_estimada ? ' Parte de la cesión es estimada y podría variar.' : ''}`
      : `Ratio de cesión elevado: ${fmtP(ces)}, supera el benchmark sectorial del 35%. Reducir al 30% mejoraría el EBITDA en aprox. ${fmtK(ahorroSi30)}. Prioridad: renegociar condiciones con los auxiliares de mayor cesión.${r.tiene_estimada ? ' Hay cesión estimada pendiente de asignar a auxiliar.' : ''}`

  const txtConc =
    top3Ing >= 60
      ? `Alta concentración de cartera: los 3 principales clientes aglutinan el ${fmtP(top3Ing)} de los ingresos (${top1Name} lidera con el ${fmtP(top1Pct)}). Riesgo de dependencia elevado — diversificación recomendada.${top1Aux ? ` En auxiliares, ${top1Aux.auxiliar} concentra el ${fmtP(top1AuxPct)} de la cesión total.` : ''}`
      : top3Ing >= 40
      ? `Concentración moderada: top 3 clientes suman el ${fmtP(top3Ing)} de ingresos (${top1Name} con ${fmtP(top1Pct)}). Cartera razonablemente diversificada, con margen para ampliar base de clientes.${top1Aux ? ` Auxiliar con mayor cesión: ${top1Aux.auxiliar} (${fmtP(top1AuxPct)} del total cedido).` : ''}`
      : `Buena diversificación: top 3 clientes concentran solo el ${fmtP(top3Ing)} de los ingresos. La correduría no depende de ningún cliente clave.${top1Aux ? ` En cesión, ${top1Aux.auxiliar} es el auxiliar principal con el ${fmtP(top1AuxPct)} del total.` : ''}`

  const txtPpto = !tieneKpis
    ? 'Sin KPIs de presupuesto calculados. Ejecuta el cálculo de KPIs en el módulo de Presupuesto para obtener el semáforo.'
    : kpisRojo.length === 0
    ? `Todos los KPIs en verde. Destacan: ${kpisOk.slice(0, 3).map(k => {
        const m = KPI_META[k.codigo]
        const v = k.nombre?.includes('(%)') ? fmtP(k.valor) : fmt(k.valor)
        return `${m?.desc ?? k.codigo} (${v})`
      }).join('; ')}.`
    : `${kpisRojo.length} KPI${kpisRojo.length > 1 ? 's' : ''} en alerta: ${kpisRojo.map(k => {
        const m = KPI_META[k.codigo]
        const v = k.nombre?.includes('(%)') ? fmtP(k.valor) : fmt(k.valor)
        return `${m?.desc ?? k.codigo} = ${v} (target ${m?.target ?? '?'})`
      }).join('; ')}.${acumulado
        ? ` Desviación real: ingresos ${((( acumulado.ingresos?.real ?? 0) - (acumulado.ingresos?.presupuesto ?? 0)) >= 0 ? '+' : '')}${fmtK((acumulado.ingresos?.real ?? 0) - (acumulado.ingresos?.presupuesto ?? 0))} · EBITDA ${(((acumulado.ebitda?.real ?? 0) - (acumulado.ebitda?.presupuesto ?? 0)) >= 0 ? '+' : '')}${fmtK((acumulado.ebitda?.real ?? 0) - (acumulado.ebitda?.presupuesto ?? 0))}.`
        : ''}`

  const cards = [
    {
      icon: <BarChartOutlined style={{ fontSize: 18 }} />,
      title: 'Rentabilidad',
      text: txtRent,
      color: mrg >= 15 ? C.green : mrg >= 0 ? C.gold : C.red,
      tag: `Margen ${fmtP(mrg)}`,
      tagColor: mrg >= 15 ? 'success' : mrg >= 0 ? 'warning' : 'error',
    },
    {
      icon: <LineChartOutlined style={{ fontSize: 18 }} />,
      title: 'Gestión de cesión',
      text: txtCes,
      color: ces <= 30 ? C.green : ces <= 35 ? C.blue : ces <= 40 ? C.gold : C.red,
      tag: `Ratio ${fmtP(ces)}`,
      tagColor: ces <= 30 ? 'success' : ces <= 35 ? 'processing' : ces <= 40 ? 'warning' : 'error',
    },
    {
      icon: <TeamOutlined style={{ fontSize: 18 }} />,
      title: 'Concentración de cartera',
      text: txtConc,
      color: top3Ing >= 60 ? C.red : top3Ing >= 40 ? C.gold : C.green,
      tag: `Top 3 clientes ${fmtP(top3Ing)} s/ingresos`,
      tagColor: top3Ing >= 60 ? 'error' : top3Ing >= 40 ? 'warning' : 'success',
    },
    {
      icon: <BankOutlined style={{ fontSize: 18 }} />,
      title: 'Estado presupuestario',
      text: txtPpto,
      color: !tieneKpis ? C.sub : kpisRojo.length === 0 ? C.green : kpisRojo.length <= 2 ? C.gold : C.red,
      tag: !tieneKpis ? 'Sin KPIs' : kpisRojo.length === 0 ? 'Todos OK' : `${kpisRojo.length} en alerta`,
      tagColor: !tieneKpis ? 'default' : kpisRojo.length === 0 ? 'success' : kpisRojo.length <= 2 ? 'warning' : 'error',
    },
  ]

  return (
    <Row gutter={[16, 16]}>
      {cards.map(card => (
        <Col span={12} key={card.title}>
          <Card
            size="small"
            style={{ borderTop: `4px solid ${card.color}`, borderRadius: 10, boxShadow: '0 1px 6px rgba(0,0,0,0.06)', height: '100%', background: '#fafafa' }}
            styles={{ body: { padding: '14px 18px' } }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <span style={{ color: card.color }}>{card.icon}</span>
              <Text strong style={{ fontSize: 13, color: '#262626' }}>{card.title}</Text>
              <Tag color={card.tagColor} style={{ fontSize: 10, marginLeft: 'auto' }}>{card.tag}</Tag>
            </div>
            <Text style={{ fontSize: 13, color: C.text, lineHeight: 1.7 }}>{card.text}</Text>
          </Card>
        </Col>
      ))}
    </Row>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Página principal
// ─────────────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { user } = useAuthStore()
  const [ejercicio,     setEjercicio]     = useState<number | null>(null)
  const [presupuestoId, setPresupuestoId] = useState<string | null>(null)

  const { data: ejercicios = [] } = useQuery({
    queryKey: ['analitico-ejercicios'],
    queryFn: () => analiticoApi.getEjercicios().then(r => r.data),
  })

  const { data: presupuestos = [] } = useQuery({
    queryKey: ['presupuestos'],
    queryFn: () => presupuestoApi.listar().then(r => r.data),
  })

  useEffect(() => {
    const ejList = ejercicios as number[]
    if (ejList.length > 0 && !ejercicio) setEjercicio(Math.max(...ejList))
  }, [ejercicios, ejercicio])

  useEffect(() => {
    const pList = presupuestos as any[]
    if (pList.length > 0 && !presupuestoId) {
      const sorted = [...pList].sort((a, b) => b.ejercicio - a.ejercicio)
      setPresupuestoId(sorted[0].id)
    }
  }, [presupuestos, presupuestoId])

  const ejList = ejercicios as number[]

  // Datos compartidos para conclusiones
  const { data: analiticoConcl } = useQuery({
    queryKey: ['dash-d1', ejercicio],
    queryFn: () => analiticoApi.dashEjecutivo(ejercicio!, 0.40).then(r => r.data),
    enabled: !!ejercicio,
  })

  const { data: auxDataConcl } = useQuery({
    queryKey: ['dash-aux', ejercicio],
    queryFn: () => analiticoApi.dashAuxiliar(ejercicio!, 0.40).then(r => r.data),
    enabled: !!ejercicio,
  })

  const { data: kpisData = [] } = useQuery({
    queryKey: ['dash-kpis', presupuestoId],
    queryFn: () => kpisApi.resultados(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: meses = [] } = useQuery({
    queryKey: ['dash-meses', presupuestoId],
    queryFn: () => realApi.getMeses(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const mesesCerrados = (meses as any[]).filter(m => m.estado === 'cerrado')
  const ultimoMes: any = mesesCerrados[mesesCerrados.length - 1]

  const { data: acumulado } = useQuery({
    queryKey: ['dash-acumulado', presupuestoId, ultimoMes?.mes],
    queryFn: () => realApi.comparativaAcumulada(presupuestoId!, ultimoMes!.mes).then(r => r.data),
    enabled: !!presupuestoId && !!ultimoMes,
  })

  const { data: rentDataConcl } = useQuery({
    queryKey: ['dash-clientes', ejercicio],
    queryFn: () => rentabilidadApi.getClientes(ejercicio!).then(r => r.data),
    enabled: !!ejercicio,
  })

  const kpisByCode: Record<string, any> = (kpisData as any[])
    .filter(k => !k.dimension)
    .reduce((acc: any, k: any) => {
      if (!acc[k.codigo] || (k.mes ?? 0) > (acc[k.codigo].mes ?? 0)) acc[k.codigo] = k
      return acc
    }, {})

  const clientesConcl: any[]  = rentDataConcl?.clientes ?? []
  const totalBrutoConcl: number = rentDataConcl?.resumen?.comision_bruta_total ?? 1

  const pActual = (presupuestos as any[]).find((p: any) => p.id === presupuestoId)

  const sectionCard = (icon: React.ReactNode, title: string, accent: string, children: React.ReactNode, extra?: React.ReactNode) => (
    <Card
      {...CARD}
      title={
        <Space>
          <span style={{ color: accent, fontSize: 16 }}>{icon}</span>
          <Text strong style={{ fontSize: 14 }}>{title}</Text>
        </Space>
      }
      extra={extra}
      headStyle={{ borderBottom: `2px solid ${accent}22`, paddingBottom: 12 }}
    >
      {children}
    </Card>
  )

  return (
    <div style={{ background: '#f5f6fa', minHeight: '100vh', padding: '0 0 40px' }}>

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div style={{
        background: '#fff',
        borderBottom: '1px solid #f0f0f0',
        padding: '20px 32px',
        marginBottom: 24,
        boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
      }}>
        <Row align="middle" justify="space-between">
          <Col>
            <Title level={3} style={{ margin: 0, color: '#141414' }}>Dashboard Financiero</Title>
            <Text style={{ color: C.sub, fontSize: 13 }}>Bienvenido, {user?.full_name}</Text>
          </Col>
          <Col>
            <Space size={16}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#f5f5f5', borderRadius: 8, padding: '6px 12px' }}>
                <Text style={{ fontSize: 12, color: C.sub }}>Año analítica</Text>
                <Select
                  size="small"
                  value={ejercicio}
                  onChange={setEjercicio}
                  style={{ width: 80 }}
                  variant="borderless"
                  options={(ejercicios as number[]).map(e => ({ value: e, label: String(e) }))}
                />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#f5f5f5', borderRadius: 8, padding: '6px 12px' }}>
                <Text style={{ fontSize: 12, color: C.sub }}>Presupuesto</Text>
                <Select
                  size="small"
                  value={presupuestoId}
                  onChange={setPresupuestoId}
                  style={{ width: 130 }}
                  variant="borderless"
                  options={(presupuestos as any[]).map((p: any) => ({ value: p.id, label: `Ej. ${p.ejercicio}` }))}
                />
              </div>
            </Space>
          </Col>
        </Row>
      </div>

      <div style={{ padding: '0 32px' }}>
        <Space direction="vertical" size={20} style={{ width: '100%' }}>

          {/* Sección 1 — Presupuesto */}
          {sectionCard(
            <BankOutlined />,
            `Presupuesto ${pActual?.ejercicio ?? ''} · Seguimiento y KPIs`,
            C.blue,
            <SeccionPresupuesto presupuestoId={presupuestoId} />,
          )}

          {/* Sección 2 — Analítica */}
          {sectionCard(
            <BarChartOutlined />,
            `Analítica ${ejercicio} — Contable vs Normalizada`,
            C.purple,
            <SeccionAnalitica ejercicio={ejercicio} />,
          )}

          {/* Sección 3 — Rankings */}
          {sectionCard(
            <TeamOutlined />,
            `Auxiliares y Clientes · ${ejercicio}`,
            C.orange,
            <SeccionAuxiliares ejercicio={ejercicio} />,
          )}

          {/* Sección 4 — Valoración */}
          {sectionCard(
            <RiseOutlined />,
            'Valoración por ejercicio',
            C.green,
            <SeccionValoracion ejList={ejList} />,
            <Text type="secondary" style={{ fontSize: 11 }}>Escenario base · múltiplo sobre comisiones y EBITDA</Text>,
          )}

          {/* Sección 5 — Conclusiones */}
          {sectionCard(
            <LineChartOutlined />,
            `Conclusiones · ${ejercicio}`,
            C.text,
            <SeccionConclusiones
              analitico={analiticoConcl}
              auxData={auxDataConcl}
              kpisByCode={kpisByCode}
              acumulado={acumulado}
              clientes={clientesConcl}
              totalBruto={totalBrutoConcl}
            />,
          )}

        </Space>
      </div>
    </div>
  )
}
