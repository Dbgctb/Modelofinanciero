import type { AxiosError } from 'axios'

// ─── Traducción de mensajes sin código ─────────────────────────────────────
// Los errores propios del backend ya llegan como "[CODIGO] mensaje en español"
// (catálogo único en backend/app/core/errores.py, documentado en
// docs/CATALOGO_ERRORES.md) y se muestran tal cual. Aquí solo quedan los textos
// genéricos que generan FastAPI/Pydantic, que no pasan por ese catálogo.
const CATALOG: Record<string, string> = {
  'No autenticado': 'Debes iniciar sesión para continuar',
  'Not authenticated': 'Debes iniciar sesión para continuar',

  // Errores de validación Pydantic (422) — enum tipo cuenta
  "Input should be 'ingreso', 'gasto' or 'tesoreria_excluida'":
    "El campo 'tipo' debe ser exactamente: ingreso, gasto o tesoreria_excluida (en minúsculas)",

  'Not Found': 'El recurso solicitado no existe',
  'Forbidden': 'No tienes permisos para realizar esta acción',
  'Internal Server Error': 'Error interno del servidor. Contacta con el administrador',
}

function translateMsg(msg: string): string {
  // Pydantic antepone "Value error, " a los ValueError de los validadores (p. ej. [AUTH-011])
  if (msg.startsWith('Value error, ')) msg = msg.slice('Value error, '.length)
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
