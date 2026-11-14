import { useState } from 'react'
import { Button, Card, message, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import { DisconnectOutlined, FileExcelOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { bancoApi, Conciliado } from '../../../api/cierres'
import { apiError } from '../../../utils/errorHandler'
import { descargarBlob, eur, fecha, num, usePuedeEditar } from '../comun'

const { Text } = Typography

export default function ConciliadosBanco({ bancoId, ejercicio }: { bancoId: number; ejercicio: number }) {
  const qc = useQueryClient()
  const puedeEditar = usePuedeEditar()
  const [nivel, setNivel] = useState<string | undefined>()
  const [pagina, setPagina] = useState({ page: 1, page_size: 200 })
  const [sel, setSel] = useState<number[]>([])
  const [ocupado, setOcupado] = useState(false)

  const datos = useQuery({
    queryKey: ['cierres', 'banco', 'conciliados', bancoId, ejercicio, nivel, pagina],
    queryFn: () => bancoApi.getConciliados(bancoId, ejercicio, nivel, pagina.page, pagina.page_size).then((r) => r.data),
  })

  const desconciliar = () =>
    Modal.confirm({
      title: `¿Desconciliar ${sel.length} movimientos?`,
      content: 'Se liberan también los demás movimientos de sus grupos y todos sus apuntes del diario.',
      okText: 'Desconciliar', okButtonProps: { danger: true }, cancelText: 'Cancelar',
      onOk: async () => {
        try {
          const { data } = await bancoApi.desconciliar(bancoId, sel)
          message.success(`${num(data.movimientos)} movimientos y ${num(data.apuntes)} apuntes desconciliados`)
          setSel([])
          qc.invalidateQueries({ queryKey: ['cierres'] })
        } catch (e) {
          message.error(apiError(e))
        }
      },
    })

  const excel = async () => {
    setOcupado(true)
    try {
      const { data } = await bancoApi.excelConciliados(bancoId, ejercicio)
      descargarBlob(data as Blob, `conciliados_banco_${ejercicio}.xlsx`)
    } catch (e) {
      message.error(apiError(e, 'No se pudo generar el Excel'))
    } finally {
      setOcupado(false)
    }
  }

  const niveles = Object.entries(datos.data?.por_nivel ?? {})

  return (
    <Card size="small">
      <Space wrap style={{ marginBottom: 12 }}>
        <Select style={{ width: 200 }} allowClear placeholder="Todos los niveles" value={nivel}
          onChange={(v) => { setNivel(v); setPagina((p) => ({ ...p, page: 1 })) }}
          options={niveles.map(([k, v]) => ({ value: k, label: `${k.startsWith('MANUAL') ? k : `Nivel ${k}`} (${num(v)})` }))} />
        <Button icon={<FileExcelOutlined />} loading={ocupado} onClick={excel}>Exportar Excel</Button>
        {puedeEditar && (
          <Button danger icon={<DisconnectOutlined />} disabled={!sel.length} onClick={desconciliar}>
            Desconciliar seleccionados ({sel.length})
          </Button>
        )}
        <Text type="secondary">
          {niveles.map(([k, v]) => `${k.startsWith('MANUAL') ? k : `N${k}`}: ${num(v)}`).join(' · ')}
        </Text>
      </Space>
      <Table<Conciliado> size="small" rowKey="id" loading={datos.isFetching} dataSource={datos.data?.filas}
        scroll={{ x: 1100 }}
        rowSelection={puedeEditar ? { selectedRowKeys: sel, onChange: (k) => setSel(k as number[]), preserveSelectedRowKeys: true } : undefined}
        pagination={{
          current: pagina.page, pageSize: pagina.page_size, total: datos.data?.total, showSizeChanger: true,
          showTotal: (t) => `${num(t)} movimientos conciliados`, onChange: (page, page_size) => setPagina({ page, page_size }),
        }}
        columns={[
          { title: 'Fecha', dataIndex: 'fecha_operacion', width: 95, render: fecha },
          { title: 'Concepto banco', dataIndex: 'concepto', ellipsis: true },
          { title: 'Importe', dataIndex: 'importe', width: 105, align: 'right', render: eur },
          { title: 'Nivel', dataIndex: 'recon_level', width: 100, render: (n: string) => <Tag>{n?.startsWith('MANUAL') ? n : `Nivel ${n}`}</Tag> },
          { title: 'Diario', ellipsis: true,
            render: (_: unknown, r) => r.recon_group_id && r.apuntes_grupo > 1
              ? `${num(r.apuntes_grupo)} apuntes · ${r.recon_group_id}`
              : r.recon_journal_id ? `${r.asiento_key ?? ''} · ${r.concepto_diario ?? ''}` : '—' },
          { title: 'Neto diario', dataIndex: 'neto', width: 105, align: 'right',
            render: (n: number | null, r) => (r.apuntes_grupo > 1 ? '' : eur(n)) },
          { title: 'Diferencia', dataIndex: 'recon_difference', width: 95, align: 'right', render: (d: number | null) => (d ? eur(d) : '') },
        ]}
      />
    </Card>
  )
}
