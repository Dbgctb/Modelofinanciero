import { useMemo, useState } from 'react'
import { Alert, Button, Card, Checkbox, InputNumber, message, Space, Table, Typography } from 'antd'
import { CopyOutlined, DeleteOutlined, FileExcelOutlined, SearchOutlined } from '@ant-design/icons'
import { DuplicadoAsiento, herramientasApi, LineaAsiento } from '../../api/cierres'
import { apiError } from '../../utils/errorHandler'
import { descargarBlob, eur, fecha, num } from './comun'

const { Title, Paragraph, Text } = Typography

type Duplicado = DuplicadoAsiento & { lineas: LineaAsiento[] }

export default function AsientosDiferencias() {
  const [ejercicio, setEjercicio] = useState(new Date().getFullYear() - 1)
  const [numero, setNumero] = useState<number | null>(1)
  const [original, setOriginal] = useState<{ ejercicio: number; numero: number; lineas: LineaAsiento[] } | null>(null)
  const [nuevoEj, setNuevoEj] = useState(new Date().getFullYear() - 1)
  const [nuevoNum, setNuevoNum] = useState<number | null>(99999)
  const [invertir, setInvertir] = useState(false)
  const [duplicados, setDuplicados] = useState<Duplicado[]>([])
  const [sel, setSel] = useState<number[]>([])
  const [ocupado, setOcupado] = useState(false)

  const cargar = async () => {
    if (!numero) return
    try {
      const { data } = await herramientasApi.asiento(ejercicio, numero)
      setOriginal({ ejercicio, numero, lineas: data })
      setNuevoEj(ejercicio)
    } catch (e) {
      setOriginal(null)
      message.error(apiError(e))
    }
  }

  const vista = useMemo(() => (original?.lineas ?? []).map((l, i) => ({
    ...l, linea: i + 1,
    debe: invertir && l.debe ? -l.debe : l.debe, haber: invertir && l.haber ? -l.haber : l.haber,
  })), [original, invertir])

  const duplicar = () => {
    if (!original || !nuevoNum) return
    setDuplicados((d) => [...d, {
      origen_ejercicio: original.ejercicio, origen_numero: original.numero,
      ejercicio: nuevoEj, numero: nuevoNum, invertido: invertir, lineas: vista,
    }])
    message.success(`Asiento ${nuevoNum} (${nuevoEj}) añadido a la lista`)
  }

  const exportar = async () => {
    setOcupado(true)
    try {
      const { data } = await herramientasApi.excelDiferencias(duplicados.map(({ lineas: _l, ...d }) => d))
      descargarBlob(data as Blob, `Asientos_Diferencias_${duplicados[duplicados.length - 1].ejercicio}.xlsx`)
    } catch (e) {
      message.error(apiError(e, 'No se pudo generar el Excel'))
    } finally {
      setOcupado(false)
    }
  }

  const totales = (ls: LineaAsiento[]) => {
    const d = ls.reduce((a, l) => a + (l.debe || 0), 0)
    const h = ls.reduce((a, l) => a + (l.haber || 0), 0)
    return `${num(ls.length)} líneas · Debe ${eur(d)} € · Haber ${eur(h)} € · Diferencia ${eur(d - h)} €`
  }

  const columnas = [
    { title: 'Línea', dataIndex: 'linea', width: 70 },
    { title: 'Cuenta', dataIndex: 'cuenta', width: 120 },
    { title: 'Debe', dataIndex: 'debe', width: 115, align: 'right' as const, render: eur },
    { title: 'Haber', dataIndex: 'haber', width: 115, align: 'right' as const, render: eur },
    { title: 'Concepto', dataIndex: 'concepto', ellipsis: true },
  ]

  return (
    <div>
      <Title level={3}>Asientos de diferencias</Title>
      <Paragraph type="secondary">
        Carga un asiento, duplícalo (igual o con el signo invertido) con otro ejercicio y número, y exporta los duplicados
        al Excel de importación de asientos del ERP. No se modifica nada en el diario.
      </Paragraph>

      <Card size="small" title="1. Asiento de origen" style={{ marginBottom: 16 }}>
        <Space wrap style={{ marginBottom: 12 }}>
          <Text>Ejercicio:</Text><InputNumber min={2000} max={2100} value={ejercicio} onChange={(v) => v && setEjercicio(v)} />
          <Text>Nº asiento:</Text><InputNumber min={1} max={999999} value={numero} onChange={setNumero} />
          <Button type="primary" icon={<SearchOutlined />} onClick={cargar}>Cargar</Button>
        </Space>
        {original && (
          <>
            <Text strong>Asiento {original.numero} de {original.ejercicio}: {totales(original.lineas)}</Text>
            <Table<LineaAsiento> size="small" rowKey={(l) => `${l.linea}-${l.cuenta}`} pagination={false}
              dataSource={original.lineas} scroll={{ x: 800, y: 300 }} style={{ marginTop: 8 }}
              columns={[...columnas.slice(0, 1), { title: 'Serie', dataIndex: 'serie', width: 60 },
                { title: 'Fecha', dataIndex: 'fecha', width: 95, render: fecha }, ...columnas.slice(1)]} />
          </>
        )}
      </Card>

      {original && (
        <Card size="small" title="2. Duplicar" style={{ marginBottom: 16 }}>
          <Space wrap style={{ marginBottom: 12 }}>
            <Text>Nuevo ejercicio:</Text><InputNumber min={2000} max={2100} value={nuevoEj} onChange={(v) => v && setNuevoEj(v)} />
            <Text>Nuevo nº:</Text><InputNumber min={1} max={999999} value={nuevoNum} onChange={setNuevoNum} />
            <Checkbox checked={invertir} onChange={(e) => setInvertir(e.target.checked)}>Invertir (signo negativo en Debe y Haber)</Checkbox>
            <Button type="primary" icon={<CopyOutlined />} disabled={!nuevoNum} onClick={duplicar}>Añadir a la lista</Button>
          </Space>
          <Text>Vista previa ({invertir ? 'invertido' : 'copia exacta'}, fecha 01/01/{nuevoEj}): {totales(vista)}</Text>
          <Table size="small" rowKey="linea" pagination={false} dataSource={vista} columns={columnas}
            scroll={{ x: 700, y: 300 }} style={{ marginTop: 8 }} />
        </Card>
      )}

      <Card size="small" title={`3. Asientos para exportar (${duplicados.length})`}>
        {!duplicados.length ? (
          <Alert type="info" showIcon message="Aún no hay asientos en la lista. Se pierde al salir de la pantalla, como en el programa anterior." />
        ) : (
          <>
            <Space style={{ marginBottom: 12 }}>
              <Button icon={<DeleteOutlined />} disabled={!sel.length}
                onClick={() => { setDuplicados((d) => d.filter((_, i) => !sel.includes(i))); setSel([]) }}>
                Quitar seleccionados
              </Button>
              <Button type="primary" icon={<FileExcelOutlined />} loading={ocupado} onClick={exportar}>Exportar a Excel</Button>
            </Space>
            <Table size="small" rowKey={(_, i) => i!} pagination={false}
              dataSource={duplicados.map((d, i) => ({ ...d, key: i }))}
              rowSelection={{ selectedRowKeys: sel, onChange: (k) => setSel(k as number[]) }}
              columns={[
                { title: 'Ejercicio', dataIndex: 'ejercicio' },
                { title: 'Nº asiento', dataIndex: 'numero' },
                { title: 'Líneas', render: (_: unknown, d: Duplicado) => d.lineas.length },
                { title: 'Invertido', dataIndex: 'invertido', render: (v: boolean) => (v ? 'Sí' : 'No') },
                { title: 'Origen', render: (_: unknown, d: Duplicado) => `${d.origen_ejercicio} / ${d.origen_numero}` },
              ]} />
          </>
        )}
      </Card>
    </div>
  )
}
