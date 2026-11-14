import { useMemo, useState } from 'react'
import { Alert, Button, Card, Col, message, Modal, Row, Space, Table, Typography } from 'antd'
import { FileTextOutlined, LinkOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ApunteBanco, bancoApi, MovimientoBanco, PropuestaAsiento } from '../../../api/cierres'
import { apiError } from '../../../utils/errorHandler'
import { eur, fecha, num, usePuedeEditar } from '../comun'

const { Text } = Typography

export default function PendientesBanco({ bancoId, ejercicio }: { bancoId: number; ejercicio: number }) {
  const qc = useQueryClient()
  const puedeEditar = usePuedeEditar()
  const [selBanco, setSelBanco] = useState<number[]>([])
  const [selDiario, setSelDiario] = useState<number[]>([])

  const pend = useQuery({
    queryKey: ['cierres', 'banco', 'pendientes', bancoId, ejercicio],
    queryFn: () => bancoApi.getPendientes(bancoId, ejercicio).then((r) => r.data),
  })

  const sumaBanco = useMemo(
    () => (pend.data?.banco ?? []).filter((m) => selBanco.includes(m.id)).reduce((a, m) => a + m.importe, 0),
    [pend.data, selBanco])
  const sumaDiario = useMemo(
    () => (pend.data?.diario ?? []).filter((m) => selDiario.includes(m.id)).reduce((a, m) => a + m.neto, 0),
    [pend.data, selDiario])
  const dif = Math.abs(sumaBanco - sumaDiario)
  const color = dif <= 0.01 ? '#389e0d' : dif <= 2 ? '#d48806' : '#cf1322'

  const recargar = () => {
    setSelBanco([])
    setSelDiario([])
    qc.invalidateQueries({ queryKey: ['cierres', 'banco'] })
  }

  const confirmarYEnviar = (titulo: string, avisos: string[], enviar: () => Promise<unknown>) =>
    Modal.confirm({
      title: titulo,
      content: avisos.length ? <Alert type="warning" showIcon message={avisos.map((a) => <div key={a}>{a}</div>)} /> : undefined,
      okText: 'Conciliar', cancelText: 'Cancelar',
      onOk: async () => {
        try {
          await enviar()
          message.success('Conciliado')
          recargar()
        } catch (e) {
          message.error(apiError(e))
        }
      },
    })

  const uno = () => {
    const b = pend.data!.banco.find((m) => m.id === selBanco[0])!
    const d = pend.data!.diario.find((m) => m.id === selDiario[0])!
    const avisos = []
    if (Math.abs(b.importe - d.neto) > 0.01) avisos.push(`Los importes no coinciden: banco ${eur(b.importe)} €, diario ${eur(d.neto)} € (diferencia ${eur(Math.abs(b.importe - d.neto))} €).`)
    if (b.fecha_operacion !== d.fecha) avisos.push(`Las fechas no coinciden: banco ${fecha(b.fecha_operacion)}, diario ${fecha(d.fecha)}.`)
    confirmarYEnviar('¿Conciliar 1 movimiento con 1 apunte?', avisos,
      () => bancoApi.manual1a1(bancoId, ejercicio, b.id, d.id))
  }

  const nn = () => {
    const avisos = dif > 2 ? [`Las sumas no coinciden: banco ${eur(sumaBanco)} €, diario ${eur(sumaDiario)} € (diferencia ${eur(dif)} €).`] : []
    confirmarYEnviar(`¿Conciliar ${selBanco.length} movimientos con ${selDiario.length} apuntes?`, avisos,
      () => bancoApi.manualNN(bancoId, ejercicio, selBanco, selDiario))
  }

  const propuesta = async () => {
    try {
      const { data } = await bancoApi.propuesta(bancoId, selBanco)
      Modal.info({
        title: 'Propuesta de asientos', width: 760,
        content: (
          <>
            <Alert type="info" showIcon style={{ marginBottom: 12 }}
              message="Solo es una propuesta para registrar en el ERP: no se crea nada en el diario." />
            {data.map((p: PropuestaAsiento) => (
              <Card key={p.id} size="small" style={{ marginBottom: 8 }}
                title={`${fecha(p.fecha)} · ${p.tipo} · ${eur(p.importe)} €`} extra={<Text type="secondary">{p.concepto}</Text>}>
                <Table size="small" pagination={false} rowKey="cuenta" dataSource={p.lineas} columns={[
                  { title: 'Cuenta', dataIndex: 'cuenta' }, { title: 'Nombre', dataIndex: 'nombre' },
                  { title: 'Debe', dataIndex: 'debe', align: 'right', render: (v: number) => (v ? eur(v) : '') },
                  { title: 'Haber', dataIndex: 'haber', align: 'right', render: (v: number) => (v ? eur(v) : '') },
                ]} />
              </Card>
            ))}
          </>
        ),
      })
    } catch (e) {
      message.error(apiError(e))
    }
  }

  return (
    <div>
      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={recargar}>Actualizar</Button>
          <Text strong style={{ color: selBanco.length || selDiario.length ? color : undefined }}>
            Banco: {selBanco.length} ({eur(sumaBanco)} €) · Diario: {selDiario.length} ({eur(sumaDiario)} €) ·
            Diferencia: {eur(dif)} €
          </Text>
          {puedeEditar && (
            <>
              <Button icon={<LinkOutlined />} disabled={selBanco.length !== 1 || selDiario.length !== 1} onClick={uno}>
                Conciliar 1:1
              </Button>
              <Button type="primary" icon={<LinkOutlined />} disabled={!selBanco.length || !selDiario.length} onClick={nn}>
                Conciliar N:N
              </Button>
              <Button icon={<FileTextOutlined />} disabled={!selBanco.length} onClick={propuesta}>
                Propuesta de asiento (comisiones…)
              </Button>
            </>
          )}
        </Space>
      </Card>
      {pend.error && <Alert type="error" showIcon message={apiError(pend.error)} />}
      <Row gutter={16}>
        <Col xs={24} xl={12}>
          <Card size="small" title={`Banco pendiente (${num(pend.data?.total_banco ?? 0)})`}>
            <Table<MovimientoBanco> size="small" rowKey="id" loading={pend.isLoading} dataSource={pend.data?.banco}
              pagination={{ pageSize: 50 }} scroll={{ x: 600 }}
              rowSelection={{ selectedRowKeys: selBanco, onChange: (k) => setSelBanco(k as number[]), preserveSelectedRowKeys: true }}
              columns={[
                { title: 'Fecha', dataIndex: 'fecha_operacion', width: 95, render: fecha },
                { title: 'Concepto', dataIndex: 'concepto', ellipsis: true },
                { title: 'Importe', dataIndex: 'importe', width: 105, align: 'right', render: eur },
              ]} />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title={`Diario pendiente ${pend.data?.cuenta_572 ?? ''} (${num(pend.data?.total_diario ?? 0)})`}>
            <Table<ApunteBanco> size="small" rowKey="id" loading={pend.isLoading} dataSource={pend.data?.diario}
              pagination={{ pageSize: 50 }} scroll={{ x: 600 }}
              rowSelection={{ selectedRowKeys: selDiario, onChange: (k) => setSelDiario(k as number[]), preserveSelectedRowKeys: true }}
              columns={[
                { title: 'Fecha', dataIndex: 'fecha', width: 95, render: fecha },
                { title: 'Asiento', dataIndex: 'asiento_key', width: 110 },
                { title: 'Concepto', dataIndex: 'concepto', ellipsis: true },
                { title: 'Neto', dataIndex: 'neto', width: 105, align: 'right', render: eur },
              ]} />
          </Card>
        </Col>
      </Row>
      {(pend.data?.total_banco ?? 0) > (pend.data?.banco.length ?? 0) && (
        <Text type="secondary">Se muestran los {num(pend.data!.banco.length)} más recientes.</Text>
      )}
    </div>
  )
}
