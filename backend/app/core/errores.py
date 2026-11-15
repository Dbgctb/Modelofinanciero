"""Catálogo único de errores de la aplicación: código, estado HTTP, mensaje y solución.

Cada error que ve el usuario sale de aquí con la forma "[CODIGO] mensaje", para que
cualquier aviso en pantalla se pueda buscar en docs/CATALOGO_ERRORES.md.

Uso:
- Servicios (lógica de negocio):  raise ErrorApp("CC-IMP-003", faltan="Fecha", encontradas="...")
  ErrorApp hereda de ValueError: todo lo que ya captura ValueError (routers de Cierres,
  tareas en segundo plano, validadores de Pydantic) sigue funcionando igual.
- Routers (HTTP):                  raise error_http("USR-003")
  Devuelve un HTTPException con el estado del catálogo.
- Texto suelto (otra excepción):   texto("CC-GEN-001")

`codigo` es solo posicional: un mensaje puede tener su propio parámetro {codigo} (CC-PUN-002).

Para añadir un error: nueva entrada aquí (código sin repetir dentro de su prefijo) y
regenerar la documentación con `python scripts/catalogo_errores.py --escribir`.
El mismo script, sin argumentos, comprueba que catálogo, código y documento cuadran.

Este módulo no importa nada de la aplicación: lo usa también core/config.py al arrancar.
"""
import logging
from dataclasses import dataclass

from fastapi import HTTPException

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntradaError:
    codigo: str
    http: int
    mensaje: str      # plantilla str.format con los parámetros del error
    solucion: str     # qué hacer; solo va al documento, no a la pantalla
    area: str


# Nota: los routers de Cierres devuelven todos los errores de servicio como 400 (_400), por eso
# sus "no existe" figuran con 400 y no con 404.

# (prefijo, nombre del área para el documento)
AREAS = {
    "GEN": "General",
    "CFG": "Configuración del servidor",
    "ARC": "Subida de archivos (común)",
    "AUTH": "Autenticación",
    "USR": "Usuarios",
    "MAP": "Mapeo de cuentas",
    "CAR": "Carga de datos",
    "ADM": "Administración",
    "ANA": "Analítico",
    "CRS": "Cross-selling",
    "PRE": "Presupuesto",
    "REA": "Seguimiento real",
    "TES": "Tesorería",
    "CC-GEN": "Cierres · general",
    "CC-IMP": "Cierres · importar diario",
    "CC-PUN": "Cierres · punteo automático y controles",
    "CC-MAN": "Cierres · punteo manual",
    "CC-REC": "Cierres · recobros",
    "CC-DIF": "Cierres · asientos de diferencias",
    "CC-BAN": "Cierres · conciliación bancaria",
}

_PASSWORD = ("La contraseña debe tener al menos 10 caracteres, una mayúscula, una minúscula, "
             "un número y un carácter especial")
_COLUMNAS = "Columnas requeridas no encontradas: {faltan}. Columnas detectadas: {detectadas}"

_ENTRADAS = [
    # ── General ──────────────────────────────────────────────────────────────
    ("GEN-001", 500, "Error interno del servidor. Contacta con el administrador.",
     "Fallo no previsto. El detalle completo está en backend/app.log buscando la hora del error."),
    ("GEN-002", 500, "Error interno. Revisa el log del servidor.",
     "Una tarea en segundo plano falló de forma no prevista. Detalle en backend/app.log."),
    ("GEN-003", 403, "No tienes permisos para esta acción",
     "Tu rol no permite esta operación. Pide a un administrador que revise tu rol."),
    ("GEN-004", 422, "Los datos no tienen el formato esperado. Revisa el fichero o los valores introducidos.",
     "Error de validación sin código propio (p. ej. un texto en una columna numérica de un fichero). "
     "El detalle técnico está en backend/app.log."),

    # ── Configuración (al arrancar el backend) ───────────────────────────────
    ("CFG-001", 500, "SECRET_KEY debe tener al menos 32 caracteres",
     "Pon en backend/.env una SECRET_KEY aleatoria de 64 caracteres."),
    ("CFG-002", 500, "ALLOWED_ORIGINS no puede contener '*' — especifica dominios concretos",
     "Lista en ALLOWED_ORIGINS solo los dominios del frontend (p. ej. http://localhost:5173)."),
    ("CFG-003", 500, "ALGORITHM no válido ({valor}): debe ser HS256, HS384 o HS512",
     "Pon ALGORITHM=HS256 en backend/.env."),
    ("CFG-004", 500, "La base de datos está en la revisión {actual} y el código espera {esperada}",
     "Haz copia de seguridad y aplica las migraciones desde backend/: "
     "venv\\Scripts\\python -m alembic upgrade head. Si la base es anterior a la migración base "
     "(revisión e0af6e045937), ver la cabecera de alembic/versions/0001_base_esquema_completo.py."),

    # ── Archivos (común a todas las cargas) ──────────────────────────────────
    ("ARC-001", 400, "El archivo seleccionado está vacío. Comprueba el fichero antes de subirlo",
     "El fichero subido tiene 0 bytes. Vuelve a exportarlo desde el origen."),
    ("ARC-002", 415, "Tipo de archivo no permitido. Se esperaba {esperado}.",
     "Sube el fichero en el formato indicado en el mensaje."),
    ("ARC-003", 413, "Archivo demasiado grande (máximo {max_mb} MB).",
     "Divide el fichero o exporta un periodo más corto."),

    # ── Autenticación ────────────────────────────────────────────────────────
    ("AUTH-001", 401, "Usuario o contraseña incorrectos",
     "Revisa usuario y contraseña. Tras varios intentos fallidos la cuenta se bloquea un tiempo."),
    ("AUTH-002", 423, "Cuenta bloqueada. Inténtalo en {minutos} minutos",
     "Espera a que termine el bloqueo o pide a un administrador que restablezca la contraseña."),
    ("AUTH-003", 423, "Cuenta bloqueada por {minutos} minutos tras demasiados intentos fallidos",
     "Espera a que termine el bloqueo o usa '¿Olvidaste tu contraseña?'."),
    ("AUTH-004", 401, "Tu sesión no es válida o ha caducado. Vuelve a iniciar sesión",
     "Vuelve a iniciar sesión."),
    ("AUTH-005", 401, "El usuario de la sesión ya no existe",
     "Vuelve a iniciar sesión; si persiste, el usuario fue borrado."),
    ("AUTH-006", 401, "Refresh token inválido",
     "Vuelve a iniciar sesión."),
    ("AUTH-007", 401, "Refresh token revocado o inválido",
     "Vuelve a iniciar sesión (la sesión se cerró en otro sitio o caducó)."),
    ("AUTH-008", 401, "Usuario inactivo",
     "Un administrador debe reactivar el usuario en Usuarios."),
    ("AUTH-009", 400, "Contraseña actual incorrecta",
     "Escribe la contraseña con la que has entrado."),
    ("AUTH-010", 400, "El enlace no es válido o ha caducado. Pide uno nuevo.",
     "Los enlaces de restablecimiento duran 60 minutos y valen una sola vez."),
    ("AUTH-011", 400, _PASSWORD,
     "Elige una contraseña que cumpla todos los requisitos del mensaje."),

    # ── Usuarios ─────────────────────────────────────────────────────────────
    ("USR-001", 400, "El email ya está registrado", "Usa otro email o edita el usuario existente."),
    ("USR-002", 400, "El usuario ya existe", "Elige otro nombre de usuario."),
    ("USR-003", 404, "Usuario no encontrado", "Recarga la lista de usuarios."),
    ("USR-004", 400, "No puedes desactivar tu propia cuenta", "Pide a otro administrador que lo haga."),
    ("USR-005", 400, "No puedes eliminarte a ti mismo", "Pide a otro administrador que lo haga."),
    ("USR-006", 404, "Solicitud no encontrada", "La solicitud ya se usó o se borró; recarga la lista."),
    ("USR-007", 400, "El usuario debe tener al menos 3 caracteres", "Elige un nombre de usuario más largo."),
    ("USR-008", 400, "El usuario solo puede contener letras, números, _ y .", "Quita espacios y símbolos."),

    # ── Mapeo de cuentas ─────────────────────────────────────────────────────
    ("MAP-001", 400, "Esta cuenta ya está configurada en el mapeo", "Edita el mapeo existente en lugar de crear otro."),
    ("MAP-002", 404, "Mapeo no encontrado", "Recarga la lista de mapeos."),
    ("MAP-003", 400, "Las cuentas de tipo Ingreso deben tener una compañía asignada", "Elige la compañía."),
    ("MAP-004", 400, "Las cuentas de tipo Gasto deben tener una familia de gasto asignada", "Elige la familia de gasto."),

    # ── Carga de datos ───────────────────────────────────────────────────────
    ("CAR-001", 422, "Error procesando el archivo. Revisa el formato e inténtalo de nuevo.",
     "El fichero no tiene el formato esperado. El detalle técnico está en backend/app.log."),
    ("CAR-002", 404, "Carga histórica no encontrada", "Recarga la lista de cargas."),
    ("CAR-003", 404, "Carga no encontrada", "Recarga la lista de cargas."),
    ("CAR-004", 404, "No hay cargas para el ejercicio {ejercicio}", "Comprueba el ejercicio elegido."),
    ("CAR-005", 404, "Incidencia no encontrada", "Recarga la lista de incidencias."),
    ("CAR-006", 400, "Solo se pueden cerrar cargas de tipo base presupuestaria", "Elige una carga base presupuestaria."),
    ("CAR-007", 400, "La carga ya está cerrada", "No hace falta volver a cerrarla."),
    ("CAR-008", 409, "Hay {n} incidencias críticas pendientes. Resuélvelas antes de cerrar.",
     "Resuelve las incidencias críticas de la carga y vuelve a cerrarla."),
    ("CAR-009", 404, "Carga de recibos no encontrada", "Recarga la lista de cargas."),

    # ── Administración ───────────────────────────────────────────────────────
    ("ADM-001", 404, "Tasa no encontrada", "Recarga la lista de tasas."),
    ("ADM-002", 404, "No hay tasas ICEA con fuente verificada para el año {anyo} en el catálogo interno.",
     "Introduce las tasas de ese año a mano."),
    ("ADM-003", 400, "Ya existe una comisión para ese auxiliar en ese año", "Edita la comisión existente."),
    ("ADM-004", 404, "Registro no encontrado", "Recarga la lista."),
    ("ADM-005", 422, "No se pudo leer el archivo. Debe ser un CSV con columnas auxiliar y comisión colaborador.",
     "Revisa separador y columnas del CSV."),
    ("ADM-006", 422, _COLUMNAS, "Renombra las columnas del fichero como indica el mensaje."),
    ("ADM-007", 400, "Confirmación incorrecta: escribe {frase} para borrar los datos",
     "El reset exige la frase de confirmación también en el servidor. Haz antes una copia de seguridad."),

    # ── Analítico ────────────────────────────────────────────────────────────
    ("ANA-001", 400, "Naturaleza inválida. Valores posibles: {valores}", "Elige una de las naturalezas listadas."),
    ("ANA-002", 404, "Cuenta no encontrada", "Recarga la lista de cuentas."),
    ("ANA-003", 400, "Driver inválido. Valores posibles: {valores}", "Elige uno de los drivers listados."),
    ("ANA-004", 404, "Tarea no encontrada o expirada", "El servidor se reinició o la tarea caducó; lánzala de nuevo."),
    ("ANA-005", 404, "Ajuste no encontrado", "Recarga la lista de ajustes."),

    # ── Cross-selling ────────────────────────────────────────────────────────
    ("CRS-001", 500, "Error al recalcular. Revisa los logs.", "Detalle en backend/app.log."),
    ("CRS-002", 500, "Error al calcular estadísticas de ramo.", "Detalle en backend/app.log."),
    ("CRS-003", 422, "Error procesando el archivo de clientes.", "Revisa el formato (ver CLAUDE.md del proyecto). Detalle en backend/app.log."),
    ("CRS-004", 404, "Acción no encontrada", "Recarga la lista de acciones."),
    ("CRS-005", 422, "No se pudo leer el archivo. Asegúrate de que es CSV o Excel.", "Exporta de nuevo el fichero de clientes."),
    ("CRS-006", 422, _COLUMNAS, "Columnas esperadas: Código;Nombre;F.Alta;F.Nacimie;Fis/Jur;T. Fijo;T. Móvil;E-Mail."),

    # ── Presupuesto ──────────────────────────────────────────────────────────
    ("PRE-001", 404, "Presupuesto no encontrado", "Recarga la página o elige otro presupuesto."),
    ("PRE-002", 409, "El ejercicio {ejercicio} no está cerrado. Cierra primero la carga base antes de presupuestar.",
     "En Carga de datos, cierra la carga base del ejercicio."),
    ("PRE-003", 400, "La línea está bloqueada tras aprobación", "Reabre el presupuesto para modificarla."),
    ("PRE-004", 400, "No hay líneas de ingresos generadas", "Genera primero las líneas de ingresos."),
    ("PRE-005", 400, "El presupuesto de ingresos ya está abierto", "No hace falta reabrirlo."),
    ("PRE-006", 400, "El mes debe estar entre 1 y 12", "Elige un mes válido."),
    ("PRE-007", 409, "Hay {n} líneas de gasto sin familia asignada", "Asigna familia a todas las líneas de gasto."),
    ("PRE-008", 400, "Solo se pueden reabrir gastos cuando están aprobados, la tesorería aprobada o el presupuesto cerrado",
     "Revisa el estado del presupuesto."),
    ("PRE-009", 400, "El presupuesto ya está cerrado", "No hace falta volver a cerrarlo."),
    ("PRE-010", 400, "No se puede cerrar un presupuesto en borrador", "Aprueba antes el presupuesto."),
    ("PRE-011", 400, "El presupuesto debe estar cerrado (estado actual: {estado})", "Cierra antes el presupuesto."),
    ("PRE-012", 404, "Cesión no encontrada", "Recarga la lista de cesiones."),
    ("PRE-013", 400, "Cesión bloqueada", "Reabre el presupuesto para modificarla."),
    ("PRE-014", 404, "Línea no encontrada", "Recarga la página."),
    ("PRE-015", 400, "El presupuesto está cerrado", "Un presupuesto cerrado no se puede modificar."),
    ("PRE-016", 422, "Columna 'Auxiliar' requerida no encontrada", "Añade la columna Auxiliar al fichero."),
    ("PRE-017", 422, "Columnas requeridas no encontradas: {faltan}", "Añade las columnas indicadas al fichero."),

    # ── Seguimiento real ─────────────────────────────────────────────────────
    ("REA-001", 400, "El mes no tiene carga vinculada", "Vincula una carga al mes antes de cerrarlo."),
    ("REA-002", 409, "Hay incidencias críticas pendientes en este mes", "Resuelve las incidencias críticas del mes."),
    ("REA-003", 404, "Mes no encontrado", "Recarga la página."),

    # ── Tesorería ────────────────────────────────────────────────────────────
    ("TES-001", 404, "Apunte no encontrado", "Recarga la página."),
    ("TES-002", 404, "Empleado no encontrado", "Recarga la lista de empleados."),
    ("TES-003", 404, "Aún no se ha calculado la tesorería", "Pulsa Calcular."),
    ("TES-004", 400, "Calcula la tesorería antes de aprobarla", "Pulsa Calcular y después Aprobar."),

    # ── Cierres · general ────────────────────────────────────────────────────
    ("CC-GEN-001", 409, "Ya hay una importación o un punteo en curso. Espera a que termine.",
     "Solo puede haber una tarea que escriba a la vez. Espera a que acabe la que está en marcha."),
    ("CC-GEN-002", 404, "Tarea no encontrada (¿se reinició el servidor?)",
     "Las tareas viven en memoria: si el backend se reinicia se pierden. Lánzala de nuevo."),
    ("CC-GEN-003", 404, "El fichero ya no está disponible; vuelve a generarlo.",
     "Los Excel generados son temporales. Genera de nuevo la exportación."),

    # ── Cierres · importar diario ────────────────────────────────────────────
    ("CC-IMP-001", 400, "No se reconoce la codificación del fichero (ni UTF-8 ni Windows-1252).",
     "Exporta de nuevo el diario desde el ERP sin cambiar la codificación."),
    ("CC-IMP-002", 400, "Formato no soportado: .{ext} (usa Excel o TXT/CSV)",
     "Sube el diario como .xlsx, .xls, .txt o .csv."),
    ("CC-IMP-003", 400, "Este fichero no es el diario exportado del ERP: le faltan las columnas {faltan}. "
                        "Columnas encontradas: {encontradas}.",
     "Exporta el diario desde el ERP. Columnas obligatorias: Linea, Serie, Numero, Ejercicio, Fecha, Debe, "
     "Haber, Numero de Cuenta y Concepto. Los ficheros intermedios excel_AAAA.csv del programa antiguo "
     "no valen (no tienen Fecha, Debe ni Haber)."),
    ("CC-IMP-004", 400, "El diario en TXT/CSV debe ir separado por '|' y este fichero usa '{separador}'.",
     "Exporta el diario desde el ERP con el separador | o súbelo en Excel."),
    ("CC-IMP-005", 400, "No se pudo leer el fichero ({tipo}). Comprueba que es el diario exportado del ERP.",
     "El fichero está dañado o tiene datos no numéricos en Linea, Numero, Ejercicio o Numero de Cuenta. "
     "Detalle en backend/app.log."),
    ("CC-IMP-006", 400, "Hay {n} filas con fecha inválida; revisa el fichero.",
     "Corrige o quita las filas sin fecha (formato dd/mm/aaaa)."),
    ("CC-IMP-007", 400, "El fichero no contiene datos con ejercicio válido.",
     "La columna Ejercicio está vacía; exporta de nuevo el diario."),
    ("CC-IMP-008", 400, "El fichero no contiene el ejercicio {ejercicio} (contiene: {ejercicios}). "
                        "No se ha borrado ni importado nada.",
     "Elige en pantalla uno de los ejercicios que contiene el fichero."),
    ("CC-IMP-009", 400, "El fichero no contiene datos del ejercicio {ejercicio}.",
     "Elige en pantalla el ejercicio que contiene el fichero."),

    # ── Cierres · punteo automático y controles ──────────────────────────────
    ("CC-PUN-001", 400, "Elige al menos un ejercicio.", "Marca uno o más ejercicios."),
    ("CC-PUN-002", 400, "Regla desconocida: {codigo}", "Recarga la lista de reglas."),
    ("CC-PUN-003", 400, "La tolerancia debe estar entre 0 y 10.000 €", "Pon una tolerancia dentro del rango."),
    ("CC-PUN-004", 400, "Tipo de control no válido (C, D, K o L)", "Elige uno de los tipos de control."),
    ("CC-PUN-005", 400, "La cuenta debe ser numérica (se usa como prefijo; en D, exacta)", "Escribe solo dígitos."),
    ("CC-PUN-006", 400, "El control C necesita mínimo y máximo de movimientos (mínimo ≤ máximo)", "Rellena ambos valores."),
    ("CC-PUN-007", 400, "El control D necesita una tolerancia en %", "Rellena la tolerancia."),
    ("CC-PUN-008", 400, "La cuenta de control no existe", "Recarga la lista de cuentas de control."),
    ("CC-PUN-009", 400, "Cuenta no válida en el filtro: {cuenta} (solo dígitos y *)", "Corrige el filtro de cuentas."),
    ("CC-PUN-010", 400, "Control desconocido", "Recarga la página y elige controles de la lista."),

    # ── Cierres · punteo manual ──────────────────────────────────────────────
    ("CC-MAN-001", 400, "La cuenta solo admite dígitos y *", "Corrige el filtro de cuenta."),
    ("CC-MAN-002", 400, "Hay {n} apuntes con esos filtros; acota la búsqueda (máximo {maximo}).",
     "Añade filtros (cuenta, fechas, importe) para reducir la selección."),
    ("CC-MAN-003", 400, "Selecciona al menos 2 apuntes.", "Marca dos o más apuntes."),
    ("CC-MAN-004", 400, "Algún apunte seleccionado ya no existe; vuelve a buscar.", "Repite la búsqueda."),
    ("CC-MAN-005", 400, "{n} de los apuntes seleccionados ya están punteados; quítalos de la selección.",
     "Desmarca los apuntes ya punteados."),
    ("CC-MAN-006", 400, "Los apuntes deben ser de la MISMA cuenta. Seleccionadas: {cuentas}", "Selecciona apuntes de una sola cuenta."),
    ("CC-MAN-007", 400, "La suma ({suma:.2f} €) supera la tolerancia (±{tolerancia:.2f} €).",
     "Ajusta la selección o sube la tolerancia."),
    ("CC-MAN-008", 400, "La cuenta debe ser numérica y empezar por 572.", "Escribe una cuenta 572…"),
    ("CC-MAN-009", 400, "El apunte no existe.", "Repite la búsqueda."),
    ("CC-MAN-010", 400, "Solo se puede cambiar la cuenta de apuntes 572* no punteados.", "Elige un apunte 572 sin puntear."),

    # ── Cierres · recobros ───────────────────────────────────────────────────
    ("CC-REC-001", 400, "Escribe el concepto del recobro (p. ej. RECOBRO COMISIONES)", "Rellena el concepto."),
    ("CC-REC-002", 400, "Algún cobro ya está conciliado o no es de la cuenta del recobro",
     "Recarga el diagnóstico y vuelve a seleccionar."),

    # ── Cierres · asientos de diferencias ────────────────────────────────────
    ("CC-DIF-001", 400, "No se encontró el asiento {numero} en el ejercicio {ejercicio}",
     "Comprueba número de asiento y ejercicio."),

    # ── Cierres · conciliación bancaria ──────────────────────────────────────
    ("CC-BAN-001", 400, "Banco no encontrado o sin cuenta 572", "Revisa la configuración del banco."),
    ("CC-BAN-002", 400, "El fichero está vacío", "Descarga de nuevo el extracto del banco."),
    ("CC-BAN-003", 400, "Línea {linea} del extracto no válida (registro 22)", "El extracto Norma 43 está dañado; descárgalo de nuevo."),
    ("CC-BAN-004", 400, "No es un fichero Norma 43 (no hay registros de cabecera 11)",
     "Sube un extracto Norma 43 o usa la importación de Excel/CSV con mapeo."),
    ("CC-BAN-005", 400, "La cuenta contable debe ser numérica y empezar por 572", "Escribe una cuenta 572…"),
    ("CC-BAN-006", 400, "El banco necesita un nombre", "Rellena el nombre."),
    ("CC-BAN-007", 400, "Ya existe un banco con ese nombre", "Usa otro nombre."),
    ("CC-BAN-008", 400, "El banco no existe", "Recarga la lista de bancos."),
    ("CC-BAN-009", 400, "El banco tiene {n} movimientos de extracto; desactívalo en lugar de borrarlo",
     "Desmarca 'activo' en lugar de borrar."),
    ("CC-BAN-010", 400, "Banco no encontrado", "Recarga la lista de bancos."),
    ("CC-BAN-011", 400, "Los días del nivel 2 deben estar entre 0 y 30", "Pon un valor dentro del rango."),
    ("CC-BAN-012", 400, "Las tolerancias deben estar entre 0 y 1.000 €", "Pon valores dentro del rango."),
    ("CC-BAN-013", 400, "Cuenta del fichero no válida", "Elige una de las cuentas que contiene el extracto."),
    ("CC-BAN-014", 400, "El fichero no tiene movimientos", "Comprueba el periodo del extracto."),
    ("CC-BAN-015", 400, "No se pudo leer el fichero (separador o codificación no reconocidos)",
     "Guarda el fichero como Excel o CSV separado por ; , tabulador o |."),
    ("CC-BAN-016", 400, "Falta la columna de {campo} en el mapeo", "Asigna en el mapeo la columna indicada."),
    ("CC-BAN-017", 400, "Algún movimiento ya no está pendiente (o no es de este banco y ejercicio); actualiza la lista",
     "Recarga los pendientes."),
    ("CC-BAN-018", 400, "Marca al menos un movimiento del banco y un apunte del diario", "Selecciona en ambas tablas."),
]


def _area(codigo: str) -> str:
    prefijo = codigo.rsplit("-", 1)[0]
    if prefijo not in AREAS:
        raise RuntimeError(f"Prefijo de error sin área: {codigo}")
    return prefijo


CATALOGO: dict[str, EntradaError] = {}
for _c, _h, _m, _s in _ENTRADAS:
    if _c in CATALOGO:
        raise RuntimeError(f"Código de error repetido en el catálogo: {_c}")
    CATALOGO[_c] = EntradaError(_c, _h, _m, _s, _area(_c))


def texto(codigo: str, /, **params) -> str:
    """Mensaje final "[CODIGO] mensaje" para mostrar al usuario."""
    return f"[{codigo}] {CATALOGO[codigo].mensaje.format(**params)}"


class ErrorApp(ValueError):
    """Error de negocio con código del catálogo. Es un ValueError a propósito (compatibilidad)."""

    def __init__(self, codigo: str, /, **params):
        self.codigo = codigo
        self.params = params
        self.http = CATALOGO[codigo].http
        super().__init__(texto(codigo, **params))


def detalle_usuario(e: Exception) -> str:
    """Texto seguro para la pantalla: el de un ErrorApp tal cual; cualquier otro error
    (p. ej. un ValueError de pandas) se registra en el log y se muestra como GEN-004,
    sin detalles internos."""
    if isinstance(e, ErrorApp):
        return str(e)
    log.warning("Error sin código del catálogo (se muestra GEN-004): %s: %s", type(e).__name__, e)
    return texto("GEN-004")


def error_http(codigo: str, /, headers: dict | None = None, **params) -> HTTPException:
    """HTTPException con el estado y el mensaje del catálogo: `raise error_http("USR-003")`."""
    return HTTPException(status_code=CATALOGO[codigo].http, detail=texto(codigo, **params), headers=headers)
