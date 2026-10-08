import { useState, useEffect, useRef } from 'react'
import { Space, Typography, Card, Button, Alert, List, Input, Tag, message, Progress, Row, Col, Statistic, Divider } from 'antd'
import { DeleteOutlined, CheckCircleOutlined, DatabaseOutlined, LoadingOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { adminApi } from '../../api/admin'
import { apiError } from '../../utils/errorHandler'

const { Title, Text, Paragraph } = Typography

const PRESERVADO = [
  'Mapeo de cuentas contables',
  'Tasas de referencia de mercado',
  'Usuarios y permisos',
]

const ELIMINADO = [
  'Cargas de recibos (CSV)',
  'Cargas de diario contable (base presupuestaria, real mensual)',
  'Cargas de histórico estadístico',
  'Todos los apuntes contables procesados',
  'Todas las incidencias generadas',
]

function fmt(n: number) {
  return new Intl.NumberFormat('es-ES').format(n)
}

interface ResetResult {
  cargas_eliminadas: number
  recibos_eliminados: number
  apuntes_eliminados: number
  incidencias_eliminadas: number
  tiempo_segundos: number
}

export default function ResetDatos() {
  const qc = useQueryClient()
  const [confirmText, setConfirmText] = useState('')
  const [done, setDone] = useState<ResetResult | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const startTimeRef = useRef<number | null>(null)
  const timerRef = useRef<number | null>(null)

  const reset = useMutation({
    mutationFn: () => adminApi.resetDatos(),
    onSuccess: (res) => {
      const tiempo_segundos = startTimeRef.current
        ? Math.round((Date.now() - startTimeRef.current) / 1000)
        : 0
      setDone({ ...res.data, tiempo_segundos })
      setConfirmText('')
      qc.invalidateQueries()
    },
    onError: (e) => message.error(apiError(e, 'Error al limpiar datos')),
  })

  useEffect(() => {
    if (reset.isPending) {
      setElapsed(0)
      startTimeRef.current = Date.now()
      timerRef.current = window.setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTimeRef.current!) / 1000))
      }, 500)
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [reset.isPending])

  const habilitado = confirmText === 'LIMPIAR'

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', maxWidth: 640 }}>
      <Title level={4} style={{ margin: 0 }}>Limpiar datos de prueba</Title>

      {done ? (
        <Card style={{ background: '#f6ffed', border: '1px solid #b7eb8f' }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space>
              <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 20 }} />
              <Text strong style={{ color: '#389e0d', fontSize: 16 }}>
                Datos eliminados en {done.tiempo_segundos}s
              </Text>
            </Space>
            <Divider style={{ margin: '12px 0' }} />
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Statistic
                  title="Cargas eliminadas"
                  value={fmt(done.cargas_eliminadas)}
                  valueStyle={{ fontSize: 20, color: '#ff4d4f' }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="Recibos eliminados"
                  value={fmt(done.recibos_eliminados)}
                  valueStyle={{ fontSize: 20, color: '#ff4d4f' }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="Apuntes eliminados"
                  value={fmt(done.apuntes_eliminados)}
                  valueStyle={{ fontSize: 20, color: '#ff4d4f' }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="Incidencias eliminadas"
                  value={fmt(done.incidencias_eliminadas)}
                  valueStyle={{ fontSize: 20, color: '#ff4d4f' }}
                />
              </Col>
            </Row>
            <Divider style={{ margin: '8px 0' }} />
            <Text type="secondary">El mapeo de cuentas y las tasas de mercado se han conservado.</Text>
            <Button onClick={() => setDone(null)}>Cerrar</Button>
          </Space>
        </Card>
      ) : reset.isPending ? (
        <Card style={{ background: '#fff7e6', border: '2px solid #ffd591', borderRadius: 8 }}>
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Space>
              <LoadingOutlined style={{ color: '#fa8c16', fontSize: 20 }} spin />
              <Text strong style={{ color: '#d46b08', fontSize: 16 }}>Limpiando datos...</Text>
            </Space>
            <Progress
              percent={Math.min(elapsed * 20, 90)}
              showInfo={false}
              strokeColor={{ '0%': '#fa8c16', '100%': '#52c41a' }}
            />
            <Text type="secondary">{elapsed}s transcurridos — eliminando apuntes, incidencias y cargas...</Text>
          </Space>
        </Card>
      ) : (
        <>
          <Alert
            type="warning"
            showIcon
            message="Esta acción es irreversible"
            description="Se eliminarán permanentemente todos los datos de carga. Úsala solo en entornos de prueba."
          />

          <Card title={<Space><DatabaseOutlined />¿Qué se elimina?</Space>} size="small">
            <List
              size="small"
              dataSource={ELIMINADO}
              renderItem={(item) => (
                <List.Item style={{ padding: '4px 0' }}>
                  <Space>
                    <Tag color="red" style={{ margin: 0 }}>Eliminar</Tag>
                    <Text>{item}</Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>

          <Card title={<Space><CheckCircleOutlined style={{ color: '#52c41a' }} />¿Qué se conserva?</Space>} size="small">
            <List
              size="small"
              dataSource={PRESERVADO}
              renderItem={(item) => (
                <List.Item style={{ padding: '4px 0' }}>
                  <Space>
                    <Tag color="green" style={{ margin: 0 }}>Conservar</Tag>
                    <Text>{item}</Text>
                  </Space>
                </List.Item>
              )}
            />
          </Card>

          <Card size="small">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Paragraph>
                Para confirmar, escribe <Text code>LIMPIAR</Text> en el campo de abajo:
              </Paragraph>
              <Input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="Escribe LIMPIAR para confirmar"
                style={{ maxWidth: 300 }}
                status={confirmText && !habilitado ? 'error' : undefined}
              />
              <Button
                type="primary"
                danger
                icon={<DeleteOutlined />}
                disabled={!habilitado}
                loading={reset.isPending}
                onClick={() => reset.mutate()}
              >
                Limpiar todos los datos
              </Button>
            </Space>
          </Card>
        </>
      )}
    </Space>
  )
}
