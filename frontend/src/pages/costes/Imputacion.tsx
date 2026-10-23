import { useState } from 'react'
import {
  Card, Row, Col, Select, Button, Space, Typography, Tag, Alert,
  Table, Progress, message, Statistic,
} from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PieChart, Pie, Cell, Tooltip as RTooltip, Legend, ResponsiveContainer } from 'recharts'
import { costesApi } from '../../api/costes'
import { apiError } from '../../utils/errorHandler'

const { Title, Text } = Typography
const { Option } = Select

const MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
const COLORS = ['#1890ff', '#52c41a', '#faad14', '#f5222d', '#722ed1', '#13c2c2', '#fa8c16', '#eb2f96']

const fmt = (v: number) => v?.toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' €'

export default function Imputacion() {
  const qc = useQueryClient()
  const [ejercicio, setEjercicio] = useState<number | null>(null)
  const [mesesSel, setMesesSel] = useState<number[]>([1])

  const { data: anyos = [] } = useQuery({
    queryKey: ['costes-anyos'],
    queryFn: () => costesApi.anyosDisponibles().then(r => r.data),
  })

  const { data: lineas = [], isLoading } = useQuery({
    queryKey: ['costes-lineas-imp', ejercicio],
    queryFn: () => costesApi.listarLineas(ejercicio!).then(r => r.data),
    enabled: !!ejercicio,
  })

  const imputar = useMutation({
    mutationFn: () => costesApi.imputar(ejercicio!, mesesSel),
    onSuccess: (r) => {
      message.success(`${r.data.imputadas} líneas imputadas correctamente`)
      qc.invalidateQueries({ queryKey: ['costes-lineas-imp', ejercicio] })
    },
    onError: (e) => message.error(apiError(e, 'Error al imputar los costes')),
  })

  // Agrupaciones para gráficos
  const porTratamiento = lineas.reduce((acc: any, l: any) => {
    const t = l.tratamiento || 'sin_asignar'
    acc[t] = (acc[t] || 0) + l.importe_real
    return acc
  }, {})

  const pieTratamiento = Object.entries(porTratamiento).map(([name, value]) => ({
    name: name === 'directo' ? 'Directo' : name === 'indirecto' ? 'Indirecto' : name === 'excluido' ? 'Excluido' : 'Sin asignar',
    value: Math.round(value as number),
  }))

  const porDriver = lineas.reduce((acc: any, l: any) => {
    const d = l.driver || 'sin_driver'
    acc[d] = (acc[d] || 0) + l.importe_real
    return acc
  }, {})

  const DRIVER_LABELS: Record<string, string> = {
    comision_contable: 'Comisión contable',
    nueva_produccion: 'Nueva producción',
    numero_polizas: 'Nº pólizas',
    numero_recibos: 'Nº recibos',
    manual_porcentual: 'Manual %',
    sin_driver: 'Sin driver',
  }

  const pieDriver = Object.entries(porDriver).map(([name, value]) => ({
    name: DRIVER_LABELS[name] || name,
    value: Math.round(value as number),
  }))

  const totalDirecto = lineas.filter((l: any) => l.tratamiento === 'directo').reduce((s: number, l: any) => s + l.importe_real, 0)
  const totalIndirecto = lineas.filter((l: any) => l.tratamiento === 'indirecto').reduce((s: number, l: any) => s + l.importe_real, 0)
  const totalExcluido = lineas.filter((l: any) => l.tratamiento === 'excluido').reduce((s: number, l: any) => s + l.importe_real, 0)
  const totalImputadas = lineas.filter((l: any) => l.estado === 'imputado').length

  const colsImputacion = [
    { title: 'Cuenta', dataIndex: 'numero_cuenta', width: 100 },
    { title: 'Descripción', dataIndex: 'descripcion_cuenta', ellipsis: true },
    { title: 'Familia', dataIndex: 'familia_gasto' },
    {
      title: 'Tratamiento',
      render: (_: any, r: any) => {
        const colors: Record<string, string> = { directo: 'green', indirecto: 'blue', excluido: 'orange' }
        return r.tratamiento ? <Tag color={colors[r.tratamiento]}>{r.tratamiento}</Tag> : '—'
      },
    },
    {
      title: 'Importe real', dataIndex: 'importe_real', align: 'right' as const,
      render: (v: number) => fmt(v),
    },
    {
      title: 'Estado',
      render: (_: any, r: any) => {
        const colors: Record<string, string> = { imputado: 'success', clasificado: 'blue', pendiente: 'default', excluido: 'orange' }
        return <Tag color={colors[r.estado] || 'default'}>{r.estado}</Tag>
      },
    },
    {
      title: 'Imputación por dimensión',
      render: (_: any, r: any) => {
        if (!r.imputacion || Object.keys(r.imputacion).length === 0) return <Text type="secondary">—</Text>
        return (
          <Space size={4} wrap>
            {Object.entries(r.imputacion).slice(0, 3).map(([dim, imp]: any) => (
              <Tag key={dim} style={{ fontSize: 11 }}>{dim}: {fmt(imp)}</Tag>
            ))}
            {Object.keys(r.imputacion).length > 3 && (
              <Tag style={{ fontSize: 11 }}>+{Object.keys(r.imputacion).length - 3} más</Tag>
            )}
          </Space>
        )
      },
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Imputación de costes</Title>
          <Text type="secondary">Reparto de costes indirectos por driver entre dimensiones</Text>
        </div>
        <Space>
          <Select placeholder="Ejercicio" style={{ width: 150 }} onChange={setEjercicio} value={ejercicio}>
            {anyos.map((a: number) => <Option key={a} value={a}>Ejercicio {a}</Option>)}
          </Select>
          <Select
            mode="multiple"
            placeholder="Meses"
            style={{ width: 200 }}
            value={mesesSel}
            onChange={setMesesSel}
          >
            {MESES.map((m, i) => <Option key={i + 1} value={i + 1}>{m}</Option>)}
          </Select>
          <Button
            type="primary" icon={<ThunderboltOutlined />}
            loading={imputar.isPending}
            disabled={!ejercicio || mesesSel.length === 0}
            onClick={() => imputar.mutate()}
          >
            Ejecutar imputación
          </Button>
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        message="Vista aproximada, solo por compañía"
        description="Este reparto es una estimación rápida (comisión contable / nueva producción, agregado por compañía). Para el detalle real de rentabilidad por cliente, ramo o auxiliar, consulta el Modelo Analítico."
      />

      {!ejercicio && <Alert type="info" showIcon message="Selecciona un ejercicio para ver la imputación de costes" />}

      {ejercicio && (
        <>
          <Row gutter={16}>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center', borderTop: '3px solid #52c41a' }}>
                <Statistic title="Coste directo" value={totalDirecto} precision={2} suffix="€"
                  valueStyle={{ color: '#52c41a', fontSize: 16 }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center', borderTop: '3px solid #1890ff' }}>
                <Statistic title="Coste indirecto" value={totalIndirecto} precision={2} suffix="€"
                  valueStyle={{ color: '#1890ff', fontSize: 16 }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center', borderTop: '3px solid #faad14' }}>
                <Statistic title="Coste excluido" value={totalExcluido} precision={2} suffix="€"
                  valueStyle={{ color: '#faad14', fontSize: 16 }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center', borderTop: '3px solid #52c41a' }}>
                <Statistic title="Líneas imputadas" value={totalImputadas} suffix={`/ ${lineas.length}`}
                  valueStyle={{ color: '#52c41a', fontSize: 16 }} />
              </Card>
            </Col>
          </Row>

          {lineas.length > 0 && (
            <Progress
              percent={lineas.length > 0 ? Math.round((totalImputadas / lineas.length) * 100) : 0}
              status={totalImputadas === lineas.length ? 'success' : 'active'}
              format={p => `${p}% imputado`}
            />
          )}

          <Row gutter={16}>
            <Col span={12}>
              <Card title="Distribución por tratamiento">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={pieTratamiento} dataKey="value" nameKey="name" outerRadius={80} label>
                      {pieTratamiento.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <RTooltip formatter={(v: number) => fmt(v)} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </Card>
            </Col>
            <Col span={12}>
              <Card title="Distribución por driver de reparto">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={pieDriver} dataKey="value" nameKey="name" outerRadius={80} label>
                      {pieDriver.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <RTooltip formatter={(v: number) => fmt(v)} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </Card>
            </Col>
          </Row>

          <Card>
            <Table
              dataSource={lineas}
              columns={colsImputacion}
              rowKey="id"
              size="small"
              loading={isLoading}
              pagination={{ pageSize: 20 }}
            />
          </Card>
        </>
      )}
    </Space>
  )
}
