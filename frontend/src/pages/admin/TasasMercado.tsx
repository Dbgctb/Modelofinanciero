import { useState } from 'react'
import {
  Space, Typography, Card, Table, Tag, Button, Select,
  Modal, Form, InputNumber, Input, Switch, Popconfirm, message, Row, Col,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { adminApi } from '../../api/admin'
import { apiError } from '../../utils/errorHandler'

const { Title, Text } = Typography
const { Option } = Select

const TIPO_LABELS: Record<string, { label: string; color: string }> = {
  crecimiento:            { label: 'Crecimiento',        color: 'blue' },
  caida_cartera:          { label: 'Caída cartera',      color: 'orange' },
  caida_nueva_produccion: { label: 'Caída nueva prod.',  color: 'red' },
}

export default function TasasMercado() {
  const qc = useQueryClient()
  const [anyoFiltro, setAnyoFiltro] = useState<number | undefined>(undefined)
  const [tipoFiltro, setTipoFiltro] = useState<string | undefined>(undefined)
  const [modalVisible, setModalVisible] = useState(false)
  const [editando, setEditando] = useState<any>(null)
  const [form] = Form.useForm()

  const { data: anyos = [] } = useQuery({
    queryKey: ['admin-tasas-anyos'],
    queryFn: () => adminApi.listarAnyos().then(r => r.data),
  })

  const { data: tasas = [], isLoading } = useQuery({
    queryKey: ['admin-tasas', anyoFiltro, tipoFiltro],
    queryFn: () => adminApi.listarTasas({ anyo: anyoFiltro, tipo: tipoFiltro }).then(r => r.data),
  })

  const crear = useMutation({
    mutationFn: (datos: any) => adminApi.crearTasa(datos),
    onSuccess: () => {
      message.success('Tasa creada')
      qc.invalidateQueries({ queryKey: ['admin-tasas'] })
      qc.invalidateQueries({ queryKey: ['admin-tasas-anyos'] })
      setModalVisible(false)
      form.resetFields()
    },
    onError: (e) => message.error(apiError(e, 'Error al crear tasa')),
  })

  const actualizar = useMutation({
    mutationFn: ({ id, datos }: { id: string; datos: any }) => adminApi.actualizarTasa(id, datos),
    onSuccess: () => {
      message.success('Tasa actualizada')
      qc.invalidateQueries({ queryKey: ['admin-tasas'] })
      setModalVisible(false)
      setEditando(null)
      form.resetFields()
    },
    onError: (e) => message.error(apiError(e, 'Error al actualizar tasa')),
  })

  const eliminar = useMutation({
    mutationFn: (id: string) => adminApi.eliminarTasa(id),
    onSuccess: () => {
      message.success('Tasa eliminada')
      qc.invalidateQueries({ queryKey: ['admin-tasas'] })
    },
    onError: (e) => message.error(apiError(e, 'Error al eliminar tasa')),
  })

  const abrirCrear = () => {
    setEditando(null)
    form.resetFields()
    form.setFieldsValue({ fuente: 'ICEA', es_default: false })
    setModalVisible(true)
  }

  const abrirEditar = (tasa: any) => {
    setEditando(tasa)
    form.setFieldsValue({
      fuente: tasa.fuente,
      anyo: tasa.anyo,
      tipo: tasa.tipo,
      ramo_keyword: tasa.ramo_keyword || '',
      tasa_pct: tasa.tasa_pct,
      es_default: tasa.es_default,
      notas: tasa.notas || '',
    })
    setModalVisible(true)
  }

  const onOk = () => {
    form.validateFields().then((vals) => {
      const datos = {
        ...vals,
        ramo_keyword: vals.ramo_keyword?.trim() || null,
        notas: vals.notas?.trim() || null,
      }
      if (editando) {
        actualizar.mutate({ id: editando.id, datos })
      } else {
        crear.mutate(datos)
      }
    })
  }

  const columns = [
    {
      title: 'Año',
      dataIndex: 'anyo',
      width: 70,
      sorter: (a: any, b: any) => a.anyo - b.anyo,
    },
    {
      title: 'Fuente',
      dataIndex: 'fuente',
      width: 80,
    },
    {
      title: 'Tipo',
      dataIndex: 'tipo',
      width: 160,
      render: (v: string) => {
        const t = TIPO_LABELS[v]
        return <Tag color={t?.color}>{t?.label ?? v}</Tag>
      },
    },
    {
      title: 'Keyword ramo',
      dataIndex: 'ramo_keyword',
      width: 140,
      render: (v: string | null) => v
        ? <Text code>{v}</Text>
        : <Tag color="default">DEFAULT</Tag>,
    },
    {
      title: 'Tasa %',
      dataIndex: 'tasa_pct',
      width: 90,
      render: (v: number) => `${v.toFixed(2)}%`,
      sorter: (a: any, b: any) => a.tasa_pct - b.tasa_pct,
    },
    {
      title: 'Default',
      dataIndex: 'es_default',
      width: 80,
      render: (v: boolean) => v ? <Tag color="green">Sí</Tag> : <Tag color="default">No</Tag>,
    },
    {
      title: 'Notas',
      dataIndex: 'notas',
      ellipsis: true,
    },
    {
      title: '',
      width: 100,
      render: (_: any, row: any) => (
        <Space size={4}>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => abrirEditar(row)}
          />
          <Popconfirm
            title="¿Eliminar esta tasa?"
            okText="Eliminar"
            okType="danger"
            cancelText="Cancelar"
            onConfirm={() => eliminar.mutate(row.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={4} style={{ margin: 0 }}>Tasas de referencia de mercado</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={abrirCrear}>
          Nueva tasa
        </Button>
      </div>

      <Card size="small">
        <Row gutter={16}>
          <Col>
            <Space>
              <Text type="secondary">Año:</Text>
              <Select
                allowClear
                placeholder="Todos"
                style={{ width: 100 }}
                value={anyoFiltro}
                onChange={setAnyoFiltro}
              >
                {(anyos as number[]).map((a) => (
                  <Option key={a} value={a}>{a}</Option>
                ))}
              </Select>
            </Space>
          </Col>
          <Col>
            <Space>
              <Text type="secondary">Tipo:</Text>
              <Select
                allowClear
                placeholder="Todos"
                style={{ width: 180 }}
                value={tipoFiltro}
                onChange={setTipoFiltro}
              >
                {Object.entries(TIPO_LABELS).map(([k, v]) => (
                  <Option key={k} value={k}>{v.label}</Option>
                ))}
              </Select>
            </Space>
          </Col>
        </Row>
      </Card>

      <Card>
        <Table
          dataSource={tasas}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: false }}
        />
      </Card>

      <Modal
        title={editando ? 'Editar tasa' : 'Nueva tasa de referencia'}
        open={modalVisible}
        onOk={onOk}
        onCancel={() => { setModalVisible(false); setEditando(null); form.resetFields() }}
        confirmLoading={crear.isPending || actualizar.isPending}
        okText={editando ? 'Guardar' : 'Crear'}
        cancelText="Cancelar"
        width={500}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="fuente" label="Fuente" rules={[{ required: true }]}>
                <Input placeholder="ICEA, UNESPA..." />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="anyo" label="Año" rules={[{ required: true }]}>
                <InputNumber min={2000} max={2100} style={{ width: '100%' }} disabled={!!editando} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="tipo" label="Tipo" rules={[{ required: true }]}>
            <Select disabled={!!editando}>
              {Object.entries(TIPO_LABELS).map(([k, v]) => (
                <Option key={k} value={k}>{v.label}</Option>
              ))}
            </Select>
          </Form.Item>
          <Row gutter={12}>
            <Col span={14}>
              <Form.Item
                name="ramo_keyword"
                label="Keyword ramo"
                tooltip="Subcadena que debe contener el nombre del ramo. Vacío = fila default."
              >
                <Input placeholder="auto, salud, multirriesg... (vacío = default)" />
              </Form.Item>
            </Col>
            <Col span={10}>
              <Form.Item name="tasa_pct" label="Tasa (%)" rules={[{ required: true }]}>
                <InputNumber min={-100} max={200} step={0.1} precision={2} style={{ width: '100%' }} addonAfter="%" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="es_default" label="Es default del año/tipo" valuePropName="checked">
            <Switch checkedChildren="Sí" unCheckedChildren="No" />
          </Form.Item>
          <Form.Item name="notas" label="Notas">
            <Input.TextArea rows={2} placeholder="Fuente, observaciones..." />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
