-- Run this ONCE against your existing database to add the new 'expired'
-- booking status (used by the auto-cleanup job for abandoned reservations).
-- Not needed on a fresh database - init_db.sql already includes it there.
--
--   psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f database/migrations/001_add_expired_status.sql

ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_status_check;

ALTER TABLE bookings ADD CONSTRAINT bookings_status_check
    CHECK (status IN ('pending_payment', 'pending_confirmation', 'confirmed', 'rejected', 'expired'));