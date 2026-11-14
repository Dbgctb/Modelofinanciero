import { useState } from 'react'
import { Alert, Button, Card, Col, message, Modal, Radio, Row, Select, Space, Table, Typography, Upload } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { bancoApi, MovimientoBanco } from '../../../api/cierres'
import { apiError } from '../../../utils/errorHandler'
import { eur, fecha, num, usePuedeEditar } from '../comun'

const { Paragraph, Text } = Typography

const CAMPOS = [
  { key: 'fecha', label: 'Fecha', obligatorio: true },
  { key: 'concepto', label: 'Concepto', obligatorio: true },
  { key: 'importe', label: 'Importe', obligatorio: true },
  { key: 'fecha_valor', label: 'Fecha valor', obligatorio: false },
  { key: 'saldo', label: 'Saldo', obligatorio: false },
  { key: 'referencia', label: 'Referencia', obligatorio: false },
]

export default function ImportarExtracto({ bancoId, ejercicio }: { bancoId: number; ejercicio: number }) {
  const qc = useQueryClient()
  const puedeEditar = usePuedeEditar()
  const [fichero, setFichero] = useState<UploadFile | null>(null)
  const [formato, setFormato] = useState<'norma43' | 'tabla'>('norma43')
  const [columnas, setColumnas] = useState<string[]>([])
  const [mapeo, setMapeo] = useState<Record<string, string>>({})
  const [ocupado, setOcupado] = useState(false)
  const [resultado, setResultado] = useState<any>(null)
  const [pagina, setPagina] = useState({ page: 1, page_size: 100 })

  const extractos = useQuery({
    queryKey: ['cierres', 'banco', 'extractos', bancoId, ejercicio, pagina],
    queryFn: () => bancoApi.getExtractos(bancoId, ejercicio, pagina.page, pagina.page_size).then((r) => r.data),
  })

  const elegirFichero = async (f: UploadFile | null) => {
    setFichero(f)
    setColumnas([])
    setMapeo({})
    setResultado(null)
    if (!f?.originFileObj) return
    const nombre = f.name.toLowerCase()
    const esTabla = /\.(xlsx|xls|csv)$/.test(nombre)
    setFormato(esTabla ? 'tabla' : 'norma43')
    if (esTabla) await leerColumnas(f)
  }

  const leerColumnas = async (f: UploadFile) => {
    const form = new FormData()
    form.append('file', f.originFileObj!)
    try {
      const { data } = await bancoApi.columnas(form)
      setColumnas(data.columnas)
    } catch (e) {
      message.error(apiError(e, 'No se pudieron leer las columnas'))
    }
  }

  const enviar = async (indiceCuenta?: number) => {
    if (!fichero?.originFileObj) return
    const form = new FormData()
    form.append('file', fichero.originFileObj)
    form.append('ejercicio', String(ejercicio))
    form.append('formato', formato)
    form.append('mapeo', JSON.stringify(mapeo))
    if (indiceCuenta !== undefined) form.append('indice_cuenta', String(indiceCuenta))
    setOcupado(true)
    try {
      const { data } = await bancoApi.importar(bancoId, form)
      if (data.elegir_cuenta) {
        let elegida = 0
        Modal.confirm({
          title: 'El fichero tiene varias cuentas',
          content: (
            <Radio.Group defaultValue={0} onChange={(e) => { elegida = e.target.value }}>
              <Space direction="vertical">
                {data.elegir_cuenta.map((c: any) => (
                  <Radio key={c.indice} value={c.indice}>{c.iban} ({num(c.movimientos)} movimientos)</Radio>
                ))}
              </Space>
            </Radio.Group>
          ),
          okText: 'Importar esta', cancelText: 'Cancelar',
          onOk: () => enviar(elegida),
        })
        return
      }
      setResultado(data)
      message.success(`${num(data.insertados)} movimientos importados`)
      qc.invalidateQueries({ queryKey: ['cierres', 'banco'] })
      qc.invalidateQueries({ queryKey: ['cierres', 'bancos'] })
    } catch (e) {
      message.error(apiError(e, 'No se pudo importar el extracto'))
    } finally {
      setOcupado(false)
    }
  }

  const mapeoCompleto = CAMPOS.filter((c) => c.obligatorio).every((c) => mapeo[c.key])

  return (
    <div>
      {puedeEditar && (
        <Card size="small" title="Importar extracto" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col xs={24} md={9}>
              <Upload.Dragger maxCount={1} accept=".txt,.q43,.c43,.n43,.xlsx,.xls,.csv" beforeUpload={() => false}
                fileList={fichero ? [fichero] : []} onChange={({ fileList }) => elegirFichero(fileList[0] ?? null)}>
                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                <p>Norma 43 (.txt, .q43, .n43) o Excel/CSV</p>
              </Upload.Dragger>
            </Col>
            <Col xs={24} md={15}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Radio.Group value={formato} onChange={(e) => setFormato(e.target.value)}>
                  <Radio value="norma43">Norma 43</Radio>
                  <Radio value="tabla">Excel / CSV</Radio>
                </Radio.Group>
                {formato === 'norma43' ? (
                  <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                    Sustituye los movimientos <b>pendientes</b> del banco en {ejercicio} por los del fichero. Los ya
                    conciliados se conservan y no se vuelven a insertar.
                  </Paragraph>
                ) : (
                  <>
                    <Alert type="warning" showIcon
                      message="Excel/CSV añade los movimientos a los que ya hay: no lo importes dos veces." />
                    {columnas.length > 0 && (
                      <Row gutter={[8, 8]}>
                        {CAMPOS.map((c) => (
                          <Col key={c.key} xs={12} md={8}>
                            <Text>{c.label}{c.obligatorio ? ' *' : ''}</Text>
                            <Select style={{ width: '100%' }} allowClear={!c.obligatorio} value={mapeo[c.key]}
                              onChange={(v) => setMapeo((m) => ({ ...m, [c.key]: v }))}
                              options={columnas.map((col) => ({ value: col, label: col }))} />
                          </Col>
                        ))}
                      </Row>
                    )}
                  </>
                )}
                <Button type="primary" loading={ocupado} onClick={() => enviar()}
                  disabled={!fichero || (formato === 'tabla' && !mapeoCompleto)}>
                  Importar en {ejercicio}
                </Button>
                {resultado && (
                  <Alert type="success" showIcon message={
                    resultado.formato === 'norma43'
                      ? `Cuenta ${resultado.cuenta}: ${num(resultado.movimientos_fichero)} movimientos en el fichero; ` +
                        `${num(resultado.insertados)} insertados, ${num(resultado.ya_conciliados)} ya estaban conciliados ` +
                        `(se conservan), ${num(resultado.pendientes_sustituidos)} pendientes sustituidos. ` +
                        `Saldo inicial ${eur(resultado.saldo_inicial)} €, final ${eur(resultado.saldo_final)} €.`
                      : `${num(resultado.insertados)} movimientos insertados` +
                        (resultado.filas_descartadas ? `, ${num(resultado.filas_descartadas)} filas sin fecha o importe descartadas` : '')
                  } />
                )}
              </Space>
            </Col>
          </Row>
        </Card>
      )}

      <Card size="small" title={`Movimientos del extracto en ${ejercicio}`}>
        <Table<MovimientoBanco> size="small" rowKey="id" loading={extractos.isLoading} dataSource={extractos.data?.filas}
          scroll={{ x: 900 }}
          pagination={{
            current: pagina.page, pageSize: pagina.page_size, total: extractos.data?.total, showSizeChanger: true,
            showTotal: (t) => `${num(t)} movimientos`, onChange: (page, page_size) => setPagina({ page, page_size }),
          }}
          locale={{ emptyText: 'No hay movimientos importados para este banco y ejercicio' }}
          columns={[
            { title: 'Fecha', dataIndex: 'fecha_operacion', width: 100, render: fecha },
            { title: 'Valor', dataIndex: 'fecha_valor', width: 100, render: fecha },
            { title: 'Concepto', dataIndex: 'concepto', ellipsis: true },
            { title: 'Referencia', dataIndex: 'referencia', width: 160, ellipsis: true },
            { title: 'Importe', dataIndex: 'importe', width: 110, align: 'right', render: eur },
            { title: 'Saldo', dataIndex: 'saldo', width: 110, align: 'right', render: (s: number) => (s ? eur(s) : '') },
            { title: 'Conciliado', dataIndex: 'recon_level', width: 100,
              render: (n: string | null, r) => (r.reconciled ? `Nivel ${n}` : 'No') },
          ]}
        />
      </Card>
    </div>
  )
}
