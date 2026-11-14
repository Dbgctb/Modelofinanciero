import { useMemo, useState } from 'react'
import {
  Alert, Button, Card, Checkbox, Form, Input, InputNumber, message, Modal, Popconfirm, Select, Space,
  Switch, Table, Tag, Typography,
} from 'antd'
import { PlayCircleOutlined, SettingOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cierresApi, CuentaControl, Regla } from '../../api/cierres'
import { apiError } from '../../utils/errorHandler'
import { EstadoTarea, num, usePuedeEditar, useTarea } from './comun'

const { Title, Paragraph, Text } = Typography

const CONTROLES = [
  { value: 'C', label: 'C – Movimientos mensuales' },
  { value: 'D', label: 'D – Neto mensual estable' },
  { value: 'K', label: 'K – Duplicados de emisión' },
  { value: 'L', label: 'L – Anulación sin emisión' },
]

const FINALES = new Set(['CROSS_YEAR', 'RULE_L', 'RULE_P', 'RULE_Q', 'RULE_R', 'RULE_T'])

export default function PunteoAutomatico() {
  const qc = useQueryClient()
  const puedeEditar = usePuedeEditar()
  const [ejercicios, setEjercicios] = useState<number[]>([])
  const [filtro, setFiltro] = useState<string[]>([])
  const [controles, setControles] = useState<string[]>(['C', 'D', 'K', 'L'])
  const [taskId, setTaskId] = useState<string | null>(null)
  const [verCuentas, setVerCuentas] = useState(false)

  const { data: resumen } = useQuery({
    queryKey: ['cierres', 'resumen'],
    queryFn: () => cierresApi.getResumen().then((r) => r.data),
  })
  const disponibles = useMemo(() => (resumen?.apuntes ?? []).map((a) => a.ejercicio), [resumen])

  const reglas = useQuery({ queryKey: ['cierres', 'reglas'], queryFn: () => cierresApi.getReglas().then((r) => r.data) })
  const incidencias = useQuery({
    queryKey: ['cierres', 'incidencias'],
    queryFn: () => cierresApi.getIncidencias().then((r) => r.data),
  })

  const cambiarRegla = useMutation({
    mutationFn: ({ codigo, cambios }: { codigo: string; cambios: Partial<Regla> }) =>
      cierresApi.actualizarRegla(codigo, cambios),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cierres', 'reglas'] }),
    onError: (e) => message.error(apiError(e, 'No se pudo guardar la regla')),
  })

  const { tarea, enCurso, errorConsulta } = useTarea(taskId, () => qc.invalidateQueries({ queryKey: ['cierres'] }))

  const ejecutar = async () => {
    try {
      const filtroValido = filtro.map((f) => f.trim()).filter(Boolean)
      const { data } = await cierresApi.puntear({
        ejercicios, filtro_cuentas: filtroValido.length ? filtroValido : ['*'], controles,
      })
      setTaskId(data.task_id)
    } catch (e) {
      message.error(apiError(e, 'No se pudo iniciar el punteo'))
    }
  }

  const columnasReglas = [
    { title: 'Activa', dataIndex: 'active', width: 70,
      render: (v: boolean, r: Regla) => (
        <Switch size="small" checked={v} disabled={!puedeEditar}
          onChange={(active) => cambiarRegla.mutate({ codigo: r.rule_code, cambios: { active } })} />
      ) },
    { title: 'Regla', dataIndex: 'rule_code', width: 150,
      render: (c: string) => <>{c.replace('RULE_', '')}{FINALES.has(c) && <Tag style={{ marginLeft: 6 }}>todos los ejercicios</Tag>}</> },
    { title: 'Nombre', dataIndex: 'rule_name', width: 230 },
    { title: 'Descripción', dataIndex: 'description', ellipsis: true },
    { title: 'Tolerancia (€)', dataIndex: 'tolerance_amount', width: 130,
      render: (v: number, r: Regla) => r.rule_code === 'RULE_R'
        ? <Text type="secondary">no aplica</Text>
        : (
          <InputNumber size="small" min={0} max={10000} step={0.01} precision={2} defaultValue={v}
            disabled={!puedeEditar} key={`${r.rule_code}-${v}`} decimalSeparator=","
            onBlur={(e) => {
              const nuevo = Number(String(e.target.value).replace('.', '').replace(',', '.'))
              if (!Number.isNaN(nuevo) && nuevo !== v)
                cambiarRegla.mutate({ codigo: r.rule_code, cambios: { tolerance_amount: nuevo } })
            }} />
        ) },
  ]

  const resultado = tarea?.estado === 'terminada' ? tarea.resultado : null

  return (
    <div>
      <Title level={3}>Punteo automático</Title>
      <Paragraph type="secondary">
        Ejecuta las reglas de punteo por ejercicio y los controles de calidad. Con varios ejercicios, las reglas
        marcadas como "todos los ejercicios" se ejecutan una sola vez al final, y la V cierra cada ejercicio.
      </Paragraph>

      <Card size="small" title="1. Qué puntear" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space wrap>
            <Text>Ejercicios:</Text>
            <Select mode="multiple" style={{ minWidth: 320 }} placeholder="Elige uno o varios"
              value={ejercicios} onChange={setEjercicios}
              options={[...disponibles].reverse().map((e) => ({ value: e, label: String(e) }))} />
            <Button onClick={() => setEjercicios(disponibles)}>Todos</Button>
          </Space>
          <Space wrap>
            <Text>Cuentas:</Text>
            <Select mode="tags" style={{ minWidth: 320 }} placeholder="Todas (o escribe 430*, 4110000001…)"
              value={filtro} onChange={setFiltro} tokenSeparators={[',', ' ']} open={false} />
            <Text type="secondary">Con * es prefijo. Vacío = todas las cuentas. Se aplica a todas las reglas.</Text>
          </Space>
        </Space>
      </Card>

      <Card size="small" title="2. Reglas" style={{ marginBottom: 16 }}>
        <Table<Regla> size="small" rowKey="rule_code" pagination={false} loading={reglas.isLoading}
          dataSource={reglas.data} columns={columnasReglas} scroll={{ x: 900 }} />
      </Card>

      <Card size="small" title="3. Controles de calidad" style={{ marginBottom: 16 }}
        extra={<Button icon={<SettingOutlined />} onClick={() => setVerCuentas(true)}>Cuentas de control</Button>}>
        <Checkbox.Group options={CONTROLES} value={controles} onChange={(v) => setControles(v as string[])} />
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          Cada ejecución sustituye las incidencias de ese control y ejercicio.
        </Paragraph>
      </Card>

      {puedeEditar && (
        <Space style={{ marginBottom: 16 }}>
          <Popconfirm
            title={`¿Puntear ${ejercicios.length} ejercicio(s)?`}
            description="Solo se puntean apuntes pendientes; lo ya punteado no se toca."
            onConfirm={ejecutar} okText="Puntear" cancelText="Cancelar" disabled={!ejercicios.length || enCurso}
          >
            <Button type="primary" size="large" icon={<PlayCircleOutlined />}
              disabled={!ejercicios.length || enCurso} loading={enCurso}>
              Ejecutar punteo
            </Button>
          </Popconfirm>
        </Space>
      )}

      <EstadoTarea tarea={tarea} errorConsulta={errorConsulta} />

      {resultado && (
        <Card size="small" title="Resultado" style={{ marginBottom: 16 }}>
          {resultado.errores?.length > 0 && (
            <Alert type="error" showIcon style={{ marginBottom: 12 }} message="Algunas reglas fallaron y no se aplicaron"
              description={resultado.errores.map((e: any) => `${e.ejercicio} ${e.regla}: ${e.error}`).join(' · ')} />
          )}
          <Table size="small" rowKey="ejercicio" pagination={false} dataSource={resultado.ejercicios}
            expandable={{
              expandedRowRender: (r: any) => (
                <Space wrap>
                  {Object.entries(r.por_regla as Record<string, number>).map(([k, v]) => (
                    <Tag key={k}>{k.replace('RULE_', '')}: {num(v)}</Tag>
                  ))}
                </Space>
              ),
            }}
            columns={[
              { title: 'Ejercicio', dataIndex: 'ejercicio' },
              { title: 'Punteados ahora', align: 'right',
                render: (_: unknown, r: any) => num(Object.values(r.por_regla as Record<string, number>).reduce((a, b) => a + b, 0)) },
              { title: 'Total punteados', dataIndex: 'punteados', align: 'right', render: num },
              { title: 'Apuntes', dataIndex: 'total', align: 'right', render: num },
              { title: '% punteado', align: 'right',
                render: (_: unknown, r: any) => (r.total ? `${((r.punteados / r.total) * 100).toFixed(1)} %` : '—') },
              { title: 'Incidencias', render: (_: unknown, r: any) => r.incidencias
                ? Object.entries(r.incidencias as Record<string, number>).map(([k, v]) => `${k}: ${num(v)}`).join(' · ')
                : '—' },
              { title: 'Tiempo', dataIndex: 'segundos', align: 'right', render: (s: number) => `${s} s` },
            ]}
          />
        </Card>
      )}

      <Card size="small" title="Incidencias de los controles (última ejecución de cada ejercicio)">
        <Table size="small" pagination={{ pageSize: 20 }} loading={incidencias.isLoading}
          rowKey={(r) => `${r.ejercicio}-${r.control_type}-${r.severity}`}
          dataSource={incidencias.data}
          columns={[
            { title: 'Ejercicio', dataIndex: 'ejercicio' },
            { title: 'Control', dataIndex: 'control_type',
              render: (c: string) => CONTROLES.find((x) => x.value === c)?.label ?? c },
            { title: 'Gravedad', dataIndex: 'severity',
              render: (s: string) => <Tag color={s === 'ERROR' ? 'red' : s === 'WARNING' ? 'orange' : 'blue'}>{s}</Tag> },
            { title: 'Incidencias', dataIndex: 'n', align: 'right', render: num },
          ]}
          locale={{ emptyText: 'Sin incidencias' }}
        />
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          El detalle de las incidencias sale en el Excel de la opción Exportar.
        </Paragraph>
      </Card>

      <ModalCuentasControl abierto={verCuentas} puedeEditar={puedeEditar} onCerrar={() => setVerCuentas(false)} />
    </div>
  )
}

function ModalCuentasControl({ abierto, puedeEditar, onCerrar }: { abierto: boolean; puedeEditar: boolean; onCerrar: () => void }) {
  const qc = useQueryClient()
  const [form] = Form.useForm<CuentaControl>()
  const [editando, setEditando] = useState<CuentaControl | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['cierres', 'cuentas-control'],
    queryFn: () => cierresApi.getCuentasControl().then((r) => r.data),
    enabled: abierto,
  })
  const tipo = Form.useWatch('tipo', form)

  const guardar = async () => {
    const v = await form.validateFields()
    try {
      if (editando?.id) await cierresApi.actualizarCuentaControl(editando.id, v)
      else await cierresApi.crearCuentaControl(v)
      message.success('Guardado')
      setEditando(null)
      qc.invalidateQueries({ queryKey: ['cierres', 'cuentas-control'] })
    } catch (e) {
      message.error(apiError(e))
    }
  }

  const borrar = async (id: number) => {
    try {
      await cierresApi.borrarCuentaControl(id)
      qc.invalidateQueries({ queryKey: ['cierres', 'cuentas-control'] })
    } catch (e) {
      message.error(apiError(e))
    }
  }

  const nueva: CuentaControl = { tipo: 'C', name: '', cuenta: '', min_mov: 10, max_mov: 500, tolerance_pct: null, active: true }

  return (
    <Modal open={abierto} onCancel={onCerrar} footer={null} width={900} title="Cuentas de los controles de calidad">
      <Paragraph type="secondary">
        C: meses con movimientos fuera del rango. D: variación del neto mensual por encima del % (cuenta exacta).
        K y L: la cuenta es un prefijo (430 = todas las 430*). Sin cuentas de K o L, el control mira todas las cuentas.
      </Paragraph>
      {puedeEditar && !editando && (
        <Button type="primary" style={{ marginBottom: 12 }}
          onClick={() => { setEditando(nueva); form.setFieldsValue(nueva) }}>Añadir cuenta</Button>
      )}
      {editando && (
        <Card size="small" style={{ marginBottom: 12 }}>
          <Form form={form} layout="inline">
            <Form.Item name="tipo" label="Control" rules={[{ required: true }]}>
              <Select style={{ width: 80 }} options={['C', 'D', 'K', 'L'].map((v) => ({ value: v, label: v }))} />
            </Form.Item>
            <Form.Item name="cuenta" label="Cuenta" rules={[{ required: true, pattern: /^\d+$/, message: 'Solo dígitos' }]}>
              <Input style={{ width: 130 }} />
            </Form.Item>
            <Form.Item name="name" label="Nombre"><Input style={{ width: 160 }} /></Form.Item>
            {tipo === 'C' && (
              <>
                <Form.Item name="min_mov" label="Mín." rules={[{ required: true }]}><InputNumber min={0} /></Form.Item>
                <Form.Item name="max_mov" label="Máx." rules={[{ required: true }]}><InputNumber min={0} /></Form.Item>
              </>
            )}
            {tipo === 'D' && (
              <Form.Item name="tolerance_pct" label="Tolerancia %" rules={[{ required: true }]}>
                <InputNumber min={0} max={1000} />
              </Form.Item>
            )}
            <Form.Item name="active" label="Activa" valuePropName="checked"><Switch /></Form.Item>
            <Space>
              <Button type="primary" onClick={guardar}>Guardar</Button>
              <Button onClick={() => setEditando(null)}>Cancelar</Button>
            </Space>
          </Form>
        </Card>
      )}
      <Table<CuentaControl> size="small" rowKey="id" pagination={false} loading={isLoading} dataSource={data}
        columns={[
          { title: 'Control', dataIndex: 'tipo', width: 80 },
          { title: 'Cuenta', dataIndex: 'cuenta' },
          { title: 'Nombre', dataIndex: 'name' },
          { title: 'Parámetros',
            render: (_: unknown, c) => c.tipo === 'C' ? `${c.min_mov}–${c.max_mov} movimientos/mes`
              : c.tipo === 'D' ? `${c.tolerance_pct} %` : '—' },
          { title: 'Activa', dataIndex: 'active', render: (v: boolean) => (v ? 'Sí' : 'No') },
          ...(puedeEditar ? [{
            title: '', width: 160,
            render: (_: unknown, c: CuentaControl) => (
              <Space>
                <Button size="small" onClick={() => { setEditando(c); form.setFieldsValue(c) }}>Editar</Button>
                <Popconfirm title="¿Borrar esta cuenta de control?" onConfirm={() => borrar(c.id!)}
                  okText="Borrar" cancelText="Cancelar">
                  <Button size="small" danger>Borrar</Button>
                </Popconfirm>
              </Space>
            ),
          }] : []),
        ]}
      />
    </Modal>
  )
}
