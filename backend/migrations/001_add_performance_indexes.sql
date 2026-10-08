-- Migración 001: Índices de rendimiento
-- Ejecutar UNA SOLA VEZ contra la base de datos existente.
-- Los índices CONCURRENT no bloquean la tabla durante la creación.

-- ── diario_apuntes ────────────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_diario_ejercicio
    ON diario_apuntes (ejercicio);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_diario_tipo_cuenta
    ON diario_apuntes (tipo_cuenta);

-- Cubre el patrón más frecuente: WHERE ejercicio=X AND estado!='excluido'
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_diario_ejercicio_estado
    ON diario_apuntes (ejercicio, estado);

-- Cubre: WHERE ejercicio=X AND recibo_id IS NOT NULL
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_diario_ejercicio_recibo
    ON diario_apuntes (ejercicio, recibo_id);

-- Cubre: WHERE ejercicio=X AND numero_cuenta LIKE '623%' y similares
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_diario_ejercicio_num_cuenta
    ON diario_apuntes (ejercicio, numero_cuenta);

-- ── recibos ───────────────────────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_recibos_ejercicio
    ON recibos (ejercicio);

-- GROUP BY tomador en rentabilidad por cliente
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_recibos_tomador
    ON recibos (tomador);

-- GROUP BY ente (auxiliar) en dashboards
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_recibos_ente
    ON recibos (ente);

-- ── fact_resultado_analitico ──────────────────────────────────────────────────
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fact_tipo_cuenta
    ON fact_resultado_analitico (tipo_cuenta);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fact_naturaleza
    ON fact_resultado_analitico (naturaleza);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fact_recibo_id
    ON fact_resultado_analitico (recibo_id);

-- Cubre el patrón GROUP BY tipo_cuenta, naturaleza WHERE ejercicio=X
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fact_ejercicio_tipo_nat
    ON fact_resultado_analitico (ejercicio, tipo_cuenta, naturaleza);

-- Cubre el JOIN con recibos en rentabilidad_cliente
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_fact_ejercicio_recibo
    ON fact_resultado_analitico (ejercicio, recibo_id);
