-- Synthetic SaaS analytics schema for the docker-compose Postgres stand-in.
-- Works on PostgreSQL; the agent's tool primitives also work on SQLite if you
-- load this via `sqlite3 demo.db < seed_demo.sql` (you'd just lose the FK
-- enforcement and the `TIMESTAMPTZ` precision).
--
-- Usage:
--   docker compose -f docker-compose.dev.yml up -d
--   psql postgresql://dev:dev@localhost:5432/demo -f examples/seed_demo.sql

DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS event CASCADE;
DROP TABLE IF EXISTS subscription CASCADE;
DROP TABLE IF EXISTS customer CASCADE;

CREATE TABLE customer (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    region       TEXT NOT NULL,
    signup_date  DATE NOT NULL
);

CREATE TABLE subscription (
    id            INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customer(id),
    plan_tier     TEXT NOT NULL,    -- 'free' | 'starter' | 'pro' | 'enterprise'
    status        TEXT NOT NULL,    -- 'active' | 'trial' | 'cancelled'
    started_at    TIMESTAMPTZ NOT NULL,
    cancelled_at  TIMESTAMPTZ
);

CREATE TABLE event (
    id           INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customer(id),
    type         TEXT NOT NULL,    -- 'login' | 'purchase' | 'feature_use'
    ts           TIMESTAMPTZ NOT NULL,
    properties   JSONB
);

CREATE TABLE orders (
    id            INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customer(id),
    amount_cents  INTEGER NOT NULL,
    currency      TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL
);

INSERT INTO customer VALUES
    (1, 'Acme Corp',     'us-east',  '2025-01-15'),
    (2, 'Globex',        'us-west',  '2025-02-20'),
    (3, 'Initech',       'eu-west',  '2025-03-10'),
    (4, 'Hooli',         'us-east',  '2025-04-05'),
    (5, 'Pied Piper',    'us-west',  '2025-05-12'),
    (6, 'Vehement',      'eu-west',  '2025-06-22'),
    (7, 'Massive Dynamic','us-east', '2025-07-30');

INSERT INTO subscription VALUES
    (1, 1, 'enterprise', 'active',    '2025-01-15 00:00:00+00', NULL),
    (2, 2, 'starter',    'active',    '2025-02-20 00:00:00+00', NULL),
    (3, 3, 'enterprise', 'cancelled', '2025-03-10 00:00:00+00', '2026-02-10 00:00:00+00'),
    (4, 4, 'pro',        'active',    '2025-04-05 00:00:00+00', NULL),
    (5, 5, 'starter',    'trial',     '2025-05-12 00:00:00+00', NULL),
    (6, 6, 'enterprise', 'active',    '2025-06-22 00:00:00+00', NULL),
    (7, 7, 'free',       'active',    '2025-07-30 00:00:00+00', NULL);

INSERT INTO event VALUES
    (1, 1, 'login',       '2026-05-01 09:00:00+00', '{"client":"web"}'),
    (2, 1, 'purchase',    '2026-05-02 10:00:00+00', '{"sku":"seat-pack-10"}'),
    (3, 1, 'feature_use', '2026-05-02 10:30:00+00', '{"feature":"sso"}'),
    (4, 2, 'login',       '2026-05-03 12:00:00+00', '{"client":"mobile"}'),
    (5, 3, 'login',       '2026-01-15 08:00:00+00', '{"client":"web"}'),
    (6, 4, 'purchase',    '2026-05-04 14:00:00+00', '{"sku":"seat-pack-5"}'),
    (7, 6, 'purchase',    '2026-05-05 16:00:00+00', '{"sku":"seat-pack-25"}'),
    (8, 6, 'feature_use', '2026-05-05 16:15:00+00', '{"feature":"audit-log"}');

INSERT INTO orders VALUES
    (1, 1, 4990000, 'USD', '2026-05-02 10:00:00+00'),
    (2, 4, 199000,  'USD', '2026-05-04 14:00:00+00'),
    (3, 6, 1249000, 'EUR', '2026-05-05 16:00:00+00');
