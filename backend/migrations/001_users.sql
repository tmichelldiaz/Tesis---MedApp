-- Mismo patrón que plataform-OKF-Cloud (github.com/fredyxander/plataform-OKF-Cloud):
-- pgcrypto para UUIDs, un usuario con email único, y cada tabla de datos del
-- paciente tendrá su propio owner_id -> users(id) para el aislamiento por usuario.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email             TEXT        NOT NULL UNIQUE,
    password_hash     TEXT        NOT NULL,
    nombre            TEXT        NOT NULL DEFAULT '',
    apellido          TEXT        NOT NULL DEFAULT '',
    -- Evidencia de que aceptó la política de protección de datos al registrarse
    -- (Sección 15 de la política: el consentimiento debe quedar registrado).
    policy_accepted_at    TIMESTAMPTZ,
    policy_version_accepted TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
