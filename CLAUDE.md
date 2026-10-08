# CLAUDE.md — Gestor Financiero Correduría de Seguros

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

## Convenciones

### Backend
- Lógica de negocio siempre en `services/`, nunca en routers directamente.
- Dependencias inyectadas vía `dependencies.py` (`get_db`, `get_current_user`, `require_role`).
- Roles: `admin`, `gestor`, `lector`. Los endpoints sensibles usan `require_role(["admin"])`.
- Rate limiting con `slowapi` en endpoints de login y recalcular.
- Los errores internos nunca exponen detalle al cliente en producción.

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
