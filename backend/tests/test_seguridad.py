"""Seguridad: tokens, contraseñas, configuración, subidas de ficheros y limpieza de exportaciones."""
import asyncio
import io
import os
import time

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.core import security
from app.core.config import Settings
from app.core.subidas import leer_subida
from app.services.cierres import tareas


# ── Tokens JWT ────────────────────────────────────────────────────────────────

def test_token_de_acceso_se_firma_y_se_lee():
    payload = security.decode_token(security.create_access_token({"sub": "u1"}))
    assert payload["sub"] == "u1" and payload["type"] == "access"


def test_token_manipulado_se_rechaza():
    token = security.create_access_token({"sub": "u1"})
    cabecera, cuerpo, firma = token.split(".")
    assert security.decode_token(f"{cabecera}.{cuerpo}.{firma[::-1]}") is None
    assert security.decode_token("basura") is None


def test_dos_tokens_seguidos_son_distintos():
    """Regresión: emitidos en el mismo segundo eran idénticos y la renovación daba 500."""
    assert security.create_refresh_token({"sub": "u1"}) != security.create_refresh_token({"sub": "u1"})
    assert security.create_access_token({"sub": "u1"}) != security.create_access_token({"sub": "u1"})


def test_refresh_y_acceso_se_distinguen():
    assert security.decode_token(security.create_refresh_token({"sub": "u1"}))["type"] == "refresh"


# ── Contraseñas ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("clave,valida", [
    ("Abcdefgh1!", True),
    ("abcdefgh1!", False),   # sin mayúscula
    ("ABCDEFGH1!", False),   # sin minúscula
    ("Abcdefghi!", False),   # sin número
    ("Abcdefgh12", False),   # sin carácter especial
    ("Abc1!", False),        # corta
])
def test_fortaleza_de_contrasena(clave, valida):
    assert security.validate_password_strength(clave) is valida


def test_hash_bcrypt_verifica_y_no_guarda_la_clave():
    h = security.hash_password("Abcdefgh1!")
    assert "Abcdefgh1!" not in h and h.startswith("$2b$12$")
    assert security.verify_password("Abcdefgh1!", h) and not security.verify_password("otra", h)


# ── Configuración ─────────────────────────────────────────────────────────────

BASE = {"DATABASE_URL": "postgresql://x:y@127.0.0.1:1/z", "SECRET_KEY": "k" * 40}


@pytest.mark.parametrize("algoritmo", ["none", "RS256", "hs256", ""])
def test_algoritmo_jwt_no_hmac_impide_arrancar(algoritmo):
    with pytest.raises(ValidationError) as e:
        Settings(**BASE, ALGORITHM=algoritmo)
    assert "CFG-003" in str(e.value)


def test_secret_key_corta_impide_arrancar():
    with pytest.raises(ValidationError) as e:
        Settings(DATABASE_URL=BASE["DATABASE_URL"], SECRET_KEY="corta")
    assert "CFG-001" in str(e.value)


def test_cors_con_comodin_impide_arrancar():
    with pytest.raises(ValidationError) as e:
        Settings(**BASE, ALLOWED_ORIGINS=["*"])
    assert "CFG-002" in str(e.value)


# ── Subidas de ficheros ──────────────────────────────────────────────────────

def _subir(nombre: str, contenido: bytes, **kw):
    return asyncio.run(leer_subida(UploadFile(io.BytesIO(contenido), filename=nombre), **kw))


OPC = {"extensiones": (".xlsx", ".xls"), "max_mb": 1, "esperado": "Excel"}


def test_subida_correcta_devuelve_el_contenido():
    assert _subir("PRESUPUESTO.XLSX", b"datos", **OPC) == b"datos"  # extensión sin distinguir mayúsculas


@pytest.mark.parametrize("nombre,contenido,codigo,estado", [
    ("vacio.xlsx", b"", "ARC-001", 400),
    ("informe.pdf", b"x", "ARC-002", 415),
    ("sin_extension", b"x", "ARC-002", 415),
    ("grande.xlsx", b"x" * (1024 * 1024 + 1), "ARC-003", 413),
])
def test_subida_rechazada(nombre, contenido, codigo, estado):
    with pytest.raises(HTTPException) as e:
        _subir(nombre, contenido, **OPC)
    assert e.value.status_code == estado and f"[{codigo}]" in e.value.detail


def test_subida_justo_en_el_limite_se_acepta():
    assert len(_subir("ok.xlsx", b"x" * (1024 * 1024), **OPC)) == 1024 * 1024


# ── Limpieza de exportaciones caducadas (datos financieros en la carpeta temporal) ─

def test_limpieza_borra_solo_lo_caducado(tmp_path, monkeypatch):
    monkeypatch.setattr(tareas, "DIR_DESCARGAS", str(tmp_path))
    ahora = time.time()
    viejo, nuevo = tmp_path / "viejo.xlsx", tmp_path / "nuevo.xlsx"
    viejo.write_bytes(b"x")
    nuevo.write_bytes(b"x")
    os.utime(viejo, (ahora - tareas.CADUCIDAD_S - 60,) * 2)
    monkeypatch.setattr(tareas, "_TAREAS", {
        "vieja": {"estado": "terminada", "inicio": ahora - tareas.CADUCIDAD_S - 60},
        "reciente": {"estado": "terminada", "inicio": ahora - 60},
        "larga_en_curso": {"estado": "en_curso", "inicio": ahora - tareas.CADUCIDAD_S - 60},
    })
    assert tareas.limpiar_antiguas(ahora) == {"tareas": 1, "ficheros": 1}
    assert not viejo.exists() and nuevo.exists()
    assert set(tareas._TAREAS) == {"reciente", "larga_en_curso"}  # una tarea en curso nunca se borra
