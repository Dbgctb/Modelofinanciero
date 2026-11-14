import { Alert, Card, Empty, Spin, Table, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { cierresApi, CierresResumenApuntes } from '../../api/cierres'

const { Title, Paragraph } = Typography

interface Props {
  titulo: string
  descripcion: string
  fase: string
}

/**
 * Pantalla provisional de las opciones de "Cierres contabilidad" mientras se
 * reconstruyen por fases (docs/PLAN_CIERRES_CONTABILIDAD.md). Muestra qué hará
 * la opción y el estado del diario cargado en el módulo.
 */
export default function EnPreparacion({ titulo, descripcion, fase }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['cierres', 'resumen'],
    queryFn: () => cierresApi.getResumen().then((r) => r.data),
  })

  const fmt = (n: number) => n.toLocaleString('es-ES')

  return (
    <div>
      <Title level={3}>{titulo}</Title>
      <Paragraph type="secondary">{descripcion}</Paragraph>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="En preparación"
        description={`Esta opción se está trasladando desde el programa Cuadre Contable. Llegará en la ${fase}. Mientras tanto, sigue usando el programa actual.`}
      />
      <Card title="Diario cargado en el módulo" size="small">
        {isLoading ? (
          <Spin />
        ) : !data || data.apuntes.length === 0 ? (
          <Empty description="Todavía no hay datos: se copiarán del programa actual en la fase 1." />
        ) : (
          <Table<CierresResumenApuntes>
            size="small"
            rowKey="ejercicio"
            pagination={false}
            dataSource={data.apuntes}
            columns={[
              { title: 'Ejercicio', dataIndex: 'ejercicio' },
              { title: 'Apuntes', dataIndex: 'total', align: 'right', render: fmt },
              { title: 'Punteados', dataIndex: 'punteados', align: 'right', render: fmt },
              {
                title: '% punteado',
                align: 'right',
                render: (_, r) => (r.total ? `${((r.punteados / r.total) * 100).toFixed(1)} %` : '—'),
              },
            ]}
          />
        )}
      </Card>
    </div>
  )
}
