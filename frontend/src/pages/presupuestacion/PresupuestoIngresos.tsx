import { useState, useEffect, useRef, useMemo } from 'react'
import * as XLSX from 'xlsx'
import {
  Card, Table, Button, Tag, Space, Typography, Row, Col, Statistic,
  Select, InputNumber, Tooltip, Popconfirm,
  message, Drawer, Descriptions, Divider, Modal, Input, Switch, Alert,
  Radio, Progress,
} from 'antd'
import {
  ThunderboltOutlined, CheckCircleOutlined, WarningOutlined,
  EditOutlined, InfoCircleOutlined, PlusCircleOutlined,
  ControlOutlined, LoadingOutlined, DownloadOutlined, UploadOutlined, UnlockOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { presupuestoApi } from '../../api/presupuesto'
import { apiError } from '../../utils/errorHandler'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip,
  CartesianGrid, Cell,
} from 'recharts'

const { Title, Text } = Typography
const { Option } = Select

const MESES_LABELS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
  'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

const fmt = (v: number) => v?.toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' €'
const pct = (v: number) => (v >= 0 ? '+' : '') + (v ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%'
const fmtK = (v: number) => {
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + 'M €'
  if (Math.abs(v) >= 1_000) return (v / 1_000).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'k €'
  return v.toFixed(0) + ' €'
}

const EJERCICIOS = [2023, 2024, 2025, 2026]

function calcularFinalPreview(modelo: number, mercado: number, coef: number, manual: number | null) {
  if (manual !== null && manual !== undefined) return manual
  if (mercado <= modelo) return modelo
  return modelo + (mercado - modelo) * coef
}

function OrigenTag({ row }: { row: any }) {
  if (row.crecimiento_manual !== null && row.crecimiento_manual !== undefined) {
    return <Tag color="orange" style={{ fontSize: 11, padding: '0 4px' }}>Manual</Tag>
  }
  const mercado = row.crecimiento_mercado ?? 0
  const modelo = row.crecimiento_modelo ?? 0
  if (mercado > modelo) {
    return (
      <Tooltip title={`Mdo (${pct(mercado)}) > Mod (${pct(modelo)}) → ajuste aplicado`}>
        <Tag color="cyan" style={{ fontSize: 11, padding: '0 4px' }}>Mdo↑</Tag>
      </Tooltip>
    )
  }
  return (
    <Tooltip title={`Mercado ≤ modelo → se usa modelo estadístico`}>
      <Tag color="green" style={{ fontSize: 11, padding: '0 4px' }}>Modelo</Tag>
    </Tooltip>
  )
}

export default function PresupuestoIngresos() {
  const qc = useQueryClient()
  const [presupuestoId, setPresupuestoId] = useState<string | null>(null)
  const [ejercicioNuevo, setEjercicioNuevo] = useState<number>(2025)
  const [generarResult, setGenerarResult] = useState<{ lineas: number; tiempo_segundos: number } | null>(null)
  const [elapsedGenerar, setElapsedGenerar] = useState(0)
  const startTimeGenerarRef = useRef<number | null>(null)
  const timerGenerarRef = useRef<number | null>(null)
  const [lineaEditar, setLineaEditar] = useState<any>(null)
  const [drawerVisible, setDrawerVisible] = useState(false)
  const [coefDrawerVisible, setCoefDrawerVisible] = useState(false)
  const [filtroCompania, setFiltroCompania] = useState<string | undefined>()
  const [filtroRamo, setFiltroRamo] = useState<string | undefined>()
  const [drilldownMesIdx, setDrilldownMesIdx] = useState<number | null>(null)
  const [formValues, setFormValues] = useState<any>({})

  // Estado del drawer masivo
  const [diagModalVisible, setDiagModalVisible] = useState(false)
  const [diagCompania, setDiagCompania] = useState<string>('Reale')
  const [atipicosLinea, setAtipicosLinea] = useState<any>(null)
  const [atipicosModalVisible, setAtipicosModalVisible] = useState(false)

  const [coefScope, setCoefScope] = useState<'todos' | 'compania' | 'ramo'>('todos')
  const [coefCompania, setCoefCompania] = useState<string | undefined>()
  const [coefRamo, setCoefRamo] = useState<string | undefined>()
  const [coefValor, setCoefValor] = useState<number>(0.75)
  const [coefActualizarMercado, setCoefActualizarMercado] = useState(false)
  const [coefTasaCartera, setCoefTasaCartera] = useState<number | null>(null)

  const { data: presupuestos = [] } = useQuery({
    queryKey: ['presupuestos'],
    queryFn: () => presupuestoApi.listar().then(r => r.data),
  })

  const { data: lineas = [], isLoading } = useQuery({
    queryKey: ['ingresos', presupuestoId],
    queryFn: () => presupuestoApi.listarIngresos(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: resumen } = useQuery({
    queryKey: ['resumen-ingresos', presupuestoId],
    queryFn: () => presupuestoApi.resumenIngresos(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: mercadoRef } = useQuery({
    queryKey: ['mercado-ref', presupuestoId],
    queryFn: () => presupuestoApi.mercadoReferencia(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const iniciar = useMutation({
    mutationFn: () => presupuestoApi.iniciar(ejercicioNuevo),
    onSuccess: (res) => {
      message.success(`Presupuesto ${ejercicioNuevo} iniciado`)
      qc.invalidateQueries({ queryKey: ['presupuestos'] })
      setPresupuestoId(res.data.id)
    },
    onError: (e) => message.error(apiError(e, 'Error al iniciar')),
  })

  const generar = useMutation({
    mutationFn: () => presupuestoApi.generarIngresos(presupuestoId!),
    onSuccess: (res) => {
      const tiempo_segundos = startTimeGenerarRef.current
        ? Math.round((Date.now() - startTimeGenerarRef.current) / 1000)
        : (res.data.tiempo_segundos ?? 0)
      setGenerarResult({ lineas: res.data.lineas, tiempo_segundos })
      qc.invalidateQueries({ queryKey: ['ingresos', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['resumen-ingresos', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al generar')),
  })

  const actualizar = useMutation({
    mutationFn: (datos: object) => presupuestoApi.actualizarIngreso(presupuestoId!, lineaEditar.id, datos),
    onSuccess: () => {
      message.success('Línea actualizada')
      qc.invalidateQueries({ queryKey: ['ingresos', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['resumen-ingresos', presupuestoId] })
      setDrawerVisible(false)
    },
    onError: (e) => message.error(apiError(e, 'Error al actualizar')),
  })

  const aprobar = useMutation({
    mutationFn: () => presupuestoApi.aprobarIngresos(presupuestoId!),
    onSuccess: () => {
      message.success('Presupuesto de ingresos aprobado')
      qc.invalidateQueries({ queryKey: ['presupuestos'] })
      qc.invalidateQueries({ queryKey: ['ingresos', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al aprobar')),
  })

  const reabrir = useMutation({
    mutationFn: () => presupuestoApi.reabrirIngresos(presupuestoId!),
    onSuccess: () => {
      message.success('Presupuesto de ingresos reabierto')
      qc.invalidateQueries({ queryKey: ['presupuestos'] })
      qc.invalidateQueries({ queryKey: ['ingresos', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al reabrir')),
  })

  const [importResult, setImportResult] = useState<{ importadas: number; errores: string[] } | null>(null)
  const importInputRef = useRef<HTMLInputElement>(null)

  const importar = useMutation({
    mutationFn: (file: File) => presupuestoApi.importarIngresos(presupuestoId!, file),
    onSuccess: (res) => {
      setImportResult(res.data)
      qc.invalidateQueries({ queryKey: ['ingresos', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['resumen-ingresos', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al importar')),
  })

  const handleImportChange = (e: { target: HTMLInputElement }) => {
    const file = e.target.files?.[0]
    if (file) { setImportResult(null); importar.mutate(file) }
    e.target.value = ''
  }

  const { data: diagData, isFetching: diagLoading } = useQuery({
    queryKey: ['diagnostico-ingresos', presupuestoId, diagCompania],
    queryFn: () => presupuestoApi.diagnosticoIngresos(presupuestoId!, diagCompania).then(r => r.data),
    enabled: !!presupuestoId && diagModalVisible && !!diagCompania,
  })

  const { data: atipicosData, isFetching: atipicosLoading } = useQuery({
    queryKey: ['atipicos-linea', presupuestoId, atipicosLinea?.id],
    queryFn: () => presupuestoApi.atipicosLinea(presupuestoId!, atipicosLinea.id).then(r => r.data),
    enabled: !!presupuestoId && !!atipicosLinea?.id && atipicosModalVisible,
  })

  const aplicarCoef = useMutation({
    mutationFn: () => presupuestoApi.aplicarCoeficiente(presupuestoId!, {
      coeficiente_prudencia: coefValor,
      compania: coefScope === 'compania' ? coefCompania : undefined,
      ramo: coefScope === 'ramo' ? coefRamo : undefined,
      actualizar_mercado: coefActualizarMercado,
      tasa_caida_cartera: coefTasaCartera ?? undefined,
    }),
    onSuccess: (res) => {
      message.success(res.data.mensaje)
      qc.invalidateQueries({ queryKey: ['ingresos', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['resumen-ingresos', presupuestoId] })
      setCoefDrawerVisible(false)
    },
    onError: (e) => message.error(apiError(e, 'Error al aplicar parámetros')),
  })

  // Timer generar
  useEffect(() => {
    if (generar.isPending) {
      setElapsedGenerar(0)
      startTimeGenerarRef.current = Date.now()
      timerGenerarRef.current = window.setInterval(() => {
        setElapsedGenerar(Math.floor((Date.now() - startTimeGenerarRef.current!) / 1000))
      }, 500)
    } else {
      if (timerGenerarRef.current) { clearInterval(timerGenerarRef.current); timerGenerarRef.current = null }
    }
    return () => { if (timerGenerarRef.current) clearInterval(timerGenerarRef.current) }
  }, [generar.isPending])

  const presupuestoActual = (presupuestos as any[]).find((p: any) => p.id === presupuestoId)
  const ingresosAprobados = !!presupuestoId && !!presupuestoActual && presupuestoActual.estado !== 'borrador'
  const anoBase = presupuestoActual ? presupuestoActual.ejercicio - 1 : new Date().getFullYear() - 1
  const anoPpto = presupuestoActual ? presupuestoActual.ejercicio : new Date().getFullYear()

  const abrirEditar = (linea: any) => {
    setLineaEditar(linea)
    setFormValues({
      tasa_caida: linea.tasa_caida,
      crecimiento_modelo: linea.crecimiento_modelo,
      crecimiento_mercado: linea.crecimiento_mercado,
      coeficiente_prudencia: linea.coeficiente_prudencia,
      crecimiento_manual: linea.crecimiento_manual,
      notas: linea.notas ?? '',
    })
    setDrawerVisible(true)
  }

  const lineasFiltradas = (lineas as any[]).filter((l: any) => {
    if (filtroCompania && l.compania !== filtroCompania) return false
    if (filtroRamo && l.ramo !== filtroRamo) return false
    return true
  })

  const companias = [...new Set((lineas as any[]).map((l: any) => l.compania))].filter(Boolean) as string[]
  const ramos = [...new Set((lineas as any[]).map((l: any) => l.ramo))].filter(Boolean) as string[]

  // Para cada fila cartera, lookup de la parte NP 2025 (base del compañero NP de la misma clave)
  const npBaseMap = useMemo(() => {
    const map: Record<string, number> = {}
    ;(lineas as any[]).forEach((l: any) => {
      if (l.tipo_negocio === 'nueva_produccion') {
        map[`${l.compania}|${l.ramo}|${l.auxiliar}`] = l.ingreso_base_anual || 0
      }
    })
    return map
  }, [lineas])

  // Resumen desde lineas
  const baseCartera     = (lineas as any[]).reduce((s, l) => l.tipo_negocio === 'cartera'          ? s + (l.ingreso_base_anual  || 0) : s, 0)
  const baseNuevaProd   = (lineas as any[]).reduce((s, l) => l.tipo_negocio === 'nueva_produccion' ? s + (l.ingreso_base_anual  || 0) : s, 0)
  const baseLimpiaCartera = (lineas as any[]).reduce((s, l) => l.tipo_negocio === 'cartera'        ? s + (l.ingreso_base_limpio || 0) : s, 0)
  // caída aplicada sobre la base limpia (sin atípicos)
  const caidaCarteraVal = (lineas as any[]).reduce((s, l) => l.tipo_negocio === 'cartera'
    ? s + (l.ingreso_base_limpio || 0) * (l.tasa_caida || 0) / 100 : s, 0)
  // superviviente real = base_limpia × (1 − tasa_caida%) — calculado en backend
  const supervivienteCartera = (lineas as any[]).reduce((s, l) => l.tipo_negocio === 'cartera'
    ? s + (l.base_superviviente || 0) : s, 0)
  const totalPresupuestoCartera = (lineas as any[]).reduce((s, l) => l.tipo_negocio === 'cartera'          ? s + (l.total_anual || 0) : s, 0)
  const totalPresupuestoNP      = (lineas as any[]).reduce((s, l) => l.tipo_negocio === 'nueva_produccion' ? s + (l.total_anual || 0) : s, 0)
  const totalPresupuestoGeneral = totalPresupuestoCartera + totalPresupuestoNP

  const inicialCartera2026 = baseCartera
  const caidaTotal = caidaCarteraVal  // NP no tiene caída

  // Crecimiento = Ppto 2026 − Superviviente (lo que aporta crec_final sobre los supervivientes)
  // Con suelo 0% en cartera, crecimiento_cartera_amount ≥ 0 siempre
  const crecimiento_cartera_amount = totalPresupuestoCartera - supervivienteCartera
  const crecimiento_np_amount      = totalPresupuestoNP      - baseNuevaProd
  const crecimiento_total_amount   = crecimiento_cartera_amount + crecimiento_np_amount

  const supervTotal = supervivienteCartera + baseNuevaProd  // NP superviviente = base completa (sin caída)

  // % crecimiento = importe / superviviente
  const pctCrec_cartera = supervivienteCartera > 0 ? crecimiento_cartera_amount / supervivienteCartera * 100 : 0
  const pctCrec_np      = baseNuevaProd        > 0 ? crecimiento_np_amount      / baseNuevaProd        * 100 : 0
  const pctCrec_total   = supervTotal          > 0 ? crecimiento_total_amount   / supervTotal          * 100 : 0

  const atipicosCartera = (lineas as any[]).reduce((s: number, l: any) => l.tipo_negocio === 'cartera'          ? s + (l.atipicos_excluidos || 0) : s, 0)
  const atipicosNP      = (lineas as any[]).reduce((s: number, l: any) => l.tipo_negocio === 'nueva_produccion' ? s + (l.atipicos_excluidos || 0) : s, 0)
  // % caída relativo a la base limpia → da exactamente la tasa configurada
  const pctCaidaCartera = baseLimpiaCartera > 0 ? (caidaCarteraVal / baseLimpiaCartera * 100) : 0
  const pctCaidaTotal   = (baseLimpiaCartera + baseNuevaProd) > 0 ? (caidaTotal / (baseLimpiaCartera + baseNuevaProd) * 100) : 0

  // % desviación = (Final 2026 - Base 2025) / Base 2025
  const base2025Cartera = baseCartera - baseNuevaProd   // cartera real 2025 (sin NP)
  const base2025Total   = baseCartera                   // total 2025 = total_combinado
  const desvCartera = base2025Cartera > 0 ? ((totalPresupuestoCartera - base2025Cartera) / base2025Cartera) * 100 : 0
  const desvNP      = baseNuevaProd > 0   ? ((totalPresupuestoNP - baseNuevaProd) / baseNuevaProd) * 100 : 0
  const desvTotal   = base2025Total > 0   ? ((totalPresupuestoGeneral - base2025Total) / base2025Total) * 100 : 0

  const datosGrafico = MESES_LABELS.map((mes, i) => ({
    mes,
    importe: resumen?.mensual?.[i] || 0,
  }))

  const drilldownLineas = drilldownMesIdx !== null
    ? lineasFiltradas
        .map((l: any) => ({ ...l, importe_mes: l.importes_mensuales?.[drilldownMesIdx] || 0 }))
        .filter((l: any) => l.importe_mes > 0)
        .sort((a: any, b: any) => b.importe_mes - a.importe_mes)
    : []

  // Preview drawer masivo
  const lineasPreviewCoef = (lineas as any[]).filter((l: any) => {
    if (l.bloqueado) return false
    if (coefScope === 'compania' && coefCompania && l.compania !== coefCompania) return false
    if (coefScope === 'ramo' && coefRamo && l.ramo !== coefRamo) return false
    return true
  }).map((l: any) => {
    const tcNuevo = l.tipo_negocio === 'nueva_produccion'
      ? 0
      : (coefTasaCartera !== null ? coefTasaCartera : l.tasa_caida)
    const finalNuevo = calcularFinalPreview(l.crecimiento_modelo ?? 0, l.crecimiento_mercado ?? 0, coefValor, l.crecimiento_manual)
    return { ...l, tc_nuevo: tcNuevo, final_nuevo: finalNuevo }
  })

  const exportarExcel = () => {
    const filas = lineasFiltradas.map((l: any) => {
      const base = l.ingreso_base_anual || 0
      const total = l.total_anual || 0
      const delta = base > 0 ? ((total - base) / base) * 100 : 0
      const row: Record<string, any> = {
        'Compañía':          l.compania || '',
        'Ramo':              l.ramo || '',
        'Auxiliar':          l.auxiliar || '',
        'Línea':             l.tipo_negocio === 'cartera' ? 'Cartera 2026' : 'N.Prod 2026',
        'Base 2025 (€)':     base,
        'Atíp. excluidos (€)': l.atipicos_excluidos || 0,
        'Base limpia (€)':   l.ingreso_base_limpio || 0,
        '% Caída':           l.tasa_caida || 0,
        'Superviviente (€)': l.base_superviviente || 0,
        '% Crec. modelo':    l.crecimiento_modelo || 0,
        '% Ref. mercado':    l.crecimiento_mercado || 0,
        '% Crec. final':     l.crecimiento_final || 0,
        'Total 2026 (€)':    total,
        'Δ vs base (%)':     Math.round(delta * 100) / 100,
      }
      MESES_LABELS.forEach((mes, i) => {
        row[mes] = l.importes_mensuales?.[i] ?? 0
      })
      return row
    })

    const ws = XLSX.utils.json_to_sheet(filas)
    const colWidths = [
      { wch: 18 }, { wch: 14 }, { wch: 16 }, { wch: 13 },
      { wch: 14 }, { wch: 16 }, { wch: 14 }, { wch: 10 },
      { wch: 15 }, { wch: 13 }, { wch: 13 }, { wch: 12 },
      { wch: 14 }, { wch: 12 },
      ...MESES_LABELS.map(() => ({ wch: 12 })),
    ]
    ws['!cols'] = colWidths
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Ppto Ingresos')
    XLSX.writeFile(wb, `presupuesto_ingresos_${anoPpto}.xlsx`)
  }

  // Colores de cabecera por sección para agrupar visualmente sin usar children
  const hBase   = { style: { background: '#f5f5f5', fontSize: 11 } }
  const hCaida  = { style: { background: '#fff1f0', color: '#cf1322', fontSize: 11 } }
  const hCrec   = { style: { background: '#e6f4ff', color: '#0958d9', fontSize: 11 } }
  const hPpto   = { style: { background: '#f9f0ff', color: '#531dab', fontSize: 11 } }

  const columnas: any[] = [
    // ── IDENTIFICACIÓN ──────────────────────────────────────────────────────
    {
      title: 'Compañía', dataIndex: 'compania', width: 105, fixed: 'left' as const, ellipsis: true,
      sorter: (a: any, b: any) => (a.compania || '').localeCompare(b.compania || ''),
    },
    { title: 'Ramo', dataIndex: 'ramo', width: 82, ellipsis: true },
    {
      title: 'Auxiliar', dataIndex: 'auxiliar', width: 95, ellipsis: true,
      render: (v: string) => v === 'Sin auxiliar'
        ? <Text type="secondary" style={{ fontSize: 11 }}>—</Text>
        : <span style={{ fontSize: 11 }}>{v}</span>,
    },
    {
      title: 'Línea 2026', dataIndex: 'tipo_negocio', width: 92,
      filters: [{ text: 'Cartera 2026', value: 'cartera' }, { text: 'Nueva Prod. 2026', value: 'nueva_produccion' }],
      onFilter: (value: any, record: any) => record.tipo_negocio === value,
      render: (v: string) => {
        const isCart = v === 'cartera'
        const isNP = v === 'nueva_produccion'
        return (
          <Tooltip title={isCart
            ? 'Base = Cartera 2025 + NP 2025 (todo el negocio vigente pasa a cartera). Aplica tasa de caída.'
            : 'Base = NP 2025 (captación del año anterior). Sin caída — negocio nuevo.'}>
            <Tag color={isCart ? 'blue' : isNP ? 'green' : 'default'} style={{ fontSize: 11, padding: '0 4px', cursor: 'help' }}>
              {isCart ? 'Cartera 26' : isNP ? 'N.Prod 26' : '—'}
            </Tag>
          </Tooltip>
        )
      },
    },

    // ── BASE 2025 (gris) ─────────────────────────────────────────────────────
    {
      title: <Tooltip title="Importe real 2025. Cartera 26 = Cartera+NP 2025. N.Prod 26 = solo NP 2025."><span>Base 2025 ①</span></Tooltip>,
      dataIndex: 'ingreso_base_anual', width: 125, align: 'right' as const,
      onHeaderCell: () => hBase,
      sorter: (a: any, b: any) => a.ingreso_base_anual - b.ingreso_base_anual,
      render: (v: number, row: any) => {
        const npPart = npBaseMap[`${row.compania}|${row.ramo}|${row.auxiliar}`] || 0
        const isCart = row.tipo_negocio === 'cartera'
        const tip = isCart
          ? (npPart > 0 ? `Cart. 2025: ${fmt(v - npPart)}  +  NP 2025: ${fmt(npPart)}` : 'Solo cartera 2025')
          : 'Nueva Producción 2025'
        return (
          <Tooltip title={tip}>
            <Space direction="vertical" size={0} style={{ alignItems: 'flex-end', cursor: 'help' }}>
              <span style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{fmt(v)}</span>
              <span style={{ fontSize: 10, color: isCart ? '#8c8c8c' : '#52c41a' }}>
                {isCart ? (npPart > 0 ? 'Cart.+NP 2025' : 'Cart. 2025') : 'NP 2025'}
              </span>
            </Space>
          </Tooltip>
        )
      },
    },
    {
      title: <Tooltip title="Meses atípicos excluidos (z-score>2σ). Base limpia = Base bruta − Atípicos."><span>Atíp. excluidos</span></Tooltip>,
      dataIndex: 'atipicos_excluidos', width: 90, align: 'right' as const,
      onHeaderCell: () => hBase,
      render: (v: number, row: any) => row.tiene_atipicos
        ? <Tooltip title={`Base limpia: ${fmt(row.ingreso_base_limpio)}`}>
            <Tag color="orange" style={{ fontSize: 11, cursor: 'help' }}><WarningOutlined /> -{fmtK(v)}</Tag>
          </Tooltip>
        : <Text type="secondary" style={{ fontSize: 11 }}>—</Text>,
    },

    // ── (−) CAÍDA (rojo) ─────────────────────────────────────────────────────
    {
      title: <Tooltip title="% de la base limpia que se pierde por anulaciones en renovación (ref. ICEA). Solo líneas Cartera."><span>② % Caída</span></Tooltip>,
      dataIndex: 'tasa_caida', width: 72, align: 'center' as const,
      onHeaderCell: () => hCaida,
      render: (v: number, row: any) => row.tipo_negocio === 'nueva_produccion'
        ? <Text type="secondary" style={{ fontSize: 11 }}>Sin caída</Text>
        : <Tag color={v >= 15 ? 'red' : v >= 10 ? 'orange' : 'default'} style={{ fontSize: 11, padding: '0 4px' }}>{(v ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</Tag>,
    },
    {
      title: <Tooltip title="Base limpia × (1 − % caída). Sobre este importe se aplica el crecimiento."><span>③ Superviviente</span></Tooltip>,
      dataIndex: 'base_superviviente', width: 120, align: 'right' as const,
      onHeaderCell: () => hCaida,
      render: (v: number, row: any) => {
        const bl = row.ingreso_base_limpio || 0
        const caida = bl * (row.tasa_caida || 0) / 100
        const tip = row.tipo_negocio === 'nueva_produccion'
          ? `Sin caída → igual a base limpia = ${fmt(bl)}`
          : `${fmt(bl)} − ${fmt(caida)} (${(row.tasa_caida || 0).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%) = ${fmt(v)}`
        return (
          <Tooltip title={tip}>
            <span style={{ whiteSpace: 'nowrap', fontSize: 12, color: '#d46b08', cursor: 'help' }}>{fmt(v)}</span>
          </Tooltip>
        )
      },
    },

    // ── (×) CRECIMIENTO (azul) ───────────────────────────────────────────────
    {
      title: <Tooltip title="Crecimiento estadístico calculado (interanual histórico o OLS intraanual)."><span>④ Modelo estad.</span></Tooltip>,
      dataIndex: 'crecimiento_modelo', width: 100, align: 'right' as const,
      onHeaderCell: () => hCrec,
      render: (v: number, row: any) => {
        const m = row.metodo_modelo || ''
        const color = m.startsWith('Interanual') ? 'blue' : m.startsWith('OLS') ? 'orange' : 'default'
        const nEj = m.match(/\d+/)?.[0]
        return (
          <Tooltip title={m || 'Sin método'}>
            <Space direction="vertical" size={0} style={{ alignItems: 'flex-end', cursor: 'help' }}>
              <span style={{ fontSize: 12 }}>{pct(v)}</span>
              <Tag color={color} style={{ fontSize: 9, padding: '0 3px', margin: 0, lineHeight: '14px' }}>
                {m.startsWith('Interanual') ? `IAn${nEj ? ` (${nEj}ej.)` : ''}` : m.startsWith('OLS') ? 'OLS' : '—'}
              </Tag>
            </Space>
          </Tooltip>
        )
      },
    },
    {
      title: <Tooltip title={`Ref. mercado ICEA${mercadoRef ? ` ${mercadoRef.anyo}` : ''}. Solo aplica si supera al modelo.`}><span>Ref. mercado</span></Tooltip>,
      dataIndex: 'crecimiento_mercado', width: 82, align: 'right' as const,
      onHeaderCell: () => hCrec,
      render: (v: number, row: any) => (
        <span style={{ fontSize: 12, color: v > (row.crecimiento_modelo ?? 0) ? '#08979c' : '#8c8c8c', whiteSpace: 'nowrap' }}>
          {pct(v)}{v > (row.crecimiento_modelo ?? 0) && ' ↑'}
        </span>
      ),
    },
    {
      title: <Tooltip title="Crecimiento final aplicado. Coef prudencia 0.5: se recorre la mitad del camino entre modelo y mercado. Manual sobreescribe todo."><span>⑤ Crec. final</span></Tooltip>,
      width: 115, align: 'right' as const,
      onHeaderCell: () => hCrec,
      render: (_: any, row: any) => {
        const modeloNegFinalPos = (row.crecimiento_modelo ?? 0) < 0 && (row.crecimiento_final ?? 0) > 0
        const modeloNegSuelo = (row.crecimiento_modelo ?? 0) < 0 && (row.crecimiento_final ?? 0) === 0
        const tooltipVolteado = modeloNegFinalPos
          ? `Modelo estadístico negativo (${(row.crecimiento_modelo ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%) ajustado por mercado (${(row.crecimiento_mercado ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%) con coef 0,5. Revisa si hay razón comercial.`
          : modeloNegSuelo
          ? `Modelo estadístico negativo (${(row.crecimiento_modelo ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%) y blend resultó negativo: suelo en 0%. Usa override manual si tienes plan comercial.`
          : undefined
        return (
          <Space direction="vertical" size={0} style={{ alignItems: 'flex-end' }}>
            <Space size={3} style={{ justifyContent: 'flex-end' }}>
              {(modeloNegFinalPos || modeloNegSuelo) && (
                <Tooltip title={tooltipVolteado}>
                  <span style={{ fontSize: 11, color: modeloNegFinalPos ? '#d46b08' : '#8c8c8c', cursor: 'help' }}>
                    {modeloNegFinalPos ? '⚠' : '⌀'}
                  </span>
                </Tooltip>
              )}
              <Tag color={row.crecimiento_final > 0 ? 'green' : row.crecimiento_final < 0 ? 'red' : 'default'} style={{ fontSize: 11, margin: 0 }}>
                {pct(row.crecimiento_final ?? 0)}
              </Tag>
            </Space>
            <div style={{ marginTop: 1 }}><OrigenTag row={row} /></div>
          </Space>
        )
      },
    },

    // ── PRESUPUESTO 2026 (morado) ────────────────────────────────────────────
    {
      title: '⑥ Total 2026', dataIndex: 'total_anual', width: 125, align: 'right' as const,
      onHeaderCell: () => hPpto,
      sorter: (a: any, b: any) => a.total_anual - b.total_anual,
      render: (v: number) => <Text strong style={{ whiteSpace: 'nowrap', fontSize: 13, color: '#531dab' }}>{fmt(v)}</Text>,
    },
    {
      title: <Tooltip title="(Total 2026 − Base 2025) / Base 2025. Efecto combinado de caída + crecimiento."><span>Δ vs base 2025</span></Tooltip>,
      width: 85, align: 'right' as const,
      onHeaderCell: () => hPpto,
      render: (_: any, row: any) => {
        const base = row.ingreso_base_anual || 0
        const delta = base > 0 ? ((row.total_anual - base) / base) * 100 : 0
        return <Tag color={delta >= 0 ? 'green' : 'red'} style={{ fontSize: 11 }}>{pct(delta)}</Tag>
      },
    },

    // ── EDITAR (fija derecha) ────────────────────────────────────────────────
    {
      title: '', width: 42, fixed: 'right' as const,
      render: (_: any, row: any) => (
        <Button size="small" icon={<EditOutlined />} disabled={row.bloqueado} onClick={() => abrirEditar(row)} />
      ),
    },
  ]

  const drilldownCols = [
    { title: 'Compañía', dataIndex: 'compania', width: 120, ellipsis: true },
    { title: 'Ramo', dataIndex: 'ramo', width: 90, ellipsis: true },
    { title: 'Tipo', dataIndex: 'tipo_negocio', width: 80,
      render: (v: string) => <Tag color={v === 'cartera' ? 'blue' : 'green'} style={{ fontSize: 11 }}>{v === 'cartera' ? 'Cartera' : 'N. Prod'}</Tag> },
    { title: 'Importe', dataIndex: 'importe_mes', width: 120, align: 'right' as const,
      render: (v: number) => <Text strong style={{ whiteSpace: 'nowrap' }}>{fmt(v)}</Text>,
      defaultSortOrder: 'descend' as const, sorter: (a: any, b: any) => a.importe_mes - b.importe_mes },
  ]

  const coefPreviewCols = [
    { title: 'Compañía', dataIndex: 'compania', ellipsis: true, width: 110 },
    { title: 'Ramo', dataIndex: 'ramo', ellipsis: true, width: 85 },
    { title: 'Tipo', dataIndex: 'tipo_negocio', width: 65,
      render: (v: string) => <Tag color={v === 'cartera' ? 'blue' : v === 'nueva_produccion' ? 'green' : 'default'} style={{ fontSize: 10 }}>{v === 'cartera' ? 'Cart' : v === 'nueva_produccion' ? 'Nva' : '—'}</Tag> },
    { title: 'Caída', dataIndex: 'tc_nuevo', width: 75, align: 'right' as const,
      render: (v: number, row: any) => row.tipo_negocio === 'nueva_produccion'
        ? <Tag color="default" style={{ fontSize: 10, color: '#8c8c8c' }}>Sin caída</Tag>
        : <Tag color={v >= 20 ? 'red' : v >= 12 ? 'orange' : 'default'} style={{ fontSize: 10 }}>{(v ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</Tag> },
    { title: 'Final%', dataIndex: 'final_nuevo', width: 70, align: 'right' as const,
      render: (v: number) => <Tag color={v > 0 ? 'green' : 'red'} style={{ fontSize: 10 }}>{pct(v)}</Tag> },
  ]

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {/* Cabecera */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <Title level={5} style={{ margin: 0 }}>Presupuesto de ingresos</Title>
          <Text type="secondary" style={{ fontSize: 12 }}>Proyección anual mensualizada desde el ejercicio base</Text>
        </div>
        <Space wrap size={4}>
          <Select placeholder="Selecciona ejercicio" style={{ width: 200 }} onChange={setPresupuestoId} value={presupuestoId} size="small">
            {(presupuestos as any[]).map((p: any) => (
              <Option key={p.id} value={p.id}>
                Ejercicio {p.ejercicio} — <Tag color={p.estado === 'borrador' ? 'default' : 'blue'} style={{ fontSize: 11 }}>{p.estado}</Tag>
              </Option>
            ))}
          </Select>
          <Divider type="vertical" />
          <Select value={ejercicioNuevo} onChange={setEjercicioNuevo} style={{ width: 90 }} size="small">
            {EJERCICIOS.map(e => <Option key={e} value={e}>{e}</Option>)}
          </Select>
          <Tooltip title="Requiere carga base del ejercicio anterior cerrada">
            <Button size="small" icon={<PlusCircleOutlined />} onClick={() => iniciar.mutate()} loading={iniciar.isPending}>Iniciar</Button>
          </Tooltip>
          <Divider type="vertical" />
          {presupuestoId && !ingresosAprobados && (
            <Button
              size="small"
              icon={generar.isPending ? <LoadingOutlined spin /> : <ThunderboltOutlined />}
              onClick={() => { setGenerarResult(null); generar.mutate() }}
              loading={false}
              disabled={generar.isPending}
            >
              {generar.isPending ? `Generando... ${elapsedGenerar}s` : 'Generar / Regenerar'}
            </Button>
          )}
          {presupuestoId && !ingresosAprobados && (
            <>
              <input ref={importInputRef} type="file" accept=".xlsx,.xls" style={{ display: 'none' }} onChange={handleImportChange} />
              <Button size="small" icon={<UploadOutlined />} loading={importar.isPending} onClick={() => importInputRef.current?.click()}>
                Importar Excel
              </Button>
            </>
          )}
          {presupuestoId && (
            <Button size="small" icon={<SearchOutlined />} onClick={() => setDiagModalVisible(true)}>Diagnóstico</Button>
          )}
          {(lineas as any[]).length > 0 && !ingresosAprobados && (
            <Button size="small" icon={<ControlOutlined />} onClick={() => setCoefDrawerVisible(true)}>Parámetros masivos</Button>
          )}
          {(lineas as any[]).length > 0 && !ingresosAprobados && (
            <Popconfirm title="¿Aprobar el presupuesto de ingresos?" description="Las líneas quedarán bloqueadas." onConfirm={() => aprobar.mutate()} okText="Aprobar" cancelText="Cancelar">
              <Button size="small" type="primary" icon={<CheckCircleOutlined />} loading={aprobar.isPending}>Aprobar</Button>
            </Popconfirm>
          )}
          {ingresosAprobados && (
            <>
              <Tag color="blue" icon={<CheckCircleOutlined />}>Aprobado</Tag>
              <Popconfirm
                title="¿Reabrir el presupuesto de ingresos?"
                description="Las líneas quedarán desbloqueadas para edición. Si gastos o cierre estaban aprobados también se desbloquearán."
                onConfirm={() => reabrir.mutate()}
                okText="Reabrir"
                okButtonProps={{ danger: true }}
                cancelText="Cancelar"
              >
                <Button size="small" icon={<UnlockOutlined />} loading={reabrir.isPending} danger>
                  Reabrir
                </Button>
              </Popconfirm>
            </>
          )}
        </Space>
      </div>

      {/* Progreso generación */}
      {generar.isPending && (
        <Card style={{ background: '#f0f7ff', border: '2px solid #91caff', borderRadius: 8 }}>
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Space>
              <LoadingOutlined style={{ color: '#1677ff', fontSize: 18 }} spin />
              <Text strong style={{ color: '#1677ff', fontSize: 15 }}>Generando presupuesto de ingresos...</Text>
            </Space>
            <Progress
              percent={Math.min(elapsedGenerar * 10, 90)}
              showInfo={false}
              strokeColor={{ '0%': '#1677ff', '100%': '#52c41a' }}
            />
            <Row gutter={24}>
              <Col span={12}>
                <Statistic title="Tiempo transcurrido" value={elapsedGenerar} suffix="s"
                  valueStyle={{ color: '#1677ff', fontSize: 22 }} />
              </Col>
              <Col span={12}>
                <Statistic
                  title="Tiempo estimado restante"
                  value={elapsedGenerar > 3 ? Math.max(0, Math.round(elapsedGenerar * 0.5)) : '—'}
                  suffix={elapsedGenerar > 3 ? 's' : ''}
                  valueStyle={{ fontSize: 22 }}
                />
              </Col>
            </Row>
            <Text type="secondary" style={{ fontSize: 12 }}>Calculando modelo estadístico, cruzando histórico y proyectando importes mensuales...</Text>
          </Space>
        </Card>
      )}

      {/* Resultado generación */}
      {generarResult && !generar.isPending && (
        <Card
          style={{ background: '#f6ffed', border: '2px solid #b7eb8f', borderRadius: 8 }}
          title={
            <Space>
              <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
              <Text strong style={{ color: '#389e0d' }}>
                Presupuesto generado en {generarResult.tiempo_segundos}s
              </Text>
            </Space>
          }
          extra={
            <Button size="small" onClick={() => setGenerarResult(null)}>Cerrar</Button>
          }
        >
          <Statistic
            title="Líneas de ingresos generadas"
            value={generarResult.lineas}
            valueStyle={{ fontSize: 22, color: '#52c41a' }}
          />
        </Card>
      )}

      {/* Resultado importación */}
      {importResult && !importar.isPending && (
        <Card
          style={{ background: '#f6ffed', border: '2px solid #b7eb8f', borderRadius: 8 }}
          title={
            <Space>
              <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
              <Text strong style={{ color: '#389e0d' }}>
                Importación completada — {importResult.importadas} líneas cargadas
              </Text>
            </Space>
          }
          extra={<Button size="small" onClick={() => setImportResult(null)}>Cerrar</Button>}
        >
          {importResult.errores.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message={`${importResult.errores.length} fila${importResult.errores.length > 1 ? 's' : ''} con error`}
              description={
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                  {importResult.errores.slice(0, 10).map((e, i) => <li key={i}>{e}</li>)}
                  {importResult.errores.length > 10 && <li>…y {importResult.errores.length - 10} más</li>}
                </ul>
              }
            />
          )}
        </Card>
      )}

      {/* Resumen por tipo de negocio */}
      {(lineas as any[]).length > 0 && (
        <Card
          title={<span style={{ fontSize: 13, fontWeight: 600 }}>Resumen presupuesto por tipo de negocio</span>}
          style={{ borderRadius: 10, boxShadow: '0 1px 6px rgba(0,0,0,0.07)' }}
          bodyStyle={{ padding: '0 0 12px 0' }}
          extra={mercadoRef && <Text type="secondary" style={{ fontSize: 11 }}>Ref. mercado: ICEA/UNESPA {mercadoRef.anyo} · No Vida +{(mercadoRef.no_vida_pct ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</Text>}
        >
          <div style={{ overflowX: 'auto', padding: '4px 0' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <colgroup>
                <col style={{ minWidth: 150 }} />
                <col style={{ minWidth: 115 }} />
                <col style={{ minWidth: 115 }} />
                <col style={{ minWidth: 155 }} />
                <col style={{ minWidth: 160 }} />
                <col style={{ minWidth: 125 }} />
                <col style={{ minWidth: 110 }} />
              </colgroup>
              <thead>
                <tr>
                  <th style={{ padding: '10px 16px', background: '#fafafa', borderBottom: '2px solid #e8e8e8', textAlign: 'left', color: '#8c8c8c', fontWeight: 500, fontSize: 11 }} />
                  <th style={{ padding: '10px 16px', background: '#fafafa', borderBottom: '2px solid #e8e8e8', textAlign: 'right', color: '#595959', fontWeight: 600, fontSize: 12 }}>
                    Base {anoBase}
                  </th>
                  <th style={{ padding: '10px 16px', background: '#fafafa', borderBottom: '2px solid #e8e8e8', textAlign: 'right', color: '#595959', fontWeight: 600, fontSize: 12 }}>
                    <Tooltip title={`Punto de partida ${anoPpto}: la NP ${anoBase} pasa a ser cartera. Atípicos excluidos del cálculo: ${fmtK(atipicosCartera + atipicosNP)}.`}>
                      <span style={{ borderBottom: '1px dashed #bfbfbf', cursor: 'help' }}>Inicial {anoPpto}</span>
                    </Tooltip>
                  </th>
                  <th style={{ padding: '10px 16px', background: '#fafafa', borderBottom: '2px solid #e8e8e8', textAlign: 'right', color: '#595959', fontWeight: 600, fontSize: 12 }}>
                    (−) Caída anulaciones
                  </th>
                  <th style={{ padding: '10px 16px', background: '#fafafa', borderBottom: '2px solid #e8e8e8', textAlign: 'right', color: '#595959', fontWeight: 600, fontSize: 12 }}>
                    (+) Crecimiento
                  </th>
                  <th style={{ padding: '10px 16px', background: '#fafafa', borderBottom: '2px solid #e8e8e8', textAlign: 'right', color: '#595959', fontWeight: 700, fontSize: 12 }}>
                    = Final {anoPpto}
                  </th>
                  <th style={{ padding: '10px 16px', background: '#fafafa', borderBottom: '2px solid #e8e8e8', textAlign: 'center', color: '#595959', fontWeight: 600, fontSize: 12 }}>
                    % {anoPpto} vs {anoBase}
                  </th>
                </tr>
              </thead>
              <tbody>
                {/* ── Cartera ── */}
                <tr style={{ borderBottom: '1px solid #f0f0f0' }}>
                  <td style={{ padding: '14px 16px', verticalAlign: 'middle', fontWeight: 600, fontSize: 13, color: '#262626' }}>Cartera</td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 600, fontSize: 14, color: '#262626' }}>
                    {fmtK(baseCartera - baseNuevaProd)}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 600, fontSize: 14, color: '#262626' }}>
                    <Tooltip title={`Cartera ${anoBase} (${fmtK(baseCartera - baseNuevaProd)}) + NP ${anoBase} (${fmtK(baseNuevaProd)}) = ${fmtK(inicialCartera2026)}`}>
                      <span style={{ borderBottom: '1px dashed #d9d9d9', cursor: 'help' }}>{fmtK(inicialCartera2026)}</span>
                    </Tooltip>
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 600, fontSize: 14, color: '#cf1322', whiteSpace: 'nowrap' }}>
                    {pctCaidaCartera.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% / −{fmtK(caidaCarteraVal)}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 600, fontSize: 14, whiteSpace: 'nowrap', color: crecimiento_cartera_amount >= 0 ? '#389e0d' : '#cf1322' }}>
                    {pct(pctCrec_cartera)} / {crecimiento_cartera_amount >= 0 ? '+' : ''}{fmtK(crecimiento_cartera_amount)}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 700, fontSize: 15, color: '#1677ff' }}>
                    {fmtK(totalPresupuestoCartera)}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'center', verticalAlign: 'middle' }}>
                    <span style={{ fontWeight: 600, fontSize: 13, color: desvCartera >= 0 ? '#389e0d' : '#cf1322' }}>
                      {pct(desvCartera)}
                    </span>
                  </td>
                </tr>

                {/* ── Nueva Producción ── */}
                {baseNuevaProd > 0 && (
                  <tr style={{ borderBottom: '1px solid #f0f0f0' }}>
                    <td style={{ padding: '14px 16px', verticalAlign: 'middle', fontWeight: 600, fontSize: 13, color: '#262626' }}>Nueva Producción</td>
                    <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 600, fontSize: 14, color: '#262626' }}>
                      {fmtK(baseNuevaProd)}
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 600, fontSize: 14, color: '#262626' }}>
                      {fmtK(baseNuevaProd)}
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'center', verticalAlign: 'middle', color: '#8c8c8c', fontSize: 12 }}>
                      —
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 600, fontSize: 14, whiteSpace: 'nowrap', color: crecimiento_np_amount >= 0 ? '#389e0d' : '#cf1322' }}>
                      {pct(pctCrec_np)} / {crecimiento_np_amount >= 0 ? '+' : ''}{fmtK(crecimiento_np_amount)}
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 700, fontSize: 15, color: '#389e0d' }}>
                      {fmtK(totalPresupuestoNP)}
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'center', verticalAlign: 'middle' }}>
                      <span style={{ fontWeight: 600, fontSize: 13, color: desvNP >= 0 ? '#389e0d' : '#cf1322' }}>
                        {pct(desvNP)}
                      </span>
                    </td>
                  </tr>
                )}

                {/* ── Total ── */}
                <tr style={{ background: '#fafafa', borderTop: '2px solid #d9d9d9' }}>
                  <td style={{ padding: '14px 16px', verticalAlign: 'middle', fontWeight: 700, fontSize: 13, color: '#262626' }}>Total</td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 700, fontSize: 14, color: '#262626' }}>
                    {fmtK(baseCartera)}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 700, fontSize: 14, color: '#262626' }}>
                    {fmtK(inicialCartera2026 + baseNuevaProd)}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 700, fontSize: 14, color: '#cf1322', whiteSpace: 'nowrap' }}>
                    {pctCaidaTotal.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}% / −{fmtK(caidaTotal)}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 700, fontSize: 14, whiteSpace: 'nowrap', color: crecimiento_total_amount >= 0 ? '#389e0d' : '#cf1322' }}>
                    {pct(pctCrec_total)} / {crecimiento_total_amount >= 0 ? '+' : ''}{fmtK(crecimiento_total_amount)}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 700, fontSize: 16, color: '#531dab' }}>
                    {fmtK(totalPresupuestoGeneral)}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'center', verticalAlign: 'middle' }}>
                    <span style={{ fontWeight: 700, fontSize: 14, color: desvTotal >= 0 ? '#389e0d' : '#cf1322' }}>
                      {pct(desvTotal)}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <Divider style={{ margin: '8px 0 4px 0' }} />
          <Row gutter={[16, 4]} style={{ padding: '0 14px 4px' }}>
            <Col xs={12} sm={8}><Statistic title={<span style={{ fontSize: 11, color: '#8c8c8c' }}>Líneas de presupuesto</span>} value={(lineas as any[]).length} valueStyle={{ fontSize: 16, fontWeight: 600 }} /></Col>
            <Col xs={12} sm={8}><Statistic title={<span style={{ fontSize: 11, color: '#1677ff' }}>Líneas cartera</span>} value={(lineas as any[]).filter((l:any) => l.tipo_negocio === 'cartera').length} valueStyle={{ fontSize: 16, fontWeight: 600, color: '#1677ff' }} /></Col>
            <Col xs={12} sm={8}><Statistic title={<span style={{ fontSize: 11, color: '#52c41a' }}>Líneas nueva producción</span>} value={(lineas as any[]).filter((l:any) => l.tipo_negocio === 'nueva_produccion').length} valueStyle={{ fontSize: 16, fontWeight: 600, color: '#52c41a' }} /></Col>
          </Row>
        </Card>
      )}

      {/* Gráfico mensual */}
      {resumen && (
        <Card size="small" title={<Text style={{ fontSize: 12 }}>Distribución mensual — pulsa una barra para ver detalle</Text>} bodyStyle={{ padding: '8px 12px' }}>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={datosGrafico} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="mes" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
              <RTooltip formatter={(v: number) => fmt(v)} />
              <Bar dataKey="importe" name="Ingresos" radius={[3, 3, 0, 0]} cursor="pointer"
                onClick={(_d: any, index: number) => setDrilldownMesIdx(index)}>
                {datosGrafico.map((_, i) => (
                  <Cell key={i} fill={drilldownMesIdx === i ? '#0050b3' : '#1890ff'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Tabla */}
      {(lineas as any[]).length > 0 && (
        <Card size="small" bodyStyle={{ padding: 0 }}
          extra={
            <Space size={4}>
              <Select allowClear placeholder="Compañía" style={{ width: 150 }} size="small" onChange={setFiltroCompania} value={filtroCompania}>
                {companias.map(c => <Option key={c} value={c}>{c}</Option>)}
              </Select>
              <Select allowClear placeholder="Ramo" style={{ width: 120 }} size="small" onChange={setFiltroRamo} value={filtroRamo}>
                {ramos.map(r => <Option key={r} value={r}>{r}</Option>)}
              </Select>
              <Text type="secondary" style={{ fontSize: 11 }}>{lineasFiltradas.length} líneas</Text>
              <Button
                size="small"
                icon={<DownloadOutlined />}
                onClick={exportarExcel}
                disabled={lineasFiltradas.length === 0}
              >
                Excel
              </Button>
            </Space>
          }>
          <Table dataSource={lineasFiltradas} columns={columnas} rowKey="id" loading={isLoading}
            size="small" scroll={{ x: 1380 }}
            pagination={{ pageSize: 25, showTotal: (t) => `${t} líneas`, size: 'small' }}
            style={{ fontSize: 12 }}
            onRow={(record: any) => ({ style: record.tipo_negocio === 'nueva_produccion' ? { background: '#f6ffed' } : {} })}
            summary={(data) => {
              // Índices columnas planas: 0=Cía 1=Ramo 2=Aux 3=Línea 4=Base 5=Atíp 6=%Caída 7=Superv 8=Modelo 9=Mercado 10=CrecFinal 11=Total 12=Delta 13=Edit
              const base  = (data as any[]).reduce((s, r) => s + (r.ingreso_base_anual  || 0), 0)
              const superv = (data as any[]).reduce((s, r) => s + (r.base_superviviente || 0), 0)
              const total  = (data as any[]).reduce((s, r) => s + (r.total_anual        || 0), 0)
              const delta  = base > 0 ? ((total - base) / base) * 100 : 0
              return (
                <Table.Summary.Row style={{ background: '#fafafa', fontWeight: 600 }}>
                  <Table.Summary.Cell index={0} colSpan={4}><Text strong style={{ fontSize: 12 }}>TOTAL FILTRADO</Text></Table.Summary.Cell>
                  <Table.Summary.Cell index={4} align="right"><span style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{fmt(base)}</span></Table.Summary.Cell>
                  <Table.Summary.Cell index={5} />
                  <Table.Summary.Cell index={6} />
                  <Table.Summary.Cell index={7} align="right"><span style={{ whiteSpace: 'nowrap', fontSize: 12, color: '#d46b08' }}>{fmt(superv)}</span></Table.Summary.Cell>
                  <Table.Summary.Cell index={8} /><Table.Summary.Cell index={9} /><Table.Summary.Cell index={10} />
                  <Table.Summary.Cell index={11} align="right"><Text strong style={{ whiteSpace: 'nowrap', fontSize: 13, color: '#531dab' }}>{fmt(total)}</Text></Table.Summary.Cell>
                  <Table.Summary.Cell index={12} align="right"><Tag color={delta >= 0 ? 'green' : 'red'} style={{ fontSize: 11 }}>{pct(delta)}</Tag></Table.Summary.Cell>
                  <Table.Summary.Cell index={13} />
                </Table.Summary.Row>
              )
            }} />
        </Card>
      )}

      {/* Modal drilldown */}
      <Modal title={drilldownMesIdx !== null ? `Detalle ${MESES_LABELS[drilldownMesIdx]} — ${fmt(datosGrafico[drilldownMesIdx]?.importe || 0)}` : ''} open={drilldownMesIdx !== null} onCancel={() => setDrilldownMesIdx(null)} footer={null} width={600}>
        <Table dataSource={drilldownLineas} columns={drilldownCols} rowKey="id" size="small" pagination={false} scroll={{ y: 400, x: 460 }}
          summary={(data) => {
            const total = (data as any[]).reduce((s, r) => s + (r.importe_mes || 0), 0)
            return (
              <Table.Summary.Row>
                <Table.Summary.Cell index={0} colSpan={3}><Text strong>TOTAL</Text></Table.Summary.Cell>
                <Table.Summary.Cell index={3} align="right"><Text strong style={{ whiteSpace: 'nowrap' }}>{fmt(total)}</Text></Table.Summary.Cell>
              </Table.Summary.Row>
            )
          }} />
      </Modal>

      {/* Drawer parámetros masivos */}
      <Drawer title="Parámetros masivos — coeficiente y tasa de caída" open={coefDrawerVisible} onClose={() => setCoefDrawerVisible(false)} width={640}
        extra={
          <Popconfirm title={`¿Aplicar a ${lineasPreviewCoef.length} líneas?`} onConfirm={() => aplicarCoef.mutate()} okText="Aplicar" cancelText="Cancelar">
            <Button type="primary" size="small" loading={aplicarCoef.isPending}>Aplicar a {lineasPreviewCoef.length} líneas</Button>
          </Popconfirm>
        }>
        <Space direction="vertical" style={{ width: '100%' }} size={14}>
          <Alert type="info" showIcon message="Arquitectura de dos líneas por grupo"
            description={
              <span style={{ fontSize: 12 }}>
                <b style={{ color: '#1890ff' }}>Cartera 2026</b>: base = Cartera 2025 + NP 2025 · aplica tasa de caída · aplica crecimiento.<br />
                <code style={{ fontSize: 11 }}>superviviente = base_limpia × (1 − caída%) → proyectado = superviviente × (1 + crec%)</code><br />
                <b style={{ color: '#52c41a' }}>Nueva Producción 2026</b>: base = NP 2025 · <b>sin caída</b> (negocio nuevo) · aplica crecimiento.<br />
                <b>Crecimiento final</b>: mercado &gt; modelo → <code style={{ fontSize: 11 }}>modelo + (mercado−modelo) × coef</code>; si no, se usa el modelo.
              </span>
            } />

          <div>
            <Text style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>Ámbito de aplicación</Text>
            <Radio.Group value={coefScope} onChange={e => setCoefScope(e.target.value)} size="small">
              <Radio.Button value="todos">Todas las líneas</Radio.Button>
              <Radio.Button value="compania">Por compañía</Radio.Button>
              <Radio.Button value="ramo">Por ramo</Radio.Button>
            </Radio.Group>
          </div>
          {coefScope === 'compania' && (
            <Select placeholder="Selecciona compañía" style={{ width: '100%' }} size="small" value={coefCompania} onChange={setCoefCompania} allowClear>
              {companias.map(c => <Option key={c} value={c}>{c}</Option>)}
            </Select>
          )}
          {coefScope === 'ramo' && (
            <Select placeholder="Selecciona ramo" style={{ width: '100%' }} size="small" value={coefRamo} onChange={setCoefRamo} allowClear>
              {ramos.map(r => <Option key={r} value={r}>{r}</Option>)}
            </Select>
          )}

          <Divider orientation="left" plain style={{ fontSize: 12, margin: '4px 0' }}>Coeficiente de prudencia</Divider>
          <Space align="center">
            <InputNumber min={0} max={1} step={0.05} style={{ width: 100 }} size="small" value={coefValor} onChange={(v) => setCoefValor(v ?? 1.0)} />
            <Text type="secondary" style={{ fontSize: 11 }}>
              {coefValor === 0 ? 'Solo modelo estadístico' : coefValor === 1 ? 'Acepta mercado íntegro' : `Absorbe ${Math.round(coefValor * 100).toLocaleString('es-ES')}% del exceso de mercado`}
            </Text>
          </Space>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Switch size="small" checked={coefActualizarMercado} onChange={setCoefActualizarMercado} />
            <Text style={{ fontSize: 12 }}>Actualizar referencia de mercado (ICEA {mercadoRef?.anyo ?? '—'})<Tooltip title="Sobreescribe el crecimiento_mercado con la tasa ICEA para cada ramo.">{' '}<InfoCircleOutlined /></Tooltip></Text>
          </div>

          <Divider orientation="left" plain style={{ fontSize: 12, margin: '4px 0' }}>Tasa de caída — solo líneas Cartera 2026</Divider>
          <Row gutter={12}>
            <Col span={12}>
              <Text style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                Tasa de caída Cartera (%)<Tooltip title="Pólizas en renovación. Dejar vacío para no cambiar.">{' '}<InfoCircleOutlined /></Tooltip>
              </Text>
              <InputNumber min={0} max={100} step={0.5} style={{ width: '100%' }} size="small" placeholder="Vacío = sin cambio" value={coefTasaCartera} onChange={(v) => setCoefTasaCartera(v)} />
            </Col>
            <Col span={12}>
              <div style={{ background: '#f6ffed', border: '1px solid #b7eb8f', borderRadius: 6, padding: '8px 10px', height: '100%' }}>
                <Tag color="green" style={{ fontSize: 11, marginBottom: 4 }}>N.Prod 2026</Tag>
                <Text style={{ fontSize: 11, display: 'block', color: '#52c41a' }}>Sin caída — siempre 0%</Text>
                <Text type="secondary" style={{ fontSize: 10 }}>Las líneas de nueva producción no tienen tasa de caída: son negocio nuevo, no sujeto a renovación.</Text>
              </div>
            </Col>
          </Row>
          <Card size="small" style={{ background: '#fffbe6' }} bodyStyle={{ padding: '6px 10px' }}>
            <Text style={{ fontSize: 11 }}>
              Tasas de caída por ramo (BD — aplicadas al generar):<br />
              Decesos 3% · Vida 5% · Salud 8% · Multirriesgo/Hogar 8% · Auto 10% · RC/Empresa 9-10% · Defecto: 9%
            </Text>
          </Card>

          <Divider style={{ margin: '4px 0' }} />
          <Text strong style={{ fontSize: 12 }}>Vista previa — {lineasPreviewCoef.length} líneas afectadas</Text>
          <Table dataSource={lineasPreviewCoef} columns={coefPreviewCols} rowKey="id" size="small"
            pagination={{ pageSize: 10, size: 'small' }} scroll={{ x: 480, y: 260 }} />
        </Space>
      </Drawer>

      {/* Modal diagnóstico por compañía */}
      <Modal
        title="Diagnóstico de ingresos por compañía"
        open={diagModalVisible}
        onCancel={() => setDiagModalVisible(false)}
        footer={null}
        width={1100}
        styles={{ body: { padding: '12px 16px' } }}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          {/* Selector de compañía con atajos rápidos */}
          <Space wrap>
            <Text style={{ fontSize: 12 }}>Compañía:</Text>
            <Input
              size="small"
              style={{ width: 220 }}
              value={diagCompania}
              onChange={e => setDiagCompania(e.target.value)}
              placeholder="Nombre o parte del nombre"
              allowClear
            />
            {['Reale', 'Mutua de Propietarios', 'Sanitas'].map(c => (
              <Button key={c} size="small" type={diagCompania === c ? 'primary' : 'default'}
                onClick={() => setDiagCompania(c)}>
                {c}
              </Button>
            ))}
          </Space>

          {/* Tarjetas de resumen */}
          {diagData && (
            <Row gutter={12}>
              {[
                { label: 'Base 2025', value: diagData.total_base, color: '#1677ff' },
                { label: 'Presupuesto 2026', value: diagData.total_presupuesto, color: '#531dab' },
                {
                  label: 'Variación',
                  value: null,
                  pct: diagData.variacion_total_pct,
                  color: (diagData.variacion_total_pct ?? 0) >= 0 ? '#389e0d' : '#cf1322',
                },
                { label: 'Líneas', value: null, count: diagData.n_lineas, color: '#595959' },
              ].map((item, i) => (
                <Col key={i} span={6}>
                  <Card size="small" style={{ background: '#fafafa', borderRadius: 8 }} bodyStyle={{ padding: '8px 12px' }}>
                    <Text style={{ fontSize: 11, color: '#8c8c8c', display: 'block' }}>{item.label}</Text>
                    <Text strong style={{ fontSize: 16, color: item.color }}>
                      {item.value != null
                        ? fmtK(item.value)
                        : item.pct != null
                          ? `${item.pct > 0 ? '+' : ''}${item.pct.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
                          : item.count}
                    </Text>
                  </Card>
                </Col>
              ))}
            </Row>
          )}

          {/* Tabla detalle */}
          <Table
            loading={diagLoading}
            dataSource={diagData?.lineas ?? []}
            rowKey={(r: any) => `${r.ramo}-${r.tipo_negocio}-${r.auxiliar}`}
            size="small"
            scroll={{ x: 1050, y: 380 }}
            pagination={false}
            rowClassName={(r: any) => r.variacion_vs_base_pct != null && r.variacion_vs_base_pct < -15 ? 'ant-table-row-danger' : ''}
            columns={[
              { title: 'Ramo', dataIndex: 'ramo', width: 140, ellipsis: true,
                render: (v: string) => <Text style={{ fontSize: 11 }}>{v}</Text> },
              { title: 'Tipo', dataIndex: 'tipo_negocio', width: 72,
                render: (v: string) => <Tag color={v === 'cartera' ? 'blue' : 'green'} style={{ fontSize: 10 }}>{v === 'cartera' ? 'Cartera' : 'N.Prod'}</Tag> },
              { title: 'Base 2025', dataIndex: 'ingreso_base_anual', width: 90, align: 'right' as const,
                render: (v: number) => <Text style={{ fontSize: 11 }}>{fmt(v)}</Text> },
              { title: 'Atípicos', dataIndex: 'atipicos_excluidos', width: 90, align: 'right' as const,
                render: (v: number, row: any) => v > 0
                  ? (
                    <Button
                      type="link" size="small"
                      style={{ fontSize: 11, color: '#d48806', padding: 0, height: 'auto' }}
                      onClick={() => { setAtipicosLinea(row); setAtipicosModalVisible(true) }}
                    >
                      −{fmt(v)} ↗
                    </Button>
                  )
                  : <Text type="secondary" style={{ fontSize: 11 }}>—</Text> },
              { title: 'Base limpia', dataIndex: 'ingreso_base_limpio', width: 90, align: 'right' as const,
                render: (v: number) => <Text style={{ fontSize: 11 }}>{fmt(v)}</Text> },
              { title: 'Caída %', dataIndex: 'tasa_caida_pct', width: 65, align: 'right' as const,
                render: (v: number) => <Tag color={v >= 15 ? 'red' : v >= 10 ? 'orange' : 'default'} style={{ fontSize: 10 }}>{v.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</Tag> },
              { title: 'Superv.', dataIndex: 'superviviente', width: 85, align: 'right' as const,
                render: (v: number) => <Text style={{ fontSize: 11 }}>{fmt(v)}</Text> },
              { title: 'Crec.mod.%', dataIndex: 'crecimiento_modelo_pct', width: 80, align: 'right' as const,
                render: (v: number) => <Text style={{ fontSize: 11, color: v >= 0 ? '#389e0d' : '#cf1322' }}>{v > 0 ? '+' : ''}{v.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%</Text> },
              { title: 'Mdo.%', dataIndex: 'crecimiento_mercado_pct', width: 60, align: 'right' as const,
                render: (v: number) => <Text type="secondary" style={{ fontSize: 11 }}>{v.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</Text> },
              { title: 'Coef.', dataIndex: 'coeficiente_prudencia', width: 52, align: 'right' as const,
                render: (v: number) => <Text type="secondary" style={{ fontSize: 11 }}>{v.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Text> },
              { title: 'Final%', dataIndex: 'crecimiento_final_pct', width: 60, align: 'right' as const,
                render: (v: number) => <Text strong style={{ fontSize: 11, color: v >= 0 ? '#389e0d' : '#cf1322' }}>{v > 0 ? '+' : ''}{v.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%</Text> },
              { title: 'Ppto 2026', dataIndex: 'total_anual', width: 90, align: 'right' as const,
                render: (v: number) => <Text strong style={{ fontSize: 11 }}>{fmt(v)}</Text> },
              { title: 'Var.%', dataIndex: 'variacion_vs_base_pct', width: 65, align: 'right' as const,
                render: (v: number | null) => v == null ? '—' : (
                  <Text strong style={{ fontSize: 11, color: v >= 0 ? '#389e0d' : '#cf1322' }}>
                    {v > 0 ? '+' : ''}{v.toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%
                  </Text>
                ) },
              { title: 'Método', dataIndex: 'metodo_modelo', width: 130, ellipsis: true,
                render: (v: string) => <Text type="secondary" style={{ fontSize: 10 }}>{v}</Text> },
            ]}
            summary={() => diagData && (
              <Table.Summary fixed>
                <Table.Summary.Row style={{ background: '#f0f7ff', fontWeight: 700 }}>
                  <Table.Summary.Cell index={0} colSpan={2}><Text strong style={{ fontSize: 11 }}>TOTAL {diagCompania?.toUpperCase()}</Text></Table.Summary.Cell>
                  <Table.Summary.Cell index={2} align="right"><Text strong style={{ fontSize: 11 }}>{fmt(diagData.total_base)}</Text></Table.Summary.Cell>
                  <Table.Summary.Cell index={3} />
                  <Table.Summary.Cell index={4} />
                  <Table.Summary.Cell index={5} />
                  <Table.Summary.Cell index={6} />
                  <Table.Summary.Cell index={7} />
                  <Table.Summary.Cell index={8} />
                  <Table.Summary.Cell index={9} />
                  <Table.Summary.Cell index={10} />
                  <Table.Summary.Cell index={11} align="right"><Text strong style={{ fontSize: 11 }}>{fmt(diagData.total_presupuesto)}</Text></Table.Summary.Cell>
                  <Table.Summary.Cell index={12} align="right">
                    <Text strong style={{ fontSize: 11, color: (diagData.variacion_total_pct ?? 0) >= 0 ? '#389e0d' : '#cf1322' }}>
                      {(diagData.variacion_total_pct ?? 0) > 0 ? '+' : ''}{(diagData.variacion_total_pct ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%
                    </Text>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={13} />
                </Table.Summary.Row>
              </Table.Summary>
            )}
          />
          {diagData?.lineas?.length === 0 && !diagLoading && (
            <Alert type="warning" showIcon message={`No se encontraron líneas para "${diagCompania}"`} />
          )}
        </Space>
      </Modal>

      {/* Modal detalle atípicos */}
      <Modal
        title={atipicosLinea ? `Atípicos — ${atipicosLinea.compania} / ${atipicosLinea.ramo}` : 'Atípicos'}
        open={atipicosModalVisible}
        onCancel={() => setAtipicosModalVisible(false)}
        footer={null}
        width={560}
      >
        {atipicosLoading && <div style={{ textAlign: 'center', padding: 24 }}><LoadingOutlined style={{ fontSize: 24 }} /></div>}
        {atipicosData && !atipicosLoading && (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Descriptions size="small" bordered column={2}>
              <Descriptions.Item label="Base bruta">{fmt(atipicosData.ingreso_base_anual)}</Descriptions.Item>
              <Descriptions.Item label="Base limpia">{fmt(atipicosData.ingreso_base_limpio)}</Descriptions.Item>
              <Descriptions.Item label="Total excluido" span={2}>
                <Text strong style={{ color: '#d48806' }}>−{fmt(atipicosData.importe_excluido)}</Text>
                <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                  ({atipicosData.n_atipicos} {atipicosData.n_atipicos === 1 ? 'mes' : 'meses'} con z-score &gt; 2,0σ)
                </Text>
              </Descriptions.Item>
            </Descriptions>

            <Table
              dataSource={atipicosData.meses}
              rowKey="mes"
              size="small"
              pagination={false}
              rowClassName={(r: any) => r.es_atipico ? 'ant-table-row-selected' : ''}
              columns={[
                {
                  title: 'Mes', dataIndex: 'mes_nombre', width: 60,
                  render: (v: string, r: any) => (
                    <Text strong={r.es_atipico} style={{ color: r.es_atipico ? '#d48806' : undefined }}>
                      {v}
                    </Text>
                  ),
                },
                {
                  title: 'Importe real', dataIndex: 'importe', align: 'right' as const,
                  render: (v: number, r: any) => (
                    <Text style={{ color: r.es_atipico ? '#d48806' : undefined, fontWeight: r.es_atipico ? 600 : 400 }}>
                      {fmt(v)}
                    </Text>
                  ),
                },
                {
                  title: 'Z-score', dataIndex: 'zscore', width: 90, align: 'right' as const,
                  render: (v: number | null, _r: any) => v != null
                    ? <Tag color="orange" style={{ fontSize: 11 }}>{v.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}σ</Tag>
                    : <Text type="secondary" style={{ fontSize: 11 }}>—</Text>,
                },
                {
                  title: '', width: 80, align: 'center' as const,
                  render: (_: any, r: any) => r.es_atipico
                    ? <Tag color="warning" style={{ fontSize: 10 }}>Excluido</Tag>
                    : null,
                },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 11 }}>
              Los meses excluidos se eliminan de la base de cálculo y su peso se redistribuye
              en los meses normales para mantener la estacionalidad sin distorsiones.
            </Text>
          </Space>
        )}
      </Modal>

      {/* Drawer edición individual */}
      <Drawer title={lineaEditar ? `${lineaEditar.compania} / ${lineaEditar.ramo}` : ''} open={drawerVisible} onClose={() => setDrawerVisible(false)} width={460}
        extra={<Button type="primary" size="small" onClick={() => actualizar.mutate(formValues)} loading={actualizar.isPending}>Guardar</Button>}>
        {lineaEditar && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Base anual"><span style={{ whiteSpace: 'nowrap' }}>{fmt(lineaEditar.ingreso_base_anual)}</span></Descriptions.Item>
              <Descriptions.Item label="Atípicos excluidos"><span style={{ whiteSpace: 'nowrap' }}>{fmt(lineaEditar.atipicos_excluidos)}</span></Descriptions.Item>
              <Descriptions.Item label="Base limpia"><span style={{ whiteSpace: 'nowrap' }}>{fmt(lineaEditar.ingreso_base_limpio)}</span></Descriptions.Item>
              <Descriptions.Item label="Tasa de caída">
                <Tag color={lineaEditar.tasa_caida >= 20 ? 'red' : lineaEditar.tasa_caida >= 12 ? 'orange' : 'default'}>{(lineaEditar.tasa_caida ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%</Tag>
                <Text type="secondary" style={{ fontSize: 11 }}>−{fmt(lineaEditar.ingreso_base_limpio * lineaEditar.tasa_caida / 100)}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Base superviviente"><span style={{ whiteSpace: 'nowrap', color: '#fa8c16' }}>{fmt(lineaEditar.base_superviviente)}</span></Descriptions.Item>
              <Descriptions.Item label="Crecimiento aplicado">
                <Tag color={lineaEditar.crecimiento_final > 0 ? 'green' : 'red'}>{pct(lineaEditar.crecimiento_final)}</Tag>
                <OrigenTag row={lineaEditar} />
              </Descriptions.Item>
              <Descriptions.Item label="Total presupuestado"><Text strong style={{ whiteSpace: 'nowrap' }}>{fmt(lineaEditar.total_anual)}</Text></Descriptions.Item>
            </Descriptions>

            <Divider orientation="left" plain style={{ fontSize: 12 }}>Tasa de caída</Divider>
            <div>
              <Text style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>
                Tasa de caída (%)<Tooltip title="% de la base limpia que se pierde por anulaciones. Referencia ICEA según ramo y tipo.">{' '}<InfoCircleOutlined /></Tooltip>
              </Text>
              <InputNumber style={{ width: '100%' }} size="small" min={0} max={100} step={0.5}
                value={formValues.tasa_caida} onChange={(v) => setFormValues((f: any) => ({ ...f, tasa_caida: v }))} />
            </div>

            <Divider orientation="left" plain style={{ fontSize: 12 }}>Estrategia de crecimiento</Divider>
            <Card size="small" style={{ background: '#fafafa', fontSize: 12 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                <b>Modelo estadístico</b>: {pct(lineaEditar.crecimiento_modelo)}<br />
                <b>Referencia mercado ICEA 2024</b>: {pct(lineaEditar.crecimiento_mercado)}<br />
                {lineaEditar.crecimiento_mercado > lineaEditar.crecimiento_modelo
                  ? <>Mercado &gt; modelo → <code style={{ fontSize: 11 }}>modelo + (mercado−modelo) × coef</code></>
                  : <>Mercado ≤ modelo → <code style={{ fontSize: 11 }}>se usa el modelo</code></>}
              </Text>
            </Card>

            <Space direction="vertical" style={{ width: '100%' }} size={4}>
              <div>
                <Text style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>Crecimiento manual (%) — prioridad absoluta<Tooltip title="Sobrescribe modelo y mercado.">{' '}<InfoCircleOutlined style={{ color: '#faad14' }} /></Tooltip></Text>
                <InputNumber style={{ width: '100%' }} size="small" placeholder="Ej: 5.0" step={0.5} value={formValues.crecimiento_manual ?? null} onChange={(v) => setFormValues((f: any) => ({ ...f, crecimiento_manual: v }))} />
              </div>
              <div>
                <Text style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>Crecimiento modelo estadístico (%)</Text>
                <InputNumber style={{ width: '100%' }} size="small" step={0.5} value={formValues.crecimiento_modelo} onChange={(v) => setFormValues((f: any) => ({ ...f, crecimiento_modelo: v }))} />
              </div>
              <div>
                <Text style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>Referencia mercado ICEA 2024 (%)<Tooltip title="Solo eleva el crecimiento si supera al modelo.">{' '}<InfoCircleOutlined style={{ color: '#1890ff' }} /></Tooltip></Text>
                <InputNumber style={{ width: '100%' }} size="small" step={0.5} value={formValues.crecimiento_mercado} onChange={(v) => setFormValues((f: any) => ({ ...f, crecimiento_mercado: v }))} />
              </div>
              <div>
                <Text style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>Coeficiente de prudencia<Tooltip title="Controla cuánto del exceso de mercado sobre el modelo se acepta.">{' '}<InfoCircleOutlined /></Tooltip></Text>
                <InputNumber style={{ width: '100%' }} size="small" min={0} max={1} step={0.05} value={formValues.coeficiente_prudencia} onChange={(v) => setFormValues((f: any) => ({ ...f, coeficiente_prudencia: v }))} />
              </div>
              <div>
                <Text style={{ fontSize: 12, display: 'block', marginBottom: 2 }}>Notas</Text>
                <Input.TextArea rows={2} size="small" placeholder="Observaciones..." value={formValues.notas} onChange={(e) => setFormValues((f: any) => ({ ...f, notas: e.target.value }))} />
              </div>
            </Space>

            <Divider plain style={{ fontSize: 12 }}>Distribución mensual</Divider>
            <Table size="small" pagination={false}
              dataSource={MESES_LABELS.map((mes, i) => ({ key: i, mes, importe: lineaEditar.importes_mensuales?.[i] || 0, peso: ((lineaEditar.estacionalidad?.[i] || 0) * 100).toFixed(1) + '%' }))}
              columns={[
                { title: 'Mes', dataIndex: 'mes', width: 50 },
                { title: 'Peso', dataIndex: 'peso', align: 'right' as const, width: 60 },
                { title: 'Importe', dataIndex: 'importe', align: 'right' as const, render: fmt },
              ]} />
          </Space>
        )}
      </Drawer>
    </Space>
  )
}
