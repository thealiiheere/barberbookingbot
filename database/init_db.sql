-- Run once to set up the database:
--   psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f init_db.sql

-- =========================================================
-- users: one row per Telegram user
-- =========================================================
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    telegram_id   BIGINT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    phone_number  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================================================
-- time_slots: one row per bookable 30-minute slot, per day.
-- A nightly job (scheduler.py, built later) inserts tomorrow's
-- slots so the table never runs dry.
-- =========================================================
CREATE TABLE IF NOT EXISTS time_slots (
    id          SERIAL PRIMARY KEY,
    slot_date   DATE NOT NULL,
    slot_time   TIME NOT NULL,
    is_booked   BOOLEAN NOT NULL DEFAULT false,
    booked_by   INTEGER REFERENCES users(id),
    UNIQUE (slot_date, slot_time)
);

CREATE INDEX IF NOT EXISTS idx_time_slots_date_available
    ON time_slots (slot_date, is_booked);

-- =========================================================
-- bookings: one row per booking attempt/confirmation.
-- phone_number is a SNAPSHOT copied at booking time, so it stays
-- accurate even if the user later changes their saved number.
-- status flow: pending_payment -> pending_confirmation -> confirmed / rejected
-- =========================================================
CREATE TABLE IF NOT EXISTS bookings (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id),
    slot_id          INTEGER NOT NULL REFERENCES time_slots(id),
    phone_number     TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending_payment'
                        CHECK (status IN ('pending_payment', 'pending_confirmation', 'confirmed', 'rejected', 'expired')),
    receipt_file_id  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at     TIMESTAMPTZ,
    confirmed_by     BIGINT
);

CREATE INDEX IF NOT EXISTS idx_bookings_status
    ON bookings (status);