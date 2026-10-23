import { useState, useRef } from 'react'
import * as XLSX from 'xlsx'
import {
  Card, Table, Button, Tag, Space, Typography, Row, Col, Statistic,
  Select, InputNumber, Modal, Form, Alert, Popconfirm, message,
  Drawer, Descriptions, Divider, Tooltip, Input,
} from 'antd'
import {
  CheckCircleOutlined, ThunderboltOutlined, EditOutlined,
  PlusOutlined, HistoryOutlined, InfoCircleOutlined,
  DownloadOutlined, SyncOutlined, UploadOutlined, UnlockOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { presupuestoApi } from '../../api/presupuesto'
import { apiError } from '../../utils/errorHandler'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  Tooltip as RTooltip, CartesianGrid, Cell,
} from 'recharts'

const { Title, Text } = Typography
const { Option } = Select

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
  'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

const fmt = (v: number) => (v ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' €'
const fmtK = (v: number) => {
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + 'M €'
  if (Math.abs(v) >= 1_000) return (v / 1_000).toLocaleString('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'k €'
  return (v ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' €'
}
const pct = (v: number) => (v >= 0 ? '+' : '') + (v ?? 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%'

const TIPO_REGLA_LABELS: Record<string, { label: string; color: string }> = {
  mantener: { label: 'Mantener', color: 'default' },
  ipc: { label: 'IPC / Variación', color: 'orange' },
  importe_anual: { label: 'Importe fijo', color: 'blue' },
  excluir: { label: 'Excluir', color: 'error' },
  nuevo: { label: 'Nuevo', color: 'green' },
}

const FAMILIAS_COLOR: Record<string, string> = {
  'Personal': '#1890ff',
  'Cesiones a auxiliares': '#52c41a',
  'Alquiler y oficina': '#faad14',
  'Tecnología y software': '#722ed1',
  'Servicios profesionales': '#eb2f96',
  'Marketing y captación': '#fa8c16',
  'Gastos financieros': '#f5222d',
  'Tributos y seguros': '#13c2c2',
  'Amortizaciones y ajustes': '#bfbfbf',
  'Otros gastos': '#8c8c8c',
}

export default function PresupuestoGastos() {
  const qc = useQueryClient()
  const [presupuestoId, setPresupuestoId] = useState<string | null>(null)
  const [lineaEditar, setLineaEditar] = useState<any>(null)
  const [drawerRegla, setDrawerRegla] = useState(false)
  const [drawerAjuste, setDrawerAjuste] = useState(false)
  const [drawerCesion, setDrawerCesion] = useState(false)
  const [cesionEditar, setCesionEditar] = useState<any>(null)
  const [modalNuevo, setModalNuevo] = useState(false)
  const [filtroFamilia, setFiltroFamilia] = useState<string | undefined>()
  const [mesAjuste, setMesAjuste] = useState<number>(1)
  const [importeAjuste, setImporteAjuste] = useState<number>(0)
  const [mantenerTotal, setMantenerTotal] = useState(false)
  const [motivoAjuste, setMotivoAjuste] = useState('')
  const [formRegla] = Form.useForm()
  const [formNuevo] = Form.useForm()
  const [formCesion] = Form.useForm()
  const [tipoReglaForm, setTipoReglaForm] = useState('mantener')
  const [drilldownMesIdx, setDrilldownMesIdx] = useState<number | null>(null)

  const { data: presupuestos = [] } = useQuery({
    queryKey: ['presupuestos'],
    queryFn: () => presupuestoApi.listar().then(r => r.data),
  })

  const { data: lineas = [], isLoading } = useQuery({
    queryKey: ['gastos', presupuestoId, filtroFamilia],
    queryFn: () => presupuestoApi.listarGastos(presupuestoId!, filtroFamilia).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: resumen } = useQuery({
    queryKey: ['resumen-gastos', presupuestoId],
    queryFn: () => presupuestoApi.resumenGastos(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const { data: cesiones = [] } = useQuery({
    queryKey: ['cesiones', presupuestoId],
    queryFn: () => presupuestoApi.listarCesiones(presupuestoId!).then(r => r.data),
    enabled: !!presupuestoId,
  })

  const generar = useMutation({
    mutationFn: () => presupuestoApi.generarGastos(presupuestoId!),
    onSuccess: (res) => {
      message.success(res.data.mensaje)
      qc.invalidateQueries({ queryKey: ['gastos', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['resumen-gastos', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al generar gastos')),
  })

  const generarCes = useMutation({
    mutationFn: () => presupuestoApi.generarCesiones(presupuestoId!),
    onSuccess: (res) => {
      message.success(res.data.mensaje)
      qc.invalidateQueries({ queryKey: ['cesiones', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al generar cesiones')),
  })

  const actualizarRegla = useMutation({
    mutationFn: (datos: object) => presupuestoApi.actualizarReglaGasto(presupuestoId!, lineaEditar.id, datos),
    onSuccess: () => {
      message.success('Regla actualizada y recalculada')
      qc.invalidateQueries({ queryKey: ['gastos', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['resumen-gastos', presupuestoId] })
      setDrawerRegla(false)
    },
    onError: (e) => message.error(apiError(e, 'Error al actualizar la regla')),
  })

  const ajustarMes = useMutation({
    mutationFn: () => presupuestoApi.ajusteManualGasto(presupuestoId!, lineaEditar.id, {
      mes: mesAjuste, nuevo_importe: importeAjuste, mantener_total: mantenerTotal, motivo: motivoAjuste,
    }),
    onSuccess: () => {
      message.success('Ajuste registrado con trazabilidad')
      qc.invalidateQueries({ queryKey: ['gastos', presupuestoId] })
      setDrawerAjuste(false)
    },
    onError: (e) => message.error(apiError(e, 'Error al registrar el ajuste')),
  })

  const nuevoGasto = useMutation({
    mutationFn: (datos: object) => presupuestoApi.nuevoGasto(presupuestoId!, datos),
    onSuccess: () => {
      message.success('Gasto nuevo añadido')
      qc.invalidateQueries({ queryKey: ['gastos', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['resumen-gastos', presupuestoId] })
      setModalNuevo(false)
      formNuevo.resetFields()
    },
    onError: (e) => message.error(apiError(e, 'Error al añadir el gasto')),
  })

  const actualizarCesion = useMutation({
    mutationFn: (datos: object) => presupuestoApi.actualizarCesion(presupuestoId!, cesionEditar.id, datos),
    onSuccess: () => {
      message.success('Parámetros de cesión actualizados')
      qc.invalidateQueries({ queryKey: ['cesiones', presupuestoId] })
      setDrawerCesion(false)
    },
    onError: (e) => message.error(apiError(e, 'Error al actualizar cesión')),
  })

  const [importCesResult, setImportCesResult] = useState<{ actualizadas: number; errores: string[] } | null>(null)
  const importCesRef = useRef<HTMLInputElement>(null)

  const importarCes = useMutation({
    mutationFn: (file: File) => presupuestoApi.importarCesiones(presupuestoId!, file),
    onSuccess: (res) => {
      setImportCesResult(res.data)
      qc.invalidateQueries({ queryKey: ['cesiones', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al importar cesiones')),
  })

  const handleImportCes = (e: { target: HTMLInputElement }) => {
    const file = e.target.files?.[0]
    if (file) { setImportCesResult(null); importarCes.mutate(file) }
    e.target.value = ''
  }

  const exportarCesionesExcel = () => {
    const filas = (cesiones as any[]).map((c: any) => {
      const row: Record<string, any> = {
        'Auxiliar':           c.auxiliar || '',
        'Tipo':               c.tipo_persona === 'fisico' ? 'Físico' : c.tipo_persona === 'juridico' ? 'Jurídico' : '',
        'Ingreso ppto (€)':   c.total_ingreso_base || 0,
        '% Comisión':         c.pct_comision || 0,
        '% Retención':        c.pct_retencion || 0,
        'Gasto comisión (€)': c.gasto_comision_total || 0,
      }
      MESES.forEach((mes, i) => { row[mes] = c.importes_mensuales?.[i] ?? 0 })
      return row
    })
    const ws = XLSX.utils.json_to_sheet(filas)
    ws['!cols'] = [{ wch: 22 }, { wch: 12 }, { wch: 16 }, { wch: 12 }, { wch: 12 }, { wch: 16 },
      ...MESES.map(() => ({ wch: 10 }))]
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Cesiones')
    XLSX.writeFile(wb, `cesiones_auxiliares.xlsx`)
  }

  const aprobar = useMutation({
    mutationFn: () => presupuestoApi.aprobarGastos(presupuestoId!),
    onSuccess: () => {
      message.success('Presupuesto de gastos aprobado y bloqueado')
      qc.invalidateQueries({ queryKey: ['presupuestos'] })
    },
    onError: (e) => message.error(apiError(e, 'Error al aprobar el presupuesto')),
  })

  const reabrir = useMutation({
    mutationFn: () => presupuestoApi.reabrirGastos(presupuestoId!),
    onSuccess: () => {
      message.success('Presupuesto de gastos reabierto')
      qc.invalidateQueries({ queryKey: ['presupuestos'] })
      qc.invalidateQueries({ queryKey: ['gastos', presupuestoId] })
      qc.invalidateQueries({ queryKey: ['cesiones', presupuestoId] })
    },
    onError: (e) => message.error(apiError(e, 'Error al reabrir')),
  })

  const presupuestoActual = (presupuestos as any[]).find((p: any) => p.id === presupuestoId)
  const gastosAprobados = presupuestoActual?.estado === 'gastos_aprobados' ||
    presupuestoActual?.estado === 'tesoreria_aprobada' ||
    presupuestoActual?.estado === 'cerrado'
  const anoPpto = presupuestoActual?.ejercicio ?? new Date().getFullYear()
  const anoBase = presupuestoActual?.ejercicio_base ?? (anoPpto - 1)

  const abrirRegla = (l: any) => {
    setLineaEditar(l)
    setTipoReglaForm(l.tipo_regla)
    formRegla.setFieldsValue({
      tipo_regla: l.tipo_regla,
      porcentaje_variacion: l.porcentaje_variacion,
      mes_inicio_variacion: l.mes_inicio_variacion,
      importe_anual_manual: l.importe_anual_manual,
      distribucion: l.distribucion,
      motivo_exclusion: l.motivo_exclusion,
    })
    setDrawerRegla(true)
  }

  const abrirAjuste = (l: any) => {
    setLineaEditar(l)
    setMesAjuste(1)
    setImporteAjuste(l.importes_efectivos?.[0] || 0)
    setDrawerAjuste(true)
  }

  const abrirCesion = (c: any) => {
    setCesionEditar(c)
    formCesion.setFieldsValue({
      tipo_persona: c.tipo_persona,
      pct_comision: c.pct_comision,
      pct_retencion: c.pct_retencion,
      gasto_comision_manual: c.gasto_comision_manual ?? null,
      notas: c.notas,
    })
    setDrawerCesion(true)
  }

  const familias = [...new Set((lineas as any[]).map((l: any) => l.familia_gasto))].filter(Boolean).sort()

  // Gráfico mensual (como ingresos)
  const datosGrafico = MESES.map((mes, i) => ({
    mes,
    importe: resumen?.mensual?.[i] || 0,
  }))

  const drilldownLineas = drilldownMesIdx !== null
    ? (lineas as any[])
        .filter((l: any) => l.tipo_regla !== 'excluir')
        .map((l: any) => ({ ...l, importe_mes: l.importes_efectivos?.[drilldownMesIdx] || 0 }))
        .filter((l: any) => l.importe_mes > 0)
        .sort((a: any, b: any) => b.importe_mes - a.importe_mes)
    : []

  // Excel export
  const exportarExcel = () => {
    const filas = (lineas as any[]).map((l: any) => {
      const row: Record<string, any> = {
        'Cuenta': l.numero_cuenta || '',
        'Descripción': l.descripcion_cuenta || '',
        'Familia': l.familia_gasto || '',
        'Es nuevo': l.es_gasto_nuevo ? 'Sí' : 'No',
        [`Gasto base ${anoBase} (€)`]: l.gasto_base_anual || 0,
        'Regla': TIPO_REGLA_LABELS[l.tipo_regla]?.label || l.tipo_regla || '',
        [`Total ppto ${anoPpto} (€)`]: l.tipo_regla === 'excluir' ? 0 : (l.total_anual || 0),
        'Δ vs base (%)': l.gasto_base_anual > 0
          ? Math.round(((l.total_anual - l.gasto_base_anual) / l.gasto_base_anual) * 10000) / 100
          : 0,
      }
      MESES.forEach((mes, i) => {
        row[mes] = l.importes_efectivos?.[i] ?? 0
      })
      return row
    })
    const ws = XLSX.utils.json_to_sheet(filas)
    ws['!cols'] = [
      { wch: 12 }, { wch: 30 }, { wch: 22 }, { wch: 8 }, { wch: 16 },
      { wch: 14 }, { wch: 16 }, { wch: 12 },
      ...MESES.map(() => ({ wch: 11 })),
    ]
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, `Ppto Gastos ${anoPpto}`)
    XLSX.writeFile(wb, `presupuesto_gastos_${anoPpto}.xlsx`)
  }

  const columnas: any[] = [
    {
      title: 'Cuenta', dataIndex: 'numero_cuenta', width: 100,
      render: (v: string) => v ? <Text code style={{ fontSize: 11 }}>{v}</Text> : <Tag color="green" style={{ fontSize: 11 }}>Nuevo</Tag>,
    },
    { title: 'Descripción', dataIndex: 'descripcion_cuenta', ellipsis: true },
    {
      title: 'Familia', dataIndex: 'familia_gasto',
      render: (v: string) => (
        <Tag style={{ backgroundColor: FAMILIAS_COLOR[v] || '#8c8c8c', color: '#fff', border: 'none', fontSize: 11 }}>
          {v}
        </Tag>
      ),
    },
    {
      title: `Base ${anoBase}`, dataIndex: 'gasto_base_anual', align: 'right' as const, width: 120,
      render: (v: number) => <Text type="secondary" style={{ fontSize: 12 }}>{fmt(v)}</Text>,
      sorter: (a: any, b: any) => a.gasto_base_anual - b.gasto_base_anual,
    },
    {
      title: 'Regla', dataIndex: 'tipo_regla', width: 155,
      filters: Object.entries(TIPO_REGLA_LABELS).map(([k, v]) => ({ text: v.label, value: k })),
      onFilter: (value: any, record: any) => record.tipo_regla === value,
      render: (v: string, row: any) => {
        const cfg = TIPO_REGLA_LABELS[v] || { label: v, color: 'default' }
        return (
          <Space size={4}>
            <Tag color={cfg.color} style={{ fontSize: 11 }}>{cfg.label}</Tag>
            {v === 'ipc' && row.porcentaje_variacion !== null && (
              <Text type="secondary" style={{ fontSize: 11 }}>{row.porcentaje_variacion}%{row.mes_inicio_variacion ? ` desde m${row.mes_inicio_variacion}` : ''}</Text>
            )}
          </Space>
        )
      },
    },
    {
      title: `Total ppto ${anoPpto}`, dataIndex: 'total_anual', align: 'right' as const, width: 130,
      sorter: (a: any, b: any) => a.total_anual - b.total_anual,
      render: (v: number, row: any) => row.tipo_regla === 'excluir'
        ? <Text type="secondary" style={{ fontSize: 12 }}>—</Text>
        : <Text strong style={{ fontSize: 13, color: '#531dab' }}>{fmt(v)}</Text>,
    },
    {
      title: `Δ vs ${anoBase}`, align: 'right' as const, width: 85,
      render: (_: any, row: any) => {
        if (row.tipo_regla === 'excluir' || !row.gasto_base_anual) return <Text type="secondary">—</Text>
        const delta = (row.total_anual - row.gasto_base_anual) / row.gasto_base_anual * 100
        return <Tag color={delta >= 0 ? 'orange' : 'green'} style={{ fontSize: 11 }}>{pct(delta)}</Tag>
      },
    },
    {
      title: '', width: 90,
      render: (_: any, row: any) => (
        <Space size={4}>
          <Tooltip title="Cambiar regla">
            <Button size="small" icon={<EditOutlined />} disabled={row.bloqueado} onClick={() => abrirRegla(row)} />
          </Tooltip>
          <Tooltip title="Ajuste mensual">
            <Button size="small" icon={<HistoryOutlined />} disabled={row.bloqueado} onClick={() => abrirAjuste(row)} />
          </Tooltip>
        </Space>
      ),
    },
  ]

  const columnaCesiones: any[] = [
    { title: 'Auxiliar', dataIndex: 'auxiliar', ellipsis: true },
    {
      title: 'Tipo', dataIndex: 'tipo_persona', width: 100,
      render: (v: string) => v
        ? <Tag color={v === 'fisico' ? 'blue' : 'purple'} style={{ fontSize: 11 }}>{v === 'fisico' ? 'Físico' : 'Jurídico'}</Tag>
        : <Text type="secondary" style={{ fontSize: 11 }}>—</Text>,
    },
    {
      title: 'Ingreso ppto', dataIndex: 'total_ingreso_base', align: 'right' as const, width: 130,
      render: (v: number) => <Text type="secondary" style={{ fontSize: 12 }}>{fmt(v)}</Text>,
    },
    {
      title: '% Comisión', dataIndex: 'pct_comision', align: 'center' as const, width: 95,
      render: (v: number) => <Tag color={v > 0 ? 'orange' : 'default'} style={{ fontSize: 11 }}>{(v || 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%</Tag>,
    },
    {
      title: '% Retención', dataIndex: 'pct_retencion', align: 'center' as const, width: 95,
      render: (v: number) => <Tag color={v > 0 ? 'blue' : 'default'} style={{ fontSize: 11 }}>{(v || 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%</Tag>,
    },
    {
      title: 'Gasto comisión', dataIndex: 'gasto_comision_total', align: 'right' as const, width: 130,
      render: (v: number) => <Text strong style={{ fontSize: 13, color: '#cf1322' }}>{fmt(v)}</Text>,
      sorter: (a: any, b: any) => a.gasto_comision_total - b.gasto_comision_total,
    },
    {
      title: '', width: 50,
      render: (_: any, row: any) => (
        <Button size="small" icon={<EditOutlined />} disabled={row.bloqueado} onClick={() => abrirCesion(row)} />
      ),
    },
  ]

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {/* Cabecera */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <Title level={5} style={{ margin: 0 }}>Presupuesto de gastos</Title>
          <Text type="secondary" style={{ fontSize: 12 }}>Proyección por cuenta contable (cuentas 6*) y familia desde el ejercicio base</Text>
        </div>
        <Space wrap size={4}>
          <Select placeholder="Selecciona ejercicio" style={{ width: 200 }} onChange={setPresupuestoId} value={presupuestoId} size="small">
            {(presupuestos as any[]).map((p: any) => (
              <Option key={p.id} value={p.id}>
                Ejercicio {p.ejercicio} — <Tag color={p.estado === 'borrador' ? 'default' : 'blue'} style={{ fontSize: 11 }}>{p.estado}</Tag>
              </Option>
            ))}
          </Select>
          {presupuestoId && !gastosAprobados && (
            <>
              <Button size="small" icon={<ThunderboltOutlined />} onClick={() => generar.mutate()} loading={generar.isPending}>
                Generar / Regenerar
              </Button>
              <Button size="small" icon={<PlusOutlined />} onClick={() => setModalNuevo(true)}>
                Nuevo gasto
              </Button>
            </>
          )}
          {(lineas as any[]).length > 0 && !gastosAprobados && (
            <Popconfirm
              title="¿Aprobar el presupuesto de gastos?"
              description="Las líneas quedarán bloqueadas."
              onConfirm={() => aprobar.mutate()}
              okText="Aprobar"
              cancelText="Cancelar"
            >
              <Button size="small" type="primary" icon={<CheckCircleOutlined />} loading={aprobar.isPending}>
                Aprobar gastos
              </Button>
            </Popconfirm>
          )}
          {gastosAprobados && (
            <>
              <Tag color="blue" icon={<CheckCircleOutlined />}>Gastos aprobados</Tag>
              <Popconfirm
                title="¿Reabrir el presupuesto de gastos?"
                description="Las líneas de gastos y cesiones quedarán desbloqueadas para edición."
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

      {!presupuestoId && <Alert type="info" showIcon message="Selecciona un ejercicio presupuestario" />}

      {/* ── Resumen tipo ingresos ── */}
      {resumen && (
        <Card
          title={<span style={{ fontSize: 13, fontWeight: 600 }}>Resumen presupuesto de gastos</span>}
          style={{ borderRadius: 10, boxShadow: '0 1px 6px rgba(0,0,0,0.07)' }}
          bodyStyle={{ padding: '0 0 12px 0' }}
        >
          <div style={{ overflowX: 'auto', padding: '4px 0' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <colgroup>
                <col style={{ minWidth: 170 }} />
                <col style={{ minWidth: 140 }} />
                <col style={{ minWidth: 140 }} />
                <col style={{ minWidth: 100 }} />
              </colgroup>
              <thead>
                <tr>
                  <th style={{ padding: '10px 16px', background: '#fafafa', borderBottom: '2px solid #e8e8e8', textAlign: 'left', color: '#8c8c8c', fontWeight: 500, fontSize: 11 }}>
                    Familia
                  </th>
                  <th style={{ padding: '10px 16px', background: '#fafafa', borderBottom: '2px solid #e8e8e8', textAlign: 'right', color: '#595959', fontWeight: 600, fontSize: 12 }}>
                    Gastos {anoBase}
                  </th>
                  <th style={{ padding: '10px 16px', background: '#fafafa', borderBottom: '2px solid #e8e8e8', textAlign: 'right', color: '#595959', fontWeight: 600, fontSize: 12 }}>
                    Presupuesto {anoPpto}
                  </th>
                  <th style={{ padding: '10px 16px', background: '#fafafa', borderBottom: '2px solid #e8e8e8', textAlign: 'center', color: '#595959', fontWeight: 600, fontSize: 12 }}>
                    % Desviación
                  </th>
                </tr>
              </thead>
              <tbody>
                {(resumen.resumen_familia || []).map((fila: any) => (
                  <tr key={fila.familia} style={{ borderBottom: '1px solid #f0f0f0' }}>
                    <td style={{ padding: '12px 16px', verticalAlign: 'middle' }}>
                      <Tag style={{ backgroundColor: FAMILIAS_COLOR[fila.familia] || '#8c8c8c', color: '#fff', border: 'none', fontSize: 11 }}>
                        {fila.familia}
                      </Tag>
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right', verticalAlign: 'middle', fontSize: 13, color: '#595959' }}>
                      {fmtK(fila.gasto_base)}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'right', verticalAlign: 'middle', fontWeight: 600, fontSize: 14, color: '#531dab' }}>
                      {fmtK(fila.presupuesto)}
                    </td>
                    <td style={{ padding: '12px 16px', textAlign: 'center', verticalAlign: 'middle' }}>
                      <Tag color={fila.pct_desviacion >= 0 ? 'orange' : 'green'} style={{ fontSize: 11 }}>
                        {pct(fila.pct_desviacion)}
                      </Tag>
                    </td>
                  </tr>
                ))}
                {/* Fila total */}
                <tr style={{ background: '#fafafa', borderTop: '2px solid #d9d9d9' }}>
                  <td style={{ padding: '14px 16px', fontWeight: 700, fontSize: 13 }}>Total</td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 700, fontSize: 14, color: '#262626' }}>
                    {fmtK(resumen.gasto_base_total || 0)}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 700, fontSize: 15, color: '#531dab' }}>
                    {fmtK(resumen.total_anual || 0)}
                  </td>
                  <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                    <span style={{ fontWeight: 700, fontSize: 14, color: (resumen.pct_desviacion || 0) >= 0 ? '#d46b08' : '#389e0d' }}>
                      {pct(resumen.pct_desviacion || 0)}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <Divider style={{ margin: '8px 0 4px 0' }} />
          <Row gutter={[16, 4]} style={{ padding: '0 14px 4px' }}>
            <Col xs={12} sm={8}>
              <Statistic
                title={<span style={{ fontSize: 11, color: '#8c8c8c' }}>Líneas de presupuesto</span>}
                value={(lineas as any[]).length}
                valueStyle={{ fontSize: 16, fontWeight: 600 }}
              />
            </Col>
            <Col xs={12} sm={8}>
              <Statistic
                title={<span style={{ fontSize: 11, color: '#1677ff' }}>Gastos {anoBase} (base real cuentas 6*)</span>}
                value={resumen.gasto_base_total || 0}
                precision={0}
                suffix="€"
                valueStyle={{ fontSize: 16, fontWeight: 600, color: '#1677ff' }}
              />
            </Col>
            <Col xs={12} sm={8}>
              <Statistic
                title={<span style={{ fontSize: 11, color: '#531dab' }}>Presupuesto {anoPpto}</span>}
                value={resumen.total_anual || 0}
                precision={0}
                suffix="€"
                valueStyle={{ fontSize: 16, fontWeight: 600, color: '#531dab' }}
              />
            </Col>
          </Row>
        </Card>
      )}

      {/* ── Gráfico mensual (como ingresos) ── */}
      {resumen && (
        <Card size="small" title={<Text style={{ fontSize: 12 }}>Distribución mensual — pulsa una barra para ver detalle</Text>} bodyStyle={{ padding: '8px 12px' }}>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={datosGrafico} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="mes" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
              <RTooltip formatter={(v: number) => fmt(v)} />
              <Bar dataKey="importe" name="Gastos" radius={[3, 3, 0, 0]} cursor="pointer"
                onClick={(_d: any, index: number) => setDrilldownMesIdx(index)}>
                {datosGrafico.map((_, i) => (
                  <Cell key={i} fill={drilldownMesIdx === i ? '#820014' : '#cf1322'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* ── Tabla principal de gastos ── */}
      {(lineas as any[]).length > 0 && (
        <Card
          size="small"
          bodyStyle={{ padding: 0 }}
          extra={
            <Space size={4}>
              <Select allowClear placeholder="Filtrar familia" style={{ width: 200 }} size="small" onChange={setFiltroFamilia}>
                {familias.map((f: any) => <Option key={f} value={f}>{f}</Option>)}
              </Select>
              <Text type="secondary" style={{ fontSize: 11 }}>{(lineas as any[]).length} cuentas</Text>
              <Button
                size="small"
                icon={<DownloadOutlined />}
                onClick={exportarExcel}
                disabled={(lineas as any[]).length === 0}
              >
                Excel
              </Button>
            </Space>
          }
        >
          <Table
            dataSource={lineas as any[]}
            columns={columnas}
            rowKey="id"
            loading={isLoading}
            size="small"
            pagination={{ pageSize: 20, showTotal: (t) => `${t} cuentas`, size: 'small' }}
            rowClassName={(row: any) => row.tipo_regla === 'excluir' ? 'opacity-40' : ''}
            summary={() => {
              const total = resumen?.total_anual || 0
              const base = resumen?.gasto_base_total || 0
              const delta = base > 0 ? ((total - base) / base) * 100 : 0
              return (
                <Table.Summary.Row style={{ background: '#fafafa', fontWeight: 600 }}>
                  <Table.Summary.Cell index={0} colSpan={3}><Text strong style={{ fontSize: 12 }}>TOTAL incl. cesiones auxiliares</Text></Table.Summary.Cell>
                  <Table.Summary.Cell index={3} align="right"><Text style={{ fontSize: 12 }}>{fmt(base)}</Text></Table.Summary.Cell>
                  <Table.Summary.Cell index={4} />
                  <Table.Summary.Cell index={5} align="right"><Text strong style={{ fontSize: 13, color: '#531dab' }}>{fmt(total)}</Text></Table.Summary.Cell>
                  <Table.Summary.Cell index={6} align="right">
                    <Tag color={delta >= 0 ? 'orange' : 'green'} style={{ fontSize: 11 }}>{pct(delta)}</Tag>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={7} />
                </Table.Summary.Row>
              )
            }}
          />
        </Card>
      )}

      {/* ── Cesiones de auxiliares ── */}
      {presupuestoId && (
        <Card
          size="small"
          title={<span style={{ fontSize: 13, fontWeight: 600 }}>Cesiones a auxiliares — comisiones sobre ingresos presupuestados</span>}
          extra={
            <Space size={4}>
              <Tooltip title="Genera o actualiza las filas de cesiones desde el presupuesto de ingresos. Rellena el % comisión y el % retención desde el catálogo de Administración → Auxiliares para los auxiliares sin configurar. Mantiene los parámetros ya configurados.">
                <Button size="small" icon={<SyncOutlined />} onClick={() => generarCes.mutate()} loading={generarCes.isPending}>
                  Sincronizar desde ingresos
                </Button>
              </Tooltip>
              {(cesiones as any[]).length > 0 && (
                <>
                  <Button size="small" icon={<DownloadOutlined />} onClick={exportarCesionesExcel}>Excel</Button>
                  <input ref={importCesRef} type="file" accept=".xlsx,.xls" style={{ display: 'none' }} onChange={handleImportCes} />
                  <Tooltip title="Importa % comisión, tipo y retención desde Excel (mismo formato que el export)">
                    <Button size="small" icon={<UploadOutlined />} loading={importarCes.isPending} onClick={() => importCesRef.current?.click()}>
                      Importar
                    </Button>
                  </Tooltip>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    Total: <strong style={{ color: '#cf1322' }}>{fmt((cesiones as any[]).reduce((s: number, c: any) => s + c.gasto_comision_total, 0))}</strong>
                  </Text>
                </>
              )}
            </Space>
          }
        >
          {importCesResult && (
            <Alert
              closable
              onClose={() => setImportCesResult(null)}
              style={{ margin: '8px 12px 0' }}
              type={importCesResult.errores.length > 0 ? 'warning' : 'success'}
              showIcon
              message={`${importCesResult.actualizadas} cesión(es) actualizadas${importCesResult.errores.length > 0 ? ` · ${importCesResult.errores.length} error(es)` : ''}`}
              description={importCesResult.errores.length > 0
                ? <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                    {importCesResult.errores.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
                    {importCesResult.errores.length > 5 && <li>…y {importCesResult.errores.length - 5} más</li>}
                  </ul>
                : undefined}
            />
          )}
          {(cesiones as any[]).length === 0 ? (
            <Alert
              type="info"
              showIcon
              message="Sin cesiones configuradas"
              description='Pulsa "Sincronizar desde ingresos" para generar automáticamente las filas de auxiliares del presupuesto de ingresos.'
              style={{ margin: 12 }}
            />
          ) : (
            <Table
              dataSource={cesiones as any[]}
              columns={columnaCesiones}
              rowKey="id"
              size="small"
              pagination={false}
              summary={(data) => {
                const totalIngreso = (data as any[]).reduce((s: number, c: any) => s + c.total_ingreso_base, 0)
                const totalGasto = (data as any[]).reduce((s: number, c: any) => s + c.gasto_comision_total, 0)
                return (
                  <Table.Summary.Row style={{ background: '#fafafa', fontWeight: 600 }}>
                    <Table.Summary.Cell index={0} colSpan={2}><Text strong style={{ fontSize: 12 }}>TOTAL</Text></Table.Summary.Cell>
                    <Table.Summary.Cell index={2} align="right"><Text style={{ fontSize: 12 }}>{fmt(totalIngreso)}</Text></Table.Summary.Cell>
                    <Table.Summary.Cell index={3} /><Table.Summary.Cell index={4} />
                    <Table.Summary.Cell index={5} align="right"><Text strong style={{ fontSize: 13, color: '#cf1322' }}>{fmt(totalGasto)}</Text></Table.Summary.Cell>
                    <Table.Summary.Cell index={6} />
                  </Table.Summary.Row>
                )
              }}
            />
          )}
        </Card>
      )}

      {/* Modal drilldown mensual */}
      <Modal
        title={drilldownMesIdx !== null ? `Detalle ${MESES[drilldownMesIdx]} — ${fmt(datosGrafico[drilldownMesIdx]?.importe || 0)}` : ''}
        open={drilldownMesIdx !== null}
        onCancel={() => setDrilldownMesIdx(null)}
        footer={null}
        width={560}
      >
        <Table
          dataSource={drilldownLineas}
          rowKey="id"
          size="small"
          pagination={false}
          scroll={{ y: 380, x: 420 }}
          columns={[
            { title: 'Cuenta', dataIndex: 'numero_cuenta', width: 90, render: (v: string) => v ? <Text code style={{ fontSize: 11 }}>{v}</Text> : <Tag color="green">Nuevo</Tag> },
            { title: 'Descripción', dataIndex: 'descripcion_cuenta', ellipsis: true },
            { title: 'Importe', dataIndex: 'importe_mes', width: 115, align: 'right' as const,
              render: (v: number) => <Text strong style={{ whiteSpace: 'nowrap' }}>{fmt(v)}</Text>,
              defaultSortOrder: 'descend' as const, sorter: (a: any, b: any) => a.importe_mes - b.importe_mes },
          ]}
          summary={(data) => {
            const total = (data as any[]).reduce((s: number, r: any) => s + (r.importe_mes || 0), 0)
            return (
              <Table.Summary.Row>
                <Table.Summary.Cell index={0} colSpan={2}><Text strong>TOTAL</Text></Table.Summary.Cell>
                <Table.Summary.Cell index={2} align="right"><Text strong>{fmt(total)}</Text></Table.Summary.Cell>
              </Table.Summary.Row>
            )
          }}
        />
      </Modal>

      {/* Drawer: cambiar regla */}
      <Drawer
        title={`Regla: ${lineaEditar?.numero_cuenta} — ${lineaEditar?.descripcion_cuenta}`}
        open={drawerRegla}
        onClose={() => setDrawerRegla(false)}
        width={460}
        extra={
          <Button type="primary" size="small" loading={actualizarRegla.isPending}
            onClick={() => formRegla.validateFields().then(v => actualizarRegla.mutate(v))}>
            Aplicar y recalcular
          </Button>
        }
      >
        {lineaEditar && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Descriptions size="small" bordered column={1}>
              <Descriptions.Item label="Base real">{fmt(lineaEditar.gasto_base_anual)}</Descriptions.Item>
              <Descriptions.Item label="Total actual">{fmt(lineaEditar.total_anual)}</Descriptions.Item>
            </Descriptions>
            <Divider>Configurar regla</Divider>
            <Form form={formRegla} layout="vertical">
              <Form.Item name="tipo_regla" label="Regla de proyección" rules={[{ required: true }]}>
                <Select onChange={(v) => setTipoReglaForm(v)}>
                  <Option value="mantener">Mantener gasto real</Option>
                  <Option value="ipc">Aplicar IPC / variación %</Option>
                  <Option value="importe_anual">Fijar importe anual</Option>
                  <Option value="excluir">Excluir (no proyectar)</Option>
                </Select>
              </Form.Item>
              {tipoReglaForm === 'ipc' && (
                <>
                  <Form.Item name="porcentaje_variacion" label="Porcentaje de variación (%)" rules={[{ required: true }]}>
                    <InputNumber style={{ width: '100%' }} step={0.5} placeholder="Ej: 3.5 para +3.5%" />
                  </Form.Item>
                  <Form.Item name="mes_inicio_variacion" label={
                    <span>Mes de inicio (opcional) <Tooltip title="Si se indica, los meses anteriores mantienen el gasto base."><InfoCircleOutlined /></Tooltip></span>
                  }>
                    <Select allowClear placeholder="Desde el mes 1 (todo el año)">
                      {MESES.map((m, i) => <Option key={i + 1} value={i + 1}>{m} (mes {i + 1})</Option>)}
                    </Select>
                  </Form.Item>
                </>
              )}
              {tipoReglaForm === 'importe_anual' && (
                <>
                  <Form.Item name="importe_anual_manual" label="Importe anual presupuestado (€)" rules={[{ required: true }]}>
                    <InputNumber style={{ width: '100%' }} step={100} min={0} />
                  </Form.Item>
                  <Form.Item name="distribucion" label="Distribución mensual">
                    <Select>
                      <Option value="estacionalidad">Por estacionalidad histórica</Option>
                      <Option value="lineal">Lineal (igual cada mes)</Option>
                    </Select>
                  </Form.Item>
                </>
              )}
              {tipoReglaForm === 'excluir' && (
                <Form.Item name="motivo_exclusion" label="Motivo de exclusión" rules={[{ required: true }]}>
                  <Select>
                    <Option value="gasto_no_recurrente">Gasto no recurrente</Option>
                    <Option value="proveedor_eliminado">Proveedor eliminado</Option>
                    <Option value="plan_eficiencia">Plan de eficiencia</Option>
                    <Option value="extraordinario">Gasto extraordinario</Option>
                    <Option value="decision_direccion">Decisión de dirección</Option>
                  </Select>
                </Form.Item>
              )}
            </Form>

            {lineaEditar && (
              <>
                <Divider plain style={{ fontSize: 12 }}>Distribución mensual actual</Divider>
                <Table size="small" pagination={false}
                  dataSource={MESES.map((mes, i) => ({ key: i, mes, importe: lineaEditar.importes_efectivos?.[i] || 0 }))}
                  columns={[
                    { title: 'Mes', dataIndex: 'mes', width: 50 },
                    { title: 'Importe', dataIndex: 'importe', align: 'right' as const, render: fmt },
                  ]} />
              </>
            )}
          </Space>
        )}
      </Drawer>

      {/* Drawer: ajuste manual de mes */}
      <Drawer
        title={`Ajuste mensual: ${lineaEditar?.numero_cuenta}`}
        open={drawerAjuste}
        onClose={() => setDrawerAjuste(false)}
        width={420}
        extra={
          <Button type="primary" size="small" loading={ajustarMes.isPending} onClick={() => ajustarMes.mutate()}>
            Registrar ajuste
          </Button>
        }
      >
        {lineaEditar && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Alert type="info" showIcon message="El ajuste queda registrado con usuario, fecha y motivo para trazabilidad." />
            <div>
              <Text style={{ fontSize: 12 }}>Mes a ajustar</Text>
              <Select style={{ width: '100%', marginTop: 4 }} size="small" value={mesAjuste}
                onChange={(v) => { setMesAjuste(v); setImporteAjuste(lineaEditar.importes_efectivos?.[v - 1] || 0) }}>
                {MESES.map((m, i) => (
                  <Option key={i + 1} value={i + 1}>{m} — actual: {fmt(lineaEditar.importes_efectivos?.[i] || 0)}</Option>
                ))}
              </Select>
            </div>
            <div>
              <Text style={{ fontSize: 12 }}>Nuevo importe (€)</Text>
              <InputNumber style={{ width: '100%', marginTop: 4 }} size="small" value={importeAjuste} onChange={(v) => setImporteAjuste(v || 0)} step={100} />
            </div>
            <div>
              <Text style={{ fontSize: 12 }}>¿Mantener total anual?</Text>
              <Select style={{ width: '100%', marginTop: 4 }} size="small" value={mantenerTotal ? 'si' : 'no'}
                onChange={(v) => setMantenerTotal(v === 'si')}>
                <Option value="no">No — modificar total anual</Option>
                <Option value="si">Sí — redistribuir diferencia en otros meses</Option>
              </Select>
            </div>
            <div>
              <Text style={{ fontSize: 12 }}>Motivo (obligatorio para trazabilidad)</Text>
              <Input.TextArea value={motivoAjuste} onChange={(e) => setMotivoAjuste(e.target.value)}
                rows={2} placeholder="Ej: Ajuste por cambio de proveedor en octubre" style={{ marginTop: 4 }} />
            </div>
          </Space>
        )}
      </Drawer>

      {/* Drawer: editar parámetros cesión auxiliar */}
      <Drawer
        title={`Cesión: ${cesionEditar?.auxiliar}`}
        open={drawerCesion}
        onClose={() => setDrawerCesion(false)}
        width={460}
        extra={
          <Button type="primary" size="small" loading={actualizarCesion.isPending}
            onClick={() => formCesion.validateFields().then(v => {
              const payload: any = {
                tipo_persona: v.tipo_persona,
                pct_comision: v.pct_comision,
                pct_retencion: v.pct_retencion,
                notas: v.notas,
                gasto_comision_manual: v.gasto_comision_manual ?? null,
              }
              actualizarCesion.mutate(payload)
            })}>
            Guardar y recalcular
          </Button>
        }
      >
        {cesionEditar && (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Descriptions size="small" bordered column={1}>
              <Descriptions.Item label="Ingreso presupuestado">{fmt(cesionEditar.total_ingreso_base)}</Descriptions.Item>
              <Descriptions.Item label="Gasto comisión actual">
                <Space size={6}>
                  <Text strong style={{ color: '#cf1322' }}>{fmt(cesionEditar.gasto_comision_total)}</Text>
                  {cesionEditar.gasto_comision_manual != null && (
                    <Tag color="volcano" style={{ fontSize: 10 }}>Override manual activo</Tag>
                  )}
                </Space>
              </Descriptions.Item>
            </Descriptions>
            <Divider>Parámetros</Divider>
            <Form form={formCesion} layout="vertical" size="small"
              onValuesChange={(changed) => {
                if (changed.tipo_persona === 'fisico') {
                  const cur = formCesion.getFieldValue('pct_retencion')
                  if (!cur) formCesion.setFieldValue('pct_retencion', 15)
                } else if (changed.tipo_persona === 'juridico') {
                  formCesion.setFieldValue('pct_retencion', 0)
                }
                // Al cambiar el %, limpiar el override manual
                if ('pct_comision' in changed) {
                  formCesion.setFieldValue('gasto_comision_manual', null)
                }
                // Al escribir importe manual, no tocamos el %
              }}
            >
              <Form.Item name="tipo_persona" label="Tipo de persona">
                <Select placeholder="Selecciona tipo">
                  <Option value="fisico">Físico (con retención IRPF)</Option>
                  <Option value="juridico">Jurídico (sin retención)</Option>
                </Select>
              </Form.Item>
              <Form.Item name="pct_comision" label={<span>% Comisión <Tooltip title="Porcentaje aplicado sobre el ingreso presupuestado. Si especificas un importe fijo abajo, este % se usa solo como referencia."><InfoCircleOutlined /></Tooltip></span>}>
                <InputNumber style={{ width: '100%' }} min={0} max={100} step={0.5} precision={4} placeholder="Ej: 15.00" />
              </Form.Item>
              <Form.Item name="pct_retencion" label={<span>% Retención IRPF <Tooltip title="Solo aplica a físicos. No cambia el gasto, solo la retención a ingresar a Hacienda."><InfoCircleOutlined /></Tooltip></span>}>
                <InputNumber style={{ width: '100%' }} min={0} max={100} step={0.5} precision={4} placeholder="Ej: 15.00 (físico), 0 (jurídico)" />
              </Form.Item>
              <Divider plain style={{ fontSize: 11, margin: '4px 0' }}>Importe fijo manual (opcional)</Divider>
              <Form.Item
                name="gasto_comision_manual"
                label={
                  <span>
                    Gasto comisión fijo (€){' '}
                    <Tooltip title="Si se especifica, este importe reemplaza el cálculo por porcentaje. Se distribuye mensualmente en proporción al ingreso del auxiliar. Déjalo vacío para usar el % automático.">
                      <InfoCircleOutlined />
                    </Tooltip>
                  </span>
                }
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  step={100}
                  precision={2}
                  placeholder={`Calculado: ${fmt((formCesion.getFieldValue('pct_comision') || 0) / 100 * cesionEditar.total_ingreso_base)}`}
                  addonAfter={
                    <Button
                      size="small"
                      type="link"
                      style={{ padding: 0, height: 'auto', fontSize: 11 }}
                      onClick={() => formCesion.setFieldValue('gasto_comision_manual', null)}
                    >
                      Limpiar
                    </Button>
                  }
                />
              </Form.Item>
              <Form.Item name="notas" label="Notas">
                <Input.TextArea rows={2} placeholder="Observaciones..." />
              </Form.Item>
            </Form>
            <Alert
              type="info"
              showIcon
              style={{ fontSize: 11 }}
              message="Fórmula (sin override manual)"
              description={`${(cesionEditar.pct_comision || 0).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}% × ${fmt(cesionEditar.total_ingreso_base)} = ${fmt((cesionEditar.pct_comision || 0) / 100 * cesionEditar.total_ingreso_base)}`}
            />
            <Divider plain style={{ fontSize: 12 }}>Distribución mensual</Divider>
            <Table size="small" pagination={false}
              dataSource={MESES.map((mes, i) => ({ key: i, mes, importe: cesionEditar.importes_mensuales?.[i] || 0 }))}
              columns={[
                { title: 'Mes', dataIndex: 'mes', width: 50 },
                { title: 'Gasto comisión', dataIndex: 'importe', align: 'right' as const, render: fmt },
              ]} />
          </Space>
        )}
      </Drawer>

      {/* Modal: nuevo gasto */}
      <Modal
        title="Añadir gasto nuevo"
        open={modalNuevo}
        onOk={() => formNuevo.validateFields().then(v => nuevoGasto.mutate(v))}
        onCancel={() => { setModalNuevo(false); formNuevo.resetFields() }}
        confirmLoading={nuevoGasto.isPending}
        okText="Añadir"
        cancelText="Cancelar"
      >
        <Form form={formNuevo} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="descripcion_cuenta" label="Descripción del gasto" rules={[{ required: true }]}>
            <Input placeholder="Ej: Suscripción CRM nuevo" />
          </Form.Item>
          <Form.Item name="familia_gasto" label="Familia de gasto" rules={[{ required: true }]}>
            <Select>
              {['Personal', 'Cesiones a auxiliares', 'Alquiler y oficina', 'Tecnología y software',
                'Servicios profesionales', 'Marketing y captación', 'Gastos financieros',
                'Tributos y seguros', 'Amortizaciones y ajustes', 'Otros gastos'].map(f => (
                <Option key={f} value={f}>{f}</Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item name="importe_anual_manual" label="Importe anual (€)" rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} min={0} step={100} />
          </Form.Item>
          <Form.Item name="distribucion" label="Distribución mensual" initialValue="lineal">
            <Select>
              <Option value="lineal">Lineal (igual cada mes)</Option>
              <Option value="estacionalidad">Por estacionalidad media</Option>
            </Select>
          </Form.Item>
          <Form.Item name="notas" label="Notas">
            <Input.TextArea rows={2} placeholder="Justificación del nuevo gasto..." />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
