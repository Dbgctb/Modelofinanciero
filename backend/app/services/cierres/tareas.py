"""Tareas largas del módulo Cierres (importar, puntear, exportar) en segundo plano.

Mismo patrón que el recálculo del Analítico: un hilo por tarea y un diccionario en
memoria con su progreso, que la pantalla consulta por task_id. Si el backend se
reinicia, las tareas en curso se pierden (las operaciones de BD son transaccionales,
así que no quedan a medias).

Solo se permite una tarea que escriba en cc_apuntes a la vez (importar o puntear):
dos a la vez se pisarían.
"""
import logging
import os
import tempfile
import threading
import time
import uuid
from ...core.errores import ErrorApp, texto

log = logging.getLogger(__name__)

_TAREAS: dict[str, dict] = {}
_LOCK = threading.Lock()
_ESCRITURA = threading.Lock()  # una sola tarea de escritura sobre cc_apuntes a la vez

DIR_DESCARGAS = os.path.join(tempfile.gettempdir(), "gestor_cierres_descargas")


class TareaOcupada(Exception):
    """Ya hay una importación o un punteo en curso."""


def _actualizar(task_id, **campos):
    with _LOCK:
        _TAREAS.setdefault(task_id, {}).update(campos)


def estado(task_id: str) -> dict | None:
    with _LOCK:
        t = _TAREAS.get(task_id)
        return dict(t) if t else None


def lanzar(tipo: str, funcion, *args, escribe: bool = False, usuario: str | None = None, **kwargs) -> str:
    """Ejecuta `funcion(progreso, *args, **kwargs)` en un hilo y devuelve el task_id.

    `progreso(mensaje, paso=None, total=None)` actualiza lo que ve la pantalla.
    El valor devuelto por la función queda en `resultado`. Si devuelve un dict con
    `archivo`, la descarga queda disponible por el task_id.
    """
    if escribe and not _ESCRITURA.acquire(blocking=False):
        raise TareaOcupada(texto("CC-GEN-001"))
    task_id = uuid.uuid4().hex
    _actualizar(task_id, tipo=tipo, estado="en_curso", mensaje="Iniciando…", paso=0, total=None,
                inicio=time.time(), usuario=usuario, resultado=None, error=None)

    def progreso(mensaje, paso=None, total=None):
        _actualizar(task_id, mensaje=mensaje, paso=paso, total=total)

    def run():
        try:
            res = funcion(progreso, *args, **kwargs)
            _actualizar(task_id, estado="terminada", mensaje="Terminado", resultado=res,
                        segundos=round(time.time() - _TAREAS[task_id]["inicio"], 1))
        except Exception as e:  # el error se muestra en pantalla; el detalle va al log
            log.exception("Tarea %s (%s) fallida", task_id, tipo)
            mensaje = str(e) if isinstance(e, ErrorApp) else texto("GEN-002")
            _actualizar(task_id, estado="error", error=mensaje, mensaje="Error")
        finally:
            if escribe:
                from .consultas import invalidar_cache
                invalidar_cache()
                _ESCRITURA.release()

    threading.Thread(target=run, daemon=True, name=f"cierres-{tipo}").start()
    return task_id


def ruta_descarga(nombre: str) -> str:
    os.makedirs(DIR_DESCARGAS, exist_ok=True)
    return os.path.join(DIR_DESCARGAS, f"{uuid.uuid4().hex}_{nombre}")
