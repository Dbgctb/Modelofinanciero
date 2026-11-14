"""Utilidades comunes de las reglas de punteo (PostgreSQL, tabla cc_apuntes).

Criterios de traducción desde el original SQLite (ver docs/PLAN_CIERRES_CONTABILIDAD.md):

- `LIKE` de SQLite no distingue mayúsculas en ASCII: los patrones sobre conceptos
  usan `ILIKE`. Los patrones sobre `cuenta` (solo dígitos) usan `LIKE`.
- SQLite ordena el texto byte a byte; PostgreSQL usa la intercalación de la base
  (Spanish_Spain), que ignora signos como `|`. Donde el orden decide qué apunte se
  consume primero se ordena con `COLLATE "C"` y se desempata por `id`.
- Las reglas que son un algoritmo en Python trabajan con `neto` en coma flotante
  (`neto::float8`), igual que el original con REAL: los mismos importes dan el mismo
  double y el algoritmo (redondeos incluidos) se comporta igual. Las reglas que son
  SQL puro suman en NUMERIC exacto.
- Las marcas de agrupación (`recon_group_id`) se construyen con el mismo formato,
  incluidos los `hash()` de Python sobre tuplas de enteros (deterministas).
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection

# SET común a todas las reglas: lo que el original escribía en cada UPDATE.
SET_PUNTEO = """reconciled = true, recon_rule = :regla, recon_run_id = :run_id,
                recon_timestamp = LOCALTIMESTAMP"""


def marcar(conn: Connection, regla: str, pares, run_id: int, solo_pendientes: bool = False,
           filtro_cuentas=None) -> int:
    """Puntea apuntes con su grupo. `pares` es una lista de (group_id, id_apunte).

    Reproduce el `executemany` del original, que ejecutaba un UPDATE por par en orden:
    - sin `solo_pendientes` (UPDATE ... WHERE id = ?): si un id se repite, gana el último;
    - con `solo_pendientes` (... AND reconciled = 0): gana el primero.
    Devuelve el número de apuntes distintos marcados.
    """
    grupo_de = {}
    for gid, lid in pares:
        if solo_pendientes and lid in grupo_de:
            continue
        grupo_de[lid] = gid
    if not grupo_de:
        return 0
    ids = list(grupo_de.keys())
    gids = [grupo_de[i] for i in ids]
    filtro = "AND NOT a.reconciled" if solo_pendientes else ""
    fc, fc_params = filtro_cuentas_sql(filtro_cuentas, alias="a.")
    res = conn.execute(text(f"""
        UPDATE cc_apuntes a
        SET {SET_PUNTEO}, recon_group_id = v.gid
        FROM unnest(CAST(:ids AS integer[]), CAST(:gids AS text[])) AS v(id, gid)
        WHERE a.id = v.id {filtro} {fc}
    """), {"regla": regla, "run_id": run_id, "ids": ids, "gids": gids, **fc_params})
    return res.rowcount or 0


def filtro_cuentas_sql(filtro_cuentas, alias: str = "", prefijo_param: str = "fc"):
    """Condición SQL parametrizada para el filtro de cuentas de la pantalla Punteo automático.

    Se aplica a TODAS las reglas (decisión del usuario 2026-11-14; el original solo lo
    aplicaba a la regla A). Como todos los grupos de todas las reglas son de una sola
    cuenta, filtrar al puntear equivale a puntear solo esas cuentas sin alterar los grupos.

    `filtro_cuentas`: lista como ["4300*", "4110000001"]; "*" o vacío = todas.
    El original concatenaba el texto en el SQL; aquí solo se admiten dígitos y "*".
    Devuelve (sql, params). sql vacío si no hay filtro.
    """
    if not filtro_cuentas or any(str(c).strip() == "*" for c in filtro_cuentas):
        return "", {}
    conds, params = [], {}
    for n, cuenta in enumerate(filtro_cuentas):
        c = str(cuenta).strip()
        base = c.replace("*", "")
        if not base.isdigit():
            raise ValueError(f"Cuenta no válida en el filtro: {cuenta!r} (solo dígitos y *)")
        p = f"{prefijo_param}{n}"
        if "*" in c:
            conds.append(f"{alias}cuenta LIKE :{p}")
            params[p] = base + "%"
        else:
            conds.append(f"{alias}cuenta = :{p}")
            params[p] = base
    return "AND (" + " OR ".join(conds) + ")", params
