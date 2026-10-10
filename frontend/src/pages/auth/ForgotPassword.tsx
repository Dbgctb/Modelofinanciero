import { useState } from 'react'
import { Form, Input, Button, Card, Alert, Typography } from 'antd'
import { MailOutlined, ArrowLeftOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'
import { authApi } from '../../api/auth'

const { Title, Text } = Typography

export default function ForgotPassword() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [enviado, setEnviado] = useState(false)

  const onFinish = async (values: { email: string }) => {
    setLoading(true)
    setError(null)
    try {
      await authApi.forgotPassword(values.email)
      setEnviado(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Error de conexión')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%)',
    }}>
      <Card
        style={{ width: 400, borderRadius: 12, boxShadow: '0 20px 60px rgba(0,0,0,0.4)' }}
        styles={{ body: { padding: '40px 36px' } }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <img src="/logo.png" alt="Logo" style={{ height: 72, marginBottom: 16, objectFit: 'contain' }} />
          <Title level={3} style={{ margin: 0, color: '#1a1a2e' }}>Recuperar contraseña</Title>
          <Text type="secondary">Te diremos cómo seguir</Text>
        </div>

        {error && (
          <Alert message={error} type="error" showIcon style={{ marginBottom: 20 }} closable onClose={() => setError(null)} />
        )}

        {enviado ? (
          <Alert
            type="success"
            showIcon
            message="Solicitud registrada"
            description="Si el email corresponde a una cuenta activa, se ha generado un enlace de recuperación. Contacta con el administrador para que te lo pase."
          />
        ) : (
          <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
            <Form.Item
              name="email"
              rules={[{ required: true, type: 'email', message: 'Introduce un email válido' }]}
            >
              <Input
                prefix={<MailOutlined />}
                placeholder="Tu email"
                size="large"
                autoComplete="email"
              />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0 }}>
              <Button
                type="primary"
                htmlType="submit"
                size="large"
                block
                loading={loading}
                style={{ borderRadius: 8, height: 44 }}
              >
                Enviar solicitud
              </Button>
            </Form.Item>
          </Form>
        )}

        <div style={{ textAlign: 'center', marginTop: 16 }}>
          <Link to="/login"><ArrowLeftOutlined /> Volver al login</Link>
        </div>
      </Card>
    </div>
  )
}
