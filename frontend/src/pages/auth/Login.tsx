import { useState } from 'react'
import { Form, Input, Button, Card, Alert, Typography } from 'antd'
import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../../api/auth'
import { useAuthStore } from '../../store/authStore'

const { Title, Text } = Typography

export default function Login() {
  const navigate = useNavigate()
  const { setTokens, setUser } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    setError(null)
    try {
      const { data: tokens } = await authApi.login(values.username, values.password)
      setTokens(tokens.access_token, tokens.refresh_token)
      const { data: user } = await authApi.me()
      setUser(user)
      if (user.must_change_password) {
        navigate('/cambiar-password')
      } else {
        navigate('/dashboard')
      }
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Error de conexión'
      setError(msg)
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
          <img
            src="/logo.png"
            alt="Logo"
            style={{ height: 72, marginBottom: 16, objectFit: 'contain' }}
          />
          <Title level={3} style={{ margin: 0, color: '#1a1a2e' }}>
            Gestor Financiero
          </Title>
          <Text type="secondary">Correduría de Seguros</Text>
        </div>

        {error && (
          <Alert
            message={error}
            type="error"
            showIcon
            style={{ marginBottom: 20 }}
            closable
            onClose={() => setError(null)}
          />
        )}

        <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
          <Form.Item
            name="username"
            rules={[{ required: true, message: 'Introduce tu usuario o email' }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="Usuario o email"
              size="large"
              autoComplete="username"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: 'Introduce tu contraseña' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="Contraseña"
              size="large"
              autoComplete="current-password"
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
              Entrar
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
