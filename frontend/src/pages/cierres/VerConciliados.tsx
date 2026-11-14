import { useState } from 'react'
import { Alert, Button, Card, Col, Descriptions, message, Row, Select, Space, Table, Tag, Typography } from 'antd'
import { FileExcelOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Apunte, Bloque, cierresApi } from '../../api/cierres'
import { apiError } from '../../utils/errorHandler'
import { descargarBlob, EstadoTarea, eur, fecha, num, useTarea } from './comun'

const { Title, Paragraph } = Typography

const colorEstado = (e: string) => (e === 'OK' ? 'green' : e === 'Solo 1 línea' ? 'orange' : 'red')

export default function VerConciliados() {
  const [ejercicio, setEjercicio] = useState<number | undefined>(undefined)
  const [regla, setRegla] = useState<string | undefined>(undefined)
  const [cargado, setCargado] = useState<{ ejercicio?: number; regla?: string } | null>(null)
  const [pagina, setPagina] = useState(1)
  const [grupo, setGrupo] = useState<string | null>(null)
  const [refrescar, setRefrescar] = useState(0)
  const [taskId, setTaskId] = useState<string | null>(null)

  const { data: resumen } = useQuery({
    queryKey: ['cierres', 'resumen'],
    queryFn: () => cierresApi.getResumen().then((r) => r.data),
  })
  const reglas = useQuery({
    queryKey: ['cierres', 'reglas-punteo'],
    queryFn: () => cierresApi.getReglasPunteo().then((r) => r.data),
  })

  const bloques = useQuery({
    queryKey: ['cierres', 'bloques', cargado, pagina, refrescar],
    queryFn: () => cierresApi.getBloques({
      ejercicio: cargado?.ejercicio, regla: cargado?.regla, page: pagina, page_size: 200,
      refrescar: refrescar > 0 && pagina === 1,
    }).then((r) => r.data),
    enabled: !!cargado,
  })

  const detalle = useQuery({
    queryKey: ['cierres', 'bloque', grupo],
    queryFn: () => cierresApi.getBloque(grupo!).then((r) => r.data),
    enabled: !!grupo,
  })

  const { tarea, enCurso, errorConsulta } = useTarea(taskId, async () => {
    try {
      const { data } = await cierresApi.descargarTarea(taskId!)
      descargarBlob(data as Blob, `conciliados_${cargado?.ejercicio ?? 'todos'}_${cargado?.regla ?? 'todas_reglas'}.xlsx`)
    } catch (e) {
      message.error(apiError(e, 'No se pudo descargar el Excel'))
    }
  })

  const exportar = async () => {
    try {
      const { data } = await cierresApi.excelConciliados(cargado?.ejercicio, cargado?.regla)
      setTaskId(data.task_id)
    } catch (e) {
      message.error(apiError(e))
    }
  }

  const ejercicios = [...(resumen?.apuntes ?? [])].reverse().map((a) => ({ value: a.ejercicio, label: String(a.ejercicio) }))

  return (
    <div>
      <Title level={3}>Ver conciliados</Title>
      <Paragraph type="secondary">
        Cada bloque es un grupo de apuntes punteados juntos. En rojo, los que no suman 0 (±0,05 €); en naranja,
        los de una sola línea. En la regla H la suma mira solo las cuentas 440*.
      </Paragraph>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select style={{ width: 160 }} placeholder="Todos los ejercicios" allowClear
            value={ejercicio} onChange={setEjercicio} options={ejercicios} />
          <Select style={{ width: 200 }} placeholder="Todas las reglas" allowClear showSearch
            value={regla} onChange={setRegla}
            options={(reglas.data ?? []).map((r) => ({ value: r, label: r }))} />
          <Button type="primary" onClick={() => { setCargado({ ejercicio, regla }); setPagina(1); setGrupo(null) }}>
            Cargar bloques
          </Button>
          <Button icon={<ReloadOutlined />} disabled={!cargado}
            onClick={() => { setPagina(1); setRefrescar((n) => n + 1) }}>Recargar</Button>
          <Button icon={<FileExcelOutlined />} disabled={!cargado || enCurso} loading={enCurso} onClick={exportar}>
            Exportar Excel
          </Button>
        </Space>
        <div style={{ marginTop: 12 }}><EstadoTarea tarea={tarea} errorConsulta={errorConsulta} /></div>
      </Card>

      {bloques.error && <Alert type="error" showIcon message={apiError(bloques.error)} style={{ marginBottom: 12 }} />}

      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card size="small" title={bloques.data ? `${num(bloques.data.total)} bloques` : 'Bloques'}>
            <Table<Bloque>
              size="small" rowKey="grupo" loading={bloques.isFetching} dataSource={bloques.data?.bloques}
              onRow={(b) => ({ onClick: () => setGrupo(b.grupo), style: { cursor: 'pointer' } })}
              rowClassName={(b) => (b.grupo === grupo ? 'ant-table-row-selected' : '')}
              pagination={{
                current: pagina, pageSize: 200, total: bloques.data?.total, showSizeChanger: false,
                onChange: setPagina,
              }}
              locale={{ emptyText: cargado ? 'No hay bloques con esos filtros' : 'Elige filtros y pulsa Cargar bloques' }}
              columns={[
                { title: 'Ejercicio', width: 95,
                  render: (_: unknown, b) => (b.min_ej === b.max_ej ? b.min_ej : `${b.min_ej}–${b.max_ej}`) },
                { title: 'Regla', dataIndex: 'regla', width: 110 },
                { title: 'Líneas', dataIndex: 'num_lineas', width: 65, align: 'right' },
                { title: 'Suma', dataIndex: 'suma', width: 100, align: 'right', render: eur },
                { title: 'Estado', dataIndex: 'estado', render: (e: string) => <Tag color={colorEstado(e)}>{e}</Tag> },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card size="small" title="Detalle del bloque">
            {!grupo ? (
              <Paragraph type="secondary">Haz clic en un bloque para ver sus apuntes.</Paragraph>
            ) : (
              <>
                <Descriptions size="small" column={2} style={{ marginBottom: 12 }}>
                  <Descriptions.Item label="Grupo" span={2}>{grupo}</Descriptions.Item>
                  <Descriptions.Item label="Líneas">{detalle.data?.filas.length}</Descriptions.Item>
                  <Descriptions.Item label="Suma neto">{eur(detalle.data?.suma)} €</Descriptions.Item>
                </Descriptions>
                <Table<Apunte>
                  size="small" rowKey="id" loading={detalle.isLoading} dataSource={detalle.data?.filas}
                  pagination={false} scroll={{ x: 800, y: 500 }}
                  columns={[
                    { title: 'ID', dataIndex: 'id', width: 85 },
                    { title: 'Ejercicio', dataIndex: 'ejercicio', width: 80 },
                    { title: 'Fecha', dataIndex: 'fecha', width: 95, render: fecha },
                    { title: 'Cuenta', dataIndex: 'cuenta', width: 110 },
                    { title: 'Concepto', dataIndex: 'concepto', ellipsis: true },
                    { title: 'Recibo', dataIndex: 'recibo_norm', width: 80 },
                    { title: 'Neto', dataIndex: 'neto', width: 100, align: 'right',
                      render: (n: number) => <span style={{ color: n >= 0 ? '#389e0d' : '#cf1322' }}>{eur(n)}</span> },
                  ]}
                />
              </>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
