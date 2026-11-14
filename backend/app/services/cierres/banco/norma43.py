"""Lector de extractos Norma 43 (cuaderno 43 de la AEB).

Copia fiel de app/services/norma43_parser.py del programa original, que se verificó
con ficheros reales del Santander, incluida su forma de decidir el signo: por el
código de concepto del registro 22 y, después, por el texto del concepto (registros
23). Única diferencia: recibe el contenido en bytes en lugar de una ruta.
"""
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

log = logging.getLogger(__name__)

# Códigos de concepto (pos. 23-28 del registro 22) que el original trata como ingreso.
_HABER = ("000712", "000692", "000432")
_DEBE = ("000721", "001741", "000021", "001001", "000701", "001732")


def _fecha(aammdd: str):
    if not aammdd or len(aammdd) != 6 or not aammdd.isdigit():
        return None
    aa, mm, dd = int(aammdd[0:2]), int(aammdd[2:4]), int(aammdd[4:6])
    if not (1 <= mm <= 12) or not (1 <= dd <= 31):
        return None
    try:
        return date(2000 + aa if aa < 50 else 1900 + aa, mm, dd)
    except ValueError:
        return None


def _cabecera(linea: str) -> dict:
    entidad, oficina, cuenta = linea[2:6], linea[6:10], linea[10:20]
    saldo = Decimal("0")
    try:
        if len(linea) > 49:
            saldo = Decimal(linea[35:49]) / 100
            if (linea[34] if len(linea) > 34 else "2") == "1":
                saldo = -saldo
    except (InvalidOperation, IndexError):
        pass
    return {"cuenta": cuenta, "iban": f"ES00{entidad}{oficina}{cuenta}", "entidad": entidad,
            "oficina": oficina, "fecha_inicial": _fecha(linea[20:26]), "fecha_final": _fecha(linea[26:32]),
            "saldo_inicial": saldo}


def _movimiento(linea: str) -> dict:
    oficina = linea[6:10].strip()
    codigo = linea[22:28].strip()
    importe_abs = Decimal(linea[28:42]) / 100
    if codigo.startswith(_HABER):
        haber = True
    elif codigo.startswith(_DEBE):
        haber = False
    elif oficina and oficina[0] in ("1", "0", "5"):
        haber = False
    elif oficina and oficina[0] == "9":
        haber = True
    else:
        haber = False
    saldo = Decimal("0")
    if len(linea) >= 70:
        s = linea[56:70].strip()
        if s.isdigit():
            saldo = Decimal(s) / 100
    return {"fecha_operacion": _fecha(linea[10:16]), "fecha_valor": _fecha(linea[16:22]),
            "concepto": f"Operación {codigo}", "referencia": linea[56:].strip() if len(linea) > 56 else "",
            "importe": importe_abs if haber else -importe_abs, "saldo": saldo, "concepto_codigo": codigo}


def _ajustar_signo(mov: dict) -> dict:
    """Remesas emitidas, ingresos sin tarjeta y traspasos de ingreso: siempre positivos."""
    c = mov["concepto"].upper()
    if (("EMISION" in c and "REMESA" in c) or "INGRESO SIN TARJETA" in c
            or ("TRASPASO" in c and "INGRESO" in c)) and mov["importe"] < 0:
        mov["importe"] = abs(mov["importe"])
    return mov


def _saldo_final(linea: str):
    try:
        if len(linea) > 71:
            saldo = Decimal(linea[55:69]) / 100
            return -saldo if (linea[54] if len(linea) > 54 else "2") == "1" else saldo
    except (InvalidOperation, IndexError):
        pass
    return None


def leer_norma43(contenido: bytes) -> list[dict]:
    """Devuelve una lista de cuentas: {cuenta, iban, ..., movimientos: [...]}."""
    lineas = contenido.decode("latin-1").splitlines()
    if not lineas:
        raise ValueError("El fichero está vacío")
    cuentas, i = [], 0
    while i < len(lineas):
        if not lineas[i].startswith("11"):
            i += 1
            continue
        cab = _cabecera(lineas[i].rstrip())
        movs, j = [], i + 1
        while j < len(lineas):
            l = lineas[j].rstrip()
            if l.startswith("11"):
                break
            if l.startswith("22"):
                try:
                    mov = _movimiento(l)
                except (InvalidOperation, IndexError) as e:
                    raise ValueError(f"Línea {j + 1} del extracto no válida (registro 22)") from e
                k, conceptos = j + 1, []
                while k < len(lineas) and lineas[k].startswith("23"):
                    conceptos.append(lineas[k][4:].rstrip())
                    k += 1
                if conceptos:
                    mov["concepto"] = " ".join(conceptos)
                movs.append(_ajustar_signo(mov))
                j = k - 1
            elif l.startswith("33"):
                sf = _saldo_final(l)
                if sf is not None:
                    cab["saldo_final"] = sf
            elif l.startswith("88"):
                break
            j += 1
        cab.setdefault("saldo_final", Decimal("0"))
        cab["movimientos"] = movs
        cuentas.append(cab)
        i = j
    if not cuentas:
        raise ValueError("No es un fichero Norma 43 (no hay registros de cabecera 11)")
    return cuentas
