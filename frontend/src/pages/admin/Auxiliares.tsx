import { useRef, useState } from 'react'
import {
  Space, Typography, Card, Table, Button, Select,
  Modal, Form, InputNumber, Input, Popconfirm, message, Row, Col, Alert, Tooltip,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, UploadOutlined, FileOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { adminApi } from '../../api/admin'
import { apiError } from '../../utils/errorHandler'

const { Title, Text } = Typography
const { Option } = Select

export default function Auxiliares() {
  const qc = useQueryClient()
  const [anyoFiltro, setAnyoFiltro] = useState<number | undefined>(undefined)
  const [modalVisible, setModalVisible] = useState(false)
  const [editando, setEditando] = useState<any>(null)
  const [form] = Form.useForm()
  const importRef = useRef<HTMLInputElement>(null)
  const [importModalVisible, setImportModalVisible] = useState(false)
  const [importAnyo, setImportAnyo] = useState<number | null>(null)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importResult, setImportResult] = useState<{ insertados: number; actualizados: number; errores: string[] } | null>(null)

  const { data: anyos = [] } = useQuery({
    queryKey: ['admin-auxiliares-anyos'],
    queryFn: () => adminApi.listarAuxiliaresComisionAnyos().then(r => r.data),
  })

  const { data: filas = [], isLoading } = useQuery({
    queryKey: ['admin-auxiliares', anyoFiltro],
    queryFn: () => adminApi.listarAuxiliaresComision({ anyo: anyoFiltro }).then(r => r.data),
  })

  const crear = useMutation({
    mutationFn: (datos: any) => adminApi.crearAuxiliarComision(datos),
    onSuccess: () => {
      message.success('Auxiliar creado')
      qc.invalidateQueries({ queryKey: ['admin-auxiliares'] })
      qc.invalidateQueries({ queryKey: ['admin-auxiliares-anyos'] })
      setModalVisible(false)
      form.resetFields()
    },
    onError: (e) => message.error(apiError(e, 'Error al crear el registro')),
  })

  const actualizar = useMutation({
    mutationFn: ({ id, comision_colaborador, pct_retencion }: { id: string; comision_colaborador: number; pct_retencion: number }) =>
      adminApi.actualizarAuxiliarComision(id, { comision_colaborador, pct_retencion }),
    onSuccess: () => {
      message.success('Comisión actualizada')
      qc.invalidateQueries({ queryKey: ['admin-auxiliares'] })
      setModalVisible(false)
      setEditando(null)
      form.resetFields()
    },
    onError: (e) => message.error(apiError(e, 'Error al actualizar')),
  })

  const eliminar = useMutation({
    mutationFn: (id: string) => adminApi.eliminarAuxiliarComision(id),
    onSuccess: () => {
      message.success('Registro eliminado')
      qc.invalidateQueries({ queryKey: ['admin-auxiliares'] })
    },
    onError: (e) => message.error(apiError(e, 'Error al eliminar')),
  })

  const importar = useMutation({
    mutationFn: ({ anyo, file }: { anyo: number; file: File }) =>
      adminApi.importarAuxiliaresComisionCsv(anyo, file),
    onSuccess: (res) => {
      setImportResult(res.data)
      qc.invalidateQueries({ queryKey: ['admin-auxiliares'] })
      qc.invalidateQueries({ queryKey: ['admin-auxiliares-anyos'] })
      setImportModalVisible(false)
      setImportAnyo(null)
      setImportFile(null)
    },
    onError: (e) => message.error(apiError(e, 'Error al importar el CSV')),
  })

  const abrirImportar = () => {
    setImportAnyo(null)
    setImportFile(null)
    setImportModalVisible(true)
  }

  const handleSeleccionarFichero = (e: { target: HTMLInputElement }) => {
    const file = e.target.files?.[0]
    if (file) setImportFile(file)
    e.target.value = ''
  }

  const confirmarImportar = () => {
    if (!importAnyo) {
      message.error('Indica el año')
      return
    }
    if (!importFile) {
      message.error('Selecciona el fichero CSV')
      return
    }
    importar.mutate({ anyo: importAnyo, file: importFile })
  }

  const abrirCrear = () => {
    setEditando(null)
    form.resetFields()
    setModalVisible(true)
  }

  const abrirEditar = (fila: any) => {
    setEditando(fila)
    form.setFieldsValue({
      anyo: fila.anyo,
      auxiliar: fila.auxiliar,
      comision_colaborador: fila.comision_colaborador,
      pct_retencion: fila.pct_retencion,
    })
    setModalVisible(true)
  }

  const onOk = () => {
    form.validateFields().then((vals) => {
      if (editando) {
        actualizar.mutate({ id: editando.id, comision_colaborador: vals.comision_colaborador, pct_retencion: vals.pct_retencion })
      } else {
        crear.mutate(vals)
      }
    })
  }

  const columns = [
    {
      title: 'Año',
      dataIndex: 'anyo',
      width: 80,
      sorter: (a: any, b: any) => a.anyo - b.anyo,
    },
    {
      title: 'Auxiliar',
      dataIndex: 'auxiliar',
    },
    {
      title: 'Comisión colaborador',
      dataIndex: 'comision_colaborador',
      width: 170,
      render: (v: number) => `${v.toFixed(2)}%`,
      sorter: (a: any, b: any) => a.comision_colaborador - b.comision_colaborador,
    },
    {
      title: '% Retención',
      dataIndex: 'pct_retencion',
      width: 120,
      render: (v: number) => `${v.toFixed(2)}%`,
      sorter: (a: any, b: any) => a.pct_retencion - b.pct_retencion,
    },
    {
      title: '',
      width: 100,
      render: (_: any, row: any) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => abrirEditar(row)} />
          <Popconfirm
            title="¿Eliminar este registro?"
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
        <Title level={4} style={{ margin: 0 }}>Comisión de colaborador por auxiliar</Title>
        <Space>
          <Tooltip title="CSV con columnas: auxiliar, comisión colaborador">
            <Button icon={<UploadOutlined />} onClick={abrirImportar}>
              Importar CSV
            </Button>
          </Tooltip>
          <Button type="primary" icon={<PlusOutlined />} onClick={abrirCrear}>
            Nuevo
          </Button>
        </Space>
      </div>

      <Text type="secondary">
        Al generar las cesiones de auxiliares en el presupuesto de gastos, el % comisión de
        cada auxiliar nuevo se rellena automáticamente con la comisión de este catálogo para
        el año del presupuesto. El % de retención se autocalcula al crear el auxiliar: 15% si
        no lleva "S.L." en el nombre (persona física), 0% si lo lleva — corrígelo a mano si
        es otra forma jurídica (S.A., S.COOP, C.B...).
      </Text>

      {importResult && (
        <Alert
          closable
          onClose={() => setImportResult(null)}
          type={importResult.errores.length > 0 ? 'warning' : 'success'}
          showIcon
          message={`${importResult.insertados} insertado(s), ${importResult.actualizados} actualizado(s)${importResult.errores.length > 0 ? ` · ${importResult.errores.length} error(es)` : ''}`}
          description={importResult.errores.length > 0
            ? <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                {importResult.errores.slice(0, 5).map((e, i) => <li key={i}>{e}</li>)}
                {importResult.errores.length > 5 && <li>…y {importResult.errores.length - 5} más</li>}
              </ul>
            : undefined}
        />
      )}

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
        </Row>
      </Card>

      <Card>
        <Table
          dataSource={filas}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: false }}
        />
      </Card>

      <Modal
        title={editando ? 'Editar comisión' : 'Nuevo registro'}
        open={modalVisible}
        onOk={onOk}
        onCancel={() => { setModalVisible(false); setEditando(null); form.resetFields() }}
        confirmLoading={crear.isPending || actualizar.isPending}
        okText={editando ? 'Guardar' : 'Crear'}
        cancelText="Cancelar"
        width={450}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="anyo" label="Año" rules={[{ required: true }]}>
                <InputNumber min={2000} max={2100} style={{ width: '100%' }} disabled={!!editando} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="comision_colaborador" label="Comisión colaborador (%)" rules={[{ required: true }]}>
                <InputNumber min={0} max={100} step={0.1} precision={2} style={{ width: '100%' }} addonAfter="%" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="auxiliar" label="Auxiliar" rules={[{ required: true }]}>
            <Input placeholder="Nombre del auxiliar" disabled={!!editando} />
          </Form.Item>
          {editando && (
            <Form.Item
              name="pct_retencion"
              label="% Retención (IRPF)"
              tooltip="Se rellena solo al crear: 15% si el auxiliar no lleva 'S.L.' en el nombre (persona física), 0% si lo lleva. Corrígelo a mano para S.A., S.COOP, C.B. u otras formas jurídicas que esta regla no detecta."
              rules={[{ required: true }]}
            >
              <InputNumber min={0} max={100} step={0.1} precision={2} style={{ width: '100%' }} addonAfter="%" />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        title="Importar CSV de auxiliares"
        open={importModalVisible}
        onOk={confirmarImportar}
        onCancel={() => { setImportModalVisible(false); setImportAnyo(null); setImportFile(null) }}
        confirmLoading={importar.isPending}
        okText="Importar"
        cancelText="Cancelar"
        width={450}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%', marginTop: 16 }}>
          <div>
            <Text strong>Año</Text>
            <div style={{ marginTop: 4 }}>
              <InputNumber
                min={2000}
                max={2100}
                style={{ width: '100%' }}
                placeholder="Año al que corresponde el fichero"
                value={importAnyo}
                onChange={setImportAnyo}
              />
            </div>
          </div>
          <div>
            <Text strong>Fichero CSV</Text>
            <div style={{ marginTop: 4 }}>
              <input ref={importRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={handleSeleccionarFichero} />
              <Button icon={<FileOutlined />} onClick={() => importRef.current?.click()} block>
                {importFile ? importFile.name : 'Seleccionar fichero...'}
              </Button>
            </div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              Columnas esperadas: auxiliar, comisión colaborador. El año se aplica a todas las filas.
            </Text>
          </div>
        </Space>
      </Modal>
    </Space>
  )
}
