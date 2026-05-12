-- 001_ref_tables.sql
-- Reference tables: field managers, stores, dashboard users.

CREATE TABLE IF NOT EXISTS ref_field_managers (
    name        TEXT PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    phone       TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS ref_stores (
    store_number        TEXT PRIMARY KEY,
    store_name          TEXT NOT NULL,
    city                TEXT NOT NULL,
    state               CHAR(2) NOT NULL CHECK (state IN ('WA', 'OR')),
    timezone            TEXT NOT NULL DEFAULT 'America/Los_Angeles',
    field_manager_name  TEXT REFERENCES ref_field_managers(name),
    store_manager_name  TEXT,
    opening_date        DATE,
    is_active           BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ref_users (
    email            TEXT PRIMARY KEY,
    display_name     TEXT NOT NULL,
    role             TEXT NOT NULL CHECK (role IN ('owner', 'field_manager', 'readonly')),
    password_hash    TEXT NOT NULL,
    assigned_stores  TEXT[],
    is_active        BOOLEAN NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
