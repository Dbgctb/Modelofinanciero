import type { AxiosError } from 'axios'

// ─── Catálogo de errores ───────────────────────────────────────────────────
// Mapea el campo `detail` del backend a mensajes en español amigables.
// Soporta coincidencia exacta y coincidencia parcial (startsWith).
const CATALOG: Record<string, string> = {
  // Auth
  'Credenciales incorrectas': 'Usuario o contraseña incorrectos',
  'Token inválido o expirado': 'Tu sesión ha expirado. Vuelve a iniciar sesión',
  'No autenticado': 'Debes iniciar sesión para continuar',

  // Mapeo de cuentas
  'Ya existe un mapeo para esa cuenta': 'Esta cuenta ya está configurada en el sistema',
  'Ya existe un mapeo para esta cuenta': 'Esta cuenta ya está configurada en el sistema',
  'Las cuentas de ingreso requieren compañía':
    'Las cuentas de tipo Ingreso deben tener una compañía asignada',
  'Las cuentas de gasto requieren familia de gasto':
    'Las cuentas de tipo Gasto deben tener una familia de gasto asignada',
  'Mapeo no encontrado': 'No se encontró el mapeo de cuenta solicitado',

  // Errores de validación Pydantic (422) — enum tipo cuenta
  "Input should be 'ingreso', 'gasto' or 'tesoreria_excluida'":
    "El campo 'tipo' debe ser exactamente: ingreso, gasto o tesoreria_excluida (en minúsculas)",

  // Carga de datos
  'El archivo está vacío': 'El archivo seleccionado está vacío. Comprueba el fichero antes de subirlo',
  'Error procesando el archivo': 'No se pudo procesar el archivo. Verifica que el formato sea correcto',
  'Carga no encontrada': 'No se encontró la carga solicitada',

  // Incidencias
  'Incidencia no encontrada': 'No se encontró la incidencia solicitada',

  // Presupuesto / genéricos
  'Not Found': 'El recurso solicitado no existe',
  'Forbidden': 'No tienes permisos para realizar esta acción',
  'Internal Server Error': 'Error interno del servidor. Contacta con el administrador',
}

function translateMsg(msg: string): string {
  if (CATALOG[msg]) return CATALOG[msg]
  // Coincidencia parcial para mensajes que empiezan por una clave conocida
  for (const [key, val] of Object.entries(CATALOG)) {
    if (msg.startsWith(key)) return val
  }
  return msg
}

// Pydantic validation error shape (FastAPI 422)
type ValidationDetail = { msg: string; loc?: (string | number)[] }
type ApiErrorShape = { detail?: string | ValidationDetail[] }

/**
 * Extrae el mensaje de error de una respuesta Axios / FastAPI.
 *
 * Cubre tres formas que puede tener `detail`:
 *  1. String literal → busca en el catálogo y lo devuelve
 *  2. Array de objetos Pydantic (422) → concatena los mensajes
 *  3. Sin detail → usa el fallback
 */
export function apiError(error: unknown, fallback = 'Error inesperado. Inténtalo de nuevo'): string {
  const e = error as AxiosError<ApiErrorShape>

  if (!e?.response) {
    if (e?.message === 'Network Error') return 'No hay conexión con el servidor'
    return fallback
  }

  const detail = e.response.data?.detail

  if (!detail) {
    // Errores HTTP sin body (401, 403, 404 sin detail...)
    const status = e.response.status
    if (status === 401) return 'Sesión expirada. Vuelve a iniciar sesión'
    if (status === 403) return 'No tienes permisos para realizar esta acción'
    if (status === 404) return 'El recurso solicitado no existe'
    return fallback
  }

  if (typeof detail === 'string') {
    return translateMsg(detail)
  }

  if (Array.isArray(detail)) {
    // Deduplicar: muchas filas pueden tener el mismo error
    const unique = [...new Set(detail.map(d => translateMsg(d.msg)))]
    const total = detail.length
    if (unique.length === 1 && total > 1) {
      return `${unique[0]} (${total} filas afectadas)`
    }
    return unique.join(' · ')
  }

  return fallback
}
