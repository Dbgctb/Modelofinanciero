import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Row, Col, Upload, Button, Select, Space, Typography,
  Table, Tag, Alert, Statistic, Modal, Input, message, Tabs, Badge,
  Progress, Divider,
} from 'antd'
import {
  UploadOutlined, CheckCircleOutlined, WarningOutlined,
  InboxOutlined, LoadingOutlined, RiseOutlined, FallOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cargaApi } from '../../api/carga'
import { apiError } from '../../utils/errorHandler'

const { Title, Text } = Typography
const { Dragger } = Upload
const { Option } = Select

const EJERCICIOS = [2023, 2024, 2025, 2026]

const LABEL_TIPO: Record<string, string> = {
  cuenta_sin_mapear: 'Cuenta sin mapear',
  compania_no_identificada: 'Compañía no identificada',
  recibo_no_extraido: 'Recibo no extraíble',
  recibo_no_encontrado: 'Recibo no encontrado',
  recibo_sin_ramo: 'Recibo sin ramo',
  recibo_sin_cartera: 'Sin cartera/nueva producción',
  gasto_sin_familia: 'Gasto sin familia',
  periodo_incorrecto: 'Periodo incorrecto',
  posible_duplicado: 'Posible duplicado',
}

function TagEstado({ estado }: { estado: string }) {
  if (estado === 'validado') return <Tag icon={<CheckCircleOutlined />} color="success">Validado</Tag>
  if (estado === 'con_incidencias') return <Tag icon={<WarningOutlined />} color="warning">Con incidencias</Tag>
  if (estado === 'cerrado') return <Tag icon={<CheckCircleOutlined />} color="blue">Cerrado</Tag>
  return <Tag color="default">{estado}</Tag>
}

function fmt(n: number) {
  return new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n)
}

interface UploadResult {
  carga_id: string
  total_registros: number
  registros_correctos: number
  registros_con_incidencia: number
  importe_debe_total: number
  importe_haber_total: number
  tiempo_segundos: number
}

export default function CargaDatos() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [ejercicioRecibos, setEjercicioRecibos] = useState<number>(2025)
  const [ejercicioDiario, setEjercicioDiario] = useState<number>(2025)
  const [ejercicioHistorico, setEjercicioHistorico] = useState<number>(2024)
  const [fileHistorico, setFileHistorico] = useState<File | null>(null)
  const [tipoCarga, setTipoCarga] = useState<string>('base_presupuestaria')
  const [fileRecibos, setFileRecibos] = useState<File | null>(null)
  const [fileDiario, setFileDiario] = useState<File | null>(null)
  const [cargaSeleccionada, setCargaSeleccionada] = useState<string | null>(null)
  const [modalResolverVisible, setModalResolverVisible] = useState(false)
  const [incidenciaActiva, setIncidenciaActiva] = useState<any>(null)
  const [resolucion, setResolucion] = useState('')
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const startTimeRef = useRef<number | null>(null)
  const timerRef = useRef<number | null>(null)
  const [uploadResultRecibos, setUploadResultRecibos] = useState<{ insertados: number; actualizados: number; tiempo_segundos: number } | null>(null)
  const [elapsedRecibos, setElapsedRecibos] = useState(0)
  const startTimeRecibosRef = useRef<number | null>(null)
  const timerRecibosRef = useRef<number | null>(null)
  const [uploadResultHistorico, setUploadResultHistorico] = useState<UploadResult | null>(null)
  const [elapsedHistorico, setElapsedHistorico] = useState(0)
  const startTimeHistoricoRef = useRef<number | null>(null)
  const timerHistoricoRef = useRef<number | null>(null)
  const [activeTabKey, setActiveTabKey] = useState('cargar')

  const { data: historial, isLoading: cargandoHistorial } = useQuery({
    queryKey: ['historial-cargas'],
    queryFn: () => cargaApi.historial().then(r => r.data),
  })

  const { data: historico = [], isLoading: cargandoHistorico } = useQuery({
    queryKey: ['historico-estadistico'],
    queryFn: () => cargaApi.listarHistorico().then(r => r.data),
  })

  const { data: resumen } = useQuery({
    queryKey: ['resumen-carga', cargaSeleccionada],
    queryFn: () => cargaApi.resumen(cargaSeleccionada!).then(r => r.data),
    enabled: !!cargaSeleccionada,
  })

  const { data: incidencias } = useQuery({
    queryKey: ['incidencias', cargaSeleccionada],
    queryFn: () => cargaApi.incidencias(cargaSeleccionada!).then(r => r.data),
    enabled: !!cargaSeleccionada,
  })

  const subirRecibos = useMutation({
    mutationFn: () => cargaApi.subirRecibos(fileRecibos!, ejercicioRecibos),
    onSuccess: (res) => {
      const tiempoSegundos = startTimeRecibosRef.current
        ? Math.round((Date.now() - startTimeRecibosRef.current) / 1000)
        : 0
      setUploadResultRecibos({ ...res.data, tiempo_segundos: tiempoSegundos })
      qc.invalidateQueries({ queryKey: ['historial-cargas'] })
      setFileRecibos(null)
    },
    onError: (e) => message.error(apiError(e, 'Error al cargar recibos')),
  })

  const subirDiario = useMutation({
    mutationFn: () => cargaApi.subirDiario(fileDiario!, ejercicioDiario, tipoCarga),
    onSuccess: (res) => {
      const tiempoSegundos = startTimeRef.current
        ? Math.round((Date.now() - startTimeRef.current) / 1000)
        : 0
      setUploadResult({ ...res.data, tiempo_segundos: tiempoSegundos })
      qc.invalidateQueries({ queryKey: ['historial-cargas'] })
      setCargaSeleccionada(res.data.carga_id)
      setFileDiario(null)
    },
    onError: (e) => message.error(apiError(e, 'Error al procesar el diario')),
  })

  // Timer diario
  useEffect(() => {
    if (subirDiario.isPending) {
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
  }, [subirDiario.isPending])

  // Timer recibos
  useEffect(() => {
    if (subirRecibos.isPending) {
      setElapsedRecibos(0)
      startTimeRecibosRef.current = Date.now()
      timerRecibosRef.current = window.setInterval(() => {
        setElapsedRecibos(Math.floor((Date.now() - startTimeRecibosRef.current!) / 1000))
      }, 500)
    } else {
      if (timerRecibosRef.current) {
        clearInterval(timerRecibosRef.current)
        timerRecibosRef.current = null
      }
    }
    return () => {
      if (timerRecibosRef.current) clearInterval(timerRecibosRef.current)
    }
  }, [subirRecibos.isPending])

  const subirHistorico = useMutation({
    mutationFn: () => cargaApi.subirDiario(fileHistorico!, ejercicioHistorico, 'historico_estadistico'),
    onSuccess: (res) => {
      const tiempo_segundos = startTimeHistoricoRef.current
        ? Math.round((Date.now() - startTimeHistoricoRef.current) / 1000)
        : 0
      setUploadResultHistorico({ ...res.data, tiempo_segundos })
      qc.invalidateQueries({ queryKey: ['historico-estadistico'] })
      setFileHistorico(null)
    },
    onError: (e) => message.error(apiError(e, 'Error al cargar el histórico')),
  })

  const eliminarHistorico = useMutation({
    mutationFn: (id: string) => cargaApi.eliminarHistorico(id),
    onSuccess: (_, deletedId) => {
      message.success('Ejercicio histórico eliminado')
      qc.setQueryData(['historico-estadistico'], (old: any[]) =>
        (old || []).filter((item: any) => item.id !== deletedId)
      )
      qc.invalidateQueries({ queryKey: ['historico-estadistico'] })
    },
    onError: (e) => message.error(apiError(e, 'Error al eliminar el histórico')),
  })

  // Timer histórico
  useEffect(() => {
    if (subirHistorico.isPending) {
      setElapsedHistorico(0)
      startTimeHistoricoRef.current = Date.now()
      timerHistoricoRef.current = window.setInterval(() => {
        setElapsedHistorico(Math.floor((Date.now() - startTimeHistoricoRef.current!) / 1000))
      }, 500)
    } else {
      if (timerHistoricoRef.current) {
        clearInterval(timerHistoricoRef.current)
        timerHistoricoRef.current = null
      }
    }
    return () => {
      if (timerHistoricoRef.current) clearInterval(timerHistoricoRef.current)
    }
  }, [subirHistorico.isPending])

  const resolverInc = useMutation({
    mutationFn: () => cargaApi.resolverIncidencia(cargaSeleccionada!, incidenciaActiva.id, resolucion),
    onSuccess: () => {
      message.success('Incidencia resuelta')
      qc.invalidateQueries({ queryKey: ['incidencias', cargaSeleccionada] })
      qc.invalidateQueries({ queryKey: ['resumen-carga', cargaSeleccionada] })
      setModalResolverVisible(false)
      setResolucion('')
    },
  })

  const TIPO_CARGA_LABEL: Record<string, string> = {
    base_presupuestaria: 'Base presup.',
    mensual_real: 'Real mensual',
    recibos: 'Recibos',
    historico_estadistico: 'Histórico',
    HISTORICO_ESTADISTICO: 'Histórico',
  }

  const colsHistorial = [
    { title: 'Ejercicio', dataIndex: 'ejercicio', width: 80 },
    { title: 'Tipo', dataIndex: 'tipo_carga', width: 110, render: (v: string) => TIPO_CARGA_LABEL[v] ?? v },
    { title: 'Fichero', dataIndex: 'nombre_fichero', ellipsis: true },
    { title: 'Registros', dataIndex: 'total_registros', width: 100 },
    {
      title: 'Incidencias',
      dataIndex: 'registros_con_incidencia',
      width: 110,
      render: (v: number) => <Tag color={v > 0 ? 'warning' : 'success'}>{v}</Tag>,
    },
    { title: 'Estado', dataIndex: 'estado', render: (v: string) => <TagEstado estado={v} /> },
    {
      title: '',
      render: (_: any, row: any) => (
        <Button
          size="small"
          onClick={() => {
            if (row.tipo_carga === 'recibos') {
              navigate(`/presupuestacion/carga/recibos/${row.id}`)
            } else {
              navigate(`/presupuestacion/carga/diario/${row.id}`)
            }
          }}
        >
          Ver detalle
        </Button>
      ),
    },
  ]

  const colsIncidencias = [
    {
      title: 'Tipo',
      dataIndex: 'tipo',
      render: (v: string) => LABEL_TIPO[v] || v,
    },
    {
      title: 'Crítica',
      dataIndex: 'es_critica',
      width: 90,
      render: (v: string) => (
        <Tag color={v === 'si' ? 'error' : 'warning'}>{v === 'si' ? 'Crítica' : 'Menor'}</Tag>
      ),
    },
    { title: 'Descripción', dataIndex: 'descripcion', ellipsis: true },
    {
      title: 'Cuenta',
      render: (_: any, row: any) => row.apunte?.numero_cuenta || '—',
      width: 120,
    },
    {
      title: 'Estado',
      dataIndex: 'estado',
      width: 110,
      render: (v: string) => (
        v === 'resuelta'
          ? <Tag color="success">Resuelta</Tag>
          : v === 'excluida'
            ? <Tag color="default">Excluida</Tag>
            : <Tag color="warning">Pendiente</Tag>
      ),
    },
    {
      title: '',
      width: 100,
      render: (_: any, row: any) => row.estado === 'pendiente' ? (
        <Button
          size="small"
          type="primary"
          ghost
          onClick={() => { setIncidenciaActiva(row); setModalResolverVisible(true) }}
        >
          Resolver
        </Button>
      ) : null,
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Title level={4} style={{ margin: 0 }}>Carga de datos contables</Title>

      <Tabs
        activeKey={activeTabKey}
        onChange={setActiveTabKey}
        items={[
          {
            key: 'cargar',
            label: 'Cargar ficheros',
            children: (
              <Row gutter={[24, 24]}>
                {/* Recibos */}
                <Col xs={24} lg={12}>
                  <Card title="1. Tabla de recibos (CSV)" extra={<Tag color="blue">Cargar primero</Tag>}>
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                      <div>
                        <Text type="secondary">Ejercicio</Text>
                        <Select value={ejercicioRecibos} onChange={setEjercicioRecibos} style={{ width: '100%', marginTop: 4 }}>
                          {EJERCICIOS.map(e => <Option key={e} value={e}>{e}</Option>)}
                        </Select>
                      </div>
                      <Dragger
                        accept=".csv"
                        beforeUpload={(file) => { setFileRecibos(file); return false }}
                        fileList={fileRecibos ? [{ uid: '1', name: fileRecibos.name, status: 'done' } as UploadFile] : []}
                        onRemove={() => setFileRecibos(null)}
                        maxCount={1}
                      >
                        <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                        <p>Arrastra el CSV de recibos aquí o haz clic para seleccionar</p>
                        <p style={{ color: '#999', fontSize: 12 }}>Columna clave: Código</p>
                      </Dragger>
                      {/* Progreso carga recibos */}
                      {subirRecibos.isPending && (
                        <Card size="small" style={{ background: '#f0f7ff', border: '1px solid #91caff' }}>
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                              <LoadingOutlined style={{ color: '#1677ff', fontSize: 16 }} spin />
                              <Text strong style={{ color: '#1677ff' }}>Cargando recibos...</Text>
                              <Text type="secondary">{elapsedRecibos}s transcurridos</Text>
                            </Space>
                            <Progress
                              percent={Math.min(elapsedRecibos * 5, 90)}
                              showInfo={false}
                              strokeColor={{ '0%': '#1677ff', '100%': '#52c41a' }}
                              size="small"
                            />
                          </Space>
                        </Card>
                      )}

                      {/* Resumen tras carga de recibos */}
                      {uploadResultRecibos && !subirRecibos.isPending && (
                        <Card
                          size="small"
                          style={{ background: '#f6ffed', border: '1px solid #b7eb8f' }}
                          title={
                            <Space>
                              <CheckCircleOutlined style={{ color: '#52c41a' }} />
                              <Text strong style={{ color: '#389e0d' }}>
                                Recibos cargados en {uploadResultRecibos.tiempo_segundos}s
                              </Text>
                            </Space>
                          }
                        >
                          <Row gutter={[12, 0]}>
                            <Col span={12}>
                              <Statistic
                                title="Nuevos"
                                value={uploadResultRecibos.insertados}
                                valueStyle={{ fontSize: 20, color: '#52c41a' }}
                              />
                            </Col>
                            <Col span={12}>
                              <Statistic
                                title="Actualizados"
                                value={uploadResultRecibos.actualizados}
                                valueStyle={{ fontSize: 20, color: '#1677ff' }}
                              />
                            </Col>
                          </Row>
                        </Card>
                      )}

                      <Button
                        type="primary"
                        icon={<UploadOutlined />}
                        loading={subirRecibos.isPending}
                        disabled={!fileRecibos}
                        onClick={() => { setUploadResultRecibos(null); subirRecibos.mutate() }}
                        block
                      >
                        Cargar recibos
                      </Button>
                    </Space>
                  </Card>
                </Col>

                {/* Diario */}
                <Col xs={24} lg={12}>
                  <Card title="2. Diario contable (Excel)">
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                      <Row gutter={12}>
                        <Col span={12}>
                          <Text type="secondary">Ejercicio</Text>
                          <Select value={ejercicioDiario} onChange={setEjercicioDiario} style={{ width: '100%', marginTop: 4 }} disabled={subirDiario.isPending || !!uploadResult}>
                            {EJERCICIOS.map(e => <Option key={e} value={e}>{e}</Option>)}
                          </Select>
                        </Col>
                        <Col span={12}>
                          <Text type="secondary">Tipo de carga</Text>
                          <Select value={tipoCarga} onChange={setTipoCarga} style={{ width: '100%', marginTop: 4 }} disabled={subirDiario.isPending || !!uploadResult}>
                            <Option value="base_presupuestaria">Base presupuestaria</Option>
                            <Option value="mensual_real">Real mensual</Option>
                          </Select>
                        </Col>
                      </Row>

                      {/* Dragger — oculto mientras procesa o hay resultado */}
                      {!subirDiario.isPending && !uploadResult && (
                        <Dragger
                          accept=".xlsx,.xls"
                          beforeUpload={(file) => { setFileDiario(file); return false }}
                          fileList={fileDiario ? [{ uid: '1', name: fileDiario.name, status: 'done' } as UploadFile] : []}
                          onRemove={() => setFileDiario(null)}
                          maxCount={1}
                        >
                          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                          <p>Arrastra el Excel del diario aquí o haz clic para seleccionar</p>
                          <p style={{ color: '#999', fontSize: 12 }}>Columnas: Linea, Fecha, Debe, Haber, Numero de Cuenta, Concepto</p>
                        </Dragger>
                      )}

                      {/* PROGRESO — reemplaza al dragger mientras procesa */}
                      {subirDiario.isPending && (
                        <Card style={{ background: '#f0f7ff', border: '2px solid #91caff', borderRadius: 8 }}>
                          <Space direction="vertical" style={{ width: '100%' }} size="middle">
                            <Space>
                              <LoadingOutlined style={{ color: '#1677ff', fontSize: 20 }} spin />
                              <Text strong style={{ color: '#1677ff', fontSize: 16 }}>Procesando diario...</Text>
                            </Space>
                            <Progress
                              percent={Math.min(elapsed * 4, 90)}
                              showInfo={false}
                              strokeColor={{ '0%': '#1677ff', '100%': '#52c41a' }}
                            />
                            <Row gutter={24}>
                              <Col span={12}>
                                <Statistic
                                  title="Tiempo transcurrido"
                                  value={elapsed}
                                  suffix="s"
                                  valueStyle={{ color: '#1677ff', fontSize: 24 }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="Tiempo estimado restante"
                                  value={elapsed > 5 ? Math.max(0, Math.round(elapsed * 0.6)) : '—'}
                                  suffix={elapsed > 5 ? 's' : ''}
                                  valueStyle={{ fontSize: 24 }}
                                />
                              </Col>
                            </Row>
                            <Text type="secondary">Clasificando cuentas y cruzando recibos...</Text>
                          </Space>
                        </Card>
                      )}

                      {/* RESUMEN — reemplaza al dragger tras la carga */}
                      {uploadResult && !subirDiario.isPending && (
                        <Card
                          style={{ background: '#f6ffed', border: '2px solid #b7eb8f', borderRadius: 8 }}
                          title={
                            <Space>
                              <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 18 }} />
                              <Text strong style={{ color: '#389e0d', fontSize: 15 }}>
                                Carga completada en {uploadResult.tiempo_segundos}s
                              </Text>
                            </Space>
                          }
                        >
                          <Row gutter={[12, 12]}>
                            <Col span={8}>
                              <Statistic
                                title="Total registros"
                                value={uploadResult.total_registros}
                                valueStyle={{ fontSize: 22 }}
                              />
                            </Col>
                            <Col span={8}>
                              <Statistic
                                title="Correctos"
                                value={uploadResult.registros_correctos}
                                valueStyle={{ fontSize: 22, color: '#52c41a' }}
                              />
                            </Col>
                            <Col span={8}>
                              <Statistic
                                title="Con incidencias"
                                value={uploadResult.registros_con_incidencia}
                                valueStyle={{ fontSize: 22, color: uploadResult.registros_con_incidencia > 0 ? '#faad14' : '#52c41a' }}
                              />
                            </Col>
                          </Row>
                          <Divider style={{ margin: '12px 0' }} />
                          <Row gutter={[12, 8]}>
                            <Col span={12}>
                              <Space>
                                <RiseOutlined style={{ color: '#1677ff' }} />
                                <Text type="secondary">Debe total:</Text>
                                <Text strong>{fmt(uploadResult.importe_debe_total)} €</Text>
                              </Space>
                            </Col>
                            <Col span={12}>
                              <Space>
                                <FallOutlined style={{ color: '#722ed1' }} />
                                <Text type="secondary">Haber total:</Text>
                                <Text strong>{fmt(uploadResult.importe_haber_total)} €</Text>
                              </Space>
                            </Col>
                          </Row>
                          {uploadResult.registros_con_incidencia > 0 && (
                            <Button
                              type="link"
                              size="small"
                              style={{ padding: '8px 0 0 0' }}
                              onClick={() => {
                                setCargaSeleccionada(uploadResult.carga_id)
                                setActiveTabKey('incidencias')
                              }}
                            >
                              Ver {uploadResult.registros_con_incidencia} incidencias →
                            </Button>
                          )}
                        </Card>
                      )}

                      {/* Botón principal */}
                      {!uploadResult && (
                        <Button
                          type="primary"
                          icon={<UploadOutlined />}
                          loading={subirDiario.isPending}
                          disabled={!fileDiario || subirDiario.isPending}
                          onClick={() => subirDiario.mutate()}
                          block
                        >
                          {subirDiario.isPending ? 'Procesando...' : 'Procesar diario'}
                        </Button>
                      )}
                      {uploadResult && !subirDiario.isPending && (
                        <Button
                          block
                          onClick={() => { setUploadResult(null); setFileDiario(null) }}
                        >
                          Nueva carga
                        </Button>
                      )}
                    </Space>
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: 'historial',
            label: 'Historial de cargas',
            children: (
              <Card>
                <Table
                  dataSource={historial || []}
                  columns={colsHistorial}
                  rowKey="id"
                  loading={cargandoHistorial}
                  size="small"
                  pagination={{ pageSize: 10 }}
                />
              </Card>
            ),
          },
          {
            key: 'historico',
            label: 'Histórico estadístico',
            children: (
              <Row gutter={[24, 24]}>
                <Col xs={24} lg={9}>
                  <Card title="Cargar ejercicio histórico" extra={<Tag color="purple">Modelo estadístico</Tag>}>
                    <Space direction="vertical" style={{ width: '100%' }} size="middle">
                      <Alert
                        type="info"
                        showIcon
                        message="Los diarios históricos se usan para calcular la tasa de crecimiento interanual. Carga al menos 3 ejercicios anteriores para obtener un modelo estadístico fiable."
                      />
                      <div>
                        <Text type="secondary">Ejercicio a cargar</Text>
                        <Select
                          value={ejercicioHistorico}
                          onChange={setEjercicioHistorico}
                          style={{ width: '100%', marginTop: 4 }}
                        >
                          {[2019, 2020, 2021, 2022, 2023, 2024].map(e => (
                            <Option key={e} value={e}>{e}</Option>
                          ))}
                        </Select>
                      </div>
                      <Dragger
                        accept=".xlsx,.xls"
                        beforeUpload={(f) => { setFileHistorico(f); return false }}
                        fileList={fileHistorico ? [{ uid: '1', name: fileHistorico.name, status: 'done' } as UploadFile] : []}
                        onRemove={() => setFileHistorico(null)}
                        maxCount={1}
                        disabled={subirHistorico.isPending}
                      >
                        <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                        <p>Arrastra el Excel del diario histórico aquí o haz clic para seleccionar</p>
                        <p style={{ color: '#999', fontSize: 12 }}>Columnas: Linea, Fecha, Debe, Haber, Numero de Cuenta, Concepto</p>
                      </Dragger>

                      {/* Progreso carga histórico */}
                      {subirHistorico.isPending && (
                        <Card size="small" style={{ background: '#f0f7ff', border: '1px solid #91caff' }}>
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                              <LoadingOutlined style={{ color: '#1677ff', fontSize: 16 }} spin />
                              <Text strong style={{ color: '#1677ff' }}>Procesando histórico...</Text>
                              <Text type="secondary">{elapsedHistorico}s transcurridos</Text>
                            </Space>
                            <Progress
                              percent={Math.min(elapsedHistorico * 3, 90)}
                              showInfo={false}
                              strokeColor={{ '0%': '#722ed1', '100%': '#52c41a' }}
                              size="small"
                            />
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              Clasificando cuentas y cruzando recibos históricos...
                            </Text>
                          </Space>
                        </Card>
                      )}

                      {/* Resumen tras carga histórica */}
                      {uploadResultHistorico && !subirHistorico.isPending && (
                        <Card
                          size="small"
                          style={{ background: '#f6ffed', border: '1px solid #b7eb8f' }}
                          title={
                            <Space>
                              <CheckCircleOutlined style={{ color: '#52c41a' }} />
                              <Text strong style={{ color: '#389e0d' }}>
                                Histórico cargado en {uploadResultHistorico.tiempo_segundos}s
                              </Text>
                            </Space>
                          }
                        >
                          <Row gutter={[12, 8]}>
                            <Col span={8}>
                              <Statistic
                                title="Total registros"
                                value={uploadResultHistorico.total_registros}
                                valueStyle={{ fontSize: 18 }}
                              />
                            </Col>
                            <Col span={8}>
                              <Statistic
                                title="Correctos"
                                value={uploadResultHistorico.registros_correctos}
                                valueStyle={{ fontSize: 18, color: '#52c41a' }}
                              />
                            </Col>
                            <Col span={8}>
                              <Statistic
                                title="Incidencias"
                                value={uploadResultHistorico.registros_con_incidencia}
                                valueStyle={{ fontSize: 18, color: uploadResultHistorico.registros_con_incidencia > 0 ? '#faad14' : '#52c41a' }}
                              />
                            </Col>
                          </Row>
                          <Divider style={{ margin: '10px 0' }} />
                          <Row gutter={[12, 0]}>
                            <Col span={12}>
                              <Space>
                                <RiseOutlined style={{ color: '#1677ff' }} />
                                <Text type="secondary">Debe:</Text>
                                <Text strong>{fmt(uploadResultHistorico.importe_debe_total)} €</Text>
                              </Space>
                            </Col>
                            <Col span={12}>
                              <Space>
                                <FallOutlined style={{ color: '#722ed1' }} />
                                <Text type="secondary">Haber:</Text>
                                <Text strong>{fmt(uploadResultHistorico.importe_haber_total)} €</Text>
                              </Space>
                            </Col>
                          </Row>
                        </Card>
                      )}

                      <Button
                        type="primary"
                        icon={<UploadOutlined />}
                        loading={subirHistorico.isPending}
                        disabled={!fileHistorico || subirHistorico.isPending}
                        onClick={() => { setUploadResultHistorico(null); subirHistorico.mutate() }}
                        block
                      >
                        {subirHistorico.isPending ? 'Procesando...' : `Cargar histórico ${ejercicioHistorico}`}
                      </Button>
                    </Space>
                  </Card>
                </Col>
                <Col xs={24} lg={15}>
                  <Card title="Ejercicios históricos disponibles">
                    <Table
                      dataSource={historico}
                      rowKey="id"
                      loading={cargandoHistorico}
                      size="small"
                      pagination={false}
                      scroll={{ x: 480 }}
                      columns={[
                        { title: 'Ejercicio', dataIndex: 'ejercicio', width: 80 },
                        {
                          title: 'Registros',
                          dataIndex: 'total_registros',
                          width: 85,
                          render: (v: number) => v?.toLocaleString('es-ES') ?? '—',
                        },
                        {
                          title: 'Correctos',
                          dataIndex: 'registros_correctos',
                          width: 85,
                          render: (v: number) => (
                            <Tag color="success">{v?.toLocaleString('es-ES') ?? '—'}</Tag>
                          ),
                        },
                        {
                          title: 'Incidencias',
                          dataIndex: 'registros_con_incidencia',
                          width: 95,
                          render: (v: number) => (
                            <Tag color={v > 0 ? 'warning' : 'success'}>{v?.toLocaleString('es-ES') ?? '—'}</Tag>
                          ),
                        },
                        {
                          title: 'Estado',
                          dataIndex: 'estado',
                          width: 110,
                          render: (v: string) => <TagEstado estado={v} />,
                        },
                        {
                          title: '',
                          width: 80,
                          render: (_: any, row: any) => (
                            <Button
                              size="small"
                              danger
                              onClick={() => {
                                Modal.confirm({
                                  title: `¿Eliminar histórico ${row.ejercicio}?`,
                                  content: 'Se eliminarán todos los apuntes de este ejercicio histórico.',
                                  okText: 'Eliminar',
                                  okType: 'danger',
                                  cancelText: 'Cancelar',
                                  onOk: () => eliminarHistorico.mutate(row.id),
                                })
                              }}
                            >
                              Eliminar
                            </Button>
                          ),
                        },
                      ]}
                      locale={{ emptyText: 'Sin ejercicios históricos cargados' }}
                    />
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: 'incidencias',
            label: cargaSeleccionada
              ? <Badge count={resumen?.incidencias_criticas_pendientes || 0} size="small">Incidencias</Badge>
              : 'Incidencias',
            disabled: !cargaSeleccionada,
            children: cargaSeleccionada && (
              <Space direction="vertical" size="large" style={{ width: '100%' }}>
                {resumen && (
                  <Row gutter={[16, 16]}>
                    <Col span={6}>
                      <Card>
                        <Statistic title="Total registros" value={resumen.totales.registros} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card>
                        <Statistic title="Correctos" value={resumen.totales.correctos} valueStyle={{ color: '#52c41a' }} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card>
                        <Statistic title="Con incidencia" value={resumen.totales.con_incidencia} valueStyle={{ color: '#faad14' }} />
                      </Card>
                    </Col>
                    <Col span={6}>
                      <Card>
                        <Statistic
                          title="Incidencias críticas"
                          value={resumen.incidencias_criticas_pendientes}
                          valueStyle={{ color: resumen.incidencias_criticas_pendientes > 0 ? '#ff4d4f' : '#52c41a' }}
                        />
                      </Card>
                    </Col>
                  </Row>
                )}

                {resumen?.puede_validar === false && (
                  <Alert
                    type="error"
                    showIcon
                    message="Existen incidencias críticas pendientes"
                    description="Debes resolver todas las incidencias críticas antes de poder validar y cerrar esta carga."
                  />
                )}

                <Card title="Incidencias pendientes">
                  <Table
                    dataSource={incidencias || []}
                    columns={colsIncidencias}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 15 }}
                    rowClassName={(row) => row.es_critica === 'si' && row.estado === 'pendiente' ? 'ant-table-row-danger' : ''}
                  />
                </Card>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title="Resolver incidencia"
        open={modalResolverVisible}
        onOk={() => resolverInc.mutate()}
        onCancel={() => { setModalResolverVisible(false); setResolucion('') }}
        confirmLoading={resolverInc.isPending}
        okText="Resolver"
        cancelText="Cancelar"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text strong>{incidenciaActiva?.descripcion}</Text>
          <Input.TextArea
            value={resolucion}
            onChange={(e) => setResolucion(e.target.value)}
            placeholder="Describe cómo se ha resuelto esta incidencia..."
            rows={3}
          />
        </Space>
      </Modal>
    </Space>
  )
}
