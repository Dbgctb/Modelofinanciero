import { useMemo, useState } from 'react'
import {
  Alert, Button, Card, Form, Input, InputNumber, message, Modal, Select, Space, Table, Tag, Typography,
} from 'antd'
import { FileExcelOutlined, LinkOutlined, PlayCircleOutlined, PlusOutlined, SearchOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CandidatoCobro, cierresApi, EmparejamientoH, FilaRecobro, herramientasApi } from '../../api/cierres'
import { apiError } from '../../utils/errorHandler'
import { descargarBlob, EstadoTarea, eur, fecha, num, usePuedeEditar, useTarea } from './comun'

const { Title, Paragraph, Text } = Typography

const claveFila = (f: FilaRecobro) => `${f.grupo}|${f.recibo ?? ''}`
const colorEstado = (e: string) => (e.startsWith('OK') ? 'green' : e.startsWith('FALTANTE') ? 'red' : 'orange')

export default function Recobros() {
  const qc = useQueryClient()
  const puedeEditar = usePuedeEditar()
  const [form] = Form.useForm()
  const [filtro, setFiltro] = useState<{ ejercicio: number; concepto: string; cuenta?: string } | null>(null)
  const [sel, setSel] = useState<string[]>([])
  const [tolerancia, setTolerancia] = useState(0.01)
  const [asignar, setAsignar] = useState<{ fila: FilaRecobro; extra: boolean } | null>(null)
  const [verEmparejamientos, setVerEmparejamientos] = useState(false)
  const [verGruposH, setVerGruposH] = useState(false)

  const { data: resumen } = useQuery({ queryKey: ['cierres', 'resumen'], queryFn: () => cierresApi.getResumen().then((r) => r.data) })
  const ejercicios = [...(resumen?.apuntes ?? [])].reverse().map((a) => ({ value: a.ejercicio, label: String(a.ejercicio) }))

  const diag = useQuery({
    queryKey: ['cierres', 'recobros', filtro],
    queryFn: () => herramientasApi.diagnostico(filtro!).then((r) => r.data),
    enabled: !!filtro,
  })
  const filas = diag.data?.filas ?? []
  const filasSel = useMemo(() => filas.filter((f) => sel.includes(claveFila(f))), [filas, sel])

  const buscar = (v: any) => {
    setSel([])
    setFiltro({ ejercicio: v.ejercicio, concepto: v.concepto.trim(), cuenta: v.cuenta?.trim() || undefined })
  }

  const conciliar = (modo: 'grupo' | 'filas') =>
    Modal.confirm({
      title: modo === 'grupo' ? '¿Conciliar los grupos completos de las filas marcadas?' : '¿Conciliar solo las filas marcadas?',
      content: `Recobros del grupo + ${modo === 'grupo' ? 'todos los cobros OK del grupo' : 'los cobros de las filas marcadas'}. ` +
        `La suma debe quedar dentro de ±${eur(tolerancia)} €.`,
      okText: 'Conciliar', cancelText: 'Cancelar',
      onOk: async () => {
        try {
          const { data } = await herramientasApi.conciliarRecobros({
            ...filtro!, modo, tolerancia, seleccion: filasSel.map((f) => ({ grupo: f.grupo, recibo: f.recibo })),
          })
          Modal.info({
            title: `${num(data.conciliados)} apuntes conciliados`,
            content: (
              <>
                {data.grupos_ok.length > 0 && <><b>Conciliados:</b><ul>{data.grupos_ok.map((g) => <li key={g}>{g}</li>)}</ul></>}
                {data.grupos_error.length > 0 && <><b>No conciliados:</b><ul>{data.grupos_error.map((g) => <li key={g}>{g}</li>)}</ul></>}
              </>
            ),
          })
          setSel([])
          qc.invalidateQueries({ queryKey: ['cierres'] })
        } catch (e) {
          message.error(apiError(e))
        }
      },
    })

  const excel = async () => {
    try {
      const { data } = await herramientasApi.excelRecobros(filtro!)
      descargarBlob(data as Blob, `diagnostico_H_${filtro!.ejercicio}.xlsx`)
    } catch (e) {
      message.error(apiError(e, 'No se pudo generar el Excel'))
    }
  }

  const unaFaltante = filasSel.length === 1 && filasSel[0].estado.startsWith('FALTANTE') ? filasSel[0] : null

  return (
    <div>
      <Title level={3}>Recobros (Diagnóstico H)</Title>
      <Paragraph type="secondary">
        Recobros de comisiones 440* sin conciliar y, por cada recibo 4152* de su asiento, el cobro que les corresponde.
        En las filas FALTANTE puedes asignar el cobro a mano: queda guardado y se aplica en las siguientes búsquedas.
      </Paragraph>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline" onFinish={buscar} initialValues={{ concepto: 'RECOBRO COMISIONES' }}>
          <Form.Item name="ejercicio" label="Ejercicio" rules={[{ required: true, message: 'Elige ejercicio' }]}>
            <Select style={{ width: 110 }} options={ejercicios} />
          </Form.Item>
          <Form.Item name="concepto" label="Concepto recobro" rules={[{ required: true }]}>
            <Input style={{ width: 240 }} />
          </Form.Item>
          <Form.Item name="cuenta" label="Cuenta 440"><Input style={{ width: 140 }} placeholder="todas" /></Form.Item>
          <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>Buscar</Button>
        </Form>
        <Space wrap style={{ marginTop: 12 }}>
          <Button icon={<UnorderedListOutlined />} onClick={() => setVerEmparejamientos(true)}>Emparejamientos guardados</Button>
          {puedeEditar && <Button icon={<PlayCircleOutlined />} onClick={() => setVerGruposH(true)}>Conciliar grupos (regla H)…</Button>}
          <Button icon={<FileExcelOutlined />} disabled={!filas.length} onClick={excel}>Exportar Excel</Button>
        </Space>
      </Card>

      {diag.error && <Alert type="error" showIcon message={apiError(diag.error)} style={{ marginBottom: 12 }} />}

      {diag.data && (
        <Card size="small">
          <Space wrap style={{ marginBottom: 12 }}>
            <Text>Grupos: <b>{num(diag.data.resumen.grupos)}</b> · Filas: <b>{num(diag.data.resumen.filas)}</b> ·
              Faltantes: <b>{num(diag.data.resumen.faltantes)}</b> · Sin recibos 4152*: <b>{num(diag.data.resumen.sin_recibos)}</b></Text>
          </Space>
          {puedeEditar && (
            <Space wrap style={{ marginBottom: 12 }}>
              <Button onClick={() => setSel(filas.map(claveFila))}>Seleccionar todas</Button>
              <Button disabled={!sel.length} onClick={() => setSel([])}>Deseleccionar</Button>
              <Text>Tolerancia (€):</Text>
              <InputNumber min={0} max={10000} step={0.01} precision={2} decimalSeparator="," value={tolerancia}
                onChange={(v) => setTolerancia(v ?? 0)} />
              <Button type="primary" icon={<LinkOutlined />} disabled={!sel.length} onClick={() => conciliar('grupo')}>
                Conciliar grupo completo
              </Button>
              <Button icon={<LinkOutlined />} disabled={!sel.length} onClick={() => conciliar('filas')}>
                Conciliar filas marcadas
              </Button>
              <Button disabled={!unaFaltante} onClick={() => setAsignar({ fila: unaFaltante!, extra: false })}>
                Asignar cobro (recibo vacío)
              </Button>
              <Button icon={<PlusOutlined />} disabled={!unaFaltante?.recibo} onClick={() => setAsignar({ fila: unaFaltante!, extra: true })}>
                Cobro extra (mismo recibo)
              </Button>
              <Text type="secondary">{sel.length} filas marcadas</Text>
            </Space>
          )}
          <Table<FilaRecobro>
            size="small" rowKey={claveFila} loading={diag.isFetching} dataSource={filas} scroll={{ x: 1100 }}
            pagination={{ pageSize: 100, showSizeChanger: true }}
            rowSelection={puedeEditar ? { selectedRowKeys: sel, onChange: (k) => setSel(k as string[]), preserveSelectedRowKeys: true } : undefined}
            columns={[
              { title: 'Asiento', dataIndex: 'asiento_key', width: 120 },
              { title: 'Concepto', dataIndex: 'concepto', ellipsis: true },
              { title: 'Cuenta', dataIndex: 'cuenta', width: 110 },
              { title: 'Neto recobros', dataIndex: 'neto_recobros', width: 115, align: 'right', render: eur },
              { title: 'Recibo', dataIndex: 'recibo', width: 90, render: (r: string | null) => r ?? '—' },
              { title: 'Neto 4152*', dataIndex: 'neto_4152', width: 105, align: 'right', render: eur },
              { title: 'Neto cobro', dataIndex: 'neto_cobro', width: 105, align: 'right', render: eur },
              { title: 'Estado', dataIndex: 'estado', width: 210, render: (e: string) => <Tag color={colorEstado(e)}>{e}</Tag> },
            ]}
          />
        </Card>
      )}

      {asignar && (
        <ModalAsignar fila={asignar.fila} extra={asignar.extra} tolerancia={tolerancia}
          onCerrar={(guardado) => { setAsignar(null); if (guardado) { setSel([]); qc.invalidateQueries({ queryKey: ['cierres', 'recobros'] }) } }} />
      )}
      <ModalEmparejamientos abierto={verEmparejamientos} puedeEditar={puedeEditar}
        onCerrar={() => { setVerEmparejamientos(false); qc.invalidateQueries({ queryKey: ['cierres', 'recobros'] }) }} />
      <ModalGruposH abierto={verGruposH} ejercicios={ejercicios} onCerrar={() => setVerGruposH(false)} />
    </div>
  )
}

function ModalAsignar({ fila, extra, tolerancia, onCerrar }: {
  fila: FilaRecobro; extra: boolean; tolerancia: number; onCerrar: (guardado: boolean) => void
}) {
  const [sel, setSel] = useState<number[]>([])
  const cands = useQuery({
    queryKey: ['cierres', 'recobros', 'candidatos', fila.cuenta, extra ? fila.recibo : null],
    queryFn: () => herramientasApi.candidatos(fila.cuenta, extra ? fila.recibo ?? undefined : undefined).then((r) => r.data),
  })
  const suma = (cands.data ?? []).filter((c) => sel.includes(c.id)).reduce((a, c) => a + c.neto, 0)
  const dif = fila.neto_4152 != null ? Math.abs(suma - fila.neto_4152) : null

  const guardar = async () => {
    if (extra && dif != null && dif > tolerancia + 1e-9) {
      const seguir = await new Promise<boolean>((res) => Modal.confirm({
        title: 'La suma no cuadra con el 4152*', content: `Diferencia ${eur(dif)} € (tolerancia ${eur(tolerancia)} €). ¿Asignar igualmente?`,
        okText: 'Asignar', cancelText: 'Cancelar', onOk: () => res(true), onCancel: () => res(false),
      }))
      if (!seguir) return
    }
    try {
      await herramientasApi.guardarEmparejamiento({ grupo: fila.grupo, recibo: fila.recibo, neto_recobros: fila.neto_recobros, cobro_ids: sel })
      message.success('Emparejamiento guardado')
      onCerrar(true)
    } catch (e) {
      message.error(apiError(e))
    }
  }

  return (
    <Modal open onCancel={() => onCerrar(false)} width={860} okText="Asignar" cancelText="Cancelar"
      okButtonProps={{ disabled: !sel.length }} onOk={guardar}
      title={extra ? `Cobro extra — cuenta ${fila.cuenta}, recibo ${fila.recibo}` : `Asignar cobro (recibo vacío) — cuenta ${fila.cuenta}`}>
      <Paragraph>
        Asiento {fila.asiento_key} · recibo {fila.recibo ?? '—'} · neto 4152*: <b>{eur(fila.neto_4152)} €</b> ·
        Seleccionados: <b>{eur(suma)} €</b>{' '}
        {dif != null && sel.length > 0 && (dif < 0.005 ? <Tag color="green">cuadra</Tag> : <Tag color="red">diferencia {eur(dif)} €</Tag>)}
      </Paragraph>
      <Table<CandidatoCobro> size="small" rowKey="id" loading={cands.isLoading} dataSource={cands.data}
        pagination={{ pageSize: 20 }} rowSelection={{ selectedRowKeys: sel, onChange: (k) => setSel(k as number[]) }}
        locale={{ emptyText: 'No hay apuntes disponibles' }}
        columns={[
          { title: 'Id', dataIndex: 'id', width: 90 },
          { title: 'Fecha', dataIndex: 'fecha', width: 95, render: fecha },
          { title: 'Ejercicio', dataIndex: 'ejercicio', width: 80 },
          { title: 'Concepto', dataIndex: 'concepto_norm', ellipsis: true },
          { title: 'Recibo', dataIndex: 'recibo_norm', width: 90 },
          { title: 'Neto', dataIndex: 'neto', width: 105, align: 'right', render: eur },
        ]} />
    </Modal>
  )
}

function ModalEmparejamientos({ abierto, puedeEditar, onCerrar }: { abierto: boolean; puedeEditar: boolean; onCerrar: () => void }) {
  const qc = useQueryClient()
  const [sel, setSel] = useState<number[]>([])
  const datos = useQuery({
    queryKey: ['cierres', 'recobros', 'emparejamientos'],
    queryFn: () => herramientasApi.emparejamientos().then((r) => r.data),
    enabled: abierto,
  })
  const borrar = () => Modal.confirm({
    title: `¿Borrar ${sel.length} emparejamientos guardados?`, okText: 'Borrar', okButtonProps: { danger: true }, cancelText: 'Cancelar',
    onOk: async () => {
      try {
        await herramientasApi.borrarEmparejamientos(sel)
        setSel([])
        qc.invalidateQueries({ queryKey: ['cierres', 'recobros', 'emparejamientos'] })
      } catch (e) {
        message.error(apiError(e))
      }
    },
  })
  return (
    <Modal open={abierto} onCancel={onCerrar} footer={null} width={1000} title="Emparejamientos guardados">
      <Paragraph type="secondary">
        Se aplican solos a las filas FALTANTE al buscar. Los marcados como "ya conciliado" o "no existe" ya no se aplican.
      </Paragraph>
      {puedeEditar && <Button danger disabled={!sel.length} onClick={borrar} style={{ marginBottom: 12 }}>Borrar seleccionados</Button>}
      <Table<EmparejamientoH> size="small" rowKey="id" loading={datos.isLoading} dataSource={datos.data} pagination={{ pageSize: 20 }}
        rowSelection={puedeEditar ? { selectedRowKeys: sel, onChange: (k) => setSel(k as number[]) } : undefined}
        columns={[
          { title: 'Asiento', dataIndex: 'asiento_key', width: 120 },
          { title: 'Concepto', dataIndex: 'concepto_norm', ellipsis: true },
          { title: 'Cuenta', dataIndex: 'cuenta_440', width: 110 },
          { title: 'Recibo', dataIndex: 'recibo', width: 90 },
          { title: 'Cobro', dataIndex: 'cobro_id', width: 90 },
          { title: 'Neto cobro', dataIndex: 'neto_cobro', width: 100, align: 'right', render: eur },
          { title: 'Situación', width: 130, render: (_: unknown, m) => m.cobro_inexistente ? <Tag color="red">no existe</Tag>
            : m.cobro_conciliado ? <Tag>ya conciliado</Tag> : <Tag color="green">pendiente</Tag> },
          { title: 'Guardado', dataIndex: 'created_at', width: 100, render: fecha },
        ]} />
    </Modal>
  )
}

function ModalGruposH({ abierto, ejercicios, onCerrar }: { abierto: boolean; ejercicios: { value: number; label: string }[]; onCerrar: () => void }) {
  const qc = useQueryClient()
  const [ejs, setEjs] = useState<number[]>([])
  const [tol, setTol] = useState(0.01)
  const [taskId, setTaskId] = useState<string | null>(null)
  const { tarea, enCurso, errorConsulta } = useTarea(taskId, () => qc.invalidateQueries({ queryKey: ['cierres'] }))
  const lanzar = async () => {
    try {
      const { data } = await herramientasApi.conciliarGruposH(ejs, tol)
      setTaskId(data.task_id)
    } catch (e) {
      message.error(apiError(e))
    }
  }
  const r = tarea?.estado === 'terminada' ? tarea.resultado : null
  return (
    <Modal open={abierto} onCancel={onCerrar} footer={null} width={700} title="Conciliar grupos de recobros (regla H)">
      <Paragraph type="secondary">
        Recobros "RECOBRO COMISIONES" con sus cobros por recibo 4152* y los emparejamientos guardados. Concilia los grupos
        cuya suma quede dentro de la tolerancia.
      </Paragraph>
      <Space wrap style={{ marginBottom: 12 }}>
        <Select mode="multiple" style={{ minWidth: 260 }} placeholder="Ejercicios" value={ejs} onChange={setEjs} options={ejercicios} />
        <Button onClick={() => setEjs(ejercicios.map((e) => e.value))}>Todos</Button>
        <Text>Tolerancia (€):</Text>
        <InputNumber min={0} step={0.01} precision={2} decimalSeparator="," value={tol} onChange={(v) => setTol(v ?? 0)} />
        <Button type="primary" disabled={!ejs.length || enCurso} loading={enCurso} onClick={lanzar}>Conciliar</Button>
      </Space>
      <EstadoTarea tarea={tarea} errorConsulta={errorConsulta} />
      {r && (
        <Alert type="info" showIcon message={`${num(r.apuntes)} apuntes conciliados en ${num(r.grupos_ok)} grupos; ${num(r.grupos_error)} grupos sin conciliar`}
          description={r.errores?.length ? <ul style={{ maxHeight: 200, overflow: 'auto' }}>{r.errores.map((e: string) => <li key={e}>{e}</li>)}</ul> : undefined} />
      )}
    </Modal>
  )
}
