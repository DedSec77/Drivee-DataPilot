CREATE SCHEMA IF NOT EXISTS drivee;
ALTER DATABASE drivee SET search_path TO drivee, public;
SET search_path TO drivee, public;

CREATE TABLE IF NOT EXISTS dim_cities (
    city_id       SERIAL PRIMARY KEY,
    city_name     TEXT NOT NULL UNIQUE,
    country       TEXT DEFAULT 'Россия',
    timezone      TEXT
);

CREATE TABLE IF NOT EXISTS dim_channels (
    channel_id       SERIAL PRIMARY KEY,
    channel_name     TEXT NOT NULL UNIQUE,
    channel_name_ru  TEXT
);

CREATE TABLE IF NOT EXISTS dim_users (
    user_id       SERIAL PRIMARY KEY,
    signup_ts     TIMESTAMP,
    segment       TEXT,
    is_driver     BOOLEAN DEFAULT FALSE,
    is_rider      BOOLEAN DEFAULT TRUE,
    phone_masked  TEXT,
    email_hash    TEXT
);

CREATE TABLE IF NOT EXISTS fct_trips (
    trip_id              BIGSERIAL PRIMARY KEY,
    rider_id             INT REFERENCES dim_users(user_id),
    driver_id            INT REFERENCES dim_users(user_id),
    city_id              INT REFERENCES dim_cities(city_id),
    channel_id           INT REFERENCES dim_channels(channel_id),
    booking_ts           TIMESTAMP,
    trip_start_ts        TIMESTAMP,
    trip_end_ts          TIMESTAMP,
    cancellation_ts      TIMESTAMP,
    status               TEXT NOT NULL,
    cancellation_party   TEXT,
    cancellation_reason  TEXT,
    estimated_fare       NUMERIC(10, 2),
    actual_fare          NUMERIC(10, 2),
    distance_km          NUMERIC(8, 2),
    duration_minutes     INT,
    surge_multiplier     NUMERIC(3, 2),
    rating               INT
);

CREATE INDEX IF NOT EXISTS ix_trips_start         ON fct_trips (trip_start_ts);
CREATE INDEX IF NOT EXISTS ix_trips_city_status   ON fct_trips (city_id, status);
CREATE INDEX IF NOT EXISTS ix_trips_channel_start ON fct_trips (channel_id, trip_start_ts);
CREATE INDEX IF NOT EXISTS ix_trips_cancel_party  ON fct_trips (cancellation_party)
    WHERE cancellation_party IS NOT NULL;

CREATE TABLE IF NOT EXISTS saved_reports (
    report_id      BIGSERIAL PRIMARY KEY,
    owner          TEXT NOT NULL,
    title          TEXT NOT NULL,
    nl_question    TEXT NOT NULL,
    sql_text       TEXT NOT NULL,
    chart_type     TEXT,
    created_at     TIMESTAMP DEFAULT now(),
    is_approved    BOOLEAN DEFAULT FALSE,
    is_template    BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id    BIGSERIAL PRIMARY KEY,
    report_id      BIGINT REFERENCES saved_reports(report_id) ON DELETE CASCADE,
    cron_expr      TEXT NOT NULL,
    destination    TEXT NOT NULL,
    last_run_ts    TIMESTAMP,
    is_active      BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS query_log (
    log_id         BIGSERIAL PRIMARY KEY,
    ts             TIMESTAMP DEFAULT now(),
    user_ctx       JSONB,
    nl_question    TEXT,
    sql_generated  TEXT,
    sql_executed   TEXT,
    confidence     REAL,
    guard_verdict  TEXT,
    exec_ms        INT,
    result_rows    INT,
    error          TEXT,
    voting_summary JSONB
);

ALTER TABLE query_log ADD COLUMN IF NOT EXISTS voting_summary JSONB;
