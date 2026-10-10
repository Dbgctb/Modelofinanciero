import { useState } from 'react'
import { Form, Input, Button, Card, Alert, Typography, Result } from 'antd'
import { LockOutlined } from '@ant-design/icons'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { authApi } from '../../api/auth'

const { Title, Text } = Typography
const { Password } = Input

export default function ResetPassword() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hecho, setHecho] = useState(false)

  const onFinish = async (values: { new_password: string }) => {
    setLoading(true)
    setError(null)
    try {
      await authApi.resetPassword(token, values.new_password)
      setHecho(true)
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
        style={{ width: 420, borderRadius: 12, boxShadow: '0 20px 60px rgba(0,0,0,0.4)' }}
        styles={{ body: { padding: '40px 36px' } }}
      >
        {hecho ? (
          <Result
            status="success"
            title="Contraseña actualizada"
            subTitle="Ya puedes iniciar sesión con tu nueva contraseña."
            extra={<Button type="primary" onClick={() => navigate('/login')}>Ir al login</Button>}
          />
        ) : !token ? (
          <Result
            status="error"
            title="Enlace no válido"
            subTitle="Falta el token de recuperación. Pide un enlace nuevo desde el login."
            extra={<Link to="/forgot-password"><Button type="primary">Pedir enlace nuevo</Button></Link>}
          />
        ) : (
          <>
            <div style={{ textAlign: 'center', marginBottom: 32 }}>
              <img src="/logo.png" alt="Logo" style={{ height: 72, marginBottom: 16, objectFit: 'contain' }} />
              <Title level={3} style={{ margin: 0, color: '#1a1a2e' }}>Nueva contraseña</Title>
              <Text type="secondary">Elige una contraseña nueva para tu cuenta</Text>
            </div>

            {error && (
              <Alert message={error} type="error" showIcon style={{ marginBottom: 20 }} closable onClose={() => setError(null)} />
            )}

            <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
              <Form.Item
                name="new_password"
                label="Nueva contraseña"
                rules={[{ required: true, message: 'Obligatorio' }]}
              >
                <Password prefix={<LockOutlined />} placeholder="Mínimo 10 caracteres" size="large" autoComplete="new-password" />
              </Form.Item>
              <Form.Item
                name="confirm"
                label="Confirmar contraseña"
                dependencies={['new_password']}
                rules={[
                  { required: true, message: 'Obligatorio' },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                      return Promise.reject(new Error('Las contraseñas no coinciden'))
                    },
                  }),
                ]}
              >
                <Password prefix={<LockOutlined />} placeholder="Repite la contraseña" size="large" autoComplete="new-password" />
              </Form.Item>
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 20 }}
                message="La contraseña debe tener ≥10 caracteres, mayúscula, minúscula, número y carácter especial (@$!%*?&._-)"
              />
              <Form.Item style={{ marginBottom: 0 }}>
                <Button type="primary" htmlType="submit" size="large" block loading={loading} style={{ borderRadius: 8, height: 44 }}>
                  Guardar contraseña
                </Button>
              </Form.Item>
            </Form>
          </>
        )}
      </Card>
    </div>
  )
}
