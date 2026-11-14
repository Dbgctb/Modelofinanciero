import { useState } from 'react'
import { Button, Card, Form, Input, message, Popconfirm, Space, Switch, Table, Typography } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { bancoApi, BancoCC } from '../../../api/cierres'
import { apiError } from '../../../utils/errorHandler'
import { num, usePuedeEditar } from '../comun'

const { Paragraph } = Typography

export default function BancosConfig({ bancoId }: { bancoId?: number }) {
  const qc = useQueryClient()
  const puedeEditar = usePuedeEditar()
  const [form] = Form.useForm<BancoCC>()
  const [editando, setEditando] = useState<BancoCC | null>(null)
  const bancos = useQuery({ queryKey: ['cierres', 'bancos'], queryFn: () => bancoApi.getBancos().then((r) => r.data) })

  const guardar = async () => {
    const v = await form.validateFields()
    try {
      if (editando?.id) await bancoApi.actualizarBanco(editando.id, v)
      else await bancoApi.crearBanco(v)
      message.success('Banco guardado')
      setEditando(null)
      qc.invalidateQueries({ queryKey: ['cierres', 'bancos'] })
    } catch (e) {
      message.error(apiError(e))
    }
  }

  const borrar = async (id: number) => {
    try {
      await bancoApi.borrarBanco(id)
      qc.invalidateQueries({ queryKey: ['cierres', 'bancos'] })
    } catch (e) {
      message.error(apiError(e))
    }
  }

  const nuevo: BancoCC = { nombre: '', cuenta_572: '572', iban: '', entidad: '', activo: true }

  return (
    <Card size="small" title="Bancos">
      <Paragraph type="secondary">
        Cada banco se concilia contra su cuenta 572 del diario. Los días y tolerancias de los niveles se ajustan en
        la pestaña "Ejecutar conciliación" y se guardan por cuenta.
      </Paragraph>
      {puedeEditar && !editando && (
        <Button type="primary" style={{ marginBottom: 12 }} onClick={() => { setEditando(nuevo); form.setFieldsValue(nuevo) }}>
          Añadir banco
        </Button>
      )}
      {editando && (
        <Card size="small" style={{ marginBottom: 12 }}>
          <Form form={form} layout="inline">
            <Form.Item name="nombre" label="Nombre" rules={[{ required: true }]}><Input style={{ width: 200 }} /></Form.Item>
            <Form.Item name="cuenta_572" label="Cuenta 572" rules={[{ required: true, pattern: /^572\d+$/, message: 'Debe empezar por 572' }]}>
              <Input style={{ width: 130 }} />
            </Form.Item>
            <Form.Item name="iban" label="IBAN"><Input style={{ width: 240 }} /></Form.Item>
            <Form.Item name="entidad" label="Entidad"><Input style={{ width: 160 }} /></Form.Item>
            <Form.Item name="activo" label="Activo" valuePropName="checked"><Switch /></Form.Item>
            <Space>
              <Button type="primary" onClick={guardar}>Guardar</Button>
              <Button onClick={() => setEditando(null)}>Cancelar</Button>
            </Space>
          </Form>
        </Card>
      )}
      <Table<BancoCC> size="small" rowKey="id" pagination={false} loading={bancos.isLoading} dataSource={bancos.data}
        rowClassName={(b) => (b.id === bancoId ? 'ant-table-row-selected' : '')}
        columns={[
          { title: 'Nombre', dataIndex: 'nombre' },
          { title: 'Cuenta 572', dataIndex: 'cuenta_572' },
          { title: 'IBAN', dataIndex: 'iban' },
          { title: 'Entidad', dataIndex: 'entidad' },
          { title: 'Movimientos', dataIndex: 'movimientos', align: 'right', render: num },
          { title: 'Activo', dataIndex: 'activo', render: (v: boolean) => (v ? 'Sí' : 'No') },
          ...(puedeEditar ? [{
            title: '', width: 170,
            render: (_: unknown, b: BancoCC) => (
              <Space>
                <Button size="small" onClick={() => { setEditando(b); form.setFieldsValue(b) }}>Editar</Button>
                <Popconfirm title="¿Borrar este banco?" description="Solo se puede si no tiene movimientos."
                  onConfirm={() => borrar(b.id!)} okText="Borrar" cancelText="Cancelar">
                  <Button size="small" danger disabled={!!b.movimientos}>Borrar</Button>
                </Popconfirm>
              </Space>
            ),
          }] : []),
        ]}
      />
    </Card>
  )
}
