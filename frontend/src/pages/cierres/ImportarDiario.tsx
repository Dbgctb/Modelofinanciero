import { useState } from 'react'
import {
  Alert, Button, Card, Checkbox, Col, Input, InputNumber, message, Modal, Radio, Row, Select, Space,
  Table, Tabs, Typography, Upload,
} from 'antd'
import { DeleteOutlined, DiffOutlined, InboxOutlined, UndoOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Apunte, cierresApi } from '../../api/cierres'
import { apiError } from '../../utils/errorHandler'
import { EstadoTarea, eur, fecha, num, TagPunteo, usePuedeEditar, useTarea } from './comun'

const { Title, Paragraph, Text } = Typography

const columnasApunte = [
  { title: 'ID', dataIndex: 'id', width: 90 },
  { title: 'Fecha', dataIndex: 'fecha', width: 100, render: fecha },
  { title: 'Cuenta', dataIndex: 'cuenta', width: 110 },
  { title: 'Concepto', dataIndex: 'concepto', ellipsis: true },
  { title: 'Recibo', dataIndex: 'recibo_norm', width: 90 },
  { title: 'Debe', dataIndex: 'debe', width: 110, align: 'right' as const, render: eur },
  { title: 'Haber', dataIndex: 'haber', width: 110, align: 'right' as const, render: eur },
  { title: 'Neto', dataIndex: 'neto', width: 110, align: 'right' as const, render: eur },
  { title: 'Punteado', width: 120, render: (_: unknown, a: Apunte) => <TagPunteo a={a} /> },
]

export default function ImportarDiario() {
  const qc = useQueryClient()
  const puedeEditar = usePuedeEditar()
  const [ejercicio, setEjercicio] = useState<number>(new Date().getFullYear() - 1)
  const [fichero, setFichero] = useState<UploadFile | null>(null)
  const [modo, setModo] = useState<'completo' | 'incremental'>('incremental')
  const [limpiar, setLimpiar] = useState(true)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [verDiferencias, setVerDiferencias] = useState(false)

  const [cuenta, setCuenta] = useState('')
  const [conciliado, setConciliado] = useState<'todas' | 'si' | 'no'>('todas')
  const [pagina, setPagina] = useState({ page: 1, page_size: 200 })

  const { data: resumen } = useQuery({
    queryKey: ['cierres', 'resumen'],
    queryFn: () => cierresApi.getResumen().then((r) => r.data),
  })
  const totalEjercicio = resumen?.apuntes.find((a) => a.ejercicio === ejercicio)

  const apuntes = useQuery({
    queryKey: ['cierres', 'apuntes', ejercicio, cuenta, conciliado, pagina],
    queryFn: () =>
      cierresApi.getApuntes({
        ejercicio, cuenta: cuenta || undefined, page: pagina.page, page_size: pagina.page_size,
        conciliado: conciliado === 'todas' ? undefined : conciliado === 'si',
      }).then((r) => r.data),
  })

  const { tarea, enCurso, errorConsulta } = useTarea(taskId, (t) => {
    qc.invalidateQueries({ queryKey: ['cierres'] })
    if (t.resultado?.modo === 'incremental') setVerDiferencias(true)
  })

  const lanzar = async () => {
    if (!fichero?.originFileObj) return
    const form = new FormData()
    form.append('file', fichero.originFileObj)
    form.append('ejercicio', String(ejercicio))
    form.append('modo', modo)
    form.append('limpiar', String(limpiar))
    try {
      const { data } = await cierresApi.importar(form)
      setTaskId(data.task_id)
    } catch (e) {
      message.error(apiError(e, 'No se pudo iniciar la importación'))
    }
  }

  const importar = () => {
    if (modo === 'completo' && limpiar) {
      Modal.confirm({
        title: `¿Borrar y volver a importar el ejercicio ${ejercicio}?`,
        content: (
          <>
            <p>Se borrarán los <b>{num(totalEjercicio?.total ?? 0)}</b> apuntes del ejercicio {ejercicio},
              <b> incluido todo su punteo (también el manual)</b>, y se importarán los del fichero.</p>
            <p>Si el fichero no contiene el ejercicio {ejercicio}, no se borra nada.</p>
            <p>Para añadir solo lo nuevo sin perder el punteo, usa la importación <b>incremental</b>.</p>
          </>
        ),
        okText: 'Borrar e importar', okButtonProps: { danger: true }, cancelText: 'Cancelar',
        onOk: lanzar,
      })
    } else {
      lanzar()
    }
  }

  const desconciliar = () =>
    Modal.confirm({
      title: `¿Quitar TODO el punteo del ejercicio ${ejercicio}?`,
      content: 'Se desconcilian todos los apuntes del ejercicio, incluidos los punteados a mano y los conciliados con el banco. No se puede deshacer.',
      okText: 'Desconciliar todo', okButtonProps: { danger: true }, cancelText: 'Cancelar',
      onOk: async () => {
        try {
          const { data } = await cierresApi.desconciliarEjercicio(ejercicio)
          message.success(`${num(data.desconciliados)} apuntes desconciliados`)
          qc.invalidateQueries({ queryKey: ['cierres'] })
        } catch (e) {
          message.error(apiError(e))
        }
      },
    })

  return (
    <div>
      <Title level={3}>Importar diario</Title>
      <Paragraph type="secondary">
        Carga el diario completo de un ejercicio (Excel o TXT exportado del ERP). La importación
        incremental añade solo los apuntes nuevos y marca los que ya no están en el fichero, sin tocar el punteo.
      </Paragraph>

      {puedeEditar && (
        <Card title="Importar fichero" size="small" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col xs={24} md={10}>
              <Upload.Dragger
                maxCount={1} accept=".xlsx,.xls,.txt,.csv"
                beforeUpload={() => false}
                fileList={fichero ? [fichero] : []}
                onChange={({ fileList }) => setFichero(fileList[0] ?? null)}
              >
                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                <p>Arrastra el diario o haz clic para elegirlo</p>
              </Upload.Dragger>
            </Col>
            <Col xs={24} md={14}>
              <Space direction="vertical">
                <Space>
                  <Text>Ejercicio:</Text>
                  <InputNumber min={2000} max={2100} value={ejercicio} onChange={(v) => v && setEjercicio(v)} />
                  {totalEjercicio && <Text type="secondary">({num(totalEjercicio.total)} apuntes cargados)</Text>}
                </Space>
                <Radio.Group value={modo} onChange={(e) => setModo(e.target.value)}>
                  <Radio value="incremental">Incremental: solo nuevos, conserva el punteo</Radio>
                  <Radio value="completo">Completa</Radio>
                </Radio.Group>
                {modo === 'completo' && (
                  <Checkbox checked={limpiar} onChange={(e) => setLimpiar(e.target.checked)}>
                    Borrar el ejercicio antes de importar
                  </Checkbox>
                )}
                {modo === 'completo' && !limpiar && (
                  <Alert type="warning" showIcon message="Sin borrar antes, los apuntes que ya existan quedarán duplicados." />
                )}
                <Space>
                  <Button type="primary" onClick={importar} disabled={!fichero || enCurso} loading={enCurso}>
                    Importar
                  </Button>
                  <Button icon={<DiffOutlined />} onClick={() => setVerDiferencias(true)}>
                    Nuevos y huérfanos
                  </Button>
                </Space>
              </Space>
            </Col>
          </Row>
          <div style={{ marginTop: 12 }}>
            <EstadoTarea tarea={tarea} errorConsulta={errorConsulta} />
            {tarea?.estado === 'terminada' && tarea.resultado && (
              <Text>
                {tarea.resultado.modo === 'completo'
                  ? `Ejercicio ${tarea.resultado.ejercicio}: ${num(tarea.resultado.borrados)} apuntes borrados, ${num(tarea.resultado.insertados)} importados.`
                  : `Ejercicio ${tarea.resultado.ejercicio}: ${num(tarea.resultado.nuevos)} nuevos, ${num(tarea.resultado.huerfanos)} huérfanos, ${num(tarea.resultado.sin_cambios)} sin cambios.`}
              </Text>
            )}
          </div>
        </Card>
      )}

      <Card
        size="small"
        title={`Apuntes del ejercicio ${ejercicio}`}
        extra={puedeEditar && (
          <Button danger icon={<UndoOutlined />} onClick={desconciliar}>Desconciliar todos</Button>
        )}
      >
        <Space wrap style={{ marginBottom: 12 }}>
          {!puedeEditar && (
            <>
              <Text>Ejercicio:</Text>
              <InputNumber min={2000} max={2100} value={ejercicio} onChange={(v) => v && setEjercicio(v)} />
            </>
          )}
          <Input.Search
            placeholder="Cuenta: 4300 o 4300000001" allowClear style={{ width: 240 }}
            onSearch={(v) => { setCuenta(v.trim()); setPagina((p) => ({ ...p, page: 1 })) }}
          />
          <Select
            value={conciliado} style={{ width: 160 }}
            onChange={(v) => { setConciliado(v); setPagina((p) => ({ ...p, page: 1 })) }}
            options={[
              { value: 'todas', label: 'Todas' },
              { value: 'si', label: 'Punteadas' },
              { value: 'no', label: 'Sin puntear' },
            ]}
          />
        </Space>
        {apuntes.error && <Alert type="error" showIcon message={apiError(apuntes.error)} style={{ marginBottom: 12 }} />}
        <Table<Apunte>
          size="small" rowKey="id" columns={columnasApunte}
          dataSource={apuntes.data?.filas} loading={apuntes.isLoading}
          scroll={{ x: 1000 }}
          pagination={{
            current: pagina.page, pageSize: pagina.page_size, total: apuntes.data?.total,
            showSizeChanger: true, pageSizeOptions: [100, 200, 500, 1000],
            showTotal: (t) => `${num(t)} apuntes`,
            onChange: (page, page_size) => setPagina({ page, page_size }),
          }}
          locale={{ emptyText: 'No hay apuntes con estos filtros' }}
        />
      </Card>

      <ModalDiferencias
        abierto={verDiferencias} ejercicio={ejercicio} puedeEditar={puedeEditar}
        onCerrar={() => setVerDiferencias(false)}
      />
    </div>
  )
}

function ModalDiferencias({ abierto, ejercicio, puedeEditar, onCerrar }: {
  abierto: boolean; ejercicio: number; puedeEditar: boolean; onCerrar: () => void
}) {
  const qc = useQueryClient()
  const [seleccion, setSeleccion] = useState<number[]>([])
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['cierres', 'diferencias', ejercicio],
    queryFn: () => cierresApi.getDiferencias(ejercicio).then((r) => r.data),
    enabled: abierto,
  })

  const eliminar = () =>
    Modal.confirm({
      title: `¿Eliminar ${seleccion.length} apuntes huérfanos?`,
      content: 'Se borran de la base. Solo se pueden eliminar huérfanos sin puntear.',
      okText: 'Eliminar', okButtonProps: { danger: true }, cancelText: 'Cancelar',
      onOk: async () => {
        try {
          const r = await cierresApi.eliminarHuerfanos(ejercicio, seleccion)
          message.success(`${num(r.data.borrados)} eliminados` + (r.data.ignorados ? `, ${r.data.ignorados} ignorados` : ''))
          setSeleccion([])
          refetch()
          qc.invalidateQueries({ queryKey: ['cierres', 'apuntes'] })
          qc.invalidateQueries({ queryKey: ['cierres', 'resumen'] })
        } catch (e) {
          message.error(apiError(e))
        }
      },
    })

  return (
    <Modal open={abierto} onCancel={onCerrar} footer={null} width={1100}
      title={`Diferencias de la última importación incremental — ejercicio ${ejercicio}`}>
      <Tabs items={[
        {
          key: 'nuevos', label: `Nuevos (${num(data?.nuevos.length ?? 0)})`,
          children: (
            <>
              <Paragraph type="secondary">Estaban en el fichero y no en la base. Ya se han insertado.</Paragraph>
              <Table<Apunte> size="small" rowKey="id" columns={columnasApunte} loading={isLoading}
                dataSource={data?.nuevos} pagination={{ pageSize: 50 }} scroll={{ x: 1000 }} />
            </>
          ),
        },
        {
          key: 'huerfanos', label: `Huérfanos (${num(data?.huerfanos.length ?? 0)})`,
          children: (
            <>
              <Paragraph type="secondary">
                Están en la base pero no en el fichero. Solo se pueden eliminar los que no están punteados.
              </Paragraph>
              {puedeEditar && (
                <Space style={{ marginBottom: 8 }}>
                  <Button onClick={() => setSeleccion((data?.huerfanos ?? []).filter((a) => !a.reconciled).map((a) => a.id))}>
                    Seleccionar los no punteados
                  </Button>
                  <Button onClick={() => setSeleccion([])}>Deseleccionar</Button>
                  <Button danger icon={<DeleteOutlined />} disabled={!seleccion.length} onClick={eliminar}>
                    Eliminar seleccionados ({seleccion.length})
                  </Button>
                </Space>
              )}
              <Table<Apunte> size="small" rowKey="id" columns={columnasApunte} loading={isLoading}
                dataSource={data?.huerfanos} pagination={{ pageSize: 50 }} scroll={{ x: 1000 }}
                rowSelection={puedeEditar ? {
                  selectedRowKeys: seleccion,
                  onChange: (k) => setSeleccion(k as number[]),
                  getCheckboxProps: (a) => ({ disabled: a.reconciled }),
                  preserveSelectedRowKeys: true,
                } : undefined}
              />
            </>
          ),
        },
      ]} />
    </Modal>
  )
}
