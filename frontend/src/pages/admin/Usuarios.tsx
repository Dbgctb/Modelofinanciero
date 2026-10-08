import { useState } from 'react'
import {
  Card, Table, Button, Tag, Space, Typography, Modal, Form,
  Input, Select, Switch, Tooltip, message, Tabs,
  Alert, Row, Col, Statistic, Descriptions,
} from 'antd'
import {
  PlusOutlined, EditOutlined, KeyOutlined, UserOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi, type AppUser, type UserRole } from '../../api/users'
import { useAuthStore } from '../../store/authStore'
import { apiError } from '../../utils/errorHandler'

const { Title, Text } = Typography
const { Option } = Select
const { Password } = Input

const ROL_CONFIG: Record<UserRole, { label: string; color: string }> = {
  admin:  { label: 'Administrador', color: 'red' },
  gestor: { label: 'Gestor',        color: 'orange' },
  lector: { label: 'Lector',        color: 'blue' },
}

const ACCION_LABELS: Record<string, string> = {
  LOGIN_SUCCESS:    'Inicio de sesión',
  LOGIN_FAILED:     'Login fallido',
  LOGOUT:           'Cierre de sesión',
  USER_CREATED:     'Usuario creado',
  USER_UPDATED:     'Usuario modificado',
  PASSWORD_RESET:   'Contraseña reseteada',
  PASSWORD_CHANGED: 'Contraseña cambiada',
}

function fmtDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('es-ES', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function Usuarios() {
  const qc = useQueryClient()
  const { user: me } = useAuthStore()

  const [modalCrear, setModalCrear]     = useState(false)
  const [modalEditar, setModalEditar]   = useState(false)
  const [modalReset, setModalReset]     = useState(false)
  const [usuarioActivo, setUsuarioActivo] = useState<AppUser | null>(null)
  const [formCrear] = Form.useForm()
  const [formEditar] = Form.useForm()
  const [formReset] = Form.useForm()
  const [auditPage, setAuditPage] = useState(1)
  const PAGE = 20

  // ── Queries ───────────────────────────────────────────────────────────────

  const { data: usuarios = [], isLoading } = useQuery({
    queryKey: ['usuarios'],
    queryFn: () => usersApi.listar().then(r => r.data),
  })

  const { data: auditData } = useQuery({
    queryKey: ['audit-log', auditPage],
    queryFn: () => usersApi.auditLog(PAGE, (auditPage - 1) * PAGE).then(r => r.data),
  })

  // ── Mutations ─────────────────────────────────────────────────────────────

  const crear = useMutation({
    mutationFn: (data: any) => usersApi.crear(data),
    onSuccess: (res) => {
      message.success(`Usuario '${res.data.username}' creado. Debe cambiar su contraseña en el primer acceso.`)
      qc.invalidateQueries({ queryKey: ['usuarios'] })
      setModalCrear(false)
      formCrear.resetFields()
    },
    onError: (e) => message.error(apiError(e, 'Error al crear el usuario')),
  })

  const actualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => usersApi.actualizar(id, data),
    onSuccess: () => {
      message.success('Usuario actualizado')
      qc.invalidateQueries({ queryKey: ['usuarios'] })
      setModalEditar(false)
    },
    onError: (e) => message.error(apiError(e, 'Error al actualizar el usuario')),
  })

  const toggleActivo = useMutation({
    mutationFn: ({ user, activo }: { user: AppUser; activo: boolean }) =>
      usersApi.actualizar(user.id, { is_active: activo }),
    onSuccess: (_, vars) => {
      message.success(vars.activo ? 'Usuario activado' : 'Usuario desactivado')
      qc.invalidateQueries({ queryKey: ['usuarios'] })
    },
    onError: (e) => message.error(apiError(e, 'No se pudo cambiar el estado')),
  })

  const resetPass = useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) =>
      usersApi.resetPassword(id, password),
    onSuccess: () => {
      message.success('Contraseña reseteada. El usuario deberá cambiarla en su próximo acceso.')
      setModalReset(false)
      formReset.resetFields()
    },
    onError: (e) => message.error(apiError(e, 'Error al resetear la contraseña')),
  })

  // ── Handlers ──────────────────────────────────────────────────────────────

  const abrirEditar = (u: AppUser) => {
    setUsuarioActivo(u)
    formEditar.setFieldsValue({ full_name: u.full_name, role: u.role })
    setModalEditar(true)
  }

  const abrirReset = (u: AppUser) => {
    setUsuarioActivo(u)
    formReset.resetFields()
    setModalReset(true)
  }

  // ── Stats ─────────────────────────────────────────────────────────────────

  const totalActivos   = usuarios.filter(u => u.is_active).length
  const totalInactivos = usuarios.filter(u => !u.is_active).length
  const totalAdmins    = usuarios.filter(u => u.role === 'admin').length

  // ── Columnas tabla ────────────────────────────────────────────────────────

  const columnas = [
    {
      title: 'Usuario',
      dataIndex: 'username',
      render: (v: string, row: AppUser) => (
        <Space>
          <UserOutlined style={{ color: '#999' }} />
          <div>
            <div style={{ fontWeight: 500 }}>{row.full_name}</div>
            <Text type="secondary" style={{ fontSize: 12 }}>@{v}</Text>
          </div>
        </Space>
      ),
    },
    {
      title: 'Email',
      dataIndex: 'email',
      ellipsis: true,
    },
    {
      title: 'Rol',
      dataIndex: 'role',
      width: 150,
      render: (v: UserRole) => (
        <Tag color={ROL_CONFIG[v]?.color}>{ROL_CONFIG[v]?.label}</Tag>
      ),
    },
    {
      title: 'Último acceso',
      dataIndex: 'last_login',
      width: 160,
      render: (v: string | null) => (
        <Text type="secondary" style={{ fontSize: 12 }}>{fmtDate(v)}</Text>
      ),
    },
    {
      title: 'Alta',
      dataIndex: 'created_at',
      width: 130,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {new Date(v).toLocaleDateString('es-ES')}
        </Text>
      ),
    },
    {
      title: 'Activo',
      dataIndex: 'is_active',
      width: 80,
      render: (v: boolean, row: AppUser) => (
        <Tooltip title={row.id === me?.id ? 'No puedes desactivarte a ti mismo' : ''}>
          <Switch
            size="small"
            checked={v}
            disabled={row.id === me?.id}
            onChange={(checked) => toggleActivo.mutate({ user: row, activo: checked })}
          />
        </Tooltip>
      ),
    },
    {
      title: '',
      width: 100,
      render: (_: any, row: AppUser) => (
        <Space>
          <Tooltip title="Editar">
            <Button size="small" icon={<EditOutlined />} onClick={() => abrirEditar(row)} />
          </Tooltip>
          <Tooltip title="Resetear contraseña">
            <Button size="small" icon={<KeyOutlined />} onClick={() => abrirReset(row)} />
          </Tooltip>
        </Space>
      ),
    },
  ]

  // ── Columnas audit log ────────────────────────────────────────────────────

  const colsAudit = [
    {
      title: 'Fecha',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => <Text style={{ fontSize: 12 }}>{fmtDate(v)}</Text>,
    },
    {
      title: 'Usuario',
      dataIndex: 'username',
      width: 130,
      render: (v: string) => v ? <Text code style={{ fontSize: 12 }}>@{v}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Acción',
      dataIndex: 'action',
      width: 180,
      render: (v: string) => {
        const label = ACCION_LABELS[v] ?? v
        const color = v.includes('FAIL') || v.includes('BLOCK') ? 'error'
          : v.includes('LOGIN') ? 'success'
          : 'default'
        return <Tag color={color} style={{ fontSize: 11 }}>{label}</Tag>
      },
    },
    {
      title: 'Detalle',
      dataIndex: 'detail',
      ellipsis: true,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    {
      title: 'IP',
      dataIndex: 'ip_address',
      width: 130,
      render: (v: string) => <Text type="secondary" style={{ fontSize: 12 }}>{v || '—'}</Text>,
    },
  ]

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Gestión de usuarios</Title>
          <Text type="secondary">Administra los accesos y permisos de la aplicación.</Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalCrear(true)}>
          Nuevo usuario
        </Button>
      </div>

      {/* Estadísticas */}
      <Row gutter={16}>
        <Col span={6}>
          <Card size="small" style={{ borderTop: '3px solid #52c41a' }}>
            <Statistic title="Usuarios activos" value={totalActivos} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ borderTop: '3px solid #d9d9d9' }}>
            <Statistic title="Usuarios inactivos" value={totalInactivos} valueStyle={{ color: '#bfbfbf' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ borderTop: '3px solid #ff4d4f' }}>
            <Statistic title="Administradores" value={totalAdmins} valueStyle={{ color: '#ff4d4f' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic title="Total usuarios" value={usuarios.length} />
          </Card>
        </Col>
      </Row>

      <Tabs
        items={[
          {
            key: 'usuarios',
            label: 'Usuarios',
            icon: <UserOutlined />,
            children: (
              <Card>
                <Table
                  dataSource={usuarios}
                  columns={columnas}
                  rowKey="id"
                  loading={isLoading}
                  size="small"
                  pagination={{ pageSize: 15, showTotal: (t) => `${t} usuarios` }}
                  rowClassName={(row) => !row.is_active ? 'ant-table-row-disabled' : ''}
                />
              </Card>
            ),
          },
          {
            key: 'audit',
            label: (
              <span>
                <HistoryOutlined /> Registro de actividad
              </span>
            ),
            children: (
              <Card>
                <Table
                  dataSource={auditData?.items || []}
                  columns={colsAudit}
                  rowKey="id"
                  size="small"
                  pagination={{
                    current: auditPage,
                    pageSize: PAGE,
                    total: auditData?.total || 0,
                    onChange: setAuditPage,
                    showTotal: (t) => `${t} registros`,
                  }}
                />
              </Card>
            ),
          },
        ]}
      />

      {/* Modal crear usuario */}
      <Modal
        title="Nuevo usuario"
        open={modalCrear}
        onOk={() => formCrear.validateFields().then(v => crear.mutate(v))}
        onCancel={() => { setModalCrear(false); formCrear.resetFields() }}
        confirmLoading={crear.isPending}
        okText="Crear usuario"
        cancelText="Cancelar"
        width={520}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="El usuario recibirá una contraseña temporal y deberá cambiarla en su primer acceso."
        />
        <Form form={formCrear} layout="vertical">
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="full_name" label="Nombre completo" rules={[{ required: true, message: 'Obligatorio' }]}>
                <Input placeholder="Ana García López" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="username"
                label="Usuario"
                rules={[{ required: true, message: 'Obligatorio' }]}
              >
                <Input placeholder="agarcia" prefix="@" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            name="email"
            label="Email"
            rules={[{ required: true, type: 'email', message: 'Email válido requerido' }]}
          >
            <Input placeholder="agarcia@empresa.com" />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="role" label="Rol" initialValue="lector" rules={[{ required: true }]}>
                <Select>
                  <Option value="admin">
                    <Tag color="red">Administrador</Tag>
                  </Option>
                  <Option value="gestor">
                    <Tag color="orange">Gestor</Tag>
                  </Option>
                  <Option value="lector">
                    <Tag color="blue">Lector</Tag>
                  </Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="password"
                label="Contraseña temporal"
                rules={[{ required: true, message: 'Obligatorio' }]}
              >
                <Password placeholder="Mínimo 10 caracteres" />
              </Form.Item>
            </Col>
          </Row>
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 4 }}
            message="La contraseña debe tener ≥10 caracteres, mayúscula, minúscula, número y carácter especial (@$!%*?&._-)"
          />
        </Form>
      </Modal>

      {/* Modal editar usuario */}
      <Modal
        title={`Editar usuario — @${usuarioActivo?.username}`}
        open={modalEditar}
        onOk={() => formEditar.validateFields().then(v => actualizar.mutate({ id: usuarioActivo!.id, data: v }))}
        onCancel={() => setModalEditar(false)}
        confirmLoading={actualizar.isPending}
        okText="Guardar"
        cancelText="Cancelar"
        width={440}
      >
        <Form form={formEditar} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item name="full_name" label="Nombre completo" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="role" label="Rol" rules={[{ required: true }]}>
            <Select>
              <Option value="admin"><Tag color="red">Administrador</Tag></Option>
              <Option value="gestor"><Tag color="orange">Gestor</Tag></Option>
              <Option value="lector"><Tag color="blue">Lector</Tag></Option>
            </Select>
          </Form.Item>
        </Form>
        {usuarioActivo && (
          <Descriptions size="small" column={1} style={{ marginTop: 8 }}>
            <Descriptions.Item label="Email">{usuarioActivo.email}</Descriptions.Item>
            <Descriptions.Item label="Último acceso">{fmtDate(usuarioActivo.last_login)}</Descriptions.Item>
            <Descriptions.Item label="Alta">{fmtDate(usuarioActivo.created_at)}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>

      {/* Modal reset contraseña */}
      <Modal
        title={
          <Space>
            <KeyOutlined />
            <span>Resetear contraseña — @{usuarioActivo?.username}</span>
          </Space>
        }
        open={modalReset}
        onOk={() =>
          formReset.validateFields().then(v =>
            resetPass.mutate({ id: usuarioActivo!.id, password: v.new_password })
          )
        }
        onCancel={() => { setModalReset(false); formReset.resetFields() }}
        confirmLoading={resetPass.isPending}
        okText="Resetear contraseña"
        okButtonProps={{ danger: true }}
        cancelText="Cancelar"
        width={460}
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="El usuario deberá cambiar esta contraseña en su próximo acceso."
        />
        <Form form={formReset} layout="vertical">
          <Form.Item
            name="new_password"
            label="Nueva contraseña temporal"
            rules={[{ required: true, message: 'Obligatorio' }]}
          >
            <Password placeholder="Mínimo 10 caracteres" />
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
            <Password placeholder="Repite la contraseña" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  )
}
