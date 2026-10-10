/**
 * Ajustes de imputación de coste por auxiliar.
 *
 * Permite reclasificar importes desde el pool indirecto de cuentas de personal
 * (640, 642, …) como coste directo de un auxiliar concreto.
 *
 * Caso típico: sueldo + SS de un empleado adscrito a un colaborador específico
 * que ya se le descuenta de su liquidación mensual. El modelo analítico mueve
 * ese importe del pool de Personal (distribuido por RECIBOS a todos) a una
 * partida directa del auxiliar.
 */
import { useState } from 'react'
import {
  Row, Col, Card, Table, Button, Form, Input, InputNumber, Switch,
  Select, Space, Typography, Alert, Divider, Popconfirm, message, Tag, Tooltip,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, InfoCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { analiticoApi } from '../../api/analitico'
import { crossSellingApi } from '../../api/crossSelling'
import { apiError } from '../../utils/errorHandler'

const { Text, Title } = Typography

const _miles = (v: number) =>
  Math.round(Math.abs(v ?? 0)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.')
const fmt = (v: number) => (v < 0 ? '-' : '') + _miles(v) + ' €'

// Cuentas más comunes que admiten este tipo de ajuste
const CUENTAS_SUGERIDAS = [
  { value: '640', label: '640 — Sueldos y salarios' },
  { value: '642', label: '642 — Seguridad Social a cargo empresa' },
  { value: '641', label: '641 — Indemnizaciones' },
  { value: '649', label: '649 — Otros gastos sociales' },
]

export default function AjustesCoste() {
  const qc = useQueryClient()
  const [ejercicio, setEjercicio] = useState<number>(2025)
  const [editId, setEditId] = useState<string | null>(null)
  const [form] = Form.useForm()

  const { data: ejercicios = [] } = useQuery({
    queryKey: ['analitico-ejercicios'],
    queryFn: () => analiticoApi.getEjercicios().then(r => r.data),
  })

  const { data: ajustes = [], isLoading } = useQuery({
    queryKey: ['ajustes-coste', ejercicio],
    queryFn: () => analiticoApi.listarAjustesCoste(ejercicio).then(r => r.data),
    enabled: !!ejercicio,
  })

  const { data: auxiliares = [] } = useQuery({
    queryKey: ['auxiliares', ejercicio],
    queryFn: () => crossSellingApi.getAuxiliares(ejercicio),
    enabled: !!ejercicio,
  })
  const opcionesAuxiliar = auxiliares.map(a => ({ value: a.auxiliar, label: a.auxiliar }))

  const invalidate = () => qc.invalidateQueries({ queryKey: ['ajustes-coste', ejercicio] })

  const crearMut = useMutation({
    mutationFn: (data: any) => analiticoApi.crearAjusteCoste(data),
    onSuccess: () => { message.success('Ajuste creado'); invalidate(); form.resetFields() },
    onError: (e: any) => message.error(apiError(e)),
  })

  const actualizarMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) =>
      analiticoApi.actualizarAjusteCoste(id, data),
    onSuccess: () => { message.success('Ajuste actualizado'); invalidate(); setEditId(null); form.resetFields() },
    onError: (e: any) => message.error(apiError(e)),
  })

  const eliminarMut = useMutation({
    mutationFn: (id: string) => analiticoApi.eliminarAjusteCoste(id),
    onSuccess: () => { message.success('Ajuste eliminado'); invalidate() },
    onError: (e: any) => message.error(apiError(e)),
  })

  const toggleActivoMut = useMutation({
    mutationFn: ({ id, activo }: { id: string; activo: boolean }) =>
      analiticoApi.actualizarAjusteCoste(id, { activo }),
    onSuccess: () => invalidate(),
    onError: (e: any) => message.error(apiError(e)),
  })

  const onFinish = (values: any) => {
    const payload = { ...values, ejercicio }
    if (editId) {
      actualizarMut.mutate({ id: editId, data: payload })
    } else {
      crearMut.mutate(payload)
    }
  }

  const startEdit = (row: any) => {
    setEditId(row.id)
    form.setFieldsValue({
      auxiliar: row.auxiliar,
      numero_cuenta: row.numero_cuenta,
      descripcion: row.descripcion,
      importe_mensual: row.importe_mensual,
    })
  }

  const cancelEdit = () => {
    setEditId(null)
    form.resetFields()
  }

  // Totales
  const totalAnual = (ajustes as any[])
    .filter((a: any) => a.activo)
    .reduce((s: number, a: any) => s + a.importe_anual, 0)

  const cols = [
    {
      title: 'Auxiliar', dataIndex: 'auxiliar', ellipsis: true, width: 200,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: 'Cuenta', dataIndex: 'numero_cuenta', width: 80,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    { title: 'Descripción', dataIndex: 'descripcion', ellipsis: true },
    {
      title: '€/mes', dataIndex: 'importe_mensual',
      render: (v: number) => fmt(v), align: 'right' as const, width: 110,
    },
    {
      title: '€/año', dataIndex: 'importe_anual',
      render: (v: number) => <Text strong>{fmt(v)}</Text>,
      align: 'right' as const, width: 120,
    },
    {
      title: 'Activo', dataIndex: 'activo', width: 70, align: 'center' as const,
      render: (v: boolean, row: any) => (
        <Switch
          size="small"
          checked={v}
          onChange={checked => toggleActivoMut.mutate({ id: row.id, activo: checked })}
        />
      ),
    },
    {
      title: 'Acciones', width: 90, align: 'center' as const,
      render: (_: any, row: any) => (
        <Space size={4}>
          <Tooltip title="Editar">
            <Button size="small" icon={<EditOutlined />} onClick={() => startEdit(row)} />
          </Tooltip>
          <Popconfirm
            title="¿Eliminar este ajuste?"
            onConfirm={() => eliminarMut.mutate(row.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div>
        <Title level={4} style={{ margin: 0 }}>Ajustes de coste por auxiliar</Title>
        <Text type="secondary" style={{ fontSize: 12 }}>
          Reclasifica costes de Personal / SS del pool indirecto a un auxiliar concreto.
          Tras guardar, recalcula el modelo analítico para que surtan efecto.
        </Text>
      </div>

      <Alert
        type="info"
        showIcon
        icon={<InfoCircleOutlined />}
        message="¿Cómo funciona?"
        description={
          <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8, fontSize: 12 }}>
            <li>
              <strong>Efecto en 640/642 (Personal / SS):</strong> el importe se <em>extrae</em> del
              pool indirecto de esa cuenta. El resto de auxiliares absorben menos coste de personal.
            </li>
            <li>
              <strong>Efecto en el auxiliar:</strong> ese mismo importe se añade a su
              <strong> Cesión auxiliar</strong> como coste directo. Su comisión neta disminuye
              en la misma cuantía.
            </li>
            <li>
              Caso típico: sueldo + SS de un empleado adscrito a un colaborador que se
              descuenta de su liquidación mensual. El ajuste refleja ese descuento en el modelo analítico.
            </li>
          </ul>
        }
        style={{ marginBottom: 0 }}
      />

      <Row gutter={[24, 0]}>
        {/* Formulario */}
        <Col xs={24} lg={8}>
          <Card
            title={editId ? 'Editar ajuste' : 'Nuevo ajuste'}
            size="small"
            extra={editId && <Button size="small" onClick={cancelEdit}>Cancelar</Button>}
          >
            <Form form={form} layout="vertical" onFinish={onFinish} size="small">
              <Form.Item label="Ejercicio">
                <Select
                  value={ejercicio}
                  onChange={setEjercicio}
                  options={(ejercicios as number[]).map(e => ({ value: e, label: String(e) }))}
                />
              </Form.Item>

              <Form.Item
                name="auxiliar"
                label="Auxiliar"
                rules={[{ required: true, message: 'Obligatorio' }]}
              >
                <Select
                  options={opcionesAuxiliar}
                  placeholder={
                    opcionesAuxiliar.length
                      ? 'Selecciona auxiliar…'
                      : `Sin auxiliares cargados para ${ejercicio} — carga recibos primero`
                  }
                  showSearch
                  allowClear
                  notFoundContent="Sin resultados"
                />
              </Form.Item>

              <Form.Item
                name="numero_cuenta"
                label={
                  <Space size={4}>
                    Cuenta origen
                    <Tooltip title="Cuenta de la que se extrae el coste del pool indirecto">
                      <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                    </Tooltip>
                  </Space>
                }
                rules={[{ required: true, message: 'Obligatorio' }]}
              >
                <Select
                  options={CUENTAS_SUGERIDAS}
                  placeholder="Selecciona cuenta…"
                  showSearch
                  allowClear
                />
              </Form.Item>

              <Form.Item
                name="descripcion"
                label="Descripción"
                rules={[{ required: true, message: 'Obligatorio' }]}
              >
                <Input placeholder="Ej: Sueldo Maria Antonia Cabeza" />
              </Form.Item>

              <Form.Item
                name="importe_mensual"
                label="Importe mensual (€)"
                rules={[{ required: true, message: 'Obligatorio' }]}
              >
                <InputNumber
                  style={{ width: '100%' }}
                  min={0}
                  precision={2}
                  step={100}
                  placeholder="0,00"
                  addonAfter="€/mes"
                />
              </Form.Item>

              <Form.Item noStyle shouldUpdate>
                {() => {
                  const m = form.getFieldValue('importe_mensual') || 0
                  return m > 0 ? (
                    <Alert
                      type="warning"
                      style={{ marginBottom: 12 }}
                      message={
                        <Text style={{ fontSize: 12 }}>
                          Importe anual a reclasificar: <strong>{fmt(m * 12)}</strong>
                          {' '}(se extrae del pool de la cuenta seleccionada)
                        </Text>
                      }
                    />
                  ) : null
                }}
              </Form.Item>

              <Button
                type="primary"
                htmlType="submit"
                block
                icon={editId ? <CheckCircleOutlined /> : <PlusOutlined />}
                loading={crearMut.isPending || actualizarMut.isPending}
              >
                {editId ? 'Guardar cambios' : 'Crear ajuste'}
              </Button>
            </Form>
          </Card>
        </Col>

        {/* Lista de ajustes */}
        <Col xs={24} lg={16}>
          <Card
            title={
              <Space>
                <span>Ajustes del ejercicio {ejercicio}</span>
                {totalAnual > 0 && (
                  <Tag color="blue">Total activos: {fmt(totalAnual)}/año</Tag>
                )}
              </Space>
            }
            size="small"
          >
            <Table
              dataSource={ajustes}
              columns={cols}
              rowKey="id"
              size="small"
              loading={isLoading}
              pagination={false}
              rowClassName={(r: any) => !r.activo ? 'ant-table-row-disabled' : ''}
              summary={pageData => {
                const activos = (pageData as any[]).filter(r => r.activo)
                const total = activos.reduce((s: number, r: any) => s + r.importe_anual, 0)
                if (!total) return null
                return (
                  <Table.Summary.Row>
                    <Table.Summary.Cell index={0} colSpan={4}>
                      <Text strong>Total activos ({activos.length} ajustes)</Text>
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={1} align="right">
                      <Text strong style={{ color: '#1890ff' }}>{fmt(total)}</Text>
                    </Table.Summary.Cell>
                    <Table.Summary.Cell index={2} />
                    <Table.Summary.Cell index={3} />
                  </Table.Summary.Row>
                )
              }}
            />

            {(ajustes as any[]).length === 0 && !isLoading && (
              <div style={{ textAlign: 'center', padding: '24px 0', color: '#8c8c8c' }}>
                <CloseCircleOutlined style={{ fontSize: 24, marginBottom: 8, display: 'block' }} />
                No hay ajustes para {ejercicio}. Usa el formulario para crear el primero.
              </div>
            )}

            <Divider style={{ margin: '12px 0 8px' }} />
            <Alert
              type="warning"
              showIcon
              message="Recuerda recalcular el modelo analítico tras guardar cambios para que los ajustes surtan efecto en los dashboards."
            />
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
