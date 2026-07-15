"""
Every SQL statement in the whole project lives here. Handlers never write
raw SQL themselves - they just call these functions with the pool that
main.py stored in context.bot_data['db_pool'].

All functions are async and take `pool: asyncpg.Pool` as the first argument.
Most are wrapped in @db_retry, which retries a few times (with backoff) if
the connection drops mid-query - e.g. Postgres restarting - instead of
letting that one blip crash the whole bot.
"""

from datetime import date, datetime, timedelta, timezone, time as time_type

import asyncpg

from database.db import db_retry


# ---------------------------------------------------------------------------
# USERS
# ---------------------------------------------------------------------------

@db_retry()
async def create_user(pool: asyncpg.Pool, telegram_id: int, full_name: str) -> asyncpg.Record:
    """Insert the user if they're new, otherwise just return the existing row.
    Called on every /start, so it must be safe to run repeatedly."""
    return await pool.fetchrow(
        """
        INSERT INTO users (telegram_id, full_name)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id) DO UPDATE SET full_name = EXCLUDED.full_name
        RETURNING id, telegram_id, full_name, phone_number, created_at;
        """,
        telegram_id, full_name,
    )


@db_retry()
async def get_user_by_telegram_id(pool: asyncpg.Pool, telegram_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "SELECT * FROM users WHERE telegram_id = $1;",
        telegram_id,
    )


@db_retry()
async def save_phone(pool: asyncpg.Pool, telegram_id: int, phone_number: str) -> None:
    await pool.execute(
        "UPDATE users SET phone_number = $1 WHERE telegram_id = $2;",
        phone_number, telegram_id,
    )


# ---------------------------------------------------------------------------
# TIME SLOTS
# ---------------------------------------------------------------------------

@db_retry()
async def generate_slots_for_date(
    pool: asyncpg.Pool,
    slot_date: date,
    start_time: time_type,
    end_time: time_type,
    duration_minutes: int,
) -> None:
    """Insert every slot between start_time and end_time for a given day,
    every duration_minutes apart. Safe to call more than once - existing
    slots are left untouched thanks to ON CONFLICT DO NOTHING. Meant to be
    called nightly by scheduler.py.

    end_time of 00:00 is treated as midnight (the end of slot_date, i.e.
    the start of the next day) rather than the very start of slot_date -
    otherwise a window like 10:00 -> 00:00 would look like it ends before
    it begins."""
    current = datetime.combine(slot_date, start_time)
    end = datetime.combine(slot_date, end_time)
    if end <= current:
        end += timedelta(days=1)

    slots = []
    while current < end:
        slots.append((slot_date, current.time()))
        current += timedelta(minutes=duration_minutes)

    await pool.executemany(
        """
        INSERT INTO time_slots (slot_date, slot_time)
        VALUES ($1, $2)
        ON CONFLICT (slot_date, slot_time) DO NOTHING;
        """,
        slots,
    )


@db_retry()
async def get_available_slots(pool: asyncpg.Pool, slot_date: date) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT id, slot_time
        FROM time_slots
        WHERE slot_date = $1 AND is_booked = false
        ORDER BY slot_time;
        """,
        slot_date,
    )


@db_retry()
async def book_slot(pool: asyncpg.Pool, slot_id: int, user_id: int) -> bool:
    """Atomically claim a slot. Returns False if someone else grabbed it a
    split second earlier - the WHERE is_booked = false is what prevents the
    double-booking race condition, no separate 'check then update' needed."""
    result = await pool.fetchrow(
        """
        UPDATE time_slots
        SET is_booked = true, booked_by = $1
        WHERE id = $2 AND is_booked = false
        RETURNING id;
        """,
        user_id, slot_id,
    )
    return result is not None


@db_retry()
async def release_slot(pool: asyncpg.Pool, slot_id: int) -> None:
    """Free up a slot again - used when a booking is rejected."""
    await pool.execute(
        "UPDATE time_slots SET is_booked = false, booked_by = NULL WHERE id = $1;",
        slot_id,
    )


@db_retry()
async def get_slot(pool: asyncpg.Pool, slot_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow("SELECT * FROM time_slots WHERE id = $1;", slot_id)


# ---------------------------------------------------------------------------
# BOOKINGS
# ---------------------------------------------------------------------------

@db_retry()
async def create_booking(
    pool: asyncpg.Pool, user_id: int, slot_id: int, phone_number: str
) -> int:
    """Creates the booking row right after a slot is successfully claimed.
    Status starts as pending_payment. Returns the new booking id."""
    row = await pool.fetchrow(
        """
        INSERT INTO bookings (user_id, slot_id, phone_number, status)
        VALUES ($1, $2, $3, 'pending_payment')
        RETURNING id;
        """,
        user_id, slot_id, phone_number,
    )
    return row["id"]


@db_retry()
async def save_receipt(pool: asyncpg.Pool, booking_id: int, file_id: str) -> bool:
    """Called when the user sends the payment screenshot. Moves the booking
    into pending_confirmation - but ONLY if it's still pending_payment.

    Returns False if the booking had already expired (see
    expire_stale_bookings below) or was otherwise no longer awaiting a
    receipt, so the caller can tell the user their reservation is gone
    instead of silently reviving an expired one."""
    result = await pool.execute(
        """
        UPDATE bookings
        SET receipt_file_id = $1, status = 'pending_confirmation'
        WHERE id = $2 AND status = 'pending_payment';
        """,
        file_id, booking_id,
    )
    return result == "UPDATE 1"


@db_retry()
async def get_booking(pool: asyncpg.Pool, booking_id: int) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        SELECT b.*, u.telegram_id, u.full_name, ts.slot_date, ts.slot_time
        FROM bookings b
        JOIN users u ON u.id = b.user_id
        JOIN time_slots ts ON ts.id = b.slot_id
        WHERE b.id = $1;
        """,
        booking_id,
    )


@db_retry()
async def confirm_booking(pool: asyncpg.Pool, booking_id: int, admin_telegram_id: int) -> None:
    await pool.execute(
        """
        UPDATE bookings
        SET status = 'confirmed', confirmed_at = now(), confirmed_by = $1
        WHERE id = $2;
        """,
        admin_telegram_id, booking_id,
    )


@db_retry()
async def reject_booking(pool: asyncpg.Pool, booking_id: int) -> None:
    """Marks the booking rejected AND frees the slot back up, in one
    transaction, so a rejected booking never permanently blocks a slot.
    Safe to retry as a whole on connection failure - either the
    transaction commits completely, or nothing happens at all."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "UPDATE bookings SET status = 'rejected' WHERE id = $1 RETURNING slot_id;",
                booking_id,
            )
            if row:
                await conn.execute(
                    "UPDATE time_slots SET is_booked = false, booked_by = NULL WHERE id = $1;",
                    row["slot_id"],
                )


@db_retry()
async def expire_stale_bookings(pool: asyncpg.Pool, minutes: int) -> list[asyncpg.Record]:
    """Finds bookings still awaiting a receipt more than `minutes` after
    they were created, marks them 'expired', and frees their slot back up
    - all in one transaction. Returns the affected rows (with the user's
    telegram_id and the slot's date/time) so the caller can notify them.

    Called periodically by scheduler.py so a slot a user reserved but
    never paid for doesn't stay stuck forever."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                UPDATE bookings b
                SET status = 'expired'
                FROM time_slots ts, users u
                WHERE b.slot_id = ts.id
                  AND b.user_id = u.id
                  AND b.status = 'pending_payment'
                  AND b.created_at < $1
                RETURNING b.id AS booking_id, b.slot_id, u.telegram_id,
                          ts.slot_date, ts.slot_time;
                """,
                cutoff,
            )
            if rows:
                slot_ids = [row["slot_id"] for row in rows]
                await conn.execute(
                    "UPDATE time_slots SET is_booked = false, booked_by = NULL WHERE id = ANY($1::int[]);",
                    slot_ids,
                )
    return rows


# ---------------------------------------------------------------------------
# ADMIN PANEL
# ---------------------------------------------------------------------------

@db_retry()
async def get_todays_bookings(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Every booking scheduled for today, any status, ordered by time.
    Powers the admin's 'Show Bookings' button - deliberately scoped to
    today only, since that's the day-to-day operational view a barber
    shop actually needs. CURRENT_DATE is safe here because create_pool()
    locks every connection's session timezone to Asia/Tashkent."""
    return await pool.fetch(
        """
        SELECT b.id, u.full_name, b.phone_number, ts.slot_date, ts.slot_time, b.status
        FROM bookings b
        JOIN users u ON u.id = b.user_id
        JOIN time_slots ts ON ts.id = b.slot_id
        WHERE ts.slot_date = CURRENT_DATE
        ORDER BY ts.slot_time;
        """
    )


@db_retry()
async def get_upcoming_bookings(
    pool: asyncpg.Pool, limit: int = 10, offset: int = 0
) -> list[asyncpg.Record]:
    """Every booking from today onward (any status), nearest first. Powers
    the admin's 'Show Upcoming Bookings' button. CURRENT_DATE is safe here
    because create_pool() locks every connection's session timezone to
    Asia/Tashkent."""
    return await pool.fetch(
        """
        SELECT b.id, u.full_name, b.phone_number, ts.slot_date, ts.slot_time, b.status
        FROM bookings b
        JOIN users u ON u.id = b.user_id
        JOIN time_slots ts ON ts.id = b.slot_id
        WHERE ts.slot_date >= CURRENT_DATE
        ORDER BY ts.slot_date ASC, ts.slot_time ASC
        LIMIT $1 OFFSET $2;
        """,
        limit, offset,
    )


@db_retry()
async def get_all_bookings(
    pool: asyncpg.Pool, limit: int = 10, offset: int = 0
) -> list[asyncpg.Record]:
    """Joined view: user info, slot date/time, and the phone number
    captured at registration time. Kept around for a future 'all bookings'
    / historical view even though the current admin button uses
    get_todays_bookings instead."""
    return await pool.fetch(
        """
        SELECT b.id, u.full_name, b.phone_number, ts.slot_date, ts.slot_time, b.status
        FROM bookings b
        JOIN users u ON u.id = b.user_id
        JOIN time_slots ts ON ts.id = b.slot_id
        ORDER BY ts.slot_date DESC, ts.slot_time DESC
        LIMIT $1 OFFSET $2;
        """,
        limit, offset,
    )


@db_retry()
async def get_pending_bookings(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Bookings waiting on admin confirmation (receipt already sent)."""
    return await pool.fetch(
        """
        SELECT b.id, u.full_name, b.phone_number, ts.slot_date, ts.slot_time, b.receipt_file_id
        FROM bookings b
        JOIN users u ON u.id = b.user_id
        JOIN time_slots ts ON ts.id = b.slot_id
        WHERE b.status = 'pending_confirmation'
        ORDER BY b.created_at;
        """,
    )