# Plan: módulo "Cierres contabilidad"

Integración en el Modelo financiero del programa de escritorio "Cuadre Contable"
(carpeta `Antigravity/CC con repositorio/`). Plan aprobado en sus decisiones de alcance
por el usuario el 2026-11-14:

1. Los datos se migran **tal como están**, con el estado de punteo y los punteos manuales.
2. Se trasladan **todas** las pantallas.
3. Lo que el programa actual no usa se descarta.
4. El orden lo fija este plan.

Estado de cada fase: ver la tabla del final.

---

## 1. Qué se traslada (inventario verificado)

### Datos (SQLite `database/cuadre_contable.db`, 384 MB)

| Tabla origen | Filas | Destino | Notas |
|---|---|---|---|
| `journal_lines` | 1.044.017 (2017–2025) | `cc_apuntes` | Se conserva el `id` original: lo referencian `h_manual_matches.cobro_id`, `control_issues.line_ids` y `bank_statements.recon_journal_id` |
| `reconciliation_rules` | 19 | `cc_reglas` | Se corrigen los textos mal codificados ("Fecha �1 d�a") |
| `reconciliation_runs` | 913 | `cc_ejecuciones` | Historial |
| `control_issues` | 81.094 | `cc_incidencias` | `line_ids` (texto) → array de enteros |
| `control_accounts` + `_d` + `_k` + `_l` | 1 + 1 + 1 + 1 | `cc_cuentas_control` | Una sola tabla con columna `tipo` (C, D, K, L) |
| `config` | 2 | `cc_config` | Tolerancias de los niveles 8 y 9 del banco |
| `h_manual_matches` | 6 | `cc_emparejamientos_h` | Emparejamientos guardados del Diagnóstico H |
| `bancos` | 2 | `cc_bancos` | |
| `bank_statements` | 1.232 (2025) | `cc_extractos` | 236 conciliados |
| `bank_reconciliation_runs` | 35 | `cc_banco_ejecuciones` | |
| `reconciliation_config` | 2 | `cc_banco_config` | Días y tolerancias por cuenta 572 |

**Se descartan (sin uso en el programa actual):** `extractos_bancarios` (0 filas, sustituida por
`bank_statements`), `quality_controls` (0 filas), `imports` (0 filas), `sqlite_sequence`.

### Punteo: estado actual

| | Apuntes |
|---|---|
| Total | 1.044.017 |
| Punteados | 866.798 (83,0 %) |
| Punteo manual (`MANUAL_H`, `MANUAL_NN`) | 1.564 |
| Conciliados con el banco (`NIVEL_*`) | 283 |

### Reglas del motor de punteo (19 activas, en orden de ejecución)

| Fase | Reglas | Alcance |
|---|---|---|
| Por ejercicio, por prioridad | K, RETROCESO, K2, RETRO, A, B, C, E, H, I, O, S | Ejercicio seleccionado |
| Al final, todos los ejercicios | CROSS_YEAR, L, P, Q, R, T | Toda la base |
| La última | V (cierre de saldo 440 por cuenta) | Ejercicio seleccionado |

- **SQL puro:** A, B, E, I, O, R, S, T, L, P, CROSS_YEAR.
- **Algoritmo en Python:** K y K2 (emparejamiento 1:1 por fases), H (combinaciones de cobros contra
  recibos 4152), V (búsqueda de subconjuntos que cierran el saldo, fases A/B/C), Q, C, RETRO y
  RETROCESO.

**Se descartan:**
- Reglas sin uso en el motor: `rule_d`, `rule_f`, `rule_m`, `rule_n`, `rule_h_fast`, `cross_year.py`
  y `query_retroceso.py`.
- Archivos bancarios sin uso: `bank_rule_agrupacion_n1`, `bank_rule_devolucion_gastos`,
  `bank_rule_emision_remesa`, `bank_rule_liquidacion` y `bank_reconciliation (1).py`.
- Carpetas: `old/`, `scripts/` y los `analizar_*`/`buscar_*` sueltos.

### Conciliación bancaria
- Importación de Norma 43 (`norma43_parser.py`) y de Excel/CSV con mapeo de columnas.
- Niveles automáticos:
  - 1: fecha e importe exactos.
  - 2: ±N días.
  - 3: tolerancia de importe.
  - 7: liquidaciones agrupadas por Nº.
  - 8: ingresos contra cobros del mes.
  - 9: devoluciones.
- Manual: 1:1, mejorado y N:N.
- Auto-crear asientos.
- Desconciliar.
- Informe Excel.

### Controles de calidad
- C: movimientos mensuales.
- D: neto estable.
- K: duplicados de emisión.
- L: anulación sin emisión.

Se configuran con las cuentas de control.

### Pantallas (8 pestañas de `gui_main.py`, 8.076 líneas)

1. Importar: completo e incremental, con diálogo de nuevos y huérfanos, filtros, paginación y "desconciliar todos".
2. Conciliar: reglas, tolerancias, cuentas, multi-ejercicio y cuentas de control.
3. Conciliación manual.
4. Diagnóstico H: recobros, emparejamientos guardados, asignar cobro, cobro extra y Excel.
5. Banco, con 5 subpestañas: importar extracto, ejecutar, conciliados, pendientes y configuración/bancos.
6. Ver conciliados: por bloques, con detalle y Excel.
7. Asientos de diferencias: cargar, duplicar o invertir un asiento y exportar "Nueva carga de asientos".
8. Exportar: Excel completo del punteo.

---

## 2. Arquitectura en el Modelo financiero

### Base de datos
- Misma base PostgreSQL local (`correduria_db`, puerto 5433). Tablas propias con prefijo `cc_`.
  **No se toca `diario_apuntes`:** solo guarda los grupos 6 y 7 (2020–2025) y alimenta la Cuenta de
  Resultados y el Analítico. El punteo necesita el diario completo.
- Migración Alembic (`e0af6e045937`). El Modelo financiero tiene una sola base (`correduria_db`); no hay base de tests.
- Nombres de columna iguales a los del original (`reconciled`, `recon_rule`, `recon_group_id`...): las reglas son mucho SQL y
  así se traducen con menos errores y la paridad se compara columna a columna. Los nombres de tabla sí van en español.
- Columnas que el original nunca usa y se descartan: `journal_lines.import_id` y `bank_id`; `reconciliation_config.key`,
  `value` y `description`.
- `cc_apuntes.cuenta` como texto (`VARCHAR(20)`), igual que `numero_cuenta` en el resto del modelo.
  Así se evitan los `CAST(cuenta AS TEXT) LIKE` del original.
- Importes `NUMERIC(18,2)` en lugar de `REAL`. Elimina errores de coma flotante en las sumas, pero puede
  cambiar algún caso límite de tolerancia 0,00 (regla R). Lo comprueba la prueba de paridad.
- Índices:
  - `(ejercicio, cuenta, reconciled)`
  - `(recibo_norm)`
  - `(asiento_key)`
  - `(recon_group_id)`
  - `(ejercicio, numero)`

### Backend
```
backend/app/models/cierres.py               tablas cc_*
backend/app/services/cierres/
    normalizador.py      extract_recibo, normalize_concepto (copia fiel)
    importador.py        diario completo e incremental (nuevos y huérfanos)
    motor.py             orquesta las reglas y la ejecución multi-ejercicio, en segundo plano
    reglas/              reglas_sql.py (A, B, I, O, S, CROSS_YEAR, L, P, R, T), reglas_python.py
                         (C, E, H, K, K2, Q, RETRO, RETROCESO, V), _comun.py y el registro
    controles.py         controles C, D, K, L
    manual.py            punteo manual, desconciliar, Diagnóstico H
    diferencias.py       asientos de diferencias
    exportador.py        Excel con openpyxl (ya instalado; no se añade xlsxwriter)
    banco/
        norma43.py, importador.py, motor.py (niveles), manual.py, exportador.py
backend/app/routers/cierres.py, cierres_banco.py
backend/scripts/migrar_cuadre_sqlite.py      migración de datos, de un solo uso
```
- Tareas largas (punteo, importación, banco) en segundo plano con `task_id` y consulta de progreso,
  el mismo patrón que el recálculo del Analítico.
- Permisos: `admin` y `gestor` modifican; `lector` solo consulta.
- Todo el SQL parametrizado. El filtro de cuentas del original concatenaba texto (riesgo de inyección).

### Frontend
Menú raíz **"Cierres contabilidad"**:

| Opción | Ruta | Origen |
|---|---|---|
| Importar diario | `/cierres/importar` | pestaña 1 |
| Punteo automático | `/cierres/punteo` | pestaña 2, más cuentas de control y controles |
| Punteo manual | `/cierres/manual` | pestaña 3 |
| Recobros (Diagnóstico H) | `/cierres/recobros` | pestaña 4 |
| Ver conciliados | `/cierres/conciliados` | pestaña 6 |
| Asientos de diferencias | `/cierres/diferencias` | pestaña 7 |
| Conciliación bancaria | `/cierres/banco` | pestaña 5 (5 subpestañas) |
| Exportar | `/cierres/exportar` | pestaña 8 |

Las tablas grandes se paginan en el servidor: el original paginaba en local sobre SQLite.

---

## 3. Fases

Rama: `feat/cierres-contabilidad`. Commit al final de cada fase, previa confirmación del usuario.
El merge a `main` requiere autorización explícita.

| # | Fase | Contenido | Verificación |
|---|---|---|---|
| 0 | Esqueleto | Modelos `cc_*`, migración Alembic, menú y rutas vacías | El backend arranca, la migración sube y baja limpia, `tsc` limpio |
| 1 | Migración de datos | `migrar_cuadre_sqlite.py`: lee el SQLite en solo lectura y copia todo conservando los ids | Recuentos y sumas de debe, haber y neto por ejercicio, cuenta (3 dígitos) y regla, **idénticos** a SQLite. Los 1.564 punteos manuales presentes |
| 2 | Motor de punteo | Normalizador y las 19 reglas en PostgreSQL, motor multi-ejercicio en segundo plano | **Prueba de paridad** (ver abajo), tiempo de ejecución medido |
| 3 | Pantallas de punteo | Importar diario, Punteo automático (reglas, tolerancias, cuentas de control, controles), Punteo manual, Ver conciliados | Probado en la app: importar un ejercicio, puntear, desconciliar, puntear a mano |
| 4 | Conciliación bancaria | Norma 43 y Excel, niveles 1 a 9, pendientes, manual 1:1 y N:N, auto-crear asientos, informe | Paridad con el programa actual sobre los extractos de 2025 |
| 5 | Herramientas | Diagnóstico H, Asientos de diferencias, Exportar (Excel del punteo) | Excels comparados con los del programa actual |
| 6 | Cierre | `CLAUDE.md` del proyecto, revisión completa y validación del usuario | El usuario valida en la app; la carpeta original se archiva (no se borra) cuando él lo confirme |

### Criterios de traducción del motor (fase 2)
- `LIKE` de SQLite no distingue mayúsculas: los patrones sobre conceptos usan `ILIKE`.
- SQLite ordena texto byte a byte; la base usa intercalación Spanish_Spain (ignora `|`, `-`, espacios).
  Donde el orden decide qué apunte se consume primero: `COLLATE "C"` y desempate por `id`.
- Reglas en Python: `neto` como float8, igual que REAL, para que sumas, redondeos y búsquedas den lo mismo.
  Reglas SQL: sumas en NUMERIC exacto.
- `recon_group_id` con el mismo formato (incluido `hash()` de tuplas de enteros, determinista).
- Cada regla en su transacción; si falla se deshace esa regla, se sigue (como el original) y la ejecución
  queda "con_errores" con el detalle.
- Peculiaridades del original que se mantienen: el filtro de cuentas de la pantalla solo afecta a la regla A;
  la regla R no usa tolerancia (exige saldo 0). Se corrige: CROSS_YEAR leía su tolerancia con un código
  inexistente y usaba siempre 0,01 (hoy configurada también a 0,01, sin efecto).
- Herramienta: `backend/scripts/paridad_punteo.py`.

### Resultado de la prueba de paridad del punteo (2026-11-14)
Los dos motores sobre los mismos datos (todo despunteado salvo MANUAL_* y NIVEL_*), 9 ejercicios:
- Normalizador: idéntico en los 1.044.017 conceptos.
- Punteados: original 866.522, nuevo 866.731. Ningún grupo con composición distinta dentro de la misma regla.
- Diferencias, todas por la suma en coma flotante del original:
  - RULE_B (tolerancia 0,00): 7.450 apuntes cuyos grupos suman exactamente 0 pero el original veía
    ±1e-15 y los rechazaba; después los cogían Q o R, o se quedaban sin puntear (210). El nuevo los puntea con B.
  - RULE_C (tolerancia 0,00): igual, 2.219 apuntes (54 grupos) que el original dejaba a la regla L.
  - 81 apuntes de S, Q y CROSS_YEAR, todos en cuentas afectadas por lo anterior (efecto arrastre).
- Tiempo: original ~190 s, nuevo ~135–170 s.
- **Decisión del usuario (2026-11-14): se mantienen las sumas exactas** (opción a).
- Pendiente de vigilar: RETRO y RETROCESO (tolerancia 0,00) siguen comparando en coma flotante como el
  original; hoy coinciden exactamente, pero con otros datos podrían tener el mismo problema.

### Fase 3: decisiones y verificación (2026-11-14)
Decisiones del usuario:
- El filtro de cuentas del punteo automático se aplica a **todas** las reglas (el original solo a la A).
  Todos los grupos de todas las reglas son de una sola cuenta, así que filtrar al puntear no altera ningún grupo.
- Los controles respetan las casillas y cada ejecución **sustituye** las incidencias de ese control y ejercicio
  (el original ejecutaba siempre los cuatro y las acumulaba: en 2025, 7.488 filas C que eran 72 repetidas 104 veces).

Correcciones respecto al original:
- Control L: comparaba la cuenta configurada ("430") con igualdad exacta y nunca encontraba nada; ahora es prefijo
  (en 2025 detecta 894 anulaciones sin emisión previa en 430*).
- Importación completa: borrado e inserción en una sola transacción.
- Punteo manual: rechaza apuntes ya punteados; el grupo incluye el id menor para que dos punteos en el mismo
  segundo no se mezclen.
- Filtro de cuenta en búsquedas: menos de 10 cifras sin * = prefijo (en el original "43" no encontraba nada).
- Se descartan los botones "Guardar cambios" y "Limpiar caché" (propios de SQLite).

Verificación (por la API, con el diario real `carga de datos/diario 2025.xlsx`):
- Incremental con el mismo fichero: 138.401 sin cambios, 0 nuevos, 0 huérfanos, punteo intacto (21 s).
- Completa: 138.401 importados, idénticos campo a campo a los del original (30 s).
- Punteo 2025 + controles por la API: 27 s, sin errores; filtro malicioso rechazado (400); segunda tarea simultánea
  rechazada (409).
- Punteo manual, rechazo de repetido, bloque visible al momento, Excel de selección y de conciliados (3 hojas).
- Al terminar, las tablas cc_* se restauraron con `migrar_cuadre_sqlite.py --reemplazar` (verificado idéntico).

### Fase 4: conciliación bancaria (2026-11-14)
Código: `services/cierres/banco/` (norma43.py, motor.py, servicio.py), `routers/cierres_banco.py`, pantalla
`pages/cierres/ConciliacionBancaria.tsx` con 5 pestañas. Prueba: `backend/scripts/paridad_banco.py`.

Paridad (todo lo conciliado por niveles deshecho en ambos lados, los dos bancos de 2025): **0 diferencias** en los
1.232 movimientos y en los 13.263 apuntes 572 (776 movimientos conciliados en ambos). Lector Norma 43: idéntico al
original en los 416 movimientos de un fichero generado con el extracto de "Antiguo banesto".

Se mantiene del original: niveles 1, 2, 3, 7, 8 y 9 en ese orden, siempre todos; el nivel 3 usa ±5,00 € fijos; los
niveles 1-3 no ponen grupo. Se descarta: el botón "Conciliar" genérico y los niveles 4, 5 y 6 (no existían),
`bank_report_exporter.py` (sin uso).

Cambios respecto al original:
- Reimportar un Norma 43 conserva los movimientos conciliados (el original los borraba y dejaba apuntes punteados
  contra movimientos inexistentes); sustituye solo los pendientes y no duplica los conciliados.
- Desconciliar libera el grupo entero (en un N:N el original dejaba conciliados los demás movimientos).
- "Auto-crear asiento" no creaba nada en el original: aquí es "Propuesta de asiento", solo consulta.
- No se puede borrar un banco con movimientos (se desactiva).

Verificado por la API: reimportación (236 conservados, 180 sustituidos), conciliación del banco 5 (539/816),
1:1, N:N, rechazo de repetidos, desconciliar grupo, propuesta, Excel y alta/baja de bancos. Al terminar, cc_*
restaurado con `migrar_cuadre_sqlite.py --reemplazar` (verificado idéntico).

### Prueba de paridad (fase 2 y fase 4)
El estado guardado en el SQLite se generó con versiones anteriores de las reglas. Por eso se compara
**código antiguo contra código nuevo sobre los mismos datos**, no contra el estado guardado:

1. Copia del SQLite en un directorio temporal, nunca el original.
2. Se desconcilia todo salvo los punteos manuales, en la copia y en PostgreSQL.
3. Se ejecuta el motor antiguo sobre la copia, en el mismo orden que la interfaz: cada ejercicio y las
   reglas entre ejercicios al final.
4. Se ejecuta el motor nuevo sobre PostgreSQL.
5. Se compara apunte a apunte: `reconciled` y `recon_rule`, más la composición de cada grupo.

Toda diferencia se explica antes de dar la fase por buena. Al terminar, PostgreSQL vuelve al estado
migrado de la fase 1, salvo que el usuario decida quedarse con el resultado del motor nuevo.

### Riesgos

| Riesgo | Mitigación |
|---|---|
| Diferencias SQLite → PostgreSQL (orden de filas sin `ORDER BY`, coma flotante, `strftime`) | `ORDER BY` explícito en las reglas que emparejan 1:1; prueba de paridad |
| Rendimiento con un millón de apuntes | Índices; ANALYZE tras cargas masivas (lección del Analítico); medir |
| Interfaz muy grande (8.076 líneas) | Por fases, una pantalla cada vez, y probada |
| Pérdida del trabajo manual | Ids conservados; el SQLite original nunca se escribe; recuentos en la fase 1 |

### Resultado de la fase 1 (2026-11-14)
`backend/scripts/migrar_cuadre_sqlite.py` copió las 11 tablas en una transacción (~70 s) y las comparó **fila a fila,
campo a campo**: 1.127.326 filas idénticas, y los 642 grupos ejercicio × cuenta (3 dígitos) × regla con los mismos
recuentos y sumas. Punteos manuales y del banco presentes: MANUAL_H 1.562, MANUAL_NN 2, NIVEL_1/2/3/7/8/9 283.

Hallazgos que vienen del original (se han copiado tal cual, no son efecto de la migración):
- **2017 no cuadra:** debe 7.281.010,04 frente a haber 7.282.524,32 (−1.514,28). El resto de ejercicios cuadra.
- **Referencias a apuntes que ya no existen** (reimportaciones antiguas que recrearon los apuntes con ids nuevos):
  4 de los 6 emparejamientos del Diagnóstico H (`cobro_id`) y 1.534 de los 5.284 ids de las incidencias K.
  Se revisan en la fase 5 (Diagnóstico H) y al volver a ejecutar los controles (fase 3), que regeneran las incidencias.

Para repetir la migración: `scripts/migrar_cuadre_sqlite.py RUTA_SQLITE --reemplazar`; solo comprobar: `--solo-verificar`.

### Vuelta atrás
- El programa original y su SQLite no se modifican en ningún momento (solo lectura).
- Para deshacer la integración basta con borrar la rama y las tablas `cc_*` (bajar la migración
  Alembic). El resto del Modelo financiero no depende de ellas.

---

## 4. Estado

| Fase | Estado | Fecha | Commit |
|---|---|---|---|
| Análisis y plan | Hecho | 2026-11-14 | — |
| 0 Esqueleto | Hecho | 2026-11-14 | (este commit) |
| 1 Migración de datos | Hecho | 2026-11-14 | (este commit) |
| 2 Motor de punteo | Hecho (sumas exactas, decisión del usuario) | 2026-11-14 | (este commit) |
| 3 Pantallas de punteo | Hecho, pendiente de tu prueba en la app | 2026-11-14 | (este commit) |
| 4 Conciliación bancaria | Hecho, pendiente de tu prueba en la app | 2026-11-14 | (este commit) |
| 5 Herramientas | Pendiente | | |
| 6 Cierre | Pendiente | | |
