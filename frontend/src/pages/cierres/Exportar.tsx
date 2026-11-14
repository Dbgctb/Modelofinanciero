import { useState } from 'react'
import { Button, Card, message, Select, Space, Typography } from 'antd'
import { FileExcelOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { cierresApi, herramientasApi } from '../../api/cierres'
import { apiError } from '../../utils/errorHandler'
import { descargarBlob, EstadoTarea, num, useTarea } from './comun'

const { Title, Paragraph, Text } = Typography

export default function Exportar() {
  const [ejercicio, setEjercicio] = useState<number | undefined>()
  const [taskId, setTaskId] = useState<string | null>(null)
  const { data: resumen } = useQuery({ queryKey: ['cierres', 'resumen'], queryFn: () => cierresApi.getResumen().then((r) => r.data) })
  const ejercicios = [...(resumen?.apuntes ?? [])].reverse()
  const pendientes = ejercicios
    .filter((a) => !ejercicio || a.ejercicio === ejercicio)
    .reduce((s, a) => s + (a.total - a.punteados), 0)

  const { tarea, enCurso, errorConsulta } = useTarea(taskId, async () => {
    try {
      const { data } = await cierresApi.descargarTarea(taskId!)
      descargarBlob(data as Blob, `Cuadre_Contable_${ejercicio ?? 'todos'}.xlsx`)
    } catch (e) {
      message.error(apiError(e, 'No se pudo descargar el Excel'))
    }
  })

  const exportar = async () => {
    try {
      const { data } = await herramientasApi.exportar(ejercicio)
      setTaskId(data.task_id)
    } catch (e) {
      message.error(apiError(e))
    }
  }

  return (
    <div>
      <Title level={3}>Exportar</Title>
      <Paragraph type="secondary">
        Excel con los apuntes sin puntear agrupados por cuenta (cada cuenta con su saldo y sus apuntes plegables) y una
        hoja con las incidencias de los controles de calidad.
      </Paragraph>
      <Card size="small">
        <Space wrap>
          <Select style={{ width: 200 }} allowClear placeholder="Todos los ejercicios" value={ejercicio} onChange={setEjercicio}
            options={ejercicios.map((a) => ({ value: a.ejercicio, label: String(a.ejercicio) }))} />
          <Text type="secondary">{num(pendientes)} apuntes sin puntear</Text>
          <Button type="primary" icon={<FileExcelOutlined />} loading={enCurso} disabled={enCurso} onClick={exportar}>
            Exportar a Excel
          </Button>
        </Space>
        <div style={{ marginTop: 12 }}><EstadoTarea tarea={tarea} errorConsulta={errorConsulta} /></div>
      </Card>
    </div>
  )
}
