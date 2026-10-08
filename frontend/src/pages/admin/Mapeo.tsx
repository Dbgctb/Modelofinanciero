import { useState } from 'react'
import * as XLSX from 'xlsx'
import {
  Card, Table, Button, Tag, Space, Typography, Modal, Form,
  Input, Select, Switch, Tooltip, Popconfirm, message,
  Upload, Alert, Row, Col, Statistic,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, UploadOutlined,
  DownloadOutlined, QuestionCircleOutlined,
  CloseCircleOutlined, StopOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { parametrosApi, type MapCuenta, type MapCuentaInput, type TipoCuenta } from '../../api/parametros'
import { apiError } from '../../utils/errorHandler'

type ImportError = { fila: number; cuenta: string; motivo: string }

const { Title, Text } = Typography
const { Option } = Select

const TIPO_LABELS: Record<string, { label: string; color: string }> = {
  ingreso: { label: 'Ingreso', color: 'green' },
  gasto: { label: 'Gasto', color: 'orange' },
  tesoreria_excluida: { label: 'Tesorería excluida', color: 'blue' },
}

const COMPAÑIAS_CONOCIDAS = [
  'REALE SEGUROS', 'CASER', 'FIATC', 'ARAG', 'MAPFRE', 'AXA',
  'OCCIDENT', 'ALLIANZ', 'ZURICH', 'GENERALI', 'OCASO',
  'MUTUA MADRILEÑA', 'DIVINA PASTORA', 'ASISA', 'SOLUNION',
  'PELAYO', 'RACE', 'AEGON', 'SURNE', 'VIDA CAIXA', 'PREVENTIVA',
]

export default function MapeoPage() {
  const qc = useQueryClient()
  const [modalVisible, setModalVisible] = useState(false)
  const [editando, setEditando] = useState<MapCuenta | null>(null)
  const [filtroTipo, setFiltroTipo] = useState<string | undefined>()
  const [filtroActivo, setFiltroActivo] = useState<boolean | undefined>(true)
  const [form] = Form.useForm()
  const [tipoForm, setTipoForm] = useState<TipoCuenta>('ingreso')
  const [importVisible, setImportVisible] = useState(false)
  const [excelRows, setExcelRows] = useState<any[]>([])
  const [excelFileName, setExcelFileName] = useState('')
  const [importErrors, setImportErrors] = useState<ImportError[]>([])

  const { data: cuentas = [], isLoading } = useQuery({
    queryKey: ['cuentas', filtroTipo, filtroActivo],
    queryFn: () =>
      parametrosApi.listarCuentas({ tipo: filtroTipo as any, activo: filtroActivo }).then(r => r.data),
  })

  const { data: familias = [] } = useQuery({
    queryKey: ['familias'],
    queryFn: () => parametrosApi.familias().then(r => r.data),
  })

  const crear = useMutation({
    mutationFn: (data: MapCuentaInput) => parametrosApi.crearCuenta(data),
    onSuccess: () => { message.success('Mapeo creado'); qc.invalidateQueries({ queryKey: ['cuentas'] }); cerrarModal() },
    onError: (e) => message.error(apiError(e, 'Error al crear el mapeo')),
  })

  const actualizar = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => parametrosApi.actualizarCuenta(id, data),
    onSuccess: () => { message.success('Mapeo actualizado'); qc.invalidateQueries({ queryKey: ['cuentas'] }); cerrarModal() },
    onError: (e) => message.error(apiError(e, 'Error al actualizar el mapeo')),
  })

  const eliminar = useMutation({
    mutationFn: (id: string) => parametrosApi.eliminarCuenta(id),
    onSuccess: () => { message.success('Mapeo eliminado'); qc.invalidateQueries({ queryKey: ['cuentas'] }) },
    onError: (e) => message.error(apiError(e, 'No se pudo eliminar el mapeo')),
  })

  const importar = useMutation({
    mutationFn: (cuentas: MapCuentaInput[]) => parametrosApi.importarLote(cuentas),
    onSuccess: (res) => {
      const { insertados, omitidos, errores = [] } = res.data
      qc.invalidateQueries({ queryKey: ['cuentas'] })
      setImportErrors(errores)
      if (errores.length === 0) {
        message.success(`Importación completada: ${insertados} insertadas, ${omitidos} omitidas`)
        setImportVisible(false)
        setExcelRows([])
        setExcelFileName('')
      } else {
        if (insertados > 0) {
          message.warning(`${insertados} insertadas · ${omitidos} omitidas con errores`)
        } else {
          message.error(`Importación fallida: ${omitidos} filas con errores`)
        }
        // El modal se queda abierto mostrando los errores
      }
    },
    onError: (e) => message.error(apiError(e, 'Error en la importación. Comprueba el formato del archivo')),
  })

  const abrirNuevo = () => {
    setEditando(null)
    form.resetFields()
    setTipoForm('ingreso')
    setModalVisible(true)
  }

  const abrirEditar = (c: MapCuenta) => {
    setEditando(c)
    setTipoForm(c.tipo)
    form.setFieldsValue({
      numero_cuenta: c.numero_cuenta,
      tipo: c.tipo,
      compania: c.compania,
      familia_gasto: c.familia_gasto,
      descripcion: c.descripcion,
      excluir_tesoreria: c.excluir_tesoreria,
    })
    setModalVisible(true)
  }

  const cerrarModal = () => { setModalVisible(false); setEditando(null); form.resetFields() }

  const cerrarImport = () => {
    setImportVisible(false)
    setExcelRows([])
    setExcelFileName('')
    setImportErrors([])
  }

  const onGuardar = () => {
    form.validateFields().then((vals) => {
      if (editando) {
        actualizar.mutate({ id: editando.id, data: vals })
      } else {
        crear.mutate(vals)
      }
    })
  }

  const toggleActivo = (c: MapCuenta) => {
    actualizar.mutate({ id: c.id, data: { activo: !c.activo } })
  }

  const exportarExcel = () => {
    const datos = cuentas.map(({ numero_cuenta, tipo, compania, familia_gasto, descripcion, excluir_tesoreria }) => ({
      numero_cuenta,
      tipo,
      compania: compania ?? '',
      familia_gasto: familia_gasto ?? '',
      descripcion: descripcion ?? '',
      excluir_tesoreria: excluir_tesoreria ? 'si' : 'no',
    }))
    const ws = XLSX.utils.json_to_sheet(datos)
    ws['!cols'] = [{ wch: 16 }, { wch: 20 }, { wch: 24 }, { wch: 22 }, { wch: 32 }, { wch: 18 }]
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Mapeo')
    XLSX.writeFile(wb, 'mapeo_cuentas.xlsx')
  }

  // Normaliza un nombre de columna: minúsculas, sin acentos, espacios → _
  // "Compañía" → "compania", "Número Cuenta" → "numero_cuenta"
  const normCol = (k: string) =>
    k.toLowerCase()
     .normalize('NFD').replace(/\p{Mn}/gu, '')
     .replace(/[\s]+/g, '_')
     .trim()

  // Devuelve un mapa normKey → clave real del Excel
  const buildColMap = (row: any): Record<string, string> => {
    const map: Record<string, string> = {}
    for (const k of Object.keys(row)) map[normCol(k)] = k
    return map
  }

  const onArchivoExcel = (file: File) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const wb = XLSX.read(e.target?.result, { type: 'binary' })
        const ws = wb.Sheets[wb.SheetNames[0]]
        const rows: any[] = XLSX.utils.sheet_to_json(ws, { defval: '' })
        if (rows.length === 0) {
          message.error('El archivo no contiene filas de datos')
          return
        }
        const colMap = buildColMap(rows[0])
        const OBLIGATORIAS = ['numero_cuenta', 'tipo']
        const faltantes = OBLIGATORIAS.filter(c => !(c in colMap))
        if (faltantes.length > 0) {
          message.error(`Faltan columnas obligatorias: ${faltantes.join(', ')}`)
          return
        }
        // Guardar junto con el mapa de columnas para usarlo al importar
        setExcelRows(rows.map(r => ({ _row: r, _map: colMap })))
        setExcelFileName(file.name)
      } catch {
        message.error('No se pudo leer el archivo Excel')
      }
    }
    reader.readAsBinaryString(file)
    return false
  }

  const intentarImportar = () => {
    if (excelRows.length === 0) { message.warning('Selecciona un archivo Excel primero'); return }

    const get = (row: any, map: Record<string, string>, campo: string): string | undefined => {
      const realKey = map[campo]
      if (!realKey) return undefined
      const val = String(row[realKey] ?? '').trim()
      return val || undefined
    }

    const parseBool = (v: string | undefined): boolean => {
      if (!v) return false
      return ['si', 'sí', 'true', '1', 'yes', 'x'].includes(v.toLowerCase())
    }

    const datos = excelRows.map(({ _row, _map }: any) => ({
      numero_cuenta: String(_row[_map['numero_cuenta']] ?? '').trim(),
      tipo: String(_row[_map['tipo']] ?? '').trim(),
      compania: get(_row, _map, 'compania'),
      familia_gasto: get(_row, _map, 'familia_gasto'),
      descripcion: get(_row, _map, 'descripcion'),
      excluir_tesoreria: parseBool(get(_row, _map, 'excluir_tesoreria')),
    })).filter(r => r.numero_cuenta && r.tipo)

    if (datos.length === 0) { message.error('No se encontraron filas válidas'); return }
    importar.mutate(datos as MapCuentaInput[])
  }

  // Estadísticas rápidas
  const totalIngreso = cuentas.filter(c => c.tipo === 'ingreso').length
  const totalGasto = cuentas.filter(c => c.tipo === 'gasto').length
  const totalExcluida = cuentas.filter(c => c.excluir_tesoreria || c.tipo === 'tesoreria_excluida').length

  const columnas = [
    {
      title: 'Cuenta / Prefijo',
      dataIndex: 'numero_cuenta',
      sorter: (a: MapCuenta, b: MapCuenta) => a.numero_cuenta.localeCompare(b.numero_cuenta),
      render: (v: string) => <Text code>{v}</Text>,
    },
    {
      title: 'Tipo',
      dataIndex: 'tipo',
      render: (v: string) => (
        <Tag color={TIPO_LABELS[v]?.color}>{TIPO_LABELS[v]?.label}</Tag>
      ),
    },
    {
      title: 'Compañía',
      dataIndex: 'compania',
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    {
      title: 'Familia de gasto',
      dataIndex: 'familia_gasto',
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    {
      title: 'Descripción',
      dataIndex: 'descripcion',
      ellipsis: true,
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
    {
      title: (
        <Tooltip title="Estas cuentas no computan en el cálculo de tesorería presupuestada">
          <span>Excl. tesorería <QuestionCircleOutlined style={{ color: '#999' }} /></span>
        </Tooltip>
      ),
      dataIndex: 'excluir_tesoreria',
      width: 130,
      render: (v: boolean, row: MapCuenta) => (
        <Switch
          size="small"
          checked={v || row.tipo === 'tesoreria_excluida'}
          checkedChildren={<StopOutlined />}
          onChange={(checked) =>
            actualizar.mutate({ id: row.id, data: { excluir_tesoreria: checked } })
          }
        />
      ),
    },
    {
      title: 'Activo',
      dataIndex: 'activo',
      width: 80,
      render: (v: boolean, row: MapCuenta) => (
        <Switch
          size="small"
          checked={v}
          onChange={() => toggleActivo(row)}
        />
      ),
    },
    {
      title: '',
      width: 90,
      render: (_: any, row: MapCuenta) => (
        <Space>
          <Tooltip title="Editar">
            <Button size="small" icon={<EditOutlined />} onClick={() => abrirEditar(row)} />
          </Tooltip>
          <Popconfirm
            title="¿Eliminar este mapeo?"
            onConfirm={() => eliminar.mutate(row.id)}
            okText="Eliminar"
            cancelText="Cancelar"
            okButtonProps={{ danger: true }}
          >
            <Tooltip title="Eliminar">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>Mapeo de cuentas contables</Title>
          <Text type="secondary">
            Define qué cuentas son ingresos, gastos o tesorería excluida, y su compañía/familia asociada.
          </Text>
        </div>
        <Space>
          <Button icon={<DownloadOutlined />} onClick={exportarExcel}>Exportar Excel</Button>
          <Button icon={<UploadOutlined />} onClick={() => setImportVisible(true)}>Importar Excel</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={abrirNuevo}>Nueva cuenta</Button>
        </Space>
      </div>

      {/* Estadísticas — clic para filtrar por tipo */}
      <Row gutter={16}>
        <Col span={6}>
          <Card
            size="small"
            hoverable
            style={{ cursor: 'pointer', borderTop: '3px solid #52c41a' }}
            onClick={() => setFiltroTipo(filtroTipo === 'ingreso' ? undefined : 'ingreso')}
          >
            <Statistic title="Cuentas de ingreso" value={totalIngreso} valueStyle={{ color: '#52c41a' }} />
            {filtroTipo === 'ingreso' && <Tag color="green" style={{ marginTop: 4 }}>Filtrando</Tag>}
          </Card>
        </Col>
        <Col span={6}>
          <Card
            size="small"
            hoverable
            style={{ cursor: 'pointer', borderTop: '3px solid #fa8c16' }}
            onClick={() => setFiltroTipo(filtroTipo === 'gasto' ? undefined : 'gasto')}
          >
            <Statistic title="Cuentas de gasto" value={totalGasto} valueStyle={{ color: '#fa8c16' }} />
            {filtroTipo === 'gasto' && <Tag color="orange" style={{ marginTop: 4 }}>Filtrando</Tag>}
          </Card>
        </Col>
        <Col span={6}>
          <Card
            size="small"
            hoverable
            style={{ cursor: 'pointer', borderTop: '3px solid #1890ff' }}
            onClick={() => setFiltroTipo(filtroTipo === 'tesoreria_excluida' ? undefined : 'tesoreria_excluida')}
          >
            <Statistic title="Excluidas de tesorería" value={totalExcluida} valueStyle={{ color: '#1890ff' }} />
            {filtroTipo === 'tesoreria_excluida' && <Tag color="blue" style={{ marginTop: 4 }}>Filtrando</Tag>}
          </Card>
        </Col>
        <Col span={6}>
          <Card
            size="small"
            hoverable
            style={{ cursor: 'pointer' }}
            onClick={() => setFiltroTipo(undefined)}
          >
            <Statistic title="Total configuradas" value={cuentas.length} />
          </Card>
        </Col>
      </Row>

      {cuentas.length === 0 && !isLoading && (
        <Alert
          type="warning"
          showIcon
          message="No hay cuentas configuradas"
          description="Añade los mapeos de cuentas contables antes de procesar el diario. Sin esta configuración, todos los apuntes quedarán como incidencias."
        />
      )}

      <Card
        extra={
          <Space>
            <Select
              allowClear
              placeholder="Filtrar por tipo"
              style={{ width: 180 }}
              onChange={setFiltroTipo}
            >
              <Option value="ingreso">Ingreso</Option>
              <Option value="gasto">Gasto</Option>
              <Option value="tesoreria_excluida">Tesorería excluida</Option>
            </Select>
            <Select
              value={filtroActivo}
              style={{ width: 120 }}
              onChange={setFiltroActivo}
            >
              <Option value={true}>Activas</Option>
              <Option value={false}>Inactivas</Option>
              <Option value={undefined}>Todas</Option>
            </Select>
          </Space>
        }
      >
        <Table
          dataSource={cuentas}
          columns={columnas}
          rowKey="id"
          loading={isLoading}
          size="small"
          pagination={{ pageSize: 20, showTotal: (t) => `${t} cuentas` }}
        />
      </Card>

      {/* Modal crear/editar */}
      <Modal
        title={editando ? 'Editar mapeo de cuenta' : 'Nueva cuenta contable'}
        open={modalVisible}
        onOk={onGuardar}
        onCancel={cerrarModal}
        confirmLoading={crear.isPending || actualizar.isPending}
        okText="Guardar"
        cancelText="Cancelar"
        width={540}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="numero_cuenta"
            label={
              <span>
                Número de cuenta o prefijo{' '}
                <Tooltip title="Puede ser una cuenta exacta (760001) o un prefijo (760). El sistema busca primero por cuenta exacta y luego por prefijos más cortos.">
                  <QuestionCircleOutlined />
                </Tooltip>
              </span>
            }
            rules={[{ required: true, message: 'Obligatorio' }]}
          >
            <Input placeholder="Ej: 7600001 o prefijo 760" disabled={!!editando} />
          </Form.Item>

          <Form.Item name="tipo" label="Tipo de cuenta" rules={[{ required: true, message: 'Selecciona el tipo de cuenta' }]}>
            <Select
              placeholder="Selecciona el tipo"
              onChange={(v) => setTipoForm(v as TipoCuenta)}
              optionLabelProp="label"
            >
              <Option value="ingreso" label={<><Tag color="green" style={{ marginRight: 6 }}>Ingreso</Tag>Comisiones de compañías aseguradoras</>}>
                <Tag color="green">Ingreso</Tag> Comisiones de compañías aseguradoras
              </Option>
              <Option value="gasto" label={<><Tag color="orange" style={{ marginRight: 6 }}>Gasto</Tag>Gasto operativo</>}>
                <Tag color="orange">Gasto</Tag> Gasto operativo
              </Option>
              <Option value="tesoreria_excluida" label={<><Tag color="blue" style={{ marginRight: 6 }}>Excluida tesorería</Tag>Excluida de tesorería</>}>
                <Tag color="blue">Excluida tesorería</Tag> Amortizaciones, ajustes contables y similares
              </Option>
            </Select>
          </Form.Item>

          {tipoForm === 'ingreso' && (
            <Form.Item name="compania" label="Compañía" rules={[{ required: true, message: 'Las cuentas de ingreso requieren compañía' }]}>
              <Select showSearch allowClear placeholder="Selecciona o escribe la compañía">
                {COMPAÑIAS_CONOCIDAS.map(c => <Option key={c} value={c}>{c}</Option>)}
              </Select>
            </Form.Item>
          )}

          {tipoForm === 'gasto' && (
            <Form.Item name="familia_gasto" label="Familia de gasto" rules={[{ required: true, message: 'Las cuentas de gasto requieren familia' }]}>
              <Select placeholder="Selecciona una familia">
                {familias.map(f => <Option key={f} value={f}>{f}</Option>)}
              </Select>
            </Form.Item>
          )}

          {tipoForm === 'tesoreria_excluida' && (
            <Text type="secondary" style={{ display: 'block', marginBottom: 16, fontSize: 12 }}>
              Estas cuentas se excluyen del cálculo de tesorería presupuestada (amortizaciones, ajustes, etc.).
              No requieren compañía ni familia de gasto.
            </Text>
          )}

          <Form.Item
            name="excluir_tesoreria"
            valuePropName="checked"
            label={
              <span>
                Excluir de tesorería{' '}
                <Tooltip title="Marca esta cuenta para que no compute en el cálculo de tesorería presupuestada. Úsalo para amortizaciones, ajustes contables y otros movimientos sin impacto en caja.">
                  <QuestionCircleOutlined />
                </Tooltip>
              </span>
            }
          >
            <Switch
              checkedChildren="Excluida"
              unCheckedChildren="Incluida"
            />
          </Form.Item>

          <Form.Item name="descripcion" label="Descripción (opcional)">
            <Input placeholder="Ej: Comisiones Mapfre Autos" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Modal importar Excel */}
      <Modal
        title="Importar mapeos desde Excel"
        open={importVisible}
        onOk={importErrors.length > 0 ? cerrarImport : intentarImportar}
        onCancel={cerrarImport}
        confirmLoading={importar.isPending}
        okText={importErrors.length > 0 ? 'Cerrar' : `Importar${excelRows.length > 0 ? ` (${excelRows.length} filas)` : ''}`}
        okButtonProps={{ danger: importErrors.length > 0 && importar.isSuccess && !excelRows.length ? false : undefined }}
        cancelText={importErrors.length > 0 ? undefined : 'Cancelar'}
        cancelButtonProps={importErrors.length > 0 ? { style: { display: 'none' } } : undefined}
        width={640}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          {importErrors.length === 0 ? (
            <>
              <Alert
                type="info"
                showIcon
                message="Formato del Excel"
                description={
                  <div style={{ fontSize: 12 }}>
                    <p style={{ margin: '4px 0' }}>Columnas necesarias (los nombres admiten mayúsculas, acentos y espacios):</p>
                    <ul style={{ margin: '4px 0', paddingLeft: 20 }}>
                      <li><strong>numero_cuenta</strong> — obligatorio (ej: 7600001 o prefijo 760)</li>
                      <li><strong>tipo</strong> — obligatorio: <em>ingreso</em>, <em>gasto</em> o <em>tesoreria_excluida</em></li>
                      <li><strong>compania</strong> / <strong>compañía</strong> — para cuentas de ingreso</li>
                      <li><strong>familia_gasto</strong> — para cuentas de gasto</li>
                      <li><strong>descripcion</strong> — opcional</li>
                    </ul>
                    <p style={{ margin: '4px 0' }}>Puedes usar <strong>Exportar Excel</strong> como plantilla.</p>
                  </div>
                }
              />
              <Upload.Dragger
                accept=".xlsx,.xls"
                beforeUpload={onArchivoExcel}
                showUploadList={false}
                maxCount={1}
              >
                <p className="ant-upload-drag-icon"><UploadOutlined style={{ fontSize: 32 }} /></p>
                {excelFileName
                  ? <p className="ant-upload-text" style={{ color: '#52c41a' }}>{excelFileName} — {excelRows.length} filas leídas</p>
                  : <p className="ant-upload-text">Haz clic o arrastra aquí el archivo Excel (.xlsx)</p>
                }
              </Upload.Dragger>
            </>
          ) : (
            <>
              <Alert
                type="error"
                showIcon
                icon={<CloseCircleOutlined />}
                message={`${importErrors.length} fila${importErrors.length > 1 ? 's' : ''} con errores`}
                description="Corrige los errores en el archivo Excel y vuelve a importarlo."
              />
              <Table
                dataSource={importErrors}
                rowKey="fila"
                size="small"
                pagination={importErrors.length > 10 ? { pageSize: 10 } : false}
                columns={[
                  { title: 'Fila', dataIndex: 'fila', width: 60 },
                  { title: 'Cuenta', dataIndex: 'cuenta', width: 120, render: (v: string) => <Text code>{v}</Text> },
                  { title: 'Motivo del error', dataIndex: 'motivo', render: (v: string) => <Text type="danger">{v}</Text> },
                ]}
              />
            </>
          )}
        </Space>
      </Modal>
    </Space>
  )
}
