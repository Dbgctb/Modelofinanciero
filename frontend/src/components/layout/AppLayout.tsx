import { useState } from 'react'
import { Layout, Menu, Avatar, Dropdown, Badge, Typography, theme, Modal, Form, Input, Descriptions, Tag, message } from 'antd'
import {
  DashboardOutlined, BarChartOutlined, DollarOutlined,
  TeamOutlined, LogoutOutlined, UserOutlined, KeyOutlined,
  BellOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  SettingOutlined, DatabaseOutlined, DeleteOutlined, RiseOutlined,
  SafetyCertificateOutlined, BulbOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'
import { authApi } from '../../api/auth'
import { apiError } from '../../utils/errorHandler'

const { Header, Sider, Content } = Layout
const { Text } = Typography

const MENU_ITEMS = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: '/panel-control', icon: <SafetyCertificateOutlined />, label: 'Panel de control' },
  {
    key: 'presupuestacion',
    icon: <BarChartOutlined />,
    label: 'Presupuestación',
    children: [
      { key: '/presupuestacion/carga', label: 'Carga de datos' },
      { key: '/presupuestacion/ingresos', label: 'Presupuesto ingresos' },
      { key: '/presupuestacion/gastos', label: 'Presupuesto gastos' },
      { key: '/presupuestacion/tesoreria', label: 'Tesorería presupuestada' },
      { key: '/presupuestacion/real', label: 'Seguimiento real' },
      { key: '/presupuestacion/kpis', label: 'KPIs' },
      { key: '/presupuestacion/cuenta-resultados', label: 'Cuenta de Resultados' },
    ],
  },
  {
    key: 'analitico',
    icon: <DollarOutlined />,
    label: 'Modelo Analítico',
    children: [
      { key: '/analitico/dashboards', label: 'Dashboards de rentabilidad' },
      { key: '/analitico/configuracion', label: 'Configuración' },
      { key: '/analitico/ajustes-coste', label: 'Ajustes de coste' },
    ],
  },
  { key: '/analitico/valoracion', icon: <RiseOutlined />, label: 'Valoración correduría' },
  {
    key: 'cross-selling',
    icon: <BulbOutlined />,
    label: 'Cross-selling / Fuga',
    children: [
      { key: '/cross-selling/oportunidades',   label: 'Oportunidades' },
      { key: '/cross-selling/alertas',         label: 'Alertas de fuga' },
      { key: '/cross-selling/efectividad',     label: 'Efectividad' },
      { key: '/cross-selling/configuracion',   label: 'Configuración' },
    ],
  },
  {
    key: 'admin',
    icon: <SettingOutlined />,
    label: 'Administración',
    children: [
      { key: '/admin/mapeo-cuentas', icon: <DatabaseOutlined />, label: 'Mapeo de cuentas' },
      { key: '/admin/tasas-mercado', icon: <BarChartOutlined />, label: 'Tasas de mercado' },
      { key: '/admin/auxiliares', icon: <TeamOutlined />, label: 'Auxiliares' },
      { key: '/usuarios', icon: <TeamOutlined />, label: 'Usuarios' },
      { key: '/admin/reset-datos', icon: <DeleteOutlined />, label: 'Limpiar datos' },
    ],
  },
]

const ROLE_LABELS: Record<string, { label: string; color: string }> = {
  admin:  { label: 'Administrador', color: 'red' },
  gestor: { label: 'Gestor',        color: 'blue' },
  lector: { label: 'Lector',        color: 'default' },
}

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [showPerfil, setShowPerfil] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [pwLoading, setPwLoading] = useState(false)
  const [pwForm] = Form.useForm()
  const navigate = useNavigate()
  const location = useLocation()
  const { user, refreshToken, logout } = useAuthStore()
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken()

  const handleLogout = async () => {
    if (refreshToken) {
      try { await authApi.logout(refreshToken) } catch {}
    }
    logout()
    navigate('/login')
  }

  const handleChangePassword = async () => {
    try {
      const values = await pwForm.validateFields()
      if (values.new_password !== values.confirm_password) {
        pwForm.setFields([{ name: 'confirm_password', errors: ['Las contraseñas no coinciden'] }])
        return
      }
      setPwLoading(true)
      await authApi.changePassword(values.current_password, values.new_password)
      message.success('Contraseña actualizada. Inicia sesión de nuevo.')
      setShowPassword(false)
      pwForm.resetFields()
      await handleLogout()
    } catch (e) {
      message.error(apiError(e, 'Error al cambiar la contraseña'))
    } finally {
      setPwLoading(false)
    }
  }

  const userMenu = [
    { key: 'profile',  icon: <UserOutlined />, label: 'Mi perfil',          onClick: () => setShowPerfil(true) },
    { key: 'password', icon: <KeyOutlined />,  label: 'Cambiar contraseña', onClick: () => { pwForm.resetFields(); setShowPassword(true) } },
    { type: 'divider' as const },
    { key: 'logout',   icon: <LogoutOutlined />, label: 'Cerrar sesión', danger: true, onClick: handleLogout },
  ]

  const selectedKeys = [location.pathname]
  const openKeys = MENU_ITEMS
    .filter((i: any) => i.children?.some((c: any) => c.key === location.pathname))
    .map((i: any) => i.key)

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={240}
        style={{ boxShadow: '2px 0 8px rgba(0,0,0,0.12)' }}
        theme="dark"
      >
        <div style={{
          height: 64, display: 'flex', alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          padding: collapsed ? 0 : '0 20px',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
        }}>
          <img
            src="/logo.png"
            alt="Logo"
            style={{ height: collapsed ? 32 : 36, objectFit: 'contain', flexShrink: 0 }}
          />
          {!collapsed && (
            <Text strong style={{ color: '#fff', marginLeft: 10, fontSize: 14, whiteSpace: 'nowrap' }}>
              Correduría
            </Text>
          )}
        </div>

        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={selectedKeys}
          defaultOpenKeys={openKeys}
          items={MENU_ITEMS}
          onClick={({ key }) => navigate(key)}
          style={{ border: 'none', marginTop: 8 }}
        />
      </Sider>

      <Layout>
        <Header style={{
          padding: '0 24px', background: colorBgContainer,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          boxShadow: '0 1px 4px rgba(0,0,0,0.12)', zIndex: 10,
        }}>
          <div
            onClick={() => setCollapsed(!collapsed)}
            style={{ fontSize: 18, cursor: 'pointer', color: '#666' }}
          >
            {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Badge count={0} showZero={false}>
              <BellOutlined style={{ fontSize: 18, color: '#666', cursor: 'pointer' }} />
            </Badge>
            <Dropdown menu={{ items: userMenu }} placement="bottomRight">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <Avatar style={{ backgroundColor: '#1890ff' }}>
                  {user?.full_name?.[0]?.toUpperCase()}
                </Avatar>
                {!collapsed && (
                  <span style={{ fontSize: 14, color: '#333' }}>{user?.full_name}</span>
                )}
              </div>
            </Dropdown>
          </div>
        </Header>

        <Content style={{ margin: 24, padding: 24, background: colorBgContainer, borderRadius: borderRadiusLG, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>

      {/* Modal: Mi perfil */}
      <Modal
        title="Mi perfil"
        open={showPerfil}
        onCancel={() => setShowPerfil(false)}
        footer={null}
        width={480}
      >
        <Descriptions column={1} bordered size="small" style={{ marginTop: 16 }}>
          <Descriptions.Item label="Nombre completo">{user?.full_name}</Descriptions.Item>
          <Descriptions.Item label="Usuario">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="Email">{user?.email}</Descriptions.Item>
          <Descriptions.Item label="Rol">
            {user?.role && (
              <Tag color={ROLE_LABELS[user.role]?.color}>
                {ROLE_LABELS[user.role]?.label ?? user.role}
              </Tag>
            )}
          </Descriptions.Item>
        </Descriptions>
      </Modal>

      {/* Modal: Cambiar contraseña */}
      <Modal
        title="Cambiar contraseña"
        open={showPassword}
        onOk={handleChangePassword}
        onCancel={() => setShowPassword(false)}
        okText="Guardar"
        cancelText="Cancelar"
        confirmLoading={pwLoading}
        width={440}
        destroyOnClose
      >
        <Form form={pwForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="current_password"
            label="Contraseña actual"
            rules={[{ required: true, message: 'Introduce tu contraseña actual' }]}
          >
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="Nueva contraseña"
            rules={[
              { required: true, message: 'Introduce la nueva contraseña' },
              { min: 10, message: 'Mínimo 10 caracteres' },
            ]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="confirm_password"
            label="Confirmar nueva contraseña"
            rules={[{ required: true, message: 'Confirma la nueva contraseña' }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </Layout>
  )
}
