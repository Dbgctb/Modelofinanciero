import { useState, useEffect } from 'react'
import {
  Row, Col, Card, Typography, Select, Table, Tag, Tooltip,
  Button, Modal, Form, Input, Statistic, Space, message,
} from 'antd'
import {
  WarningOutlined, ReloadOutlined, DollarOutlined,
  ExclamationCircleOutlined, ThunderboltOutlined, ClockCircleOutlined,
  FallOutlined, AlertOutlined, MinusCircleOutlined, CalendarOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { crossSellingApi } from '../../api/crossSelling'

const { Title, Text } = Typography

const RAMO_COLORS: Record<string, string> = {
  AUTO: 'blue', HOGAR: 'green', SALUD: 'red', VIDA: 'purple',
  DECESOS: 'default', ACCIDENTES: 'orange', RC: 'cyan',
  MULTIRRIESGO: 'geekblue', CIBER: 'magenta', FLOTILLAS: 'volcano', BAJAS: 'gold',
}

const SENAL_CONFIG: Record<string, { color: string; label: string; icon: React.ReactNode }> = {
  ramo_perdido:         { color: 'red',     label: 'Ramo perdido',     icon: <FallOutlined /> },
  prima_bajando:        { color: 'orange',  label: 'Prima baja',       icon: <FallOutlined /> },
  prima_poliza_bajando: { color: 'orange',  label: 'Póliza baja',      icon: <FallOutlined /> },
  vencimiento_proximo:  { color: 'red',     label: 'Vence pronto',     icon: <ClockCircleOutlined /> },
  cartera_reducida:     { color: 'volcano', label: 'Cartera reducida', icon: <MinusCircleOutlined /> },
  sin_renovacion:       { color: 'gold',    label: 'Sin actividad',    icon: <CalendarOutlined /> },
  mono_cartera:         { color: 'geekblue',label: '1 solo ramo',      icon: <AlertOutlined /> },
  inactividad:          { color: 'gold',    label: 'Sin actividad',    icon: <CalendarOutlined /> },
}

const ESTADO_OPTIONS = [
  { value: 'contactado',    label: 'Contactado' },
  { value: 'propuesta',     label: 'Propuesta enviada' },
  { value: 'ganado',        label: '✓ Retenido' },
  { value: 'perdido',       label: 'Perdido' },
  { value: 'no_interesado', label: 'No interesado' },
]

const fmt = (v: number | null | undefined) =>
  v != null ? v.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' €' : '—'

const riskColor = (s: number) => s >= 70 ? '#f5222d' : s >= 40 ? '#faad14' : '#52c41a'
const riskLabel = (s: number) => s >= 70 ? 'URGENTE' : s >= 40 ? 'MEDIO' : 'BAJO'

export default function FugaAlertas() {
  const qc = useQueryClient()
  const [ejercicio, setEjercicio] = useState<number | null>(null)
  const [riskMin, setRiskMin] = useState(0)
  const [modalOpen, setModalOpen] = useState(false)
  const [selected, setSelected] = useState<any>(null)
  const [form] = Form.useForm()

  const { data: ejercicios = [] } = useQuery<number[]>({
    queryKey: ['cs-ejercicios'],
    queryFn: crossSellingApi.getEjercicios,
  })

  useEffect(() => {
    if (ejercicios.length && !ejercicio) setEjercicio(ejercicios[0])
  }, [ejercicios])

  const { data: alertas = [], isLoading } = useQuery({
    queryKey: ['cs-alertas', ejercicio, riskMin],
    queryFn: () => crossSellingApi.getAlertas(ejercicio!, riskMin || undefined),
    enabled: !!ejercicio,
  })

  const recalcularMutation = useMutation({
    mutationFn: () => crossSellingApi.recalcular(ejercicio!),
    onSuccess: (data: any) => {
      message.success(`Recalculado: ${data.oportunidades} oportunidades, ${data.alertas} alertas`)
      qc.invalidateQueries({ queryKey: ['cs-alertas'] })
    },
    onError: () => message.error('Error al recalcular'),
  })

  const accionMutation = useMutation({
    mutationFn: (payload: any) => crossSellingApi.createAccion(payload),
    onSuccess: () => {
      message.success('Acción registrada')
      setModalOpen(false)
      form.resetFields()
      qc.invalidateQueries({ queryKey: ['cs-alertas'] })
    },
    onError: () => message.error('Error al registrar la acción'),
  })

  const handleAccionar = (record: any) => {
    setSelected(record)
    form.resetFields()
    setModalOpen(true)
  }

  const handleSubmitAccion = async () => {
    const values = await form.validateFields()
    accionMutation.mutate({
      tipo: 'retencion',
      alerta_id: selected.id,
      tomador: selected.tomador,
      ...values,
    })
  }

  const urgentes = alertas.filter((a: any) => a.risk_score >= 70).length
  const medias   = alertas.filter((a: any) => a.risk_score >= 40 && a.risk_score < 70).length
  const valorTotal = alertas.reduce((s: number, a: any) => s + (a.liqui_vigente || a.prima_total_activa || 0), 0)

  // ── Fila expandible ────────────────────────────────────────────────────────
  const expandedRowRender = (record: any) => (
    <div style={{ padding: '12px 16px 14px 40px', background: '#fffbe6', borderBottom: '1px solid #ffe58f' }}>
      <Row gutter={24}>
        <Col xs={24} md={9}>
          <Text type="secondary" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Señales detectadas
          </Text>
          <div style={{ marginTop: 6 }}>
            {(record.senales || []).map((s: any, i: number) => {
              const cfg = SENAL_CONFIG[s.tipo] || { color: 'default', label: s.tipo, icon: null }
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 7 }}>
                  <Tag color={cfg.color} icon={cfg.icon} style={{ fontSize: 10, flexShrink: 0, marginTop: 1 }}>
                    {cfg.label}
                  </Tag>
                  <Text style={{ fontSize: 11, color: '#595959', lineHeight: 1.55 }}>{s.desc}</Text>
                </div>
              )
            })}
          </div>
        </Col>

        <Col xs={24} md={6}>
          <Text type="secondary" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Cartera actual
          </Text>
          <div style={{ marginTop: 6, marginBottom: 10, display: 'flex', flexWrap: 'wrap', gap: 3 }}>
            {(record.ramos_actuales || []).map((r: string) => (
              <Tag key={r} color={RAMO_COLORS[r] || 'default'} style={{ fontSize: 11 }}>{r}</Tag>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 11, color: '#8c8c8c' }}>
              Pr.Tot activa
              <Tooltip title="Suma de Pr.Tot en recibos vigentes (valor del campo tal como viene del CSV)">
                <span style={{ marginLeft: 3, cursor: 'help', color: '#bfbfbf', fontSize: 10 }}>ⓘ</span>
              </Tooltip>
            </div>
            <div style={{ fontSize: 14, fontWeight: 600 }}>{fmt(record.prima_total_activa)}</div>
          </div>
          {record.liqui_vigente != null && record.liqui_vigente > 0 && (
            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: 11, color: '#8c8c8c' }}>
                Comisión activa (Liqui)
                <Tooltip title="Suma de Liqui en recibos vigentes — ingresos reales del bróker con este cliente">
                  <span style={{ marginLeft: 3, cursor: 'help', color: '#bfbfbf', fontSize: 10 }}>ⓘ</span>
                </Tooltip>
              </div>
              <div style={{ fontSize: 15, fontWeight: 700, color: '#389e0d' }}>{fmt(record.liqui_vigente)}</div>
            </div>
          )}
          {record.antiguedad_anos > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 11, color: '#8c8c8c' }}>Antigüedad</div>
              <div style={{ fontSize: 13 }}>{record.antiguedad_anos.toFixed(1)} años</div>
            </div>
          )}
        </Col>

        <Col xs={24} md={9}>
          <Text type="secondary" style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Acción recomendada
          </Text>
          <div style={{
            marginTop: 6, padding: '10px 14px',
            background: '#fff3cd', borderRadius: 6,
            borderLeft: '3px solid #faad14',
          }}>
            <Text style={{ fontSize: 12, color: '#595959', lineHeight: 1.6 }}>
              {record.accion_recomendada}
            </Text>
          </div>
        </Col>
      </Row>
    </div>
  )

  // ── Columnas tabla ─────────────────────────────────────────────────────────
  const columns = [
    {
      title: 'Cliente',
      dataIndex: 'tomador',
      key: 'tomador',
      width: 225,
      render: (v: string, record: any) => (
        <div>
          <Text strong style={{ fontSize: 13, display: 'block', lineHeight: 1.3 }}>{v}</Text>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 3, alignItems: 'center' }}>
            {record.tipo_cliente === 'juridico' && (
              <Tag style={{ fontSize: 10, margin: 0, lineHeight: '16px' }} color="geekblue">Empresa</Tag>
            )}
            {record.antiguedad_anos > 0 && (
              <Text type="secondary" style={{ fontSize: 10 }}>{record.antiguedad_anos.toFixed(0)}a</Text>
            )}
            {record.auxiliar && (
              <Text type="secondary" style={{ fontSize: 10 }}>· {record.auxiliar}</Text>
            )}
          </div>
        </div>
      ),
    },
    {
      title: 'Riesgo',
      dataIndex: 'risk_score',
      key: 'risk_score',
      width: 88,
      sorter: (a: any, b: any) => a.risk_score - b.risk_score,
      defaultSortOrder: 'descend' as const,
      render: (v: number) => {
        const color = riskColor(v)
        return (
          <div style={{ textAlign: 'center' }}>
            <div style={{
              width: 44, height: 44, borderRadius: '50%',
              border: `3px solid ${color}`,
              background: `${color}18`,
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Text strong style={{ color, fontSize: 14, lineHeight: 1 }}>{v.toFixed(0)}</Text>
            </div>
            <div style={{ fontSize: 9, color, marginTop: 2, letterSpacing: 0.3, fontWeight: 600 }}>
              {riskLabel(v)}
            </div>
          </div>
        )
      },
    },
    {
      title: 'Señales',
      dataIndex: 'senales',
      key: 'senales',
      width: 225,
      render: (senales: any[]) => (
        <Space size={2} wrap>
          {(senales || []).map((s: any, i: number) => {
            const cfg = SENAL_CONFIG[s.tipo] || { color: 'default', label: s.tipo, icon: null }
            return (
              <Tooltip key={i} title={s.desc}>
                <Tag color={cfg.color} icon={cfg.icon} style={{ fontSize: 10, cursor: 'help', marginBottom: 2 }}>
                  {cfg.label}
                </Tag>
              </Tooltip>
            )
          })}
        </Space>
      ),
    },
    {
      title: 'Comisión activa',
      key: 'valor',
      width: 125,
      align: 'right' as const,
      sorter: (a: any, b: any) => (a.liqui_vigente || a.prima_total_activa || 0) - (b.liqui_vigente || b.prima_total_activa || 0),
      render: (_: any, record: any) => {
        const v = record.liqui_vigente > 0 ? record.liqui_vigente : record.prima_total_activa
        return (
          <Tooltip title="Ingreso real del bróker en pólizas vigentes (campo Liqui del CSV). Es lo que se perdería si el cliente se va.">
            <Text style={{ color: '#722ed1', fontWeight: 700, fontSize: 13 }}>{fmt(v)}</Text>
          </Tooltip>
        )
      },
    },
    {
      title: 'Próx. venc.',
      dataIndex: 'dias_hasta_vencimiento',
      key: 'vence',
      width: 95,
      sorter: (a: any, b: any) => (a.dias_hasta_vencimiento ?? 9999) - (b.dias_hasta_vencimiento ?? 9999),
      render: (dias: number | null) => {
        if (dias == null) return <Text type="secondary" style={{ fontSize: 11 }}>—</Text>
        const color = dias <= 30 ? '#f5222d' : dias <= 90 ? '#faad14' : '#595959'
        return (
          <div style={{ textAlign: 'center' }}>
            <ClockCircleOutlined style={{ color, fontSize: 13 }} />
            <div style={{ fontSize: 12, color, fontWeight: dias <= 90 ? 600 : 400, marginTop: 2 }}>
              {dias > 0 ? `${dias}d` : 'Vencido'}
            </div>
          </div>
        )
      },
    },
    {
      title: '',
      key: 'accionar',
      width: 118,
      render: (_: any, record: any) => (
        <Button
          type="primary"
          danger
          size="small"
          icon={<ThunderboltOutlined />}
          onClick={() => handleAccionar(record)}
        >
          Accionar
        </Button>
      ),
    },
  ]

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <Title level={4} style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
          <WarningOutlined style={{ color: '#f5222d' }} />
          Alertas de Fuga
        </Title>
        <Select
          value={ejercicio}
          onChange={setEjercicio}
          options={ejercicios.map((e: number) => ({ value: e, label: String(e) }))}
          style={{ width: 100 }}
          placeholder="Año"
        />
        <Button
          type="primary"
          danger
          icon={<ReloadOutlined />}
          loading={recalcularMutation.isPending}
          onClick={() => ejercicio && Modal.confirm({
            title: 'Recalcular alertas de fuga',
            content: `Se analizarán los recibos vigentes del ejercicio ${ejercicio} y se regenerarán todas las alertas.`,
            okText: 'Recalcular',
            okButtonProps: { danger: true },
            onOk: () => recalcularMutation.mutate(),
          })}
        >
          Recalcular
        </Button>
      </div>

      {/* KPIs */}
      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        {[
          { title: 'Total alertas',    value: alertas.length, color: '#595959', icon: <WarningOutlined /> },
          { title: 'Urgentes (≥ 70)', value: urgentes,        color: '#f5222d', icon: <ExclamationCircleOutlined /> },
          { title: 'Medias (40-69)',   value: medias,          color: '#faad14', icon: <AlertOutlined /> },
          { title: 'Comisión en riesgo', value: fmt(valorTotal), color: '#722ed1', icon: <DollarOutlined /> },
        ].map((k, i) => (
          <Col key={i} xs={24} sm={12} xl={6}>
            <Card
              size="small"
              style={{ borderRadius: 12, borderLeft: `4px solid ${k.color}`, boxShadow: '0 2px 8px rgba(0,0,0,0.07)' }}
              styles={{ body: { padding: '16px 20px' } }}
            >
              <Statistic
                title={<Text type="secondary" style={{ fontSize: 12 }}>{k.title}</Text>}
                value={k.value}
                prefix={<span style={{ color: k.color }}>{k.icon}</span>}
                valueStyle={{ fontSize: 22, fontWeight: 700, color: '#262626' }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {/* Filtros */}
      <Card
        size="small"
        style={{ marginBottom: 16, borderRadius: 10, background: '#fafafa' }}
        styles={{ body: { padding: '10px 16px' } }}
      >
        <Space size={20} wrap>
          <Space size={6}>
            <Text type="secondary" style={{ fontSize: 12 }}>Riesgo mínimo:</Text>
            <Select
              value={riskMin}
              onChange={setRiskMin}
              options={[
                { value: 0,  label: 'Todos' },
                { value: 30, label: '≥ 30' },
                { value: 40, label: '≥ 40 (Medio)' },
                { value: 70, label: '≥ 70 (Urgente)' },
              ]}
              style={{ width: 155 }}
            />
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            <b>{alertas.length}</b> clientes vigentes con riesgo detectado · despliega cada fila para ver el detalle completo
          </Text>
        </Space>
      </Card>

      {/* Tabla */}
      <Card
        style={{ borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.06)' }}
        styles={{ body: { padding: 0 } }}
      >
        <Table
          rowKey="id"
          columns={columns}
          dataSource={alertas}
          loading={isLoading}
          size="small"
          pagination={{ pageSize: 15, showTotal: (t) => `${t} alertas`, showSizeChanger: false }}
          scroll={{ x: 876 }}
          expandable={{
            expandedRowRender,
            rowExpandable: () => true,
            expandRowByClick: false,
          }}
          rowClassName={(r: any) => r.risk_score >= 70 ? 'cs-row-urgente' : ''}
          style={{ borderRadius: 12, overflow: 'hidden' }}
        />
      </Card>

      {/* Modal */}
      <Modal
        open={modalOpen}
        title={selected ? `Retención — ${selected.tomador}` : ''}
        onOk={handleSubmitAccion}
        onCancel={() => { setModalOpen(false); form.resetFields() }}
        okText="Guardar"
        cancelText="Cancelar"
        confirmLoading={accionMutation.isPending}
        width={480}
        destroyOnClose
      >
        {selected && (
          <div style={{ marginBottom: 16, padding: '10px 14px', background: '#fff1f0', borderRadius: 8, borderLeft: '3px solid #f5222d' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <div style={{
                width: 36, height: 36, borderRadius: '50%',
                border: `2px solid ${riskColor(selected.risk_score)}`,
                background: `${riskColor(selected.risk_score)}18`,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <Text strong style={{ color: riskColor(selected.risk_score), fontSize: 13 }}>
                  {selected.risk_score?.toFixed(0)}
                </Text>
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600 }}>
                  Valor protegido: {fmt(selected.valor_protegido)}
                </div>
                <div style={{ fontSize: 11, color: '#8c8c8c' }}>{selected.accion_recomendada}</div>
              </div>
            </div>
            <Space size={4} wrap>
              {(selected.senales || []).map((s: any, i: number) => {
                const cfg = SENAL_CONFIG[s.tipo] || { color: 'default', label: s.tipo, icon: null }
                return (
                  <Tooltip key={i} title={s.desc}>
                    <Tag color={cfg.color} icon={cfg.icon} style={{ fontSize: 10 }}>{cfg.label}</Tag>
                  </Tooltip>
                )
              })}
            </Space>
          </div>
        )}
        <Form form={form} layout="vertical">
          <Form.Item name="estado" label="Estado" rules={[{ required: true }]} initialValue="contactado">
            <Select options={ESTADO_OPTIONS} />
          </Form.Item>
          <Form.Item name="notas" label="Notas">
            <Input.TextArea rows={3} placeholder="Resultado del contacto, razón de riesgo, próximos pasos..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
