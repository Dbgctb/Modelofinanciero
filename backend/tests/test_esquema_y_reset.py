"""Fase 3: esquema gestionado solo por Alembic y reset de datos protegido en el servidor.

Sin base de datos: las dependencias de BD y de usuario se sustituyen en el reset.
"""
import importlib.util
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

from app import main
from app.core.database import Base, get_db
from app.core.dependencies import require_admin
from app.core.errores import ErrorApp

BACKEND = Path(__file__).resolve().parent.parent


def _scripts() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))


# ── Migraciones ───────────────────────────────────────────────────────────────

def test_una_sola_cabeza_de_migraciones():
    """Dos cabezas (ramas sin fusionar) harían fallar `alembic upgrade head`."""
    assert len(_scripts().get_heads()) == 1


def test_la_cadena_empieza_en_la_migracion_base():
    revisiones = list(_scripts().walk_revisions())
    assert revisiones[-1].revision == "0001_base" and revisiones[-1].down_revision is None


def test_deshacer_la_migracion_base_esta_bloqueado():
    ruta = BACKEND / "alembic" / "versions" / "0001_base_esquema_completo.py"
    spec = importlib.util.spec_from_file_location("m0001", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    with pytest.raises(RuntimeError, match="no se puede deshacer"):
        modulo.downgrade()


def test_el_arranque_no_crea_ni_altera_tablas():
    codigo = "".join(inspect.getsource(main).split('"""')[0::2])  # sin docstrings (sí pueden citarlo)
    assert "create_all" not in codigo
    assert "ALTER TABLE" not in codigo


def test_comprobar_revision():
    main.comprobar_revision("0001_base", "0001_base")  # coincide: no lanza
    with pytest.raises(ErrorApp) as e:
        main.comprobar_revision("e0af6e045937", "0001_base")
    assert e.value.codigo == "CFG-004" and "e0af6e045937" in str(e.value)
    with pytest.raises(ErrorApp):
        main.comprobar_revision(None, "0001_base")  # base sin migrar


@pytest.mark.parametrize("tabla,indice", [
    ("diario_apuntes", "ix_diario_ejercicio"), ("diario_apuntes", "ix_diario_tipo_cuenta"),
    ("fact_resultado_analitico", "ix_fact_tipo_cuenta"), ("fact_resultado_analitico", "ix_fact_naturaleza"),
    ("fact_resultado_analitico", "ix_fact_recibo_id"), ("fact_resultado_analitico", "idx_fra_ejercicio"),
    ("fact_resultado_analitico", "idx_fra_ej_rid"), ("recibos", "idx_rec_tomador"),
])
def test_indices_de_rendimiento_declarados_en_los_modelos(tabla, indice):
    """Si faltan en los modelos, una migración autogenerada propondría BORRARLOS de la base."""
    assert indice in {i.name for i in Base.metadata.tables[tabla].indexes}


# ── Reset de datos ───────────────────────────────────────────────────────────

@pytest.fixture
def cliente_admin():
    db = MagicMock()
    main.app.dependency_overrides[get_db] = lambda: db
    main.app.dependency_overrides[require_admin] = lambda: MagicMock(id="u", username="admin_test")
    try:
        yield TestClient(main.app), db  # sin `with`: no ejecuta el arranque (no toca la BD)
    finally:
        main.app.dependency_overrides.clear()


@pytest.mark.parametrize("cuerpo", [{"confirmacion": "limpiar"}, {"confirmacion": ""}, {"confirmacion": "SI"}])
def test_reset_sin_la_frase_exacta_se_rechaza_sin_tocar_la_base(cliente_admin, cuerpo):
    cliente, db = cliente_admin
    r = cliente.post("/api/admin/reset-datos", json=cuerpo)
    assert r.status_code == 400 and "[ADM-007]" in r.json()["detail"]
    db.execute.assert_not_called()


def test_reset_sin_cuerpo_se_rechaza(cliente_admin):
    cliente, db = cliente_admin
    assert cliente.post("/api/admin/reset-datos").status_code == 422
    db.execute.assert_not_called()


def test_reset_con_la_frase_borra_y_deja_auditoria(cliente_admin):
    cliente, db = cliente_admin
    db.execute.return_value.fetchall.return_value = [("recibos", 10), ("diario_apuntes", 20)]
    r = cliente.post("/api/admin/reset-datos", json={"confirmacion": "LIMPIAR"})
    assert r.status_code == 200 and r.json()["recibos_eliminados"] == 10
    sql = " ".join(str(c.args[0]) for c in db.execute.call_args_list)
    assert "TRUNCATE" in sql and "DELETE FROM cargas_contables" in sql
    auditoria = db.add.call_args.args[0]
    assert auditoria.action == "RESET_DATOS" and "recibos=10" in auditoria.detail
    db.commit.assert_called_once()
