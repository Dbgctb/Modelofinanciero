import { useState } from 'react'
import {
  Card, Table, Button, Form, Input, Select, Space, Popconfirm,
  message, Typography, Tabs, Tag, Alert,
} from 'antd'
import { DeleteOutlined, EditOutlined, SaveOutlined, ImportOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { analiticoApi } from '../../api/analitico'
import { apiError } from '../../utils/errorHandler'

const { Title, Text } = Typography

const NATURALEZAS = [
  'Personal', 'Alquiler', 'Tecnología', 'Marketing', 'Financiero',
  'Bancos', 'Servicios profesionales', 'Comunicaciones', 'Viajes',
  'Impuestos', 'Seguros', 'Suministros', 'Cesión auxiliar',
]
const DRIVERS = ['RECIBOS', 'POLIZAS', 'COMISION_NETA', 'NUEVA_PRODUCCION']
const DRIVER_LABELS: Record<string, string> = {
  RECIBOS: 'Recibos (volumen)',
  POLIZAS: 'Pólizas (gestión)',
  COMISION_NETA: 'Comisión neta (€)',
  NUEVA_PRODUCCION: 'Nueva producción (€)',
}
const NAT_COLOR: Record<string, string> = {
  'Personal': 'blue', 'Alquiler': 'orange', 'Tecnología': 'cyan',
  'Marketing': 'purple', 'Financiero': 'geekblue', 'Bancos': 'geekblue',
  'Servicios profesionales': 'gold', 'Comunicaciones': 'lime',
  'Viajes': 'green', 'Impuestos': 'magenta', 'Seguros': 'pink', 'Suministros': 'volcano',
  'Cesión auxiliar': 'red',
}

function TabMapCuentas() {
  const qc = useQueryClient()
  const [form] = Form.useForm()
  const [editKey, setEditKey] = useState<string | null>(null)

  const { data: cuentas = [], isLoading } = useQuery({
    queryKey: ['analitico-map-cuentas'],
    queryFn: () => analiticoApi.getMapCuentas().then(r => r.data),
  })

  const save = useMutation({
    mutationFn: (d: any) => analiticoApi.saveMapCuenta(d),
    onSuccess: () => {
      message.success('Guardado')
      qc.invalidateQueries({ queryKey: ['analitico-map-cuentas'] })
      form.resetFields()
      setEditKey(null)
    },
    onError: (e: any) => message.error(apiError(e, 'Error al guardar')),
  })

  const del = useMutation({
    mutationFn: (cuenta: string) => analiticoApi.deleteMapCuenta(cuenta),
    onSuccess: () => {
      message.success('Eliminado')
      qc.invalidateQueries({ queryKey: ['analitico-map-cuentas'] })
    },
    onError: (e: any) => message.error(apiError(e, 'Error al eliminar')),
  })

  const importar = useMutation({
    mutationFn: () => analiticoApi.importarDesdeMapeo(),
    onSuccess: (res) => {
      const d = res.data
      qc.invalidateQueries({ queryKey: ['analitico-map-cuentas'] })
      const noMapeadas = Object.entries(d.familias_no_mapeadas || {}) as [string, string[]][]
      if (noMapeadas.length > 0) {
        const detalle = noMapeadas
          .map(([fam, cuentas]) => `"${fam}": ${(cuentas as string[]).join(', ')}`)
          .join(' | ')
        message.warning(
          `Importadas ${d.insertadas}. Familias no reconocidas (asígnalas manualmente): ${detalle}`,
          8,
        )
      } else {
        message.success(
          `Importadas ${d.insertadas} cuentas. Amortizaciones omitidas: ${d.omitidas_amortizaciones}. Ya existentes: ${d.omitidas_ya_existentes}.`
        )
      }
    },
    onError: (e: any) => message.error(apiError(e, 'Error al importar')),
  })

  const cols = [
    {
      title: 'Cuenta / Prefijo', dataIndex: 'numero_cuenta', width: 160,
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: 'Naturaleza', dataIndex: 'naturaleza',
      render: (v: string) => <Tag color={NAT_COLOR[v] || 'default'}>{v}</Tag>,
    },
    { title: 'Descripción', dataIndex: 'descripcion', ellipsis: true },
    {
      title: '', width: 100,
      render: (_: any, row: any) => (
        <Space>
          <Button
            size="small" icon={<EditOutlined />}
            onClick={() => { setEditKey(row.numero_cuenta); form.setFieldsValue(row) }}
          />
          <Popconfirm
            title="¿Eliminar este mapeo?"
            onConfirm={() => del.mutate(row.numero_cuenta)}
            okText="Sí" cancelText="No"
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const handleSubmit = async () => {
    const values = await form.validateFields()
    save.mutate(values)
  }

  return (
    <>
      <Alert
        type="info"
        showIcon
        message="Introduce la cuenta exacta (p.ej. 640001) o un prefijo (p.ej. 640) que abarca múltiples cuentas. El sistema busca primero coincidencia exacta y luego el prefijo más largo."
        action={
          <Button
            size="small"
            icon={<ImportOutlined />}
            loading={importar.isPending}
            onClick={() => importar.mutate()}
          >
            Importar desde Mapeo de cuentas
          </Button>
        }
        style={{ marginBottom: 16 }}
      />
      <Card
        title={editKey ? `Editar cuenta ${editKey}` : 'Nueva entrada'}
        size="small"
        style={{ marginBottom: 16 }}
      >
        <Form form={form} layout="inline" onFinish={handleSubmit}>
          <Form.Item name="numero_cuenta" label="Cuenta/Prefijo" rules={[{ required: true }]}>
            <Input placeholder="ej. 640" style={{ width: 120 }} disabled={!!editKey} />
          </Form.Item>
          <Form.Item name="naturaleza" label="Naturaleza" rules={[{ required: true }]}>
            <Select style={{ width: 200 }} options={NATURALEZAS.map(n => ({ value: n, label: n }))} />
          </Form.Item>
          <Form.Item name="descripcion" label="Descripción">
            <Input placeholder="Descripción opcional" style={{ width: 200 }} />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={save.isPending}>
                {editKey ? 'Guardar cambios' : 'Añadir'}
              </Button>
              {editKey && (
                <Button onClick={() => { setEditKey(null); form.resetFields() }}>
                  Cancelar
                </Button>
              )}
            </Space>
          </Form.Item>
        </Form>
      </Card>

      <Table
        dataSource={cuentas}
        columns={cols}
        rowKey="numero_cuenta"
        loading={isLoading}
        size="small"
        pagination={{ pageSize: 20 }}
      />
    </>
  )
}


function TabMapDrivers() {
  const qc = useQueryClient()
  const { data: drivers = [], isLoading } = useQuery({
    queryKey: ['analitico-map-drivers'],
    queryFn: () => analiticoApi.getMapDrivers().then(r => r.data),
  })

  const save = useMutation({
    mutationFn: (d: any) => analiticoApi.saveMapDriver(d),
    onSuccess: () => {
      message.success('Guardado')
      qc.invalidateQueries({ queryKey: ['analitico-map-drivers'] })
    },
    onError: (e: any) => message.error(apiError(e, 'Error')),
  })

  return (
    <>
      <Alert
        type="info"
        showIcon
        message="Define cómo se reparten los costes indirectos (sin recibo) de cada naturaleza. RECIBOS = por número de recibos; PÓLIZAS = por número de pólizas (una póliza mensual pesa lo mismo que una anual; una intermediada pesa 0,49 frente a 1 de una directa, porque el auxiliar hace parte de la gestión); COMISION_NETA = proporcional a comisión neta; NUEVA_PRODUCCIÓN = sólo entre pólizas nuevas."
        style={{ marginBottom: 16 }}
      />
      <Table
        dataSource={drivers}
        rowKey="naturaleza"
        loading={isLoading}
        size="small"
        pagination={false}
        columns={[
          {
            title: 'Naturaleza', dataIndex: 'naturaleza', width: 220,
            render: (v: string) => <Tag color={NAT_COLOR[v] || 'default'}>{v}</Tag>,
          },
          {
            title: 'Driver de reparto', dataIndex: 'driver',
            render: (v: string, row: any) => (
              <Select
                value={v}
                style={{ width: 260 }}
                onChange={val => save.mutate({ naturaleza: row.naturaleza, driver: val })}
                options={DRIVERS.map(d => ({ value: d, label: DRIVER_LABELS[d] || d }))}
                disabled={row.naturaleza === 'Cesión auxiliar'}
              />
            ),
          },
        ]}
      />
    </>
  )
}


export default function ConfiguracionAnalitico() {
  return (
    <div>
      <Title level={4} style={{ marginBottom: 4 }}>Configuración del Modelo Analítico</Title>
      <Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
        Define cómo cada cuenta contable se clasifica en una naturaleza económica y cómo se reparten los costes indirectos.
      </Text>
      <Tabs
        items={[
          {
            key: 'cuentas',
            label: 'Mapeo Cuentas → Naturaleza',
            children: <TabMapCuentas />,
          },
          {
            key: 'drivers',
            label: 'Naturaleza → Driver de Reparto',
            children: <TabMapDrivers />,
          },
        ]}
      />
    </div>
  )
}
