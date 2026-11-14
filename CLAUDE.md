# CLAUDE.md — Gestor Financiero Correduría de Seguros

Este archivo contiene lo específico de este proyecto. El contrato operativo general (cómo explorar, planificar, el trato con seguridad/datos/git/tests, etc.) vive en `../CLAUDE.md` (raíz de `Antigravity/`) y aplica igual aquí — este documento lo complementa, nunca lo sustituye.

## Descripción del proyecto
Aplicación web full-stack para gestión financiera de una correduría de seguros. Permite presupuestación, seguimiento real, control de costes, KPIs, tesorería, rentabilidad por cliente y motor de cross-selling/detección de fuga.

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | FastAPI (Python 3.11+), SQLAlchemy, Pydantic v2 |
| Base de datos | PostgreSQL 15+ |
| Frontend | React 18 + TypeScript, Vite, Ant Design, Zustand, React Query v5 |
| Auth | JWT (access 15 min + refresh 7 días con rotación), bcrypt factor 12 |

---

## Arrancar el proyecto

### Backend
```powershell
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload
# API: http://localhost:8000
# Docs: http://localhost:8000/api/docs  (solo en development)
```

### Frontend
```powershell
cd frontend
npm run dev
# App: http://localhost:5173
```

### Git (PATH requerido en PowerShell)
```powershell
$env:PATH = "C:\Program Files\Git\bin;$env:PATH"
```

---

## Estructura del proyecto

```
backend/app/
├── core/          → config.py, database.py, security.py, limiter.py, logging_config.py
├── models/        → tablas SQLAlchemy (un archivo por entidad)
├── schemas/       → validación Pydantic (request/response)
├── routers/       → endpoints REST (un archivo por módulo)
└── services/      → lógica de negocio (desacoplada de routers)

frontend/src/
├── api/           → funciones axios por módulo (client.ts es el axios base con interceptor JWT)
├── components/    → layout/AppLayout.tsx, common/ProtectedRoute.tsx
├── pages/         → organizadas por módulo (ver rutas abajo)
├── store/         → authStore.ts (Zustand)
└── types/         → index.ts con todos los tipos compartidos
```

---

## Módulos y rutas

| Módulo | Ruta frontend | Router backend |
|---|---|---|
| Dashboard | `/dashboard` | — |
| Carga de datos | `/presupuestacion/carga` | `/api/carga` |
| Presupuesto ingresos | `/presupuestacion/ingresos` | `/api/presupuesto` |
| Presupuesto gastos | `/presupuestacion/gastos` | `/api/presupuesto` |
| Tesorería | `/presupuestacion/tesoreria` | `/api/tesoreria` |
| Seguimiento real | `/presupuestacion/real` | `/api/real` |
| KPIs | `/presupuestacion/kpis` | `/api/kpis` |
| Cuenta de resultados | `/presupuestacion/cuenta-resultados` | `/api/presupuesto` |
| Panel de control (cuadre) | `/panel-control` | `/api/cuadre` |
| Rentabilidad cliente | `/rentabilidad/clientes` | `/api/rentabilidad` |
| Cross-selling oportunidades | `/cross-selling/oportunidades` | `/api/cross-selling` |
| Cross-selling alertas fuga | `/cross-selling/alertas` | `/api/cross-selling` |
| Efectividad cross-selling | `/cross-selling/efectividad` | `/api/cross-selling` |
| Analítico dashboards | `/analitico/dashboards` | `/api/analitico` |
| Analítico configuración | `/analitico/configuracion` | `/api/analitico` |
| Ajustes de coste | `/analitico/ajustes-coste` | `/api/analitico` |
| Valoración analítica | `/analitico/valoracion` | `/api/analitico` |
| Mapeo de cuentas (admin) | `/admin/mapeo-cuentas` | `/api/admin` |
| Usuarios (admin) | `/usuarios` | `/api/users` |
| Tasas de mercado (admin) | `/admin/tasas-mercado` | `/api/admin` |
| Reset de datos (admin) | `/admin/reset-datos` | `/api/admin` |
| Cierres: importar diario | `/cierres/importar` | `/api/cierres` |
| Cierres: punteo automático | `/cierres/punteo` | `/api/cierres` |
| Cierres: punteo manual | `/cierres/manual` | `/api/cierres` |
| Cierres: recobros (Diagnóstico H) | `/cierres/recobros` | `/api/cierres/recobros` |
| Cierres: ver conciliados | `/cierres/conciliados` | `/api/cierres` |
| Cierres: asientos de diferencias | `/cierres/diferencias` | `/api/cierres/diferencias` |
| Cierres: conciliación bancaria | `/cierres/banco` | `/api/cierres/banco` |
| Cierres: exportar | `/cierres/exportar` | `/api/cierres/exportar` |

---

## Recuperación de contraseña (sin email configurado)

Decisión del usuario (2026-10-10): sin SMTP configurado, `POST /auth/forgot-password`
no envía ningún correo -- genera un `PasswordResetToken` (60 min, un solo uso)
que solo un admin ya logueado puede ver y relayar, en Usuarios → "Solicitudes
de reset" (`GET/DELETE /users/reset-requests`). `POST /auth/reset-password`
consume el token.

**Gap conocido y su solución:** si el único admin olvida su propia
contraseña, no hay nadie que pueda ver su solicitud (circular -- hace falta
estar logueado como admin para ver la pantalla que la muestra). Para ese
caso, `backend/reset_password.py` resetea cualquier contraseña directamente
en BD, sin pasar por el login web (mismo patrón que `create_admin.py`). Ver
README § "Si nadie puede entrar".

Si en el futuro se conecta un email real (SMTP/Resend/SendGrid), el cambio
es en `forgot_password()` (`app/routers/auth.py`) -- añadir el envío ahí no
rompe nada del resto del flujo, que ya está construido alrededor del token.

---

## Módulo Cross-Selling y Alertas de Fuga

### Fuentes de datos
- **Recibos** (`recibo.ramo`): categoría normalizada (AUTO, HOGAR, SALUD…); `recibo.subramo`: sub-ramo real del fichero fuente (Ramo2.xlsx).
- **Clientes** (`clientes`): cargados desde CSV via `/api/cross-selling/clientes/carga`.

### Formato del fichero de clientes (CSV)
Separador `;`, codificación Latin-1 o UTF-8. Columnas esperadas:
```
Código;Nombre;F.Alta;F.Nacimie;Fis/Jur;T. Fijo;T. Móvil;E-Mail
```
- `Nombre`: formato `NOMBRE AP1 AP2` → se reordena internamente a `AP1 AP2 NOMBRE` en `nombre_normalizado` para casar con el `tomador` de recibos.
- `Fis/Jur`: `F` = físico, `J` = jurídico.
- `T. Fijo`: 9 dígitos numéricos.

### Normalización de nombres
- `nombre` en BD: valor original del fichero (para mostrar en UI).
- `nombre_normalizado` en BD: `AP1 AP2 NOMBRE` en mayúsculas (para cruzar con `tomador` de recibos).
- Función: `_reordenar_nombre()` en `carga_clientes.py` — solo reordena si hay ≥ 3 palabras.

### Motor de scoring cross-selling (`services/cross_selling.py`)
- `_RAMOS_FISICO`: productos recomendables a clientes físicos (no incluye FLOTILLAS ni RC empresarial).
- `_RAMOS_JURIDICO`: productos para empresas (incluye VIDA colectivo, RC, FLOTILLAS, CIBER…).
- `DEFAULT_MATRIZ`: 51 entradas de afinidad entre ramos (ramo_base → ramo_objetivo → score 0-1). Se auto-refresca en BD si tiene menos entradas.
- Las oportunidades se filtran por tipo de cliente antes de devolver recomendaciones.

### Señales de alerta de fuga
| Señal | Condición | Requiere histórico |
|---|---|---|
| `vencimiento_proximo` | min(hasta vigente) ≤ 90 días | No |
| `sin_renovacion` | días desde max_desde > umbral inactividad | No |
| `mono_cartera` | solo 1 ramo activo | No |
| `ramo_perdido` | ramo presente año anterior, ausente ahora | Sí |
| `prima_bajando` | prima total cae > umbral | Sí |
| `cartera_reducida` | n_ramos disminuye | Sí |

**Importante**: `dias_vencimiento` usa `min(hasta)` de pólizas vigentes, no `max(hasta)`. Usar `max` ocultaba vencimientos inminentes de pólizas secundarias.

### Campos de `FugaAlerta`
`tipo_cliente`, `auxiliar`, `ramos_actuales` se rellenan en cada "Recalcular". Si se añade un campo nuevo, siempre añadir `ALTER TABLE fuga_alertas ADD COLUMN IF NOT EXISTS ...` en `main.py`.

### Flujo tras cambios en el motor
1. Reiniciar backend (ejecuta migraciones `ALTER TABLE`).
2. Pulsar **Recalcular** en UI → regenera `cross_selling_oportunidades` y `fuga_alertas` con todos los campos actualizados.

---

## Módulo Cierres contabilidad

Punteo del diario completo y conciliación bancaria. Reconstruye en PostgreSQL el programa de escritorio
"Cuadre Contable" (PySide6 + SQLite; archivado en `Antigravity/_archivo/CC con repositorio/`). Plan, decisiones, pruebas y estado:
**`docs/PLAN_CIERRES_CONTABILIDAD.md`** (leerlo antes de tocar el módulo).

### Datos
- Tablas propias `cc_*` (migración Alembic `e0af6e045937`). **No tienen relación con `diario_apuntes`**, que solo
  guarda los grupos 6/7 para la Cuenta de Resultados y el Analítico.
- Columnas con los nombres del original (`reconciled`, `recon_rule`, `recon_group_id`…) e ids de apunte originales:
  los referencian sin clave foránea `cc_emparejamientos_h.cobro_id`, `cc_incidencias.line_ids` y
  `cc_extractos.recon_journal_id`.

### Código
- Backend: `services/cierres/` (motor.py + reglas/, controles.py, importador.py, consultas.py, recobros.py,
  diferencias.py, exportar.py, excel.py, tareas.py, banco/) y routers `cierres.py`, `cierres_banco.py`,
  `cierres_herramientas.py`.
- Frontend: `pages/cierres/` (8 pantallas; `banco/` con las 5 pestañas de la conciliación bancaria) y `api/cierres.ts`.
- Tareas largas (importar, puntear, conciliar banco, Excel grandes) en segundo plano: `tareas.lanzar()` devuelve
  `task_id` y se consulta `GET /api/cierres/tareas/{id}`. Solo una tarea que escriba a la vez (409 si hay otra).
- La lista de bloques de "Ver conciliados" se cachea en memoria; cualquier escritura debe llamar a
  `consultas.invalidar_cache()` (las tareas de escritura ya lo hacen).

### Reglas del motor (no romper la paridad con el original)
- `LIKE` de SQLite no distingue mayúsculas → patrones sobre conceptos con `ILIKE`.
- La base ordena texto con intercalación Spanish_Spain (ignora `|`, `-`, espacios). Donde el orden decide qué
  apunte se consume, `ORDER BY ... COLLATE "C"` y desempate por `id`.
- Reglas en Python con `neto::float8` (algoritmos iguales al original); reglas SQL con sumas NUMERIC exactas
  (decisión del usuario: B y C ya no rechazan grupos que cuadran al céntimo).
- Tras cambiar reglas o el motor bancario: `backend/scripts/paridad_punteo.py` y `paridad_banco.py` comparan
  con el original apunte a apunte y restauran la base al terminar.

### Restaurar los datos del original
`backend/scripts/migrar_cuadre_sqlite.py RUTA_SQLITE --reemplazar` vacía las `cc_*` y copia de nuevo el SQLite
(solo lectura) con verificación fila a fila. **Borra todo lo hecho en el módulo desde la migración**: solo con
autorización del usuario.

---

## Convenciones

### Backend
- Lógica de negocio siempre en `services/`, nunca en routers directamente.
- Dependencias inyectadas vía `dependencies.py` (`get_db`, `get_current_user`, `require_role`).
- Roles: `admin`, `gestor`, `lector`. Los endpoints sensibles usan `require_role(["admin"])`.
- Rate limiting con `slowapi` en endpoints de login y recalcular.
- Los errores internos nunca exponen detalle al cliente en producción.
- **Catálogo de errores** (`app/core/errores.py`, documentado en `docs/CATALOGO_ERRORES.md`): todo error que ve el
  usuario lleva código y sale como `"[CODIGO] mensaje"`. Nunca `raise ValueError("texto")` ni
  `HTTPException(..., detail="texto")`:
  - servicios → `raise ErrorApp("CC-IMP-003", faltan=...)` (hereda de `ValueError`, compatible con los `except ValueError`);
  - routers → `raise error_http("USR-003")` (estado HTTP del catálogo);
  - al reenviar un `ValueError` capturado → `detail=detalle_usuario(e)` (si no es del catálogo, lo registra y muestra `GEN-004`).
  - Error nuevo: entrada en `_ENTRADAS` y `venv\Scripts\python scripts\catalogo_errores.py --escribir`. El mismo script
    sin argumentos comprueba códigos, parámetros, textos literales pendientes y que el documento está al día.

### Frontend
- El cliente axios está en `api/client.ts` — maneja refresh token y redirección a `/login` en 401.
- Estado global de auth en `store/authStore.ts` (Zustand).
- Errores de React Query se propagan globalmente a través de `QueryCache.onError` en `App.tsx`.
- React Query v5: usar `isPending` (no `isLoading`) en mutaciones.
- UI en español con locale `esES` de Ant Design.
- Tema principal: `colorPrimary: #1890ff`, `borderRadius: 8`, fuente Inter.
- Tablas con mucho contenido: usar `expandable` rows de Ant Design en lugar de scroll horizontal. Ver `Oportunidades.tsx` y `FugaAlertas.tsx` como referencia.

### Git
- Mensajes de commit en español, descriptivos del cambio.
- Avisar al usuario antes de hacer cualquier commit y esperar confirmación.
- Formato: `git commit -m "tipo: descripción del cambio"`
- Push (política acordada con el usuario, 2026-10-23): una vez confirmado un commit, se puede hacer push normal a `origin` (incluida `main`, que es la rama de trabajo habitual de este repo) sin volver a preguntar. Force push, reescritura de historial, tags/releases y cualquier despliegue siguen requiriendo autorización explícita.

---

## Variables de entorno (backend/.env)

```
DATABASE_URL=postgresql://usuario:password@localhost:5432/correduría_db
SECRET_KEY=<64 chars aleatorios>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
APP_NAME=Gestor Financiero Correduría
APP_ENV=development
ALLOWED_ORIGINS=http://localhost:5173
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_MINUTES=15
```

---

## Control de calidad antes de entregar

Antes de dar por terminado cualquier cambio, verificar obligatoriamente:

1. **Backend compila** — `uvicorn app.main:app --reload` arranca sin errores de importación ni de SQLAlchemy.
2. **Migraciones de BD** — si se añade una columna a una tabla existente, añadir un `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` en el bloque de migraciones de `main.py`. `create_all` solo crea tablas nuevas, no columnas.
3. **Frontend compila** — `npx tsc --noEmit` sin errores TypeScript, o `npm run build` limpio.
4. **No variables indefinidas** — revisar que toda variable usada en el código Python esté definida en el scope correcto.
5. **Rutas y menú coherentes** — si se añade una página nueva, verificar que existe la ruta en `App.tsx` y el ítem en `AppLayout.tsx`.
6. **Señales de fuga** — si se añade una señal nueva, añadirla en `SENAL_CONFIG` de `FugaAlertas.tsx`.

---

## Seguridad implementada
- JWT access (15 min) + refresh (7 días) con rotación y revocación
- bcrypt factor 12 para contraseñas
- Bloqueo de cuenta tras 5 intentos fallidos durante 15 min
- RBAC con 3 roles: admin / gestor / lector
- Auditoría completa de acciones en tabla `audit`
- Headers de seguridad HTTP en cada respuesta (CSP, HSTS en prod, X-Frame-Options, etc.)
- CORS restringido a `ALLOWED_ORIGINS`
- Validación MIME y tamaño en carga de archivos Excel
- Rate limiting en endpoints críticos
