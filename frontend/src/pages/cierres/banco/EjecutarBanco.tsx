import { useEffect, useState } from 'react'
import { Button, Card, Descriptions, InputNumber, message, Space, Table, Typography } from 'antd'
import { PlayCircleOutlined, SaveOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { bancoApi, ConfigBanco } from '../../../api/cierres'
import { apiError } from '../../../utils/errorHandler'
import { EstadoTarea, num, usePuedeEditar, useTarea } from '../comun'

const { Text } = Typography

const NIVELES = [
  { nivel: '1', nombre: 'Fecha e importe exactos', detalle: '1 movimiento con 1 apunte de la misma fecha y el mismo importe.' },
  { nivel: '2', nombre: 'Importe exacto ± días', detalle: 'Mismo importe en los días configurados alrededor; primero el más cercano.' },
  { nivel: '3', nombre: 'Misma fecha ± 5,00 €', detalle: 'Misma fecha y diferencia de hasta 5,00 € (fija); el de menor diferencia.' },
  { nivel: '7', nombre: 'Liquidaciones Nº', detalle: 'Apuntes "Liquidac…" con el mismo "Nº XXXX" del mes contra 1 movimiento del mes o del siguiente (±0,01 €).' },
  { nivel: '8', nombre: 'Ingresos contra cobros', detalle: 'Movimiento "Ingreso…" contra apuntes "Cobro…/Extorno…" del mismo mes (mismo día, mes entero o selección).' },
  { nivel: '9', nombre: 'Devoluciones', detalle: 'Movimiento "Devoluc…" contra apuntes "Devolu…" del mismo mes.' },
]

export default function EjecutarBanco({ bancoId, ejercicio, onIrPendientes }: {
  bancoId: number; ejercicio: number; onIrPendientes: () => void
}) {
  const qc = useQueryClient()
  const puedeEditar = usePuedeEditar()
  const [cfg, setCfg] = useState<ConfigBanco | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)

  const config = useQuery({
    queryKey: ['cierres', 'banco', 'config', bancoId],
    queryFn: () => bancoApi.getConfig(bancoId).then((r) => r.data),
  })
  useEffect(() => { if (config.data) setCfg(config.data) }, [config.data])

  const { tarea, enCurso, errorConsulta } = useTarea(taskId, () => qc.invalidateQueries({ queryKey: ['cierres'] }))

  const guardar = async () => {
    if (!cfg) return false
    try {
      await bancoApi.guardarConfig(bancoId, cfg)
      qc.invalidateQueries({ queryKey: ['cierres', 'banco', 'config', bancoId] })
      return true
    } catch (e) {
      message.error(apiError(e, 'No se pudo guardar la configuración'))
      return false
    }
  }

  const ejecutar = async () => {
    if (!(await guardar())) return
    try {
      const { data } = await bancoApi.conciliar(bancoId, ejercicio)
      setTaskId(data.task_id)
    } catch (e) {
      message.error(apiError(e, 'No se pudo iniciar la conciliación'))
    }
  }

  const r = tarea?.estado === 'terminada' ? tarea.resultado : null
  const parametro = (nivel: string) => {
    if (!cfg) return null
    if (nivel === '2')
      return <Space><InputNumber size="small" min={0} max={30} value={cfg.dias_nivel2} disabled={!puedeEditar}
        onChange={(v) => setCfg({ ...cfg, dias_nivel2: v ?? 0 })} /> días</Space>
    if (nivel === '8' || nivel === '9') {
      const k = nivel === '8' ? 'tol_nivel8' : 'tol_nivel9'
      return <Space><InputNumber size="small" min={0} max={1000} step={0.01} precision={2} decimalSeparator=","
        value={cfg[k]} disabled={!puedeEditar} onChange={(v) => setCfg({ ...cfg, [k]: v ?? 0 })} /> €</Space>
    }
    return <Text type="secondary">—</Text>
  }

  return (
    <div>
      <Card size="small" title="Niveles (se ejecutan todos, en este orden)" style={{ marginBottom: 16 }}
        extra={puedeEditar && <Button icon={<SaveOutlined />} onClick={async () => (await guardar()) && message.success('Configuración guardada')}>Guardar configuración</Button>}>
        <Table size="small" rowKey="nivel" pagination={false} dataSource={NIVELES} loading={config.isLoading}
          columns={[
            { title: 'Nivel', dataIndex: 'nivel', width: 60 },
            { title: 'Criterio', dataIndex: 'nombre', width: 200 },
            { title: 'Detalle', dataIndex: 'detalle' },
            { title: 'Parámetro', width: 170, render: (_: unknown, n) => parametro(n.nivel) },
          ]} />
        <Text type="secondary">Cada nivel solo usa lo que dejan libre los anteriores. Lo ya conciliado no se toca.</Text>
      </Card>

      {puedeEditar && (
        <Button type="primary" size="large" icon={<PlayCircleOutlined />} onClick={ejecutar}
          loading={enCurso} disabled={enCurso || !cfg} style={{ marginBottom: 16 }}>
          Ejecutar conciliación {ejercicio}
        </Button>
      )}
      <EstadoTarea tarea={tarea} errorConsulta={errorConsulta} />
      {r && (
        <Card size="small" title="Resultado">
          <Descriptions size="small" column={{ xs: 1, md: 3 }} bordered>
            <Descriptions.Item label="Conciliados">
              {num(r.conciliados_banco)} de {num(r.total_banco)} movimientos
              ({r.total_banco ? ((r.conciliados_banco / r.total_banco) * 100).toFixed(1) : 0} %)
            </Descriptions.Item>
            <Descriptions.Item label="Pendientes banco">{num(r.pendientes_banco)}</Descriptions.Item>
            <Descriptions.Item label="Pendientes diario">{num(r.pendientes_diario)}</Descriptions.Item>
            {Object.entries(r.niveles as Record<string, number>).map(([k, v]) => (
              <Descriptions.Item key={k} label={k.replace('nivel_', 'Nivel ')}>
                {num(v)} {Number(k.slice(-1)) >= 7 ? 'movimientos + apuntes' : 'parejas'}
              </Descriptions.Item>
            ))}
          </Descriptions>
          <Button style={{ marginTop: 12 }} onClick={onIrPendientes}>Ver pendientes</Button>
        </Card>
      )}
    </div>
  )
}
