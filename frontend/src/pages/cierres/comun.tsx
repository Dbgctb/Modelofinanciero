import { useEffect, useRef, useState } from 'react'
import { Alert, Progress, Tag } from 'antd'
import { cierresApi, Tarea } from '../../api/cierres'
import { useAuthStore } from '../../store/authStore'
import { apiError } from '../../utils/errorHandler'

/** Formato de euros en español: 1.234,56 */
export const eur = (n: number | null | undefined) =>
  n == null ? '' : n.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export const num = (n: number | null | undefined) => (n == null ? '' : n.toLocaleString('es-ES'))

export const fecha = (f: string | null | undefined) => (f ? f.slice(0, 10).split('-').reverse().join('/') : '')

/** admin y gestor pueden modificar; lector solo consulta. */
export function usePuedeEditar() {
  const role = useAuthStore((s) => s.user?.role)
  return role === 'admin' || role === 'gestor'
}

/** Descarga un Blob recibido de la API como fichero. */
export function descargarBlob(data: Blob, nombre: string) {
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = nombre
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * Sigue una tarea en segundo plano del módulo Cierres (consulta cada 1,5 s).
 * Llama a `alTerminar` una sola vez cuando acaba bien.
 */
export function useTarea(taskId: string | null, alTerminar?: (t: Tarea) => void) {
  const [tarea, setTarea] = useState<Tarea | null>(null)
  const [errorConsulta, setErrorConsulta] = useState<string | null>(null)
  const cb = useRef(alTerminar)
  cb.current = alTerminar

  useEffect(() => {
    if (!taskId) {
      setTarea(null)
      return
    }
    setErrorConsulta(null)
    let parar = false
    const consultar = async () => {
      try {
        const { data } = await cierresApi.getTarea(taskId)
        if (parar) return
        setTarea(data)
        if (data.estado === 'en_curso') {
          setTimeout(consultar, 1500)
        } else if (data.estado === 'terminada') {
          cb.current?.(data)
        }
      } catch (e) {
        if (!parar) setErrorConsulta(apiError(e, 'No se pudo consultar el progreso'))
      }
    }
    consultar()
    return () => {
      parar = true
    }
  }, [taskId])

  return { tarea, enCurso: !!taskId && (!tarea || tarea.estado === 'en_curso'), errorConsulta }
}

/** Barra de progreso / resultado de una tarea. */
export function EstadoTarea({ tarea, errorConsulta }: { tarea: Tarea | null; errorConsulta?: string | null }) {
  if (errorConsulta) return <Alert type="error" showIcon message={errorConsulta} style={{ marginBottom: 12 }} />
  if (!tarea) return null
  if (tarea.estado === 'error')
    return <Alert type="error" showIcon message="La operación ha fallado" description={tarea.error} style={{ marginBottom: 12 }} />
  if (tarea.estado === 'terminada')
    return (
      <Alert type="success" showIcon style={{ marginBottom: 12 }}
        message={`Terminado${tarea.segundos != null ? ` en ${num(Math.round(tarea.segundos))} s` : ''}`} />
    )
  const pct = tarea.total ? Math.round(((tarea.paso || 0) / tarea.total) * 100) : undefined
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ marginBottom: 4 }}>{tarea.mensaje}</div>
      <Progress percent={pct ?? 100} status="active" showInfo={pct != null} />
    </div>
  )
}

export function TagPunteo({ a }: { a: { reconciled: boolean; recon_rule: string | null } }) {
  return a.reconciled ? <Tag color="green">{a.recon_rule || 'Sí'}</Tag> : <Tag>No</Tag>
}
