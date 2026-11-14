import { useEffect, useState } from 'react'
import {
  Alert, Button, Card, Checkbox, Col, Form, Input, InputNumber, message, Modal, Row, Select, Space, Table,
  Tooltip, Typography,
} from 'antd'
import { EditOutlined, FileExcelOutlined, LinkOutlined, SearchOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Apunte, cierresApi, FiltroManual } from '../../api/cierres'
import { apiError } from '../../utils/errorHandler'
import { descargarBlob, eur, fecha, num, TagPunteo, usePuedeEditar } from './comun'

const { Title, Paragraph, Text } = Typography

export default function PunteoManual() {
  const qc = useQueryClient()
  const puedeEditar = usePuedeEditar()
  const [form] = Form.useForm()
  const [filtro, setFiltro] = useState<FiltroManual | null>(null)
  const [pagina, setPagina] = useState({ page: 1, page_size: 200 })
  const [seleccion, setSeleccion] = useState<number[]>([])
  const [tolerancia, setTolerancia] = useState(0.2)
  const [ocupado, setOcupado] = useState(false)

  const { data: resumen } = useQuery({
    queryKey: ['cierres', 'resumen'],
    queryFn: () => cierresApi.getResumen().then((r) => r.data),
  })

  const busqueda = useQuery({
    queryKey: ['cierres', 'manual', filtro, pagina],
    queryFn: () => cierresApi.buscarManual({ ...filtro!, ...pagina }).then((r) => r.data),
    enabled: !!filtro,
  })

  // Resumen de la selección (puede abarcar varias páginas): lo calcula el servidor
  const [resSel, setResSel] = useState<{ n: number; suma: number; cuentas: string[]; punteados: number } | null>(null)
  useEffect(() => {
    if (!seleccion.length) { setResSel(null); return }
    const t = setTimeout(() => {
      cierresApi.resumenSeleccion(seleccion).then((r) => setResSel(r.data)).catch(() => setResSel(null))
    }, 250)
    return () => clearTimeout(t)
  }, [seleccion])

  const buscar = () => {
    const v = form.getFieldsValue()
    setFiltro({
      ejercicios: v.ejercicios ?? [], cuenta: v.cuenta?.trim() || undefined, recibo: v.recibo?.trim() || undefined,
      asiento: v.asiento?.trim() || undefined, concepto: v.concepto?.trim() || undefined,
      solo_pendientes: v.solo_pendientes ?? true,
    })
    setPagina((p) => ({ ...p, page: 1 }))
    setSeleccion([])
  }

  const seleccionarTodos = async () => {
    if (!filtro) return
    try {
      const { data } = await cierresApi.idsManual(filtro)
      setSeleccion(data.ids)
    } catch (e) {
      message.error(apiError(e))
    }
  }

  const sumaOk = resSel && Math.abs(resSel.suma) <= tolerancia + 1e-9
  const cuentaOk = resSel && resSel.cuentas.length === 1
  const puedePuntear = !!resSel && resSel.n >= 2 && sumaOk && cuentaOk && resSel.punteados === 0

  const puntear = () =>
    Modal.confirm({
      title: `¿Puntear ${resSel?.n} apuntes de la cuenta ${resSel?.cuentas[0]}?`,
      content: `Suma: ${eur(resSel?.suma)} € (tolerancia ±${eur(tolerancia)} €).`,
      okText: 'Puntear', cancelText: 'Cancelar',
      onOk: async () => {
        try {
          const { data } = await cierresApi.puntearManual(seleccion, tolerancia)
          message.success(`${num(data.punteados)} apuntes punteados (grupo ${data.grupo})`)
          setSeleccion([])
          qc.invalidateQueries({ queryKey: ['cierres'] })
        } catch (e) {
          message.error(apiError(e))
        }
      },
    })

  const exportar = async () => {
    setOcupado(true)
    try {
      const { data } = await cierresApi.excelManual(seleccion)
      descargarBlob(data as Blob, `Seleccion_Manual_${new Date().toISOString().slice(0, 10)}.xlsx`)
    } catch (e) {
      message.error(apiError(e, 'No se pudo generar el Excel'))
    } finally {
      setOcupado(false)
    }
  }

  const editarCuenta = (a: Apunte) => {
    let nueva = a.cuenta
    Modal.confirm({
      title: `Cambiar la cuenta del apunte ${a.id}`,
      content: (
        <>
          <Paragraph>Solo para apuntes 572* sin puntear; la nueva cuenta también debe ser 572*.</Paragraph>
          <Input defaultValue={a.cuenta} onChange={(e) => { nueva = e.target.value }} />
        </>
      ),
      okText: 'Guardar', cancelText: 'Cancelar',
      onOk: async () => {
        try {
          await cierresApi.cambiarCuenta(a.id, nueva.trim())
          message.success('Cuenta cambiada')
          qc.invalidateQueries({ queryKey: ['cierres', 'manual'] })
        } catch (e) {
          message.error(apiError(e))
          throw e
        }
      },
    })
  }

  const ejercicios = [...(resumen?.apuntes ?? [])].reverse().map((a) => ({ value: a.ejercicio, label: String(a.ejercicio) }))

  return (
    <div>
      <Title level={3}>Punteo manual</Title>
      <Paragraph type="secondary">
        Busca apuntes, selecciónalos (se mantiene la selección al cambiar de página) y puntéalos juntos.
        Tienen que ser de la misma cuenta y sumar 0 dentro de la tolerancia.
      </Paragraph>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Form form={form} layout="vertical" initialValues={{ solo_pendientes: true }} onFinish={buscar}>
          <Row gutter={12}>
            <Col xs={24} md={6}><Form.Item name="ejercicios" label="Ejercicios (vacío = todos)">
              <Select mode="multiple" options={ejercicios} allowClear />
            </Form.Item></Col>
            <Col xs={12} md={4}><Form.Item name="cuenta" label="Cuenta"><Input placeholder="43, 4300* o 4300000001" /></Form.Item></Col>
            <Col xs={12} md={3}><Form.Item name="recibo" label="Recibo"><Input /></Form.Item></Col>
            <Col xs={12} md={4}><Form.Item name="asiento" label="Asiento"><Input placeholder="2024|A|123" /></Form.Item></Col>
            <Col xs={12} md={5}><Form.Item name="concepto" label="Concepto"><Input placeholder="liquidac* o COBRO" /></Form.Item></Col>
            <Col xs={24} md={2}><Form.Item name="solo_pendientes" label="Pendientes" valuePropName="checked"><Checkbox /></Form.Item></Col>
          </Row>
          <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>Buscar</Button>
          <Button style={{ marginLeft: 8 }} onClick={() => { form.resetFields(); setFiltro(null); setSeleccion([]) }}>Limpiar</Button>
        </Form>
      </Card>

      {busqueda.error && <Alert type="error" showIcon message={apiError(busqueda.error)} style={{ marginBottom: 12 }} />}

      <Card size="small">
        <Space wrap style={{ marginBottom: 12 }}>
          <Button disabled={!filtro || !busqueda.data?.total} onClick={seleccionarTodos}>
            Seleccionar todos ({num(busqueda.data?.total ?? 0)})
          </Button>
          <Button disabled={!seleccion.length} onClick={() => setSeleccion([])}>Deseleccionar</Button>
          <Text strong>
            Seleccionados: {num(seleccion.length)} · Suma neto:{' '}
            <span style={{ color: resSel ? (sumaOk ? '#389e0d' : '#cf1322') : undefined }}>{eur(resSel?.suma ?? 0)} €</span>
          </Text>
          {resSel && resSel.cuentas.length > 1 && <Text type="danger">Hay {resSel.cuentas.length} cuentas distintas</Text>}
          {resSel && resSel.punteados > 0 && <Text type="danger">{resSel.punteados} ya punteados</Text>}
        </Space>
        <Space wrap style={{ marginBottom: 12 }}>
          {puedeEditar && (
            <>
              <Text>Tolerancia (€):</Text>
              <InputNumber min={0} max={10000} step={0.01} precision={2} value={tolerancia}
                onChange={(v) => setTolerancia(v ?? 0)} decimalSeparator="," />
              <Button type="primary" icon={<LinkOutlined />} disabled={!puedePuntear} onClick={puntear}>
                Puntear selección
              </Button>
            </>
          )}
          <Button icon={<FileExcelOutlined />} disabled={!seleccion.length} loading={ocupado} onClick={exportar}>
            Exportar selección a Excel
          </Button>
        </Space>

        <Table<Apunte>
          size="small" rowKey="id" loading={busqueda.isFetching} dataSource={busqueda.data?.filas}
          scroll={{ x: 1200 }}
          rowSelection={{
            selectedRowKeys: seleccion, preserveSelectedRowKeys: true,
            onChange: (keys) => setSeleccion(keys as number[]),
          }}
          pagination={{
            current: pagina.page, pageSize: pagina.page_size, total: busqueda.data?.total,
            showSizeChanger: true, pageSizeOptions: [100, 200, 500],
            showTotal: (t) => `${num(t)} apuntes · suma ${eur(busqueda.data?.suma_total ?? 0)} €`,
            onChange: (page, page_size) => setPagina({ page, page_size }),
          }}
          locale={{ emptyText: filtro ? 'No hay apuntes con esos filtros' : 'Usa los filtros y pulsa Buscar' }}
          columns={[
            { title: 'Ejercicio', dataIndex: 'ejercicio', width: 80 },
            { title: 'Asiento', dataIndex: 'asiento_key', width: 120 },
            { title: 'Fecha', dataIndex: 'fecha', width: 95, render: fecha },
            { title: 'Cuenta', dataIndex: 'cuenta', width: 130,
              render: (c: string, a: Apunte) => (
                <Space size={4}>
                  {c}
                  {puedeEditar && c.startsWith('572') && !a.reconciled && (
                    <Tooltip title="Cambiar cuenta 572">
                      <Button size="small" type="text" icon={<EditOutlined />} onClick={() => editarCuenta(a)} />
                    </Tooltip>
                  )}
                </Space>
              ) },
            { title: 'Recibo', dataIndex: 'recibo_norm', width: 90 },
            { title: 'Concepto', dataIndex: 'concepto', ellipsis: true },
            { title: 'Debe', dataIndex: 'debe', width: 105, align: 'right', render: eur },
            { title: 'Haber', dataIndex: 'haber', width: 105, align: 'right', render: eur },
            { title: 'Neto', dataIndex: 'neto', width: 105, align: 'right', render: eur },
            { title: 'Punteado', width: 120, render: (_: unknown, a: Apunte) => <TagPunteo a={a} /> },
          ]}
        />
      </Card>
    </div>
  )
}
