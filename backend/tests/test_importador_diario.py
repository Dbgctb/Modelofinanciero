"""Importador del diario de Cierres: lectura, validación y normalización (sin base de datos).

Datos sintéticos; nunca ficheros reales.
"""
import io
from decimal import Decimal

import openpyxl
import pytest

from app.core.errores import ErrorApp
from app.services.cierres import importador
from app.services.cierres.normalizador import extract_recibo, normalize_concepto

CABECERA = "Linea|Serie|Numero|Ejercicio|Fecha|Debe|Haber|Numero de Cuenta|Descripcion Cuenta|Concepto"


def _txt(*filas: str, cabecera: str = CABECERA, codificacion: str = "utf-8") -> bytes:
    return ("\n".join([cabecera, *filas]) + "\n").encode(codificacion)


def _codigo(exc_info) -> str:
    return exc_info.value.codigo


# ── Formato correcto ──────────────────────────────────────────────────────────

def test_txt_del_erp_se_lee_y_normaliza():
    contenido = _txt(
        "1|A|10|2025|02/01/2025|1.234,56|0|4300000001|CLIENTE|Emisión Recibo Nº 236313",
        "2|A|10|2025|02/01/2025|0|1.234,56|7050000001|VENTAS|Emisión Recibo Nº 236313",
    )
    df = importador._validar_y_normalizar(importador.leer_fichero("diario.txt", contenido))
    assert len(df) == 2
    primera = df.iloc[0]
    assert primera["asiento_key"] == "2025|A|10"
    assert primera["recibo_norm"] == "236313"
    assert primera["concepto_norm"] == "EMISION RECIBO"
    assert primera["neto"] == pytest.approx(1234.56)       # debe - haber, con miles y coma decimal
    assert df.iloc[1]["neto"] == pytest.approx(-1234.56)
    fila = importador._fila_bd(next(df.itertuples(index=False)))
    assert fila[5] == Decimal("1234.56") and fila[6] == Decimal("0.00")
    assert fila[7] == "4300000001"  # cuenta como texto


def test_txt_en_windows_1252_se_lee():
    contenido = _txt("1|A|1|2025|01/01/2025|5|0|4300000001|X|Emisión", codificacion="cp1252")
    df = importador.leer_fichero("d.txt", contenido)
    assert df.iloc[0]["Concepto"] == "Emisión"


def test_excel_del_erp_se_lee():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(CABECERA.split("|"))
    ws.append([1, "A", 7, 2025, "15/03/2025", 100.5, 0, 4300000001, "CLIENTE", "Cobro Recibo Nº 191250"])
    buf = io.BytesIO()
    wb.save(buf)
    df = importador._validar_y_normalizar(importador.leer_fichero("diario.xlsx", buf.getvalue()))
    assert df.iloc[0]["fecha"].day == 15 and df.iloc[0]["fecha"].month == 3  # dd/mm, no mm/dd
    assert df.iloc[0]["recibo_norm"] == "191250"


# ── Errores con código ───────────────────────────────────────────────────────

def test_fichero_intermedio_excel_aaaa_csv_da_cc_imp_003():
    """Regresión del caso real: el excel_2017.csv del programa antiguo (comas, sin Fecha/Debe/Haber)."""
    contenido = (b"Linea,Numero de Cuenta,Concepto,neto,asiento_key,recibo_norm,concepto_norm\n"
                 b"1,1000000000,ASIENTO DE APERTURA,-6010.12,2017|A|3649,,ASIENTO DE APERTURA\n")
    with pytest.raises(ErrorApp) as e:
        importador.leer_fichero("excel_2017.csv", contenido)
    assert _codigo(e) == "CC-IMP-003"
    assert "Fecha" in str(e.value) and "Debe" in str(e.value) and "asiento_key" in str(e.value)


def test_txt_con_otro_separador_da_cc_imp_004():
    contenido = _txt("1;A;1;2025;01/01/2025;1;0;4300000001;X;C", cabecera=CABECERA.replace("|", ";"))
    with pytest.raises(ErrorApp) as e:
        importador.leer_fichero("d.txt", contenido)
    assert _codigo(e) == "CC-IMP-004"


def test_extension_no_soportada_da_cc_imp_002():
    with pytest.raises(ErrorApp) as e:
        importador.leer_fichero("diario.pdf", b"x")
    assert _codigo(e) == "CC-IMP-002"


def test_fecha_invalida_da_cc_imp_006():
    df = importador.leer_fichero("d.txt", _txt("1|A|1|2025|32/13/2025|1|0|4300000001|X|C"))
    with pytest.raises(ErrorApp) as e:
        importador._validar_y_normalizar(df)
    assert _codigo(e) == "CC-IMP-006"


def test_texto_en_columna_numerica_da_cc_imp_005_sin_detalle_interno():
    with pytest.raises(ErrorApp) as e:
        importador.leer_fichero("d.txt", _txt("uno|A|1|2025|01/01/2025|1|0|4300000001|X|C"))
    assert _codigo(e) == "CC-IMP-005"
    assert "invalid literal" not in str(e.value)  # el mensaje de pandas no llega a la pantalla


# ── Normalizador de conceptos (base del punteo) ──────────────────────────────

@pytest.mark.parametrize("concepto,recibo", [
    ("Emisión Recibo Nº 236313", "236313"),
    ("Venta Recibo Nº REC00000123", "00000123"),
    ("Cobro Recibo 191250", "191250"),
    ("ASIENTO DE APERTURA", ""),
    (None, ""),
    (float("nan"), ""),
])
def test_extract_recibo(concepto, recibo):
    assert extract_recibo(concepto) == recibo


@pytest.mark.parametrize("concepto,normalizado", [
    ("Emisión Recibo Nº 236313", "EMISION RECIBO"),
    ("  Modificación   de prima total del Recibo Nº 182033 ", "MODIFICACION DE PRIMA TOTAL DEL RECIBO"),
    ("Pago 12345", "PAGO 12345"),  # menos de 6 cifras no es un recibo
    ("", ""),
])
def test_normalize_concepto(concepto, normalizado):
    assert normalize_concepto(concepto) == normalizado
