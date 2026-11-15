"""Comprueba el catálogo de errores y genera docs/CATALOGO_ERRORES.md.

Uso (desde backend/):
    venv\\Scripts\\python scripts\\catalogo_errores.py              comprobar (sale con 1 si algo falla)
    venv\\Scripts\\python scripts\\catalogo_errores.py --escribir   regenerar el documento

Comprueba:
1. Formato de los códigos (AREA-NNN o CC-AREA-NNN).
2. Cada ErrorApp / error_http / texto del código usa un código que existe y le pasa
   exactamente los parámetros que pide su mensaje.
3. No hay códigos del catálogo sin usar.
4. No quedan errores con texto literal (raise ValueError("..."), HTTPException(..., "...")).
5. El documento está al día con el catálogo.
"""
import ast
import re
import string
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.core.errores import AREAS, CATALOGO  # noqa: E402

APP = BACKEND / "app"
DOC = BACKEND.parent / "docs" / "CATALOGO_ERRORES.md"
FORMATO = re.compile(r"^(CC-)?[A-Z]+-\d{3}$")
FUNCIONES = {"ErrorApp", "error_http", "texto"}
# Parámetros de error_http que no son del mensaje
NO_MENSAJE = {"headers"}


def campos(plantilla: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(plantilla) if f}


def usos() -> tuple[dict, list[str]]:
    """Recorre app/ con ast: {codigo: [(archivo:línea, {parametros})]} y errores encontrados."""
    encontrados, fallos = defaultdict(list), []
    for py in APP.rglob("*.py"):
        propio = py.name == "errores.py" and py.parent.name == "core"  # define texto(codigo, ...)
        rel = py.relative_to(BACKEND)
        arbol = ast.parse(py.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            nombre = getattr(nodo.func, "id", None) or getattr(nodo.func, "attr", None)
            if nombre in FUNCIONES:
                if not (nodo.args and isinstance(nodo.args[0], ast.Constant) and isinstance(nodo.args[0].value, str)):
                    if propio:
                        continue
                    fallos.append(f"{rel}:{nodo.lineno} {nombre}() sin código literal")
                    continue
                params = {k.arg for k in nodo.keywords} - NO_MENSAJE
                encontrados[nodo.args[0].value].append((f"{rel}:{nodo.lineno}", params))
        for nodo in ast.walk(arbol):  # 4. errores con texto literal
            if isinstance(nodo, ast.Raise) and isinstance(nodo.exc, ast.Call):
                n = getattr(nodo.exc.func, "id", None) or getattr(nodo.exc.func, "attr", None)
                literales = [a for a in nodo.exc.args if isinstance(a, (ast.Constant, ast.JoinedStr))]
                literales += [k.value for k in nodo.exc.keywords
                              if k.arg == "detail" and isinstance(k.value, (ast.Constant, ast.JoinedStr))]
                if n in ("ValueError", "HTTPException") and any(
                        not isinstance(x, ast.Constant) or isinstance(x.value, str) for x in literales):
                    fallos.append(f"{rel}:{nodo.lineno} raise {n} con texto literal: usa el catálogo")
    return encontrados, fallos


def documento() -> str:
    por_area = defaultdict(list)
    for e in CATALOGO.values():
        por_area[e.area].append(e)
    lineas = [
        "# Catálogo de errores",
        "",
        "Todos los errores que la aplicación muestra al usuario llevan un código entre corchetes, "
        "por ejemplo `[CC-IMP-003]`. Busca aquí el código para ver qué significa y qué hacer.",
        "",
        "> Documento generado desde `backend/app/core/errores.py` con "
        "`python scripts/catalogo_errores.py --escribir`. No lo edites a mano.",
        "",
        "Los valores entre llaves (`{faltan}`, `{n}`…) se sustituyen por los datos concretos del error.",
        "",
        "## Índice",
        "",
    ]
    for area, nombre in AREAS.items():
        if por_area.get(area):
            ancla = re.sub(r"[^\w\- ]", "", f"{area} — {nombre}".lower()).replace(" ", "-")  # como GitHub
            lineas.append(f"- [{area} · {nombre}](#{ancla}) ({len(por_area[area])})")
    for area, nombre in AREAS.items():
        if not por_area.get(area):
            continue
        lineas += ["", f"## {area} — {nombre}", "", "| Código | HTTP | Mensaje | Qué hacer |", "|---|---|---|---|"]
        for e in sorted(por_area[area], key=lambda x: x.codigo):
            msg = e.mensaje.replace("|", "\\|")
            sol = e.solucion.replace("|", "\\|")
            lineas.append(f"| `{e.codigo}` | {e.http} | {msg} | {sol} |")
    return "\n".join(lineas) + "\n"


def main() -> int:
    if "--escribir" in sys.argv:
        DOC.write_text(documento(), encoding="utf-8", newline="\n")
        print(f"Escrito {DOC.relative_to(BACKEND.parent)} ({len(CATALOGO)} errores)")
        return 0

    fallos = [f"Código con formato no válido: {c}" for c in CATALOGO if not FORMATO.match(c)]
    encontrados, f_usos = usos()
    fallos += f_usos
    for codigo, sitios in encontrados.items():
        if codigo not in CATALOGO:
            fallos += [f"{s}: código {codigo} no existe en el catálogo" for s, _ in sitios]
            continue
        pide = campos(CATALOGO[codigo].mensaje)
        for sitio, params in sitios:
            if params != pide:
                fallos.append(f"{sitio}: {codigo} pide {sorted(pide)} y recibe {sorted(params)}")
    fallos += [f"Código sin usar en la aplicación: {c}" for c in CATALOGO if c not in encontrados]
    if not DOC.exists() or DOC.read_text(encoding="utf-8") != documento():
        fallos.append("docs/CATALOGO_ERRORES.md no está al día: ejecuta con --escribir")

    if fallos:
        print(f"{len(fallos)} problema(s):")
        print("\n".join(f"  - {f}" for f in fallos))
        return 1
    print(f"Catálogo correcto: {len(CATALOGO)} errores, "
          f"{sum(len(s) for s in encontrados.values())} usos en el código, documento al día.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
