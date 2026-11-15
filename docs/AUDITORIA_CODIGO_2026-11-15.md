# Auditoría de código — Modelo financiero

**Fecha:** 2026-11-15 · **Rama auditada:** `feat/catalogo-errores` (commit `fc07f57`) · **Alcance:** backend (FastAPI, 19.100 líneas Python), frontend (React/TS, 19.800 líneas), dependencias, configuración y scripts.

## Cómo leer este informe

- **Severidad:** 🔴 Alta (arreglar ya) · 🟠 Media (planificar) · 🟡 Baja (mejora).
- **Evidencia:** VERIFICADO = comprobado en el código o ejecutando la aplicación · INFERIDO = conclusión razonable que conviene confirmar con una herramienta.
- **Contexto de riesgo:** la aplicación corre en un solo equipo (backend en `127.0.0.1`, frontend en `localhost`). No está expuesta a Internet, lo que rebaja los riesgos de red; los riesgos de **pérdida de datos** y de **mantenibilidad** pesan más.

## Estado tras las fases 1 y 2 (2026-11-15, rama `fix/auditoria-fases-1-2`)

**Resuelto y verificado** (tests automáticos + pruebas contra el backend en marcha):

| Punto | Qué se hizo | Verificación |
|---|---|---|
| S1 | `xlsx` 0.18.5 → 0.20.3 oficial de SheetJS (CDN, con hash de integridad en el lockfile) | `npm audit` ya no la marca; `tsc` y `vite build` limpios |
| S2 | `core/subidas.py`: extensión y tamaño (CSV auxiliares 5 MB, Excel presupuesto 20 MB), lee como mucho el límite + 1 byte | Tests + API real: `ARC-002` (415) y `ARC-003` (413) |
| S3 | Reutilizar un refresh token revocado cierra todas las sesiones del usuario y lo registra (`REFRESH_TOKEN_REUSED`); margen de 30 s para carreras inocentes (pestaña duplicada) | Prueba real con usuario temporal (borrado después): 7/7 |
| S5 | Login con usuario inexistente verifica un hash ficticio | 284 ms (antes, unos pocos ms) |
| S6 | `ALGORITHM` solo HS256/384/512; si no, el backend no arranca (`CFG-003`) | Tests |
| D2 | Tareas terminadas y Excel de descarga se borran pasadas 24 h (al lanzar cada tarea) | Test con ficheros y fechas simuladas |
| D3 | Quitados los `try/except: pass` de la carga de clientes | Revisión |
| Código muerto | 7 funciones y el endpoint `/analitico/debug/cesion` eliminados; 14 scripts movidos a `Antigravity/_archivo/scripts_modelo_financiero/` (con LEEME); 4 `.txt` basura borrados | Compila, tests, comprobación de referencias |
| Q1 | **421 tests** con pytest (permisos de los 206 endpoints, importador del diario, normalizador, semáforo y alertas de KPIs, seguridad, catálogo de errores). No usan la base de datos | `pytest` verde; 5 fallos introducidos a propósito detectados (pruebas de mutación) |
| Q4 | Ruff (backend) y ESLint (frontend) configurados en modo informe | Ver abajo |
| — | La preparación de la BD (`create_all` + `ALTER`) pasa del import de `main.py` al arranque (`lifespan`) para que los tests no toquen la base | El backend arranca y aplica igual |

**Nuevo, encontrado durante las pruebas:**
- 🟠 **Bug corregido — renovación de sesión con error 500:** dos tokens del mismo usuario emitidos en el mismo segundo eran idénticos y la renovación inmediata chocaba con la unicidad de `token_hash`. Se añade un `jti` aleatorio a cada token (compatible con los ya emitidos). Test de regresión incluido.
- 🟠 **`npm audit` confirma S4 en el frontend:** 6 vulnerabilidades en dependencias que llegan a la aplicación (axios — alta —, react-router, follow-redirects, form-data) y 8 más solo de desarrollo (vite/esbuild, babel, browserslist…). **Aplicado `npm audit fix`** (commit `922c520`): axios 1.21.1, follow-redirects, form-data y react-router 6.30.6. En la aplicación solo queda **react-router** (moderada: redirección abierta con `\` en enlaces —la app solo navega a rutas internas fijas— y un fallo de SSR, que no se usa); el arreglo exige la v7 (cambios incompatibles) → fase 4. El resto (vite/esbuild, minimatch de ESLint) es solo de herramientas de desarrollo.
- **Ruff:** 79 avisos reales una vez descartados los 406 falsos positivos de FastAPI (B008). Los 2 B023 del punteo son falsos positivos (la función se usa en la misma iteración). Quedan: 29 imports y 6 variables sin usar, 15 `zip` sin `strict`, 10 `raise` sin `from`, 5 `except` que ocultan errores.
- **ESLint:** 0 errores, 729 avisos: 721 `any` y 8 dependencias de `useEffect`/`useMemo` (4 por `ejercicio` que no se recarga al cambiar). Las reglas de hooks de React no tienen ninguna violación. El `catch {}` del sondeo de tareas en `DashboardsAnalitico.tsx` oculta errores de red.

## Estado tras la fase 3 (2026-11-15)

**Hallazgo que cambió el plan:** el historial de Alembic **no podía crear la base desde cero**: 14 de las 46 tablas (`clientes`, `fact_resultado_analitico`, `password_reset_tokens`…) solo existían por el `create_all()` del arranque. Había además un quinto y un sexto mecanismo de esquema: `rentabilidad_cliente._ensure_indexes` creaba índices al ejecutarse y `create_admin.py` llamaba a `create_all()`.

| Punto | Qué se hizo | Verificación |
|---|---|---|
| Copia previa | `pg_dump` completo en `Antigravity/_archivo/backups_modelo_financiero/correduria_db_antes_fase3_20261115.dump` (24 MB) | `pg_restore -l`: 47 tablas con datos, 49 índices |
| Q2 | Las 17 migraciones, el `.sql` manual y su ejecutor, sustituidos por **una migración base** (`0001_base`) generada de los modelos; archivados en `Antigravity/_archivo/migraciones_alembic_antiguas_modelo_financiero/` | Base temporal creada desde cero con `alembic upgrade head`: `pg_dump --schema-only` idéntico a la real (233 sentencias; solo cambia el orden de columnas en 2 tablas) |
| Q2 | 8 índices que existían en la BD sin declararse, añadidos a los modelos (si no, una migración autogenerada los habría borrado) | `alembic check` sobre la base real: sin diferencias |
| Q2 | Base real marcada con `alembic stamp 0001_base --purge` (antes `e0af6e045937`; no cambia tablas ni datos) | `alembic current` = `0001_base (head)` |
| Q2 | El arranque ya no crea ni altera nada: comprueba que la base está en la última revisión y si no, no arranca (`CFG-004`). Fuera `create_all` de `create_admin.py` y los índices en tiempo de ejecución | Arranque real: "Base de datos en la revisión 0001_base (última)"; rentabilidad de clientes responde |
| Q2 | `downgrade` de la base bloqueado (borraría todas las tablas) | Test |
| D1 | El reset exige `{"confirmacion": "LIMPIAR"}` en el servidor (`ADM-007`) y deja registro `RESET_DATOS` en la auditoría con lo borrado; la pantalla recomienda copia previa | Tests con la app real (BD simulada) + API real con frase incorrecta: rechazado y datos intactos |

**Volver atrás:** `alembic stamp` no cambió datos; para deshacer del todo, restaurar el `.dump` anterior con `pg_restore` y volver al commit previo.

## Estado tras la fase 4 — dependencias (2026-11-15)

**Resultado: 0 vulnerabilidades conocidas** en backend (`pip-audit`, antes 29 en 4 paquetes) y frontend (`npm audit`, antes 14 + 6 nuevas de ESLint).

| Cambio | Motivo | Verificación |
|---|---|---|
| `python-jose` → **PyJWT 2.15.1** | jose tenía una vulnerabilidad sin arreglo y traía `pyasn1` (8 vulns) y `ecdsa` (1, sin arreglo) | Test: un token emitido por jose se sigue leyendo; tokens caducados/manipulados rechazados |
| `passlib` → **bcrypt 5.0.0** directo | passlib sin mantenimiento desde 2020 | Tests con hashes reales de passlib (corto y de 100 caracteres, truncado a 72 bytes como passlib); los 2 hashes de la base tienen formato válido; login real OK |
| FastAPI 0.115 → **0.163.1**, starlette 0.46 → **1.10.0**, pydantic 2.7 → **2.14.3**, pydantic-settings → 2.16.3 | starlette tenía 7 vulnerabilidades (arreglo ≥ 1.3.1) | 447 tests; batería en vivo 31/31; flujo de sesión 7/7 |
| react-router-dom 6 → **7.18.5** | Redirección abierta (moderada) | Sin rutas comodín relativas ni navegación relativa; `tsc`, build y `vite preview` OK |
| vite 5 → **6.4.6**, plugin-react 4.7.0 | 8 avisos de vite/esbuild (uno alto) hasta 6.4.3: no hace falta la v8 | Build y `vite preview` (rutas SPA, bundle y proxy `/api`) OK |
| `overrides` de `minimatch` → 11.0.8 | DoS en la versión que traen las herramientas de ESLint | ESLint funciona igual |

**Encontrado y corregido durante la fase:**
- 🟡 `/openapi.json` (mapa completo de la API) era **público también en producción**; ahora solo existe en desarrollo, en `/api/openapi.json`.
- Los tests de permisos dejaron de ver 204 de las 205 rutas con la FastAPI nueva (los routers incluidos ya no se copian a `app.routes`). Se reescribió la recogida de rutas para que **falle si aparece una estructura desconocida** en vez de saltarse rutas en silencio.
- `class Config` de Pydantic (se elimina en Pydantic 3) → `model_config` en `config.py` y `kpis.py`.

## Estado tras la fase 5 — refactor de funciones gigantes (primer bloque, 2026-11-15)

**Método:** ningún cambio sin red. Antes de tocar cada función se capturó su salida exacta sobre la base real (*golden master*) y después del refactor se exigió salida **idéntica**; además se introdujeron fallos a propósito para confirmar que la red los detecta. Las funciones que escriben se ejecutaron en una transacción que se deshace siempre (verificado: las tablas no cambiaron).

| Función | Antes | Después | Red de seguridad |
|---|---|---|---|
| `cross_selling.recalcular_cross_selling` | 437 líneas · complejidad 119 | 51 · 8 (+13 piezas) | 11 ejercicios, ~75.000 oportunidades y ~31.000 alertas idénticas |
| `rentabilidad_cliente.calcular_rentabilidad_clientes` | 409 · 52 | 66 · 11 (+8 piezas) | 18 combinaciones de parámetros idénticas |
| `analitico.calcular_valoracion` | 264 · 54 | 89 · 5 (+9 piezas) | 8 combinaciones idénticas |

- Los factores de ajuste de la valoración, el reparto de costes, las señales de fuga, etc. son ahora funciones puras con **69 tests nuevos** en sus límites exactos (516 tests en total).
- Herramientas para seguir: `backend/scripts/golden_lectura.py` y `backend/scripts/golden_cross_selling.py` (`capturar` antes / `comparar` después).
- Quedan 32 funciones con complejidad > 20 (la mayor: `analitico._recalcular_worker`, 326 líneas). Q3 sigue siendo trabajo continuo.

**Hallazgos durante el refactor (comportamiento conservado tal cual; pendientes de decisión):**
- 🟠 **Valor protegido de las alertas de fuga con margen fijo del 15 %.** `_margenes_reales` lee de la rentabilidad las claves `'cliente'` y `'margen_pct_normalizado'`, que no existen (son `'tomador'` y `margen_pct`/`margen_pct_estimado`); el diccionario sale siempre vacío y un `except: pass` lo oculta. Afecta a `valor_protegido` y `prioridad` de todas las alertas. Corregirlo cambia esas cifras: hay que decidir qué margen usar.
- 🟡 **Motivo de algunas oportunidades no reproducible.** Si dos ramos del cliente empatan en afinidad con el recomendado, el texto se elige según el orden de un conjunto de Python, que varía en cada proceso. Arreglo trivial (recorrer en orden alfabético), cambia textos.
- 🟡 **`-0.0` en la cesión estimada** con tasa 0: PostgreSQL suma en orden no fijo y el signo del cero varía (la pantalla puede mostrar "-0,00 €").
- La fórmula de percentiles de prima de cross-selling usa el índice `int(n·q) − 1` (p50 de 4 valores = el 2.º): se fija con un test, no se cambia.

**Pendiente:** S7, S8, D4, los avisos de Ruff/ESLint, las decisiones anteriores y seguir con Q3.

## Resumen

| Área | Estado | Hallazgos |
|---|---|---|
| Inyección SQL | ✅ Bien | 0 (30 consultas dinámicas revisadas, todas parametrizadas) |
| Control de acceso | ✅ Bien | 206 endpoints: 6 públicos (correctos), resto con sesión y rol |
| Autenticación | 🟢 Sólida, mejorable | 2 medias, 2 bajas |
| Secretos | ✅ Bien | `.env` nunca en el historial; datos reales excluidos de Git |
| Dependencias | 🟠 | 1 alta (xlsx), 3 medias |
| Integridad de datos | 🟠 | 3 medias |
| Tests | 🔴 | **0 tests** en todo el proyecto |
| Deuda técnica | 🟠 | Esquema de BD con 4 mecanismos, funciones gigantes, sin linter |
| Código muerto | 🟡 | 7 funciones, 2 endpoints, 16 scripts sueltos, 4 ficheros basura |

**Lo que está bien hecho y conviene mantener:** consultas parametrizadas (incluido el escape de comodines `LIKE` en Cierres), RBAC en el servidor (no solo en la interfaz), bcrypt factor 12, bloqueo de cuenta, rotación y hash de refresh tokens, revocación de sesiones al cambiar contraseña, recuperación de contraseña sin enumeración de cuentas, token en `sessionStorage`, cabeceras de seguridad, CORS restringido, errores internos sin detalles al cliente y catálogo de errores con código.

---

## 1. Seguridad

### 🔴 S1. Librería `xlsx` 0.18.5 con vulnerabilidades conocidas, usada para leer ficheros subidos — INFERIDO
- **Dónde:** [Mapeo.tsx:179](../frontend/src/pages/admin/Mapeo.tsx#L179) (`XLSX.read` sobre el fichero que sube el usuario); también para exportar en `CuentaResultados.tsx`.
- **Riesgo:** la versión de npm (0.18.5, abandonada en ese registro) tiene publicadas una contaminación de prototipo al leer ficheros manipulados (CVE-2023-30533) y una denegación de servicio por expresión regular (CVE-2024-22363). Un Excel malicioso podría alterar el comportamiento de la página.
- **Arreglo:** pasar a la versión oficial de SheetJS (≥ 0.20.2, se instala desde su CDN, no desde npm) o mover la lectura del Excel al backend, que ya usa pandas/openpyxl. **Esfuerzo:** bajo.

### 🟠 S2. Subidas de ficheros sin límite de tamaño ni de tipo — VERIFICADO
- **Dónde:** [admin.py:344](../backend/app/routers/admin.py#L344) (CSV de auxiliares), [presupuesto.py:434](../backend/app/routers/presupuesto.py#L434) (ingresos) y [presupuesto.py:859](../backend/app/routers/presupuesto.py#L859) (cesiones).
- **Riesgo:** el resto de cargas comprueban tamaño y tipo (`ARC-002`/`ARC-003`); estas tres leen el fichero entero en memoria sin límite. Un fichero enorme puede bloquear el backend.
- **Arreglo:** aplicar la misma comprobación que `carga.py` (helper común). **Esfuerzo:** bajo.

### 🟠 S3. Reutilizar un refresh token revocado no invalida la sesión — VERIFICADO
- **Dónde:** [auth.py:111](../backend/app/routers/auth.py#L111).
- **Riesgo:** con rotación de tokens, que llegue un token ya usado es la señal típica de robo. Ahora solo se rechaza esa petición; el ladrón y el usuario siguen cada uno con su cadena de tokens.
- **Arreglo:** si el token existe pero está revocado, revocar todos los refresh tokens del usuario y registrarlo en la auditoría. **Esfuerzo:** bajo.

### 🟠 S4. Dependencias de autenticación poco mantenidas — INFERIDO
- `python-jose` 3.4.0 y `passlib` 1.7.4 tienen un mantenimiento mínimo (passlib no publica versión desde 2020; por eso `bcrypt` está fijado en 4.0.1). `ecdsa` (dependencia de jose) tiene un CVE sin arreglo (CVE-2024-23342) que **no afecta** aquí porque se usa HS256.
- `starlette` 0.46.2: hay avisos publicados posteriores sobre `FileResponse` con cabecera `Range` y sobre multipart, que este proyecto usa (descargas de Cierres, subidas).
- **Arreglo:** ejecutar `pip-audit` y `npm audit` para confirmar; planificar el cambio a `PyJWT` + `bcrypt` directo y subir FastAPI/Starlette. **Esfuerzo:** medio.

### 🟡 S5. Enumeración de usuarios por tiempo de respuesta — VERIFICADO
- **Dónde:** [auth.py:55](../backend/app/routers/auth.py#L55). Si el usuario no existe, responde sin calcular bcrypt (milisegundos); si existe, tarda ~250 ms. Además, solo las cuentas existentes pueden dar "Cuenta bloqueada".
- **Arreglo:** verificar contra un hash ficticio cuando el usuario no existe. **Esfuerzo:** muy bajo.

### 🟡 S6. Algoritmo JWT configurable desde `.env` — VERIFICADO
- **Dónde:** [security.py:34](../backend/app/core/security.py#L34). `ALGORITHM` se lee del entorno; una configuración errónea podría debilitar la firma.
- **Arreglo:** fijar `HS256` en código o validar el valor en `config.py`. **Esfuerzo:** muy bajo.

### 🟡 S7. Exportaciones accesibles por cualquier usuario con sesión — VERIFICADO
- **Dónde:** [cierres.py:59](../backend/app/routers/cierres.py#L59). Cualquier usuario autenticado (también un lector) puede descargar el Excel de una tarea de otro si conoce su identificador (aleatorio de 128 bits, no adivinable). El estado de la tarea muestra además el email de quien la lanzó.
- **Arreglo:** guardar el usuario en la tarea y comprobarlo en la descarga. **Esfuerzo:** bajo.

### 🟡 S8. Otros menores — VERIFICADO
- Validación de listas blancas de columnas con `assert` en `analitico.py` (Python las desactiva con `-O`): usar `if ... raise`.
- CSP con `'unsafe-inline'` en scripts y cabecera `X-XSS-Protection` obsoleta en [main.py:98](../backend/app/main.py#L98) (afectan solo a respuestas de la API; impacto bajo).
- Los Excel exportados escriben textos tal cual: un concepto que empiece por `=` se guarda como fórmula (inyección de fórmulas). El origen es el propio ERP, así que el riesgo es bajo.
- `GET /api/parametros/familias-gasto` es público (lista estática, sin datos sensibles).

---

## 2. Integridad de datos y operación

### 🟠 D1. Reset de datos sin confirmación en servidor ni copia previa — VERIFICADO
- **Dónde:** [admin.py:208](../backend/app/routers/admin.py#L208). Un solo `POST` de un administrador borra todas las cargas, diarios y recibos (TRUNCATE, irreversible). La confirmación existe solo en la interfaz.
- **Arreglo:** exigir en el cuerpo una frase de confirmación (p. ej. el nombre del entorno) y registrar en auditoría cuántas filas se borraron; recomendar `pg_dump` antes. **Esfuerzo:** bajo.

### 🟠 D2. Exportaciones con datos financieros que nunca se borran — VERIFICADO
- **Dónde:** [tareas.py:25](../backend/app/services/cierres/tareas.py#L25) y [tareas.py:79](../backend/app/services/cierres/tareas.py#L79). Los Excel generados se quedan en la carpeta temporal de Windows indefinidamente (hay 6 ahora). El registro de tareas en memoria también crece sin límite.
- **Arreglo:** borrar ficheros y tareas de más de 24 h al lanzar una tarea nueva. **Esfuerzo:** bajo.

### 🟠 D3. Errores tragados en silencio al cargar clientes — VERIFICADO
- **Dónde:** `services/carga_clientes.py` líneas 176–191 (`except Exception: pass` al asignar teléfono y email). Si falla, el cliente se cuenta como "actualizado" aunque no se haya guardado. Contradice la regla del proyecto de no convertir un fallo en éxito.
- **Arreglo:** quitar esos `try` (una asignación de atributo no debería fallar) o registrar la incidencia. **Esfuerzo:** muy bajo.

### 🟡 D4. Acciones destructivas abiertas al rol gestor — VERIFICADO (decisión de negocio)
- Purgar un ejercicio entero (`DELETE /carga/ejercicio/{ej}/purgar`, sin botón en la app), desconciliar un ejercicio o borrar bancos están permitidos a gestor además de admin. Confirmar si es lo deseado.

---

## 3. Calidad y deuda técnica

### 🔴 Q1. Ningún test automático — VERIFICADO
- No hay ni un test en backend ni en frontend. Toda la verificación es manual o con scripts sueltos (`paridad_punteo.py`, `paridad_banco.py`). Cada cambio corre el riesgo de romper algo sin que nadie lo note (este mismo catálogo de errores tuvo un fallo que solo apareció al probarlo a mano).
- **Arreglo:** instalar `pytest` y empezar por lo que más vale: cálculos financieros (KPIs, tesorería, cuenta de resultados), motor de punteo e importadores, y permisos de los endpoints. **Esfuerzo:** alto, pero incremental.

### 🟠 Q2. Cuatro mecanismos distintos para el esquema de la base de datos — VERIFICADO
- 17 migraciones de Alembic, `Base.metadata.create_all()` en cada arranque, una lista de `ALTER TABLE` en [main.py](../backend/app/main.py) y `migrations/001_add_performance_indexes.sql` para ejecutar a mano.
- **Riesgo:** no se sabe con certeza qué esquema tiene cada base; un cambio puede aplicarse en un sitio y no en otro.
- **Arreglo:** dejar solo Alembic (convertir los `ALTER` y los índices en migraciones) y quitar `create_all` y los `ALTER` del arranque. **Esfuerzo:** medio. Requiere copia de seguridad previa.

### 🟠 Q3. Funciones gigantes — VERIFICADO
34 funciones con complejidad ciclomática > 20 y 26 de más de 100 líneas (de 587). Las peores:

| Función | Líneas | Complejidad aprox. |
|---|---|---|
| `cross_selling.py` · `recalcular_cross_selling` | 437 | 119 |
| `analitico.py` · `_recalcular_worker` | 326 | 79 |
| `reglas_python.py` · `_buscar_exclusion` | 133 | 65 |
| `analitico.py` · `calcular_valoracion` | 264 | 54 |
| `rentabilidad_cliente.py` · `calcular_rentabilidad_clientes` | 410 | 52 |
| `kpis.py` · `calcular_kpis` | 197 | 50 |

`analitico.py` tiene 2.682 líneas en un solo archivo. En frontend, 6 páginas superan las 750 líneas (`DashboardsAnalitico.tsx` 1.566).
- **Arreglo:** trocear **solo con tests delante** (Q1), empezando por la que más se toque.

### 🟠 Q4. Sin linter ni formateador — VERIFICADO
- No hay configuración de ESLint/Prettier ni de Ruff/mypy. Eso explica parte de lo siguiente: 530 usos de `any` en 35 archivos del frontend, 53 imports dentro de funciones en el backend y helpers repetidos (`_f`, `_norm` ×4; `_get_presupuesto`, `_find`, `_filas`, `_clave`, `_cabecera` ×3).
- **Arreglo:** añadir Ruff (backend) y ESLint (frontend) en modo informe, sin corregir todo de golpe. **Esfuerzo:** bajo para configurar.

### 🟡 Q5. Versiones del frontend sin fijar — VERIFICADO
- 16 dependencias con `^` en `package.json`. El `package-lock.json` sí las fija, así que es un riesgo bajo mientras se use `npm ci`.

---

## 4. Código muerto y basura en el repositorio

### Funciones sin ningún uso — VERIFICADO (búsqueda en todo el backend)
| Función | Ubicación |
|---|---|
| `buscar_mapa_cuenta` | `services/normalizer.py:95` |
| `buscar_recibo` | `services/normalizer.py:134` |
| `get_mercado_referencia` | `services/presupuesto_ingresos.py:76` |
| `get_tasa_caida` | `services/presupuesto_ingresos.py:83` |
| `calcular_crecimiento_estadistico_interanual` | `services/presupuesto_ingresos.py:314` |
| `tasas_por_auxiliar` | `services/tasa_cesion.py:120` |
| `_build_row` | `services/analitico.py:204` |

### Endpoints que el frontend no usa — VERIFICADO
- `GET /api/analitico/debug/cesion` (diagnóstico, solo admin, solo lectura).
- `DELETE /api/carga/ejercicio/{ejercicio}/purgar` (destructivo, ver D4).

### Scripts sueltos en `backend/` (16, todos del 08/10/2026) — VERIFICADO
- **De diagnóstico, solo leen:** `check_623_sin_recibo`, `check_auxiliar`, `debug_estac`, `debug_fecha` (1 a 5), `debug_gastos`, `diag_cesion`, `verify_fix`.
- **Parches de datos que ESCRIBEN en la base** (peligrosos si se vuelven a ejecutar): `fix_auxiliar_none`, `patch_623_recibo`, `reparar_fechas_diario`.
- **Útiles y documentados (mantener):** `create_admin.py`, `reset_password.py`.
- **Ficheros basura versionados:** `backend/repair_err.txt` y `repair_out.txt` (vacíos), `frontend/tsc_errors.txt` (vacío) y `frontend/tsc_out.txt`.
- **Arreglo:** mover los de diagnóstico y los parches a `_archivo/` (fuera del repositorio) y borrar los `.txt`. Ningún script tiene credenciales. **Esfuerzo:** muy bajo.

El frontend no tiene código muerto relevante (solo algunos tipos exportados que se usan dentro de su propio archivo).

---

## 5. Plan recomendado

| Fase | Contenido | Riesgo del cambio | Esfuerzo |
|---|---|---|---|
| **1. Rápidos y seguros** | S1 (xlsx), S2 (límites de subida), S3 (reuso de refresh), S5, S6, D2 (limpieza de exportaciones), D3, limpieza de código muerto y scripts | Bajo | 1 sesión |
| **2. Red de seguridad** | Q1: pytest con los primeros tests (permisos, importadores, KPIs) y Q4: Ruff + ESLint en modo informe | Nulo (no cambia la app) | 1–2 sesiones |
| **3. Datos** | D1 (confirmación del reset), Q2 (unificar migraciones en Alembic, con backup) | Medio | 1 sesión |
| **4. Dependencias** | S4: `pip-audit`/`npm audit`, PyJWT, subir FastAPI/Starlette | Medio | 1 sesión |
| **5. Refactor** | Q3: trocear las funciones gigantes, con tests delante | Medio-alto | Continuo |

## 6. Qué no se ha podido verificar

- **CVE de dependencias:** no he ejecutado `pip-audit` ni `npm audit` (consultan bases de datos externas y `pip-audit` no está instalado). Los avisos de S1 y S4 salen de versiones conocidas; hay que confirmarlos con esas herramientas.
- **Análisis estático con herramientas** (Bandit, Semgrep, Ruff): no están instaladas; el análisis se ha hecho con búsquedas y con el árbol sintáctico de Python.
- **Rendimiento:** fuera del alcance (no se ha medido nada).
- **Frontend en navegador:** no se ha probado la interfaz.
