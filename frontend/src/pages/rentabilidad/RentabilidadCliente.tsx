import { useState, useMemo, useEffect } from 'react'
import {
  Row, Col, Card, Typography, Select, Tag, Table, Input,
  Segmented, Statistic, Tooltip, Space, Alert, Collapse,
  InputNumber, Tabs, Button, List,
} from 'antd'
import {
  SearchOutlined, InfoCircleOutlined,
  RiseOutlined, FallOutlined, WarningOutlined, QuestionCircleOutlined,
  DownloadOutlined, TrophyOutlined, WarningFilled, AlertOutlined,
  CheckCircleOutlined, StarFilled,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { rentabilidadApi } from '../../api/rentabilidad'

const { Title, Text } = Typography

// ── Constantes de clase ───────────────────────────────────────────────────────
const CLASE_COLOR: Record<string, string> = {
  A: '#52c41a', B: '#1890ff', C: '#faad14', D: '#f5222d',
}
const CLASE_BG: Record<string, string> = {
  A: '#f6ffed', B: '#e6f4ff', C: '#fffbe6', D: '#fff1f0',
}
const CLASE_DESC: Record<string, string> = {
  A: 'Alto valor ≥25%', B: 'Rentable 10–25%', C: 'Justo 0–10%', D: 'Destruye margen <0%',
}

// ── Análisis de mercado y acciones por clase ──────────────────────────────────
const ANALISIS_CLASE: Record<string, {
  titulo: string; subtitulo: string; acciones: string[]
}> = {
  A: {
    titulo: 'Clientes de alto valor — Fidelizar y crecer',
    subtitulo: 'Representan el núcleo rentable de la cartera. Coste de sustitución muy alto.',
    acciones: [
      'Contacto personalizado mínimo trimestral: revisión de coberturas y satisfacción.',
      'Cross-sell: identifica ramos premium aún no contratados (RC, Multirriesgos, Accidentes).',
      'No reducir primas ni aumentar cesiones — el margen ya justifica el servicio completo.',
      'Programa de referencias: clientes clase A bien atendidos traen clientes similares.',
      'Monitoriza vencimientos de competencia para captar sus pólizas antes de que lleguen al mercado.',
      'Ofrece servicios de valor añadido (gestoría, asesoría de riesgos) que refuercen la relación.',
    ],
  },
  B: {
    titulo: 'Clientes rentables — Optimizar y ampliar cartera',
    subtitulo: 'Buenos clientes con potencial de mejora. Objetivo: elevarlos a clase A en 1–2 años.',
    acciones: [
      'Ampliar cartera: propón 1–2 ramos de mayor comisión (Multirriesgos, RC, Ingeniería).',
      'Revisa la cesión al auxiliar — puede haber margen de mejora sin perder la relación.',
      'Monitoriza renovaciones para evitar fugas de pólizas clave a la competencia.',
      'Considera incremento moderado de prima en renovación si el cliente no es muy precio-sensible.',
      'Analiza si el auxiliar está aportando valor real o si conviene gestión directa de parte.',
      'Fija un plan de 12 meses con objetivo de margen ≥25% (clase A).',
    ],
  },
  C: {
    titulo: 'Margen justo — Vigilar y mejorar el mix de ramos',
    subtitulo: 'Clientes en zona de riesgo. Sin acción, pueden deteriorarse a clase D.',
    acciones: [
      'Analiza el mix de ramos: sustituye productos básicos (auto, decesos) por premium.',
      'Revisa si la cesión al auxiliar es excesiva respecto al ingreso generado.',
      'Propón ramos con mayor comisión media: RC, Accidentes, Multirriesgos, Transporte.',
      'Si el auxiliar no aporta captación activa, plantea negociar la cesión a la baja.',
      'Establece objetivo de margen mínimo del 10% (clase B) en los próximos 12 meses.',
      'Para clientes con 1 solo ramo: busca ampliar antes de la próxima renovación.',
    ],
  },
  D: {
    titulo: 'Destruyen margen — Acción inmediata',
    subtitulo: 'Cada euro de comisión generado cuesta más de 1 euro en cesión y costes.',
    acciones: [
      'Analiza uno a uno: ¿la pérdida es estructural o puntual (cesión no pagada aún)?',
      'En renovación: solicita incremento de prima o reducción de cobertura para mejorar comisión.',
      'Renegocia la cesión al auxiliar — no puede superar la comisión generada sin pérdida.',
      'Para los de mayor pérdida absoluta: plantea no renovar o derivar a canal de menor coste.',
      'Revisa si la cesión estimada (40%) es la real o si hay descuentos que aún no figuran.',
      'Prioriza actuar en los que mayor pérdida absoluta generan, no solo los de peor porcentaje.',
    ],
  },
}

// ── Calidad de ramos ──────────────────────────────────────────────────────────
function scoreRamo(ramo: string): number {
  const r = ramo.toLowerCase().trim()
  if (
    r.includes('multirriesgo') || r.includes('responsabilidad') || r.includes('r.civil') ||
    r.includes('accidente') || r.includes('transport') || r.includes('ingenier') ||
    r.includes('crédito') || r.includes('credito') || r.includes('construcc') ||
    r.includes('industrial') || r.includes('riesgo') || r.includes('embargo')
  ) return 3
  if (r.includes('auto') || r.includes('deceso') || r.includes('moto') || r.includes('coche'))
    return 1
  return 2
}

function calidadCartera(ramosStr: string): { score: number; label: string; color: string; stars: number } {
  if (!ramosStr) return { score: 0, label: '—', color: '#d9d9d9', stars: 0 }
  const ramos = ramosStr.split(',').map(r => r.trim()).filter(Boolean)
  if (!ramos.length) return { score: 0, label: '—', color: '#d9d9d9', stars: 0 }
  const avg = ramos.reduce((a, r) => a + scoreRamo(r), 0) / ramos.length
  if (avg >= 2.5) return { score: avg, label: 'Premium', color: '#722ed1', stars: 3 }
  if (avg >= 1.8) return { score: avg, label: 'Mixta',   color: '#1890ff', stars: 2 }
  return { score: avg, label: 'Básica', color: '#fa8c16', stars: 1 }
}

// ── Formatters ─────────────────────────────────────────────────────────────────
const fmt   = (v: number | null | undefined) => {
  const n = v ?? 0
  return (n < 0 ? '-' : '') + Math.round(Math.abs(n)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ' €'
}
const fmtP  = (v: number | null | undefined) =>
  v != null && !isNaN(v as number) ? (v as number).toFixed(1).replace('.', ',') + '%' : '—'
const round2 = (v: number) => Math.round(v * 100) / 100

function ClaseTag({ clase, small }: { clase: string; small?: boolean }) {
  return (
    <Tag
      color={clase === 'A' ? 'success' : clase === 'B' ? 'processing' : clase === 'C' ? 'warning' : 'error'}
      style={{ fontWeight: 700, fontSize: small ? 11 : 13, minWidth: 24, textAlign: 'center', margin: 0 }}
    >
      {clase}
    </Tag>
  )
}

// ── Export CSV ────────────────────────────────────────────────────────────────
function exportarCSV(filas: any[], ejercicio: number, tasaCesion: number) {
  const ef = (c: any) => ({
    clase:  c.tiene_cesion_estimada ? c.clase_estimada  : c.clase,
    margen: c.tiene_cesion_estimada ? c.margen_neto_estimado : c.margen_neto,
    pct:    c.tiene_cesion_estimada ? c.margen_pct_estimado  : c.margen_pct,
    cesion: c.tiene_cesion_estimada ? c.cesion_estimada : c.cesion_directa,
  })

  const cabecera = [
    'Cliente', 'Clase', 'Calidad cartera', 'Ramos', 'Auxiliar(es)',
    'Nº recibos', 'Nº ramos',
    'Comisión bruta €', 'Cesión €', 'Cesión estimada (flag)', 'Costes €',
    'Margen neto €', 'Margen %',
    `Cesión estimada ${tasaCesion}% €`, 'Margen estimado €', '% Margen estimado',
  ]

  const filas_csv = filas.map(c => {
    const e   = ef(c)
    const cal = calidadCartera(c.ramos)
    const pct    = (c.margen_pct            ?? 0) as number
    const pctEst = (c.margen_pct_estimado   ?? 0) as number
    return [
      c.tomador, e.clase, cal.label, c.ramos, c.auxiliares,
      c.n_recibos, c.n_ramos,
      c.ingreso_bruto, c.cesion_directa,
      c.tiene_cesion_estimada ? 'Sí' : 'No',
      c.costes_imputados, c.margen_neto,
      pct.toFixed(2).replace('.', ','),
      c.cesion_estimada, c.margen_neto_estimado,
      pctEst.toFixed(2).replace('.', ','),
    ]
  })

  const escapar = (v: any) => {
    const s = String(v ?? '')
    return s.includes(';') || s.includes('"') || s.includes('\n')
      ? `"${s.replace(/"/g, '""')}"`
      : s
  }

  const csv = [cabecera, ...filas_csv]
    .map(fila => fila.map(escapar).join(';'))
    .join('\r\n')

  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `rentabilidad_clientes_${ejercicio}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

// ── Columnas compartidas para tablas de detalle por clase ─────────────────────
function colsDetalle(ef: (c: any) => any) {
  return [
    {
      title: 'Clase', width: 56, align: 'center' as const,
      render: (_: any, row: any) => row.tomador === '__SIN_CLIENTE__'
        ? <Tag color="orange" style={{ fontSize: 10, padding: '0 4px' }}>!</Tag>
        : <ClaseTag clase={ef(row).clase} />,
    },
    {
      title: 'Cliente', dataIndex: 'tomador', ellipsis: true,
      render: (v: string, row: any) => {
        if (v === '__SIN_CLIENTE__') {
          return (
            <div>
              <Space size={4}>
                <WarningOutlined style={{ color: '#fa8c16' }} />
                <Text italic style={{ fontSize: 12, color: '#fa8c16' }}>Sin cliente asignado</Text>
              </Space>
              <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                Ingresos sin recibo vinculado · ver detalle para ver los apuntes
              </Text>
            </div>
          )
        }
        const cal = calidadCartera(row.ramos)
        return (
          <div>
            <Space size={4}>
              <Text strong style={{ fontSize: 12 }}>{v}</Text>
              {row.tiene_cesion_estimada && (
                <Tag color="orange" style={{ fontSize: 10, padding: '0 4px', lineHeight: '16px' }}>est.</Tag>
              )}
            </Space>
            <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
              {row.n_recibos} rec. · {row.auxiliares || '—'} ·{' '}
              {[1,2,3].map(i => (
                <StarFilled key={i} style={{ fontSize: 8, color: i <= cal.stars ? cal.color : '#d9d9d9' }} />
              ))}
              {' '}<span style={{ color: cal.color, fontSize: 10 }}>{cal.label}</span>
            </Text>
          </div>
        )
      },
    },
    {
      title: 'Ramos', dataIndex: 'ramos', ellipsis: true, width: 140,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 11 }}>{v || '—'}</Text>,
    },
    {
      title: 'Com. bruta', dataIndex: 'ingreso_bruto', width: 110, align: 'right' as const,
      sorter: (a: any, b: any) => a.ingreso_bruto - b.ingreso_bruto,
      render: (v: number) => <Text style={{ fontSize: 12 }}>{fmt(v)}</Text>,
    },
    {
      title: 'Cesión', width: 100, align: 'right' as const,
      render: (_: any, row: any) => (
        <Text style={{ color: row.tiene_cesion_estimada ? '#fa8c16' : undefined, fontSize: 12 }}>
          {fmt(row.tiene_cesion_estimada ? row.cesion_estimada : row.cesion_directa)}
          {row.tiene_cesion_estimada ? ' *' : ''}
        </Text>
      ),
    },
    {
      title: 'Costes', dataIndex: 'costes_imputados', width: 95, align: 'right' as const,
      sorter: (a: any, b: any) => a.costes_imputados - b.costes_imputados,
      render: (v: number) => <Text type="secondary" style={{ fontSize: 12 }}>{fmt(v)}</Text>,
    },
    {
      title: 'Margen neto', width: 120, align: 'right' as const,
      defaultSortOrder: 'descend' as const,
      sorter: (a: any, b: any) => ef(a).margen - ef(b).margen,
      render: (_: any, row: any) => {
        const m = ef(row).margen ?? 0
        return (
          <Text strong style={{ color: m >= 0 ? '#52c41a' : '#f5222d', fontSize: 12 }}>
            {m >= 0 ? <RiseOutlined /> : <FallOutlined />} {fmt(m)}
          </Text>
        )
      },
    },
    {
      title: 'Margen %', width: 90, align: 'right' as const,
      sorter: (a: any, b: any) => (ef(a).pct ?? 0) - (ef(b).pct ?? 0),
      render: (_: any, row: any) => {
        const e = ef(row)
        return (
          <Tag color={CLASE_COLOR[e.clase]} style={{ margin: 0, fontWeight: 700, fontSize: 12 }}>
            {fmtP(e.pct)}
          </Tag>
        )
      },
    },
  ]
}

// ── Detalle de recibos por cliente (expandable row) ───────────────────────────
function RecibosClienteExpand({
  row, ejercicio,
}: { row: any; ejercicio: number }) {
  const { data: recibos = [], isLoading, isError, refetch } = useQuery({
    queryKey: ['rent-recibos-cliente', ejercicio, row.tomador],
    queryFn:  () => rentabilidadApi.getRecibosCliente(ejercicio, row.tomador).then(r => r.data),
    staleTime: 60_000,
    retry: 1,
  })

  const recibosArr = recibos as any[]

  // ── Desglose especial para el bucket de ingresos sin recibo ──────────────────
  if (row.tomador === '__SIN_CLIENTE__') {
    const apuntes = recibosArr.map((r: any, i: number) => ({ key: i, ...r }))
    const apuntesCols = [
      {
        title: 'Cuenta', dataIndex: 'numero_cuenta', width: 120,
        render: (v: string) => <Text style={{ fontSize: 11, fontFamily: 'monospace' }}>{v}</Text>,
      },
      {
        title: 'Naturaleza', dataIndex: 'naturaleza', width: 160,
        render: (v: string) => <Tag style={{ fontSize: 10 }}>{v}</Tag>,
      },
      {
        title: 'Concepto', dataIndex: 'concepto', ellipsis: true,
        render: (v: string) => <Text type="secondary" style={{ fontSize: 11 }}>{v}</Text>,
      },
      {
        title: 'Importe', dataIndex: 'ingreso', width: 110, align: 'right' as const,
        render: (v: number) => <Text strong style={{ fontSize: 12 }}>{fmt(v)}</Text>,
      },
    ]
    const totalApuntes = apuntes.reduce((s: number, r: any) => s + (r.ingreso ?? 0), 0)
    return (
      <div style={{ padding: '8px 16px 12px', background: '#fff8f0', borderTop: '2px solid #fa8c16' }}>
        <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>
          Apuntes contables con <Text strong>ingreso sin recibo vinculado</Text> — el código de recibo no aparece en el diario o no existe en el sistema
        </Text>
        {isError ? (
          <Alert type="error" showIcon message="No se pudieron cargar los apuntes"
            action={<Button size="small" onClick={() => refetch()}>Reintentar</Button>} />
        ) : (
          <Table
            dataSource={apuntes}
            columns={apuntesCols}
            loading={isLoading}
            size="small"
            pagination={false}
            scroll={{ x: 600 }}
            locale={{ emptyText: isLoading ? 'Cargando...' : 'Sin apuntes sin recibo' }}
            summary={() => {
              if (isLoading || apuntes.length === 0) return null
              return (
                <Table.Summary.Row style={{ background: '#f5f5f5', fontWeight: 600 }}>
                  <Table.Summary.Cell index={0} colSpan={3}>
                    <Text strong style={{ fontSize: 11 }}>TOTAL</Text>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={3} align="right">
                    <Text strong style={{ fontSize: 12 }}>{fmt(totalApuntes)}</Text>
                  </Table.Summary.Cell>
                </Table.Summary.Row>
              )
            }}
          />
        )}
      </div>
    )
  }

  const totalIngreso = recibosArr.reduce((s: number, r: any) => s + r.ingreso, 0)
  // Misma cesión efectiva que muestra la fila agrupada (real + estimada si no hay 623*)
  const cesionEfectiva = (row.cesion_directa ?? 0) + (row.cesion_estimada ?? 0)
  const ingresoBruto   = row.ingreso_bruto  ?? totalIngreso
  const otrosIngresos  = round2(ingresoBruto - totalIngreso)

  // Distribución proporcional con ajuste en el último recibo para cuadre exacto
  const rawFilas = recibosArr.map((r: any, i: number) => {
    const esEstimada = r.tiene_auxiliar && r.cesion_real < 0.01
    const cesion = round2(totalIngreso > 0 ? cesionEfectiva * (r.ingreso / totalIngreso) : 0)
    const coste  = round2(totalIngreso > 0 ? row.costes_imputados * (r.ingreso / totalIngreso) : 0)
    return { key: i, ...r, esEstimada, cesion, coste }
  })
  // Ajuste de último centavo para que suma coincida exactamente con el total agrupado
  if (rawFilas.length > 0) {
    const last     = rawFilas[rawFilas.length - 1]
    const sumCes   = rawFilas.slice(0, -1).reduce((s: number, f: any) => s + f.cesion, 0)
    const sumCoste = rawFilas.slice(0, -1).reduce((s: number, f: any) => s + f.coste, 0)
    last.cesion = round2(cesionEfectiva - sumCes)
    last.coste  = round2(row.costes_imputados - sumCoste)
  }
  const filas: any[] = rawFilas.map((r: any) => ({
    ...r,
    margen:    round2(r.ingreso - r.cesion - r.coste),
    margenPct: r.ingreso > 0 ? round2((r.ingreso - r.cesion - r.coste) / r.ingreso * 100) : 0,
  }))
  // Fila sintética para ingresos sin recibo vinculado (hace cuadrar la columna de ingreso)
  if (otrosIngresos > 0.01) {
    filas.push({
      key: filas.length, _esAjuste: true,
      codigo: '—', poliza: '—', ramo: 'Sin recibo asignado', compania: '—',
      tiene_auxiliar: false, ingreso: otrosIngresos, cesion_real: 0,
      cesion: 0, coste: 0, esEstimada: false,
      margen: otrosIngresos, margenPct: null,
    })
  }

  const cols = [
    {
      title: 'Código', dataIndex: 'codigo', width: 90, ellipsis: true,
      render: (v: string) => <Text style={{ fontSize: 11 }}>{v}</Text>,
    },
    {
      title: 'Póliza', dataIndex: 'poliza', width: 120, ellipsis: true,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 11 }}>{v}</Text>,
    },
    {
      title: 'Ramo', dataIndex: 'ramo', ellipsis: true,
      render: (v: string) => <Text style={{ fontSize: 11 }}>{v}</Text>,
    },
    {
      title: 'Cía', dataIndex: 'compania', width: 130, ellipsis: true,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 11 }}>{v}</Text>,
    },
    {
      title: 'Ingreso', dataIndex: 'ingreso', width: 90, align: 'right' as const,
      render: (v: number) => <Text style={{ fontSize: 12 }}>{fmt(v)}</Text>,
    },
    {
      title: (
        <Tooltip title="Cesión efectiva del cliente distribuida proporcionalmente al ingreso de cada recibo">
          <span>Cesión <InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 10 }} /></span>
        </Tooltip>
      ),
      key: 'cesion', dataIndex: 'cesion',
      width: 90, align: 'right' as const,
      render: (v: number, r: any) => (
        <span style={{ color: r.esEstimada ? '#fa8c16' : 'inherit', fontSize: 12 }}>
          {fmt(v ?? 0)}{r.esEstimada ? ' *' : ''}
        </span>
      ),
    },
    {
      title: (
        <Tooltip title="Coste operativo distribuido proporcionalmente al ingreso del recibo">
          <span>Coste <InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 10 }} /></span>
        </Tooltip>
      ),
      dataIndex: 'coste', width: 90, align: 'right' as const,
      render: (v: number) => <Text type="secondary" style={{ fontSize: 12 }}>{fmt(v)}</Text>,
    },
    {
      title: 'Margen', dataIndex: 'margen', width: 95, align: 'right' as const,
      render: (v: number) => (
        <Text strong style={{ color: v >= 0 ? '#52c41a' : '#f5222d', fontSize: 12 }}>
          {fmt(v)}
        </Text>
      ),
    },
    {
      title: '% Margen', dataIndex: 'margenPct', width: 80, align: 'right' as const,
      render: (v: number | null) => v == null
        ? <Text type="secondary" style={{ fontSize: 11 }}>—</Text>
        : (
          <Tag color={v >= 25 ? '#52c41a' : v >= 10 ? '#1890ff' : v >= 0 ? '#faad14' : '#f5222d'}
            style={{ margin: 0, fontWeight: 600, fontSize: 11 }}>
            {fmtP(v)}
          </Tag>
        ),
    },
  ]

  return (
    <div style={{ padding: '8px 16px 12px', background: '#fafafa', borderTop: '1px solid #f0f0f0' }}>
      <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>
        Recibos de <Text strong>{row.tomador}</Text> · cesión y coste distribuidos proporcionalmente al ingreso de cada recibo — el total coincide con la fila agrupada
        {row.tiene_cesion_estimada && (
          <span style={{ color: '#fa8c16', marginLeft: 8 }}>
            · cesión = real 623* {fmt(row.cesion_directa ?? 0)} + estimada {fmt(row.cesion_estimada ?? 0)}
            {' '}· * recibo con auxiliar sin cesión registrada
          </span>
        )}
      </Text>
      {isError ? (
        <Alert
          type="error"
          showIcon
          message="No se pudieron cargar los recibos"
          description={`Error al consultar recibos de «${row.tomador}». Comprueba que el servidor está activo.`}
          style={{ marginTop: 4 }}
          action={<Button size="small" onClick={() => refetch()}>Reintentar</Button>}
        />
      ) : (
        <Table
          dataSource={filas}
          columns={cols}
          loading={isLoading}
          size="small"
          pagination={false}
          onRow={(r: any) => r._esAjuste ? { style: { background: '#f5f5f5', fontStyle: 'italic', opacity: 0.75 } } : {}}
          scroll={{ x: 800 }}
          locale={{ emptyText: isLoading ? 'Cargando...' : 'Sin recibos con ingreso registrado' }}
          summary={() => {
            if (isLoading || filas.length === 0) return null
            const tMargen   = round2(ingresoBruto - cesionEfectiva - row.costes_imputados)
            const tMargenPct = ingresoBruto > 0 ? round2(tMargen / ingresoBruto * 100) : 0
            return (
              <Table.Summary.Row style={{ background: '#f5f5f5', fontWeight: 600 }}>
                <Table.Summary.Cell index={0} colSpan={4}>
                  <Text strong style={{ fontSize: 11 }}>TOTAL</Text>
                  {otrosIngresos > 0.01 && (
                    <Tooltip title={`Incluye ${fmt(otrosIngresos)} de ingresos sin recibo asignado (imputados al cliente)`}>
                      <InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 10, marginLeft: 4 }} />
                    </Tooltip>
                  )}
                </Table.Summary.Cell>
                <Table.Summary.Cell index={4} align="right">
                  <Text strong style={{ fontSize: 12 }}>{fmt(ingresoBruto)}</Text>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={5} align="right">
                  <Text strong style={{ fontSize: 12 }}>{fmt(cesionEfectiva)}</Text>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={6} align="right">
                  <Text strong style={{ fontSize: 12 }}>{fmt(row.costes_imputados)}</Text>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={7} align="right">
                  <Text strong style={{ color: tMargen >= 0 ? '#52c41a' : '#f5222d', fontSize: 12 }}>{fmt(tMargen)}</Text>
                </Table.Summary.Cell>
                <Table.Summary.Cell index={8} align="right">
                  <Tag color={tMargenPct >= 25 ? '#52c41a' : tMargenPct >= 10 ? '#1890ff' : tMargenPct >= 0 ? '#faad14' : '#f5222d'}
                    style={{ margin: 0, fontWeight: 600, fontSize: 11 }}>
                    {fmtP(tMargenPct)}
                  </Tag>
                </Table.Summary.Cell>
              </Table.Summary.Row>
            )
          }}
        />
      )}
    </div>
  )
}

// ── Panel de análisis: top perdedores + acciones por clase ────────────────────
function PanelAnalisis({ clientes }: { clientes: any[] }) {
  const [tabActiva, setTabActiva]   = useState('D')
  const [verDetalle, setVerDetalle] = useState<string | null>(null)

  const ef = (c: any) => ({
    clase:  c.tiene_cesion_estimada ? c.clase_estimada      : c.clase,
    margen: c.tiene_cesion_estimada ? (c.margen_neto_estimado ?? c.margen_neto) : c.margen_neto,
    pct:    c.tiene_cesion_estimada ? (c.margen_pct_estimado  ?? c.margen_pct)  : c.margen_pct,
  })

  const cols = colsDetalle(ef)

  const top10perdidas = useMemo(() =>
    [...clientes]
      .filter(c => (ef(c).margen ?? 0) < 0)
      .sort((a, b) => (ef(a).margen ?? 0) - (ef(b).margen ?? 0))
      .slice(0, 10),
    [clientes]
  )

  const porClase = useMemo(() => {
    const r: Record<string, any[]> = { A: [], B: [], C: [], D: [] }
    clientes.forEach(c => { r[ef(c).clase]?.push(c) })
    Object.keys(r).forEach(k => r[k].sort((a, b) => (ef(b).margen ?? 0) - (ef(a).margen ?? 0)))
    return r
  }, [clientes])

  const ClaseIcon = ({ clase }: { clase: string }) => {
    if (clase === 'A') return <TrophyOutlined style={{ color: CLASE_COLOR.A }} />
    if (clase === 'B') return <CheckCircleOutlined style={{ color: CLASE_COLOR.B }} />
    if (clase === 'C') return <WarningOutlined style={{ color: CLASE_COLOR.C }} />
    return <AlertOutlined style={{ color: CLASE_COLOR.D }} />
  }

  const tabItems = [
    {
      key: 'perdedores',
      label: (
        <span>
          <WarningFilled style={{ color: '#f5222d', marginRight: 4 }} />
          Top 10 Pérdidas
        </span>
      ),
      children: (
        <div>
          <Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
            Clientes con mayor pérdida absoluta en euros — acción prioritaria.
            {top10perdidas.length === 0 && ' ¡No hay clientes con margen negativo!'}
          </Text>
          {top10perdidas.length > 0 && (
            <Table
              dataSource={top10perdidas.map((c, i) => ({ key: i, ...c }))}
              size="small"
              pagination={false}
              scroll={{ x: 750 }}
              columns={[
                { title: '#', width: 36, render: (_: any, __: any, i: number) => (
                  <Text strong style={{ color: i < 3 ? '#f5222d' : '#8c8c8c' }}>{i + 1}</Text>
                )},
                ...cols.slice(1),
              ]}
              onRow={() => ({ style: { background: '#fff1f0' } })}
            />
          )}
        </div>
      ),
    },

    ...(['A', 'B', 'C', 'D'] as const).map(k => {
      const lista       = porClase[k] || []
      const an          = ANALISIS_CLASE[k]
      const totalMargen  = lista.reduce((s, c) => s + (ef(c).margen ?? 0), 0)
      const totalIngreso = lista.reduce((s, c) => s + c.ingreso_bruto, 0)
      const pctMedio     = totalIngreso > 0 ? totalMargen / totalIngreso * 100 : 0
      const calDist: Record<string, number> = { Premium: 0, Mixta: 0, Básica: 0 }
      lista.forEach(c => {
        const label = calidadCartera(c.ramos).label
        calDist[label] = (calDist[label] || 0) + 1
      })
      const detalleAbierto = verDetalle === k

      return {
        key: k,
        label: (
          <span>
            <ClaseIcon clase={k} />
            {' '}Clase {k}
            <Tag style={{ marginLeft: 6, fontSize: 11 }} color={CLASE_COLOR[k]}>
              {lista.length}
            </Tag>
          </span>
        ),
        children: (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Row gutter={[16, 12]}>
              <Col xs={24} md={8}>
                <Card size="small" styles={{ body: { padding: 12 } }}
                  style={{ borderTop: `3px solid ${CLASE_COLOR[k]}`, height: '100%' }}>
                  <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 8 }}>
                    MÉTRICAS · Clase {k} — {CLASE_DESC[k]}
                  </Text>
                  <Row gutter={[8, 8]}>
                    <Col span={12}>
                      <Statistic title="Clientes" value={lista.length} valueStyle={{ fontSize: 18 }} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="Com. bruta" value={totalIngreso}
                        formatter={v => fmt(Number(v))} valueStyle={{ fontSize: 14 }} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="Margen total" value={totalMargen}
                        formatter={v => fmt(Number(v))}
                        valueStyle={{ fontSize: 14, color: totalMargen >= 0 ? '#52c41a' : '#f5222d' }} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="Margen medio" value={fmtP(pctMedio)}
                        valueStyle={{ fontSize: 14, color: CLASE_COLOR[k] }} />
                    </Col>
                  </Row>
                  <div style={{ marginTop: 10 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>Calidad de cartera:</Text>
                    <div style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
                      {Object.entries(calDist).map(([label, n]) => n > 0 && (
                        <Tag key={label}
                          color={label === 'Premium' ? 'purple' : label === 'Mixta' ? 'blue' : 'orange'}
                          style={{ fontSize: 11 }}>
                          {label}: {n}
                        </Tag>
                      ))}
                    </div>
                  </div>
                  <div style={{ marginTop: 12, borderTop: '1px solid #f0f0f0', paddingTop: 10 }}>
                    <Button
                      type="link"
                      size="small"
                      style={{ padding: 0, color: CLASE_COLOR[k], fontWeight: 600 }}
                      onClick={() => setVerDetalle(detalleAbierto ? null : k)}
                    >
                      {detalleAbierto
                        ? '▲ Ocultar detalle'
                        : `▼ Ver detalle (${lista.length} clientes)`}
                    </Button>
                  </div>
                </Card>
              </Col>

              <Col xs={24} md={16}>
                <Card size="small" styles={{ body: { padding: 12 } }} style={{ height: '100%' }}>
                  <Text strong style={{ color: CLASE_COLOR[k], display: 'block', marginBottom: 4 }}>
                    {an.titulo}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 10 }}>
                    {an.subtitulo}
                  </Text>
                  <List
                    size="small"
                    dataSource={an.acciones}
                    renderItem={(item, idx) => (
                      <List.Item style={{ padding: '4px 0', borderBottom: 'none' }}>
                        <Space align="start" size={8}>
                          <Text style={{ color: CLASE_COLOR[k], fontWeight: 700, minWidth: 16 }}>
                            {idx + 1}.
                          </Text>
                          <Text style={{ fontSize: 12 }}>{item}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                </Card>
              </Col>
            </Row>

            {detalleAbierto && (
              <Card
                size="small"
                styles={{ body: { padding: 0 } }}
                style={{ borderTop: `2px solid ${CLASE_COLOR[k]}` }}
                title={
                  <Row align="middle" justify="space-between">
                    <Col>
                      <Text strong>
                        Detalle clase {k} · {lista.length} clientes · ordenados por margen (↓)
                      </Text>
                    </Col>
                    <Col>
                      <Button
                        type="link" size="small"
                        style={{ color: CLASE_COLOR[k] }}
                        onClick={() => setVerDetalle(null)}
                      >
                        Cerrar ✕
                      </Button>
                    </Col>
                  </Row>
                }
              >
                <Table
                  dataSource={lista.map((c, i) => ({ key: i, ...c }))}
                  columns={cols}
                  size="small"
                  pagination={{ pageSize: 25, showSizeChanger: true, pageSizeOptions: ['25', '50', '100'] }}
                  scroll={{ x: 860 }}
                  onRow={(row) => ({ style: { background: CLASE_BG[ef(row).clase] } })}
                />
              </Card>
            )}
          </Space>
        ),
      }
    }),
  ]

  return (
    <Card
      size="small"
      title={<Text strong>Análisis por clase y mercado</Text>}
      styles={{ body: { padding: '0 0 8px 0' } }}
    >
      <Tabs
        activeKey={tabActiva}
        onChange={setTabActiva}
        size="small"
        style={{ padding: '0 12px' }}
        items={tabItems}
      />
    </Card>
  )
}

// ── Componente principal ──────────────────────────────────────────────────────
export default function RentabilidadCliente() {
  const [ejercicio, setEjercicio] = useState<number>(2025)
  const [filtroClase, setFiltroClase] = useState<string>('Todos')
  const [busqueda, setBusqueda] = useState('')
  const [vista, setVista] = useState<'todos' | 'top20' | 'bottom20'>('todos')
  const [tasaCesion, setTasaCesion] = useState<number>(40)

  const { data: ejercicios = [] } = useQuery({
    queryKey: ['rent-ejercicios'],
    queryFn: () => rentabilidadApi.getEjercicios().then(r => r.data),
  })

  // Auto-seleccionar el primer ejercicio disponible si el actual no existe en la lista
  useEffect(() => {
    const list = ejercicios as number[]
    if (list.length > 0 && !list.includes(ejercicio)) {
      setEjercicio(list[0])
    }
  }, [ejercicios])

  const { data, isLoading, isError } = useQuery({
    queryKey: ['rent-clientes', ejercicio, tasaCesion],
    queryFn: () => rentabilidadApi.getClientes(ejercicio, undefined, tasaCesion / 100).then(r => r.data),
    enabled: !!ejercicio,
    staleTime: 5 * 60_000,
  })

  const { data: sinTomadorData } = useQuery({
    queryKey: ['rent-sin-tomador', ejercicio],
    queryFn: () => rentabilidadApi.getSinTomador(ejercicio).then(r => r.data),
    enabled: !!ejercicio,
  })

  const clientes: any[] = data?.clientes ?? []
  const top20:    any[] = data?.top20    ?? []
  const bottom20: any[] = data?.bottom20 ?? []
  const resumen         = data?.resumen
  const hayEstimacion   = (resumen?.n_con_cesion_estimada ?? 0) > 0

  const efectivo = (c: any) => ({
    clase:  c.tiene_cesion_estimada ? c.clase_estimada                         : c.clase,
    margen: c.tiene_cesion_estimada ? (c.margen_neto_estimado ?? c.margen_neto) : c.margen_neto,
    pct:    c.tiene_cesion_estimada ? (c.margen_pct_estimado  ?? c.margen_pct)  : c.margen_pct,
    cesion: c.cesion_directa + (c.cesion_estimada ?? 0),
  })

  const claseEfectiva = (c: any): string =>
    c.tiene_cesion_estimada ? c.clase_estimada : c.clase

  const filas = useMemo(() => {
    const base = vista === 'top20' ? top20 : vista === 'bottom20' ? bottom20 : clientes
    return base.filter(c => {
      if (c.tomador === '__SIN_CLIENTE__') return filtroClase === 'Todos' && !busqueda
      const okClase = filtroClase === 'Todos' || claseEfectiva(c) === filtroClase
      const okBus   = !busqueda || c.tomador.toLowerCase().includes(busqueda.toLowerCase())
      return okClase && okBus
    })
  }, [clientes, top20, bottom20, vista, filtroClase, busqueda])

  const isGlobal = vista === 'todos' && filtroClase === 'Todos' && busqueda === ''

  if (isError) {
    return (
      <Alert type="error" showIcon
        message="Error al cargar datos"
        description="No se pudo conectar con el servidor. Comprueba que el backend está activo y vuelve a intentarlo." />
    )
  }

  if (data?.sin_datos) {
    return (
      <Alert type="info" showIcon
        message="Sin datos"
        description="No hay recibos cargados para el ejercicio o no hay datos del modelo analítico. Ejecuta primero el recálculo." />
    )
  }

  // ── Columnas de la tabla principal ────────────────────────────────────────
  const columns = [
    {
      title: 'Clase', dataIndex: 'clase', width: 60, align: 'center' as const,
      render: (_: string, row: any) => {
        if (row.tomador === '__SIN_CLIENTE__')
          return <Tag color="orange" style={{ fontSize: 10, padding: '0 4px' }}>!</Tag>
        const ef = efectivo(row)
        return (
          <Tooltip title={row.tiene_cesion_estimada
            ? `Real: ${row.clase} · Con cesión est. ${tasaCesion}%: ${ef.clase}`
            : CLASE_DESC[ef.clase] ?? ''}>
            <span><ClaseTag clase={ef.clase} /></span>
          </Tooltip>
        )
      },
    },
    {
      title: 'Cliente (tomador)', dataIndex: 'tomador', ellipsis: true,
      render: (v: string, row: any) => {
        if (v === '__SIN_CLIENTE__') {
          return (
            <div>
              <Space size={4}>
                <WarningOutlined style={{ color: '#fa8c16' }} />
                <Text italic style={{ fontSize: 13, color: '#fa8c16' }}>Sin cliente asignado</Text>
              </Space>
              <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                Ingresos sin recibo vinculado · expande para ver los apuntes
              </Text>
            </div>
          )
        }
        const cal = calidadCartera(row.ramos)
        return (
          <div>
            <Space size={4}>
              <Text strong style={{ fontSize: 13 }}>{v}</Text>
              {row.tiene_cesion_estimada && (
                <Tooltip title={`Auxiliar sin cesión registrada. Estimación al ${tasaCesion}%.`}>
                  <Tag color="orange" style={{ fontSize: 10, padding: '0 4px', lineHeight: '16px' }}>
                    cesión est.
                  </Tag>
                </Tooltip>
              )}
            </Space>
            <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
              {row.n_recibos} recibo{row.n_recibos !== 1 ? 's' : ''} ·{' '}
              {row.auxiliares || '—'} ·{' '}
              <Tooltip title={`Calidad de cartera: ${cal.label} (ramos: ${row.ramos || '—'})`}>
                <span style={{ cursor: 'help' }}>
                  {[1, 2, 3].map(i => (
                    <StarFilled key={i} style={{ fontSize: 9, color: i <= cal.stars ? cal.color : '#d9d9d9' }} />
                  ))}
                  {' '}<span style={{ color: cal.color, fontSize: 10 }}>{cal.label}</span>
                </span>
              </Tooltip>
            </Text>
          </div>
        )
      },
    },
    {
      title: 'Ramos', dataIndex: 'ramos', ellipsis: true, width: 150,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 11 }}>{v || '—'}</Text>,
    },
    {
      title: 'Ingresos', dataIndex: 'ingreso_bruto', width: 110, align: 'right' as const,
      sorter: (a: any, b: any) => a.ingreso_bruto - b.ingreso_bruto,
      render: (v: number) => <Text style={{ fontSize: 12 }}>{fmt(v)}</Text>,
    },
    {
      title: (
        <Tooltip title="Cesión normalizada: real (cta. 623) + estimada si el auxiliar aún no ha cobrado">
          <span>Cesión <InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 11 }} /></span>
        </Tooltip>
      ),
      key: 'cesion', width: 110, align: 'right' as const,
      render: (_: any, row: any) => {
        const ef = efectivo(row)
        return row.tiene_cesion_estimada ? (
          <Tooltip title={`Real (623): ${fmt(row.cesion_directa)} + Estimada ${tasaCesion}%: ${fmt(row.cesion_estimada)}`}>
            <Text style={{ color: '#722ed1', fontSize: 12 }}>{fmt(ef.cesion)}</Text>
          </Tooltip>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>{fmt(ef.cesion)}</Text>
        )
      },
    },
    {
      title: (
        <Tooltip title="Costes operativos imputados. Personal/Tech/Bancos → por recibos. Alquiler/Viajes/Impuestos → por comisión neta.">
          <span>Costes <InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 11 }} /></span>
        </Tooltip>
      ),
      dataIndex: 'costes_imputados', width: 110, align: 'right' as const,
      sorter: (a: any, b: any) => a.costes_imputados - b.costes_imputados,
      render: (v: number) => <Text type="secondary" style={{ fontSize: 12 }}>{fmt(v)}</Text>,
    },
    {
      title: 'Margen neto',
      key: 'margen_neto_ef', width: 130, align: 'right' as const,
      sorter: (a: any, b: any) => (efectivo(a).margen ?? 0) - (efectivo(b).margen ?? 0),
      defaultSortOrder: 'descend' as const,
      render: (_: any, row: any) => {
        const ef = efectivo(row)
        const m  = ef.margen ?? 0
        return (
          <Tooltip title={row.tiene_cesion_estimada
            ? `Estimado (cesión ${tasaCesion}%): ${fmt(m)}\nReal (sin cesión): ${fmt(row.margen_neto)}`
            : undefined}>
            <Text strong style={{ color: m >= 0 ? '#52c41a' : '#f5222d', fontSize: 12 }}>
              {m >= 0 ? <RiseOutlined /> : <FallOutlined />} {fmt(m)}
            </Text>
          </Tooltip>
        )
      },
    },
    {
      title: 'Margen %',
      key: 'margen_pct_ef', width: 100, align: 'right' as const,
      sorter: (a: any, b: any) => (efectivo(a).pct ?? 0) - (efectivo(b).pct ?? 0),
      render: (_: any, row: any) => {
        const ef  = efectivo(row)
        const pct = ef.pct ?? 0
        return (
          <Tooltip title={row.tiene_cesion_estimada
            ? `Estimado: ${fmtP(pct)} · Real: ${fmtP(row.margen_pct)}`
            : undefined}>
            <Tag color={CLASE_COLOR[ef.clase]} style={{ margin: 0, fontWeight: 700, fontSize: 12 }}>
              {fmtP(pct)}
            </Tag>
          </Tooltip>
        )
      },
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>

      {/* ── Cabecera ────────────────────────────────────────────────────────── */}
      <Row align="middle" justify="space-between" wrap={false}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>Rentabilidad por cliente</Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Datos idénticos al modelo analítico · Costes imputados por driver (recibos / comisión neta)
          </Text>
        </Col>
        <Col>
          <Space size={16} align="center">
            <Space size={6} align="center">
              <Tooltip title="Tasa de cesión estimada para clientes con auxiliar sin cesión registrada">
                <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
                  Cesión est. <QuestionCircleOutlined />
                </Text>
              </Tooltip>
              <InputNumber
                value={tasaCesion}
                onChange={v => setTasaCesion(v ?? 40)}
                min={0} max={100} step={5}
                formatter={v => `${v}%`}
                parser={v => Number((v || '').replace('%', ''))}
                style={{ width: 80 }}
                size="small"
              />
            </Space>
            <Select
              value={ejercicio}
              onChange={setEjercicio}
              loading={isLoading}
              style={{ width: 100 }}
              options={(ejercicios as number[]).map(e => ({ value: e, label: String(e) }))}
            />
          </Space>
        </Col>
      </Row>

      {/* ── KPIs ────────────────────────────────────────────────────────────── */}
      {resumen && (
        <>
          <Row gutter={[12, 12]}>
            <Col xs={24}>
              <Card size="small" styles={{ body: { padding: '12px 16px' } }}>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 8 }}>
                  DISTRIBUCIÓN · {resumen.n_clientes} clientes
                </Text>
                <Row gutter={8}>
                  {(['A', 'B', 'C', 'D'] as const).map(k => (
                    <Col span={6} key={k}>
                      <div
                        onClick={() => setFiltroClase(filtroClase === k ? 'Todos' : k)}
                        style={{
                          cursor: 'pointer', textAlign: 'center', padding: '6px 4px',
                          borderRadius: 6, border: `2px solid ${filtroClase === k ? CLASE_COLOR[k] : 'transparent'}`,
                          background: CLASE_BG[k],
                        }}
                      >
                        <div style={{ fontSize: 22, fontWeight: 900, color: CLASE_COLOR[k], lineHeight: 1.2 }}>
                          {resumen.por_clase?.[k] ?? 0}
                        </div>
                        <div style={{ fontSize: 10, color: CLASE_COLOR[k], fontWeight: 700 }}>{k}</div>
                        <div style={{ fontSize: 10, color: '#8c8c8c' }}>{CLASE_DESC[k]}</div>
                      </div>
                    </Col>
                  ))}
                </Row>
              </Card>
            </Col>
          </Row>

          {/* ── Tabla desglose de cesión ─────────────────────────────────────── */}
          {(() => {
            const totalIng   = resumen.comision_bruta_total ?? 0
            const ingConAux  = resumen.ing_con_auxiliar ?? 0
            const cesReal    = resumen.cesion_total ?? 0
            const cesEst     = resumen.cesion_estimada_total ?? 0
            const cesNorm    = resumen.ces_normalizada_total ?? 0
            const ingEstBase = resumen.ing_estimado_base ?? 0
            const pctT = (n: number) => totalIng > 0 ? `${((n / totalIng) * 100).toFixed(1)}%` : '—'
            const filas = [
              { key:'1', concepto: 'Ingresos totales del ejercicio',             importe: totalIng,  pct: '100.0%',         color: undefined,  bold: false },
              { key:'2', concepto: 'Ingresos de recibos con auxiliar',           importe: ingConAux, pct: pctT(ingConAux),  color: undefined,  bold: false },
              { key:'3', concepto: 'Cesión real registrada (cta. 623)',          importe: cesReal,   pct: pctT(cesReal),    color: '#1677ff',  bold: false },
              { key:'4', concepto: `Cesión estimada ${tasaCesion}% (aux. sin 623)`, importe: cesEst, pct: ingEstBase > 0 ? `${tasaCesion}%` : '—', color: '#fa8c16', bold: false },
              { key:'5', concepto: 'Cesión normalizada (real + estimada)',       importe: cesNorm,   pct: pctT(cesNorm),    color: '#722ed1',  bold: true  },
            ]
            const cols = [
              {
                title: 'Concepto', dataIndex: 'concepto',
                render: (_: string, r: typeof filas[0]) => (
                  <Text strong={r.bold} style={{ color: r.color, fontSize: 12 }}>{r.concepto}</Text>
                ),
              },
              {
                title: 'Importe', dataIndex: 'importe', align: 'right' as const, width: 130,
                render: (v: number, r: typeof filas[0]) => (
                  <Text strong={r.bold} style={{ color: r.color, fontSize: 12 }}>{fmt(v)}</Text>
                ),
              },
              {
                title: '% s/ingresos', dataIndex: 'pct', align: 'right' as const, width: 100,
                render: (v: string, r: typeof filas[0]) => (
                  <Text type="secondary" strong={r.bold} style={{ fontSize: 12 }}>{v}</Text>
                ),
              },
            ]
            return (
              <Card size="small" styles={{ body: { padding: '12px 16px' } }}>
                <Text style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 8 }}>
                  DESGLOSE DE CESIÓN · {ejercicio}
                </Text>
                <Table
                  dataSource={filas} columns={cols} size="small"
                  pagination={false} showHeader={true}
                  rowClassName={(r) => r.key === '5' ? 'ant-table-row-selected' : ''}
                  style={{ fontSize: 12 }}
                />
              </Card>
            )
          })()}

          {hayEstimacion && (
            <Card size="small" style={{ borderColor: '#fa8c16', borderWidth: 1.5 }}
              styles={{ body: { padding: '12px 16px' } }}>
              <Text style={{ fontSize: 12, color: '#fa8c16', fontWeight: 600, display: 'block', marginBottom: 10 }}>
                CON CESIÓN ESTIMADA ({tasaCesion}%) · {resumen.n_con_cesion_estimada} cliente{resumen.n_con_cesion_estimada !== 1 ? 's' : ''} con auxiliar sin cesión registrada
              </Text>
              <Row gutter={[8, 4]} align="middle" wrap>
                <Col>
                  <Tooltip title="Total cesiones directas contabilizadas en el ejercicio">
                    <div>
                      <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>Cesión real calculada</Text>
                      <Text strong style={{ fontSize: 14 }}>{fmt(resumen.cesion_total ?? 0)}</Text>
                    </div>
                  </Tooltip>
                </Col>
                <Col><Text style={{ color: '#bfbfbf', fontSize: 18, margin: '0 6px', lineHeight: '40px' }}>+</Text></Col>
                <Col>
                  <Tooltip title={`Ingresos de recibos con auxiliar sin cesión registrada × ${tasaCesion}%`}>
                    <div>
                      <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>Estimada devengada ({tasaCesion}%)</Text>
                      <Text strong style={{ fontSize: 14, color: '#fa8c16' }}>{fmt(resumen.cesion_estimada_total ?? 0)}</Text>
                    </div>
                  </Tooltip>
                </Col>
                <Col><Text style={{ color: '#bfbfbf', fontSize: 18, margin: '0 6px', lineHeight: '40px' }}>=</Text></Col>
                <Col>
                  <Tooltip title="Cuadra con la cesión normalizada del modelo analítico (devengado puro del ejercicio)">
                    <div>
                      <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>Cesión normalizada total ✓</Text>
                      <Text strong style={{ fontSize: 16, color: '#722ed1' }}>{fmt(resumen.ces_normalizada_total ?? 0)}</Text>
                    </div>
                  </Tooltip>
                </Col>
              </Row>
            </Card>
          )}
        </>
      )}

      {/* ── Tabla principal ──────────────────────────────────────────────────── */}
      <Card
        size="small"
        styles={{ body: { padding: 0 } }}
        title={
          <Row gutter={12} align="middle" wrap={false}>
            <Col>
              <Segmented value={vista} onChange={v => setVista(v as any)} size="small"
                options={[
                  { label: 'Todos', value: 'todos' },
                  { label: 'Top 20 ▲', value: 'top20' },
                  { label: 'Bottom 20 ▼', value: 'bottom20' },
                ]}
              />
            </Col>
            <Col>
              <Space size={4}>
                {(['Todos', 'A', 'B', 'C', 'D'] as const).map(k => (
                  <Tag key={k}
                    color={k === 'Todos' ? undefined : CLASE_COLOR[k]}
                    style={{ cursor: 'pointer', fontWeight: filtroClase === k ? 700 : 400,
                      opacity: filtroClase !== 'Todos' && filtroClase !== k ? 0.45 : 1 }}
                    onClick={() => setFiltroClase(filtroClase === k ? 'Todos' : k)}
                  >
                    {k}
                  </Tag>
                ))}
              </Space>
            </Col>
            <Col flex="auto">
              <Input prefix={<SearchOutlined style={{ color: '#bbb' }} />}
                placeholder="Buscar cliente…" value={busqueda}
                onChange={e => setBusqueda(e.target.value)}
                allowClear size="small" style={{ maxWidth: 220 }} />
            </Col>
            <Col>
              <Tooltip title="Exportar tabla visible a CSV (abre en Excel)">
                <Button
                  icon={<DownloadOutlined />}
                  size="small"
                  onClick={() => exportarCSV(filas, ejercicio, tasaCesion)}
                  disabled={filas.length === 0}
                >
                  Excel
                </Button>
              </Tooltip>
            </Col>
          </Row>
        }
      >
        {hayEstimacion && (
          <div style={{ padding: '6px 12px', background: '#fffbe6', borderBottom: '1px solid #ffe58f', fontSize: 12 }}>
            <Text type="secondary">
              <span style={{ color: '#fa8c16', fontWeight: 600 }}>cesión est.</span>
              {' '}= auxiliar sin cesión registrada. El valor mostrado ya incluye la estimación al {tasaCesion}%.
              Pasa el ratón sobre el margen para ver el valor real (sin cesión).
              {' · '}▶ Expande la fila para ver los recibos del cliente.
            </Text>
          </div>
        )}
        <Table
          dataSource={filas.map((c, i) => ({ key: i, ...c }))}
          columns={columns}
          size="small"
          loading={isLoading}
          pagination={{ pageSize: 50, showSizeChanger: true, pageSizeOptions: ['25', '50', '100'] }}
          scroll={{ x: 900 }}
          expandable={{
            expandedRowRender: (row) => (
              <RecibosClienteExpand row={row} ejercicio={ejercicio} />
            ),
            rowExpandable: () => true,
            columnWidth: 36,
          }}
          onRow={(row) => ({
            style: {
              background: row.tomador === '__SIN_CLIENTE__'
                ? '#fff8f0'
                : row.tiene_cesion_estimada ? '#fffbf0' : CLASE_BG[row.clase] ?? '',
            },
          })}
          summary={() => filas.length > 0 ? (
            <Table.Summary.Row style={{ fontWeight: 700, background: '#f5f5f5' }}>
              <Table.Summary.Cell index={0} />
              <Table.Summary.Cell index={1} colSpan={3}>
                <Text strong>{filas.filter(c => c.tomador !== '__SIN_CLIENTE__').length} clientes</Text>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={4} align="right">
                <Text strong>{fmt(isGlobal ? (resumen?.comision_bruta_total ?? 0) : filas.reduce((s, c) => s + c.ingreso_bruto, 0))}</Text>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={5} align="right">
                <Text strong>{fmt(isGlobal ? (resumen?.ces_normalizada_total ?? 0) : filas.reduce((s, c) => s + (efectivo(c).cesion ?? 0), 0))}</Text>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={6} align="right">
                <Text strong>{fmt(isGlobal ? (resumen?.costes_total ?? 0) : filas.reduce((s, c) => s + c.costes_imputados, 0))}</Text>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={7} align="right">
                {(() => {
                  const total = isGlobal
                    ? (resumen?.margen_neto_normalizado ?? ((resumen?.comision_bruta_total ?? 0) - (resumen?.ces_normalizada_total ?? 0) - (resumen?.costes_total ?? 0) - (resumen?.mkt_total ?? 0) - (resumen?.sin_mapear_total ?? 0)))
                    : filas.reduce((s, c) => s + (efectivo(c).margen ?? 0), 0)
                  return <Text strong style={{ color: total >= 0 ? '#52c41a' : '#f5222d' }}>{fmt(total)}</Text>
                })()}
              </Table.Summary.Cell>
              <Table.Summary.Cell index={8} />
            </Table.Summary.Row>
          ) : null}
        />
      </Card>

      {/* ── Panel de análisis ─────────────────────────────────────────────────── */}
      {clientes.length > 0 && (
        <PanelAnalisis clientes={clientes} />
      )}

      {/* ── Recibos sin tomador ───────────────────────────────────────────────── */}
      {sinTomadorData && (
        <Collapse size="small" items={[{
          key: '1',
          label: (
            <Space>
              <WarningOutlined style={{ color: sinTomadorData.n_recibos > 0 ? '#faad14' : '#52c41a' }} />
              <Text strong>
                {sinTomadorData.n_recibos > 0
                  ? `${sinTomadorData.n_recibos} recibo${sinTomadorData.n_recibos !== 1 ? 's' : ''} sin tomador · ${fmt(sinTomadorData.ingreso_sin_tomador)} (${sinTomadorData.pct_sobre_total?.toFixed(1)}% del total)`
                  : 'Todos los recibos tienen tomador identificado ✓'}
              </Text>
            </Space>
          ),
          children: (
            <Table
              dataSource={(sinTomadorData.recibos || []).map((r: any, i: number) => ({ key: i, ...r }))}
              columns={[
                { title: 'Código', dataIndex: 'codigo', width: 100 },
                { title: 'Póliza', dataIndex: 'numero_poliza', width: 130, ellipsis: true },
                { title: 'Compañía', dataIndex: 'compania', ellipsis: true },
                { title: 'Ramo', dataIndex: 'ramo', width: 140, ellipsis: true },
                { title: 'Auxiliar', dataIndex: 'auxiliar', width: 160, ellipsis: true },
                { title: 'Desde', dataIndex: 'desde', width: 90 },
                { title: 'Hasta', dataIndex: 'hasta', width: 90 },
                { title: 'Ingreso', dataIndex: 'ingreso_analitico', width: 100, align: 'right' as const,
                  render: (v: number) => <Text strong>{fmt(v)}</Text> },
                { title: 'Tomador actual', dataIndex: 'tomador_actual', width: 140,
                  render: (v: string) => v ? <Tag color="orange">{v}</Tag> : <Tag color="red">Sin tomador</Tag> },
              ]}
              size="small"
              pagination={{ pageSize: 20 }}
              scroll={{ x: 900 }}
            />
          ),
        }]} />
      )}
    </Space>
  )
}
