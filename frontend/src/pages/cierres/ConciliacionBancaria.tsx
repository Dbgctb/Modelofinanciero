import { useEffect, useState } from 'react'
import { Alert, Card, InputNumber, Select, Space, Tabs, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { bancoApi } from '../../api/cierres'
import ImportarExtracto from './banco/ImportarExtracto'
import EjecutarBanco from './banco/EjecutarBanco'
import PendientesBanco from './banco/PendientesBanco'
import ConciliadosBanco from './banco/ConciliadosBanco'
import BancosConfig from './banco/BancosConfig'

const { Title, Paragraph, Text } = Typography

export default function ConciliacionBancaria() {
  const [bancoId, setBancoId] = useState<number | undefined>()
  const [ejercicio, setEjercicio] = useState<number>(new Date().getFullYear() - 1)
  const [pestana, setPestana] = useState('ejecutar')

  const bancos = useQuery({ queryKey: ['cierres', 'bancos'], queryFn: () => bancoApi.getBancos().then((r) => r.data) })
  const activos = (bancos.data ?? []).filter((b) => b.activo)
  useEffect(() => {
    if (bancoId === undefined && activos.length) setBancoId(activos[0].id)
  }, [activos, bancoId])
  const banco = activos.find((b) => b.id === bancoId)

  const necesitaBanco = (contenido: JSX.Element) =>
    banco ? contenido : <Alert type="info" showIcon message="Elige un banco (o créalo en la pestaña Bancos y configuración)." />

  return (
    <div>
      <Title level={3}>Conciliación bancaria</Title>
      <Paragraph type="secondary">
        Cruza los movimientos del extracto del banco con los apuntes de su cuenta 572 en el diario.
      </Paragraph>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Text>Banco:</Text>
          <Select style={{ minWidth: 300 }} value={bancoId} onChange={setBancoId} loading={bancos.isLoading}
            placeholder="Elige un banco"
            options={activos.map((b) => ({ value: b.id!, label: `${b.nombre} (${b.cuenta_572})` }))} />
          <Text>Ejercicio:</Text>
          <InputNumber min={2000} max={2100} value={ejercicio} onChange={(v) => v && setEjercicio(v)} />
          {banco?.iban && <Text type="secondary">IBAN {banco.iban}</Text>}
        </Space>
      </Card>
      <Tabs activeKey={pestana} onChange={setPestana} destroyInactiveTabPane items={[
        { key: 'importar', label: '1. Importar extracto',
          children: necesitaBanco(<ImportarExtracto bancoId={bancoId!} ejercicio={ejercicio} />) },
        { key: 'ejecutar', label: '2. Ejecutar conciliación',
          children: necesitaBanco(<EjecutarBanco bancoId={bancoId!} ejercicio={ejercicio} onIrPendientes={() => setPestana('pendientes')} />) },
        { key: 'pendientes', label: '3. Pendientes',
          children: necesitaBanco(<PendientesBanco bancoId={bancoId!} ejercicio={ejercicio} />) },
        { key: 'conciliados', label: '4. Conciliados',
          children: necesitaBanco(<ConciliadosBanco bancoId={bancoId!} ejercicio={ejercicio} />) },
        { key: 'bancos', label: '5. Bancos y configuración', children: <BancosConfig bancoId={bancoId} /> },
      ]} />
    </div>
  )
}
