import { useState } from 'react'
import {
  Card, Row, Col, Select, Button, Space, Typography, Tag, Alert,
  Table, Drawer, Form, Input, message, Statistic,
} from 'antd'
import {
  ThunderboltOutlined, EditOutlined, CheckCircleOutlined,
  ClockCircleOutlined, WarningOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { costesApi } from '../../api/costes'
import { apiError } from '../../utils/errorHandler'

const { Title, Text } = Typography
const { Option } = Select

const MESES = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']

const ESTADO_TAG: Record<string, { color: string; label: string }> = {
  pendiente:   { color: 'default', label: 'Pendiente' },
  clasificado: { color: 'blue', label: 'Clasificado' },
  imputado:    { color: 'success', label: 'Imputado' },
  excluido:    { color: 'orange', label: 'Excluido' },
  con_alerta:  { color: 'error', label: 'Con alerta' },
}

const TIPO_TAG: Record<string, { color: string; label: string }> = {
  fijo:     { color: 'geekblue', label: 'Fijo' },
  variable: { color: 'purple', label: 'Variable' },
}

const TRATAMIENTO_TAG: Record<string, { color: string; label: string }> = {
  directo:   { color: 'green', label: 'Directo' },
  indirecto: { color: 'blue', label: 'Indirecto' },
  excluido:  { color: 'orange', label: 'Excluido' },
}

const DRIVERS = [
  { value: 'comision_contable', label: 'Comisión contable' },
  { value: 'nueva_produccion', label: 'Nueva producción' },
  { value: 'numero_polizas', label: 'Nº pólizas' },
  { value: 'numero_recibos', label: 'Nº recibos' },
  { value: 'manual_porcentual', label: 'Manual porcentual' },
]

const MOTIVOS_EXCLUSION = [
  { value: 'amortizacion', label: 'Amortización' },
  { value: 'ajuste_contable', label: 'Ajuste contable' },
  { value: 'extraordinario', label: 'Extraordinario' },
  { value: 'sin_impacto_caja', label: 'Sin impacto en caja' },
  { value: 'no_operativo', label: 'No operativo' },
  { value: 'decision_direccion', label: 'Decisión de dirección' },
]

const fmt = (v: number) => v?.toLocaleString('es-ES', { minimumFractionDigits: 2 }) + ' €'

export default function Clasificacion() {
  const qc = useQueryClient()
  const [ejercicio, setEjercicio] = useState<number | null>(null)
  const [mes, setMes] = useState<number>(1)
  const [lineaEdit, setLineaEdit] = useState<any>(null)
  const [form] = Form.useForm()

  const { data: anyos = [] } = useQuery({
    queryKey: ['costes-anyos'],
    queryFn: () => costesApi.anyosDisponibles().then(r => r.data),
  })

  const { data: lineas = [], isLoading } = useQuery({
    queryKey: ['costes-lineas', ejercicio, mes],
    queryFn: () => costesApi.listarLineas(ejercicio!, { mes }).then(r => r.data),
    enabled: !!ejercicio,
  })

  const { data: familias = [] } = useQuery({
    queryKey: ['costes-familias'],
    queryFn: () => costesApi.familiasClasificacion().then(r => r.data),
  })

  const clasificar = useMutation({
    mutationFn: () => costesApi.clasificar(ejercicio!, mes),
    onSuccess: (r) => {
      message.success(`${r.data.clasificadas} líneas clasificadas automáticamente`)
      qc.invalidateQueries({ queryKey: ['costes-lineas', ejercicio, mes] })
    },
    onError: (e) => message.error(apiError(e, 'Error al clasificar los costes')),
  })

  const actualizar = useMutation({
    mutationFn: (data: any) => costesApi.actualizarLinea(ejercicio!, lineaEdit.id, data),
    onSuccess: () => {
      message.success('Clasificación actualizada')
      qc.invalidateQueries({ queryKey: ['costes-lineas', ejercicio, mes] })
      setLineaEdit(null)
    },
    onError: (e) => message.error(apiError(e, 'Error al actualizar la clasificación')),
  })

  const pendientes = lineas.filter((l: any) => l.estado === 'pendiente').length
  const clasificadas = lineas.filter((l: any) => l.estado === 'clasificado').length
  const imputadas = lineas.filter((l: any) => l.estado === 'imputado').length
  const conAlerta = lineas.filter((l: any) => l.estado === 'con_alerta').length

  const cols = [
    { title: 'Cuenta', dataIndex: 'numero_cuenta', width: 100 },
    { title: 'Descripción', dataIndex: 'descripcion_cuenta', ellipsis: true },
    { title: 'Familia', dataIndex: 'familia_gasto' },
    {
      title: 'Importe real', dataIndex: 'importe_real', align: 'right' as const,
      render: (v: number) => fmt(v),
    },
    {
      title: 'Tipo',
      render: (_: any, r: any) => r.tipo_coste
        ? <Tag color={TIPO_TAG[r.tipo_coste]?.color}>{TIPO_TAG[r.tipo_coste]?.label}</Tag>
        : <Text type="secondary">—</Text>,
    },
    {
      title: 'Tratamiento',
      render: (_: any, r: any) => r.tratamiento
        ? <Tag color={TRATAMIENTO_TAG[r.tratamiento]?.color}>{TRATAMIENTO_TAG[r.tratamiento]?.label}</Tag>
        : <Text type="secondary">—</Text>,
    },
    {
      title: 'Driver',
      render: (_: any, r: any) => {
        const d = DRIVERS.find(x => x.value === r.driver)
        return d ? <Tag>{d.label}</Tag> : <Text type="secondary">—</Text>
      },
    },
    {
      title: 'Estado',
      render: (_: any, r: any) => {
        const cfg = ESTADO_TAG[r.estado] || { color: 'default', label: r.estado }
        return <Tag color={cfg.color}>{cfg.label}</Tag>
      },
    },
    {
      title: 'Auto',
      dataIndex: 'clasificacion_automatica',
      render: (v: boolean) => v ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <EditOutlined style={{ color: '#1890ff' }} />,
    },
    {
      title: '',
      render: (_: any, r: any) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => {
          setLineaEdit(r)
          form.setFieldsValue({
            tipo_coste: r.tipo_coste,
            tratamiento: r.tratamiento,
            driver: r.driver,
            motivo_exclusion: r.motivo_exclusion,
            notas: r.notas,
          })
        }}>Editar</Button>
      ),
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Clasificación de costes</Title>
          <Text type="secondary">Clasificación automática y manual por familia de gasto</Text>
        </div>
        <Space>
          <Select placeholder="Ejercicio" style={{ width: 150 }} onChange={setEjercicio} value={ejercicio}>
            {anyos.map((a: number) => <Option key={a} value={a}>Ejercicio {a}</Option>)}
          </Select>
          <Select value={mes} onChange={setMes} style={{ width: 100 }}>
            {MESES.map((m, i) => <Option key={i + 1} value={i + 1}>{m}</Option>)}
          </Select>
          <Button
            type="primary" icon={<ThunderboltOutlined />}
            loading={clasificar.isPending}
            disabled={!ejercicio}
            onClick={() => clasificar.mutate()}
          >
            Clasificar automático
          </Button>
        </Space>
      </div>

      {!ejercicio && <Alert type="info" showIcon message="Selecciona un ejercicio para ver las líneas de coste" />}

      {ejercicio && (
        <>
          <Row gutter={16}>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Statistic title="Pendientes" value={pendientes} valueStyle={{ color: '#999' }}
                  prefix={<ClockCircleOutlined />} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Statistic title="Clasificadas" value={clasificadas} valueStyle={{ color: '#1890ff' }}
                  prefix={<CheckCircleOutlined />} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Statistic title="Imputadas" value={imputadas} valueStyle={{ color: '#52c41a' }}
                  prefix={<CheckCircleOutlined />} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small" style={{ textAlign: 'center' }}>
                <Statistic title="Con alerta" value={conAlerta} valueStyle={{ color: '#f5222d' }}
                  prefix={<WarningOutlined />} />
              </Card>
            </Col>
          </Row>

          {conAlerta > 0 && (
            <Alert type="warning" showIcon
              message={`${conAlerta} línea(s) sin familia asignada. Revisa el mapeo de cuentas para clasificarlas.`}
            />
          )}

          <Card>
            <Table
              dataSource={lineas}
              columns={cols}
              rowKey="id"
              size="small"
              loading={isLoading}
              pagination={{ pageSize: 20 }}
              rowClassName={(r: any) => r.estado === 'con_alerta' ? 'row-alerta' : ''}
            />
          </Card>
        </>
      )}

      <Drawer
        title="Editar clasificación"
        open={!!lineaEdit}
        onClose={() => { setLineaEdit(null); form.resetFields() }}
        width={420}
        footer={
          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button onClick={() => { setLineaEdit(null); form.resetFields() }}>Cancelar</Button>
            <Button type="primary" loading={actualizar.isPending}
              onClick={() => form.validateFields().then(v => actualizar.mutate(v))}>
              Guardar
            </Button>
          </Space>
        }
      >
        {lineaEdit && (
          <div style={{ marginBottom: 16 }}>
            <Text strong>{lineaEdit.numero_cuenta}</Text> — {lineaEdit.descripcion_cuenta}<br />
            <Text type="secondary">{lineaEdit.familia_gasto}</Text>
            <div style={{ marginTop: 4 }}>
              <Text strong>{fmt(lineaEdit.importe_real)}</Text>
            </div>
          </div>
        )}
        <Form form={form} layout="vertical">
          <Form.Item name="tipo_coste" label="Tipo de coste">
            <Select>
              <Option value="fijo">Fijo</Option>
              <Option value="variable">Variable</Option>
            </Select>
          </Form.Item>
          <Form.Item name="tratamiento" label="Tratamiento">
            <Select>
              <Option value="directo">Directo</Option>
              <Option value="indirecto">Indirecto</Option>
              <Option value="excluido">Excluido</Option>
            </Select>
          </Form.Item>
          <Form.Item name="driver" label="Driver de reparto">
            <Select>
              {DRIVERS.map(d => <Option key={d.value} value={d.value}>{d.label}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="motivo_exclusion" label="Motivo exclusión (si aplica)">
            <Select allowClear>
              {MOTIVOS_EXCLUSION.map(m => <Option key={m.value} value={m.value}>{m.label}</Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="notas" label="Notas">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>

        <Card title="Clasificación predefinida por familia" size="small">
          <Table
            dataSource={familias}
            columns={[
              { title: 'Familia', dataIndex: 'familia', ellipsis: true },
              { title: 'Tipo', dataIndex: 'tipo_coste', render: (v: string) => <Tag color={TIPO_TAG[v]?.color}>{TIPO_TAG[v]?.label}</Tag> },
              { title: 'Tratamiento', dataIndex: 'tratamiento', render: (v: string) => <Tag color={TRATAMIENTO_TAG[v]?.color}>{TRATAMIENTO_TAG[v]?.label}</Tag> },
            ]}
            rowKey="familia"
            size="small"
            pagination={false}
          />
        </Card>
      </Drawer>
    </Space>
  )
}
