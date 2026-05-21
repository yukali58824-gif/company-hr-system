-- ============================================================
-- hr_system — PostgreSQL 建表語法（完整版）
-- 執行方式：psql -U postgres -d hr_system -f init_db.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ------------------------------------------------------------
-- 1. hr_users
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hr_users (
    id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(10)  NOT NULL CHECK (role IN ('admin', 'hr')),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMP,
    created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 2. job_positions
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_positions (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title        VARCHAR(100) NOT NULL UNIQUE,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by   UUID         NOT NULL REFERENCES hr_users(id),
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 3. interview_slots
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS interview_slots (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by       UUID        NOT NULL REFERENCES hr_users(id),
    slot_date        DATE        NOT NULL,
    start_time       TIME        NOT NULL,
    end_time         TIME        NOT NULL,
    max_capacity     SMALLINT    NOT NULL CHECK (max_capacity >= 1),
    booked_count     SMALLINT    NOT NULL DEFAULT 0,
    status           VARCHAR(10) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'full', 'cancelled', 'closed')),
    google_meet_link VARCHAR(500),
    google_event_id  VARCHAR(255),
    notes            TEXT,
    log_notes        TEXT,
    created_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP   NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_end_after_start CHECK (end_time > start_time)
);

-- ------------------------------------------------------------
-- 4. applicants
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS applicants (
    id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(100) NOT NULL,
    email      VARCHAR(255) NOT NULL UNIQUE,
    phone      VARCHAR(30)  NOT NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 5. bookings
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bookings (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    slot_id          UUID         NOT NULL REFERENCES interview_slots(id),
    applicant_id     UUID         NOT NULL REFERENCES applicants(id),
    position_id      UUID         NOT NULL REFERENCES job_positions(id),
    status           VARCHAR(15)  NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled', 'no_show', 'auto_completed')),
    cancelled_by     VARCHAR(10)  CHECK (cancelled_by IN ('applicant', 'hr', 'system')),
    booked_at        TIMESTAMP    NOT NULL DEFAULT NOW(),
    cancelled_at     TIMESTAMP,
    google_meet_link VARCHAR(500),
    google_event_id  VARCHAR(255),
    notes            TEXT,
    deleted_at       TIMESTAMP,
    deleted_by       UUID         REFERENCES hr_users(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_one_active_booking_per_position
    ON bookings (applicant_id, position_id)
    WHERE status = 'confirmed' AND deleted_at IS NULL;

-- ------------------------------------------------------------
-- 6. email_logs
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_logs (
    id                      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id              UUID         NOT NULL REFERENCES bookings(id),
    recipient_email         VARCHAR(255) NOT NULL,
    email_type              VARCHAR(20)  NOT NULL CHECK (email_type IN ('booking_confirm','cancel_notify','hr_notify','reminder')),
    status                  VARCHAR(10)  NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','failed')),
    retry_count             SMALLINT     NOT NULL DEFAULT 0,
    cancel_token            VARCHAR(128) UNIQUE,
    cancel_token_expires_at TIMESTAMP,
    cancel_token_used_at    TIMESTAMP,
    last_attempted_at       TIMESTAMP,
    sent_at                 TIMESTAMP,
    updated_at              TIMESTAMP,
    error_message           TEXT
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_slots_date        ON interview_slots (slot_date);
CREATE INDEX IF NOT EXISTS idx_slots_status_date ON interview_slots (status, slot_date) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_bookings_slot      ON bookings (slot_id)      WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_bookings_applicant ON bookings (applicant_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_bookings_position  ON bookings (position_id)  WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_positions_active   ON job_positions (is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_email_retry        ON email_logs (status, retry_count) WHERE status = 'failed' AND retry_count < 3;
CREATE INDEX IF NOT EXISTS idx_email_cancel_token ON email_logs (cancel_token) WHERE cancel_token IS NOT NULL AND cancel_token_used_at IS NULL;

-- ============================================================
-- Seed: default admin account  (password: Admin1234)
-- ============================================================
INSERT INTO hr_users (name, email, password_hash, role)
VALUES (
    'admin-test',
    'admin@example.com',
    '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
    'admin'
) ON CONFLICT DO NOTHING;
