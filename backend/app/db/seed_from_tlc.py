from __future__ import annotations

import argparse
import hashlib
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from sqlalchemy import text

from app.db.session import engine

RU_CITIES = [
    ("Москва", 0.35, "Europe/Moscow"),
    ("Санкт-Петербург", 0.18, "Europe/Moscow"),
    ("Новосибирск", 0.07, "Asia/Novosibirsk"),
    ("Екатеринбург", 0.06, "Asia/Yekaterinburg"),
    ("Казань", 0.05, "Europe/Moscow"),
    ("Нижний Новгород", 0.05, "Europe/Moscow"),
    ("Самара", 0.04, "Europe/Samara"),
    ("Ростов-на-Дону", 0.04, "Europe/Moscow"),
    ("Уфа", 0.04, "Asia/Yekaterinburg"),
    ("Краснодар", 0.12, "Europe/Moscow"),
]

CHANNELS = [
    ("app", "приложение", 0.72),
    ("web", "веб", 0.18),
    ("partner", "партнёры", 0.10),
]

SEGMENTS = [("new", 0.30), ("loyal", 0.55), ("vip", 0.15)]

CANCEL_REASONS = {
    "rider": ["передумал", "долгое ожидание", "неверный адрес", "нашёл альтернативу"],
    "driver": ["далеко", "технические проблемы", "смена закончилась", "пробка"],
    "system": ["сбой оплаты", "ошибка тарифа", "технический сбой"],
}

USD_TO_RUB = 95.0
MI_TO_KM = 1.609

rng = np.random.default_rng(42)
random.seed(42)


def weighted(items: list[tuple], field_idx: int = -1) -> str:
    weights = [it[field_idx] for it in items]
    total = sum(weights)
    r = random.random() * total
    acc = 0.0
    for it in items:
        acc += it[field_idx]
        if r <= acc:
            return it[0]
    return items[-1][0]


def _seed_dim_tables() -> dict:
    with engine.begin() as conn:
        for name, _, tz in RU_CITIES:
            conn.execute(
                text(
                    "INSERT INTO dim_cities (city_name, country, timezone) VALUES (:n, 'Россия', :t) ON CONFLICT (city_name) DO NOTHING"
                ),
                {"n": name, "t": tz},
            )
        for name, name_ru, _ in CHANNELS:
            conn.execute(
                text(
                    "INSERT INTO dim_channels (channel_name, channel_name_ru) VALUES (:n, :nr) ON CONFLICT (channel_name) DO NOTHING"
                ),
                {"n": name, "nr": name_ru},
            )
        city_ids = {
            r[0]: r[1] for r in conn.execute(text("SELECT city_name, city_id FROM dim_cities")).fetchall()
        }
        channel_ids = {
            r[0]: r[1]
            for r in conn.execute(text("SELECT channel_name, channel_id FROM dim_channels")).fetchall()
        }
    return {"cities": city_ids, "channels": channel_ids}


def _seed_users(n: int) -> dict:
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT COUNT(*) FROM dim_users")).scalar_one()
        if existing >= n:
            logger.info(f"dim_users already has {existing} rows, skipping user seed")
            riders = conn.execute(
                text("SELECT user_id FROM dim_users WHERE is_rider = true AND is_driver = false LIMIT :n"),
                {"n": int(n * 0.85)},
            ).fetchall()
            drivers = conn.execute(
                text("SELECT user_id FROM dim_users WHERE is_driver = true LIMIT :n"),
                {"n": n - int(n * 0.85)},
            ).fetchall()
            return {
                "rider_ids": [r[0] for r in riders],
                "driver_ids": [r[0] for r in drivers],
            }

        riders_needed = int(n * 0.85)
        drivers_needed = n - riders_needed
        rows = []
        now = datetime.now(UTC)
        for _ in range(riders_needed):
            seg = weighted(SEGMENTS)
            rows.append(
                {
                    "signup_ts": now - timedelta(days=int(rng.integers(0, 900))),
                    "segment": seg,
                    "is_driver": False,
                    "is_rider": True,
                    "phone_masked": f"+7***{rng.integers(1000, 9999)}",
                    "email_hash": hashlib.sha256(str(rng.integers(0, 1_000_000)).encode()).hexdigest()[:16],
                }
            )
        for _ in range(drivers_needed):
            rows.append(
                {
                    "signup_ts": now - timedelta(days=int(rng.integers(60, 1500))),
                    "segment": None,
                    "is_driver": True,
                    "is_rider": False,
                    "phone_masked": f"+7***{rng.integers(1000, 9999)}",
                    "email_hash": hashlib.sha256(str(rng.integers(0, 1_000_000)).encode()).hexdigest()[:16],
                }
            )
        conn.execute(
            text("""
                INSERT INTO dim_users
                  (signup_ts, segment, is_driver, is_rider, phone_masked, email_hash)
                VALUES
                  (:signup_ts, :segment, :is_driver, :is_rider, :phone_masked, :email_hash)
            """),
            rows,
        )
        riders = conn.execute(
            text("SELECT user_id FROM dim_users WHERE is_rider = true AND is_driver = false LIMIT :n"),
            {"n": riders_needed * 2},
        ).fetchall()
        drivers = conn.execute(
            text("SELECT user_id FROM dim_users WHERE is_driver = true LIMIT :n"),
            {"n": drivers_needed * 2},
        ).fetchall()

    return {
        "rider_ids": [r[0] for r in riders],
        "driver_ids": [r[0] for r in drivers],
    }


def _load_tlc(path: Path, sample: int) -> pd.DataFrame:
    logger.info(f"reading TLC parquet: {path}")
    df = pd.read_parquet(path)
    if len(df) > sample:
        df = df.sample(sample, random_state=42).reset_index(drop=True)
    df = df.rename(
        columns={
            "tpep_pickup_datetime": "pickup_ts",
            "tpep_dropoff_datetime": "dropoff_ts",
            "trip_distance": "distance_mi",
            "total_amount": "total_usd",
        }
    )
    df = df.dropna(subset=["pickup_ts", "dropoff_ts", "distance_mi", "total_usd"])
    df = df[(df["distance_mi"] > 0) & (df["distance_mi"] < 50)]
    df = df[(df["total_usd"] > 0) & (df["total_usd"] < 500)]
    df["duration_minutes"] = ((df["dropoff_ts"] - df["pickup_ts"]).dt.total_seconds() // 60).astype(int)
    df = df[(df["duration_minutes"] >= 1) & (df["duration_minutes"] < 240)]
    return df[["pickup_ts", "dropoff_ts", "distance_mi", "total_usd", "duration_minutes"]]


def _synthesize_tlc_like(n: int, months: int) -> pd.DataFrame:
    logger.info(f"synthesizing {n} TLC-like rows over last {months} months")
    now = datetime.now(UTC).replace(microsecond=0)
    start = now - timedelta(days=months * 30)

    seconds_range = int((now - start).total_seconds())
    pickups = [start + timedelta(seconds=int(rng.integers(0, seconds_range))) for _ in range(n)]
    durations = np.clip(rng.lognormal(mean=2.3, sigma=0.6, size=n), 2, 180).astype(int)
    dropoffs = [p + timedelta(minutes=int(d)) for p, d in zip(pickups, durations, strict=False)]
    distance_km = np.clip(rng.lognormal(mean=1.3, sigma=0.7, size=n), 0.3, 60)
    fare_rub = np.clip(200 + distance_km * 45 + rng.normal(0, 80, size=n), 150, 15000)
    return pd.DataFrame(
        {
            "pickup_ts": pickups,
            "dropoff_ts": dropoffs,
            "distance_mi": distance_km / MI_TO_KM,
            "total_usd": fare_rub / USD_TO_RUB,
            "duration_minutes": durations,
        }
    )


def _surge_for(ts: datetime, city_name: str) -> float:
    h = ts.hour
    base = 1.0
    if 7 <= h <= 10 or 17 <= h <= 20:
        base = 1.4
    elif h >= 22 or h <= 2:
        base = 1.2
    city_boost = {"Москва": 0.2, "Санкт-Петербург": 0.15}.get(city_name, 0.0)
    noise = rng.normal(0, 0.1)
    return round(max(0.8, min(3.0, base + city_boost + noise)), 2)


def _synth_trip_row(row: dict, ids: dict, users: dict) -> dict:
    status = weighted([("completed", 0.88), ("cancelled", 0.10), ("no_show", 0.02)], field_idx=1)
    cancel_party = None
    cancel_reason = None
    cancel_ts = None
    if status == "cancelled":
        cancel_party = weighted([("rider", 0.55), ("driver", 0.35), ("system", 0.10)], field_idx=1)
        cancel_reason = random.choice(CANCEL_REASONS[cancel_party])
        cancel_ts = row["pickup_ts"] + timedelta(minutes=int(rng.integers(0, 10)))
    channel = weighted([(n, w) for n, _, w in CHANNELS], field_idx=1)

    city_name = weighted([(n, w) for n, w, _ in RU_CITIES], field_idx=1)
    city_id = ids["cities"].get(city_name)
    channel_id = ids["channels"].get(channel)

    distance_km = round(float(row["distance_mi"]) * MI_TO_KM, 2)
    actual_fare_rub = round(float(row["total_usd"]) * USD_TO_RUB, 2)
    surge = _surge_for(row["pickup_ts"], city_name)

    trip_start_ts = (
        row["pickup_ts"]
        if status == "completed"
        else (cancel_ts if status == "cancelled" else row["pickup_ts"])
    )
    trip_end_ts = row["dropoff_ts"] if status == "completed" else None

    rating = int(np.clip(rng.normal(4.7, 0.4), 1, 5)) if status == "completed" else None

    return {
        "rider_id": random.choice(users["rider_ids"]) if users["rider_ids"] else None,
        "driver_id": random.choice(users["driver_ids"]) if users["driver_ids"] else None,
        "city_id": city_id,
        "channel_id": channel_id,
        "booking_ts": row["pickup_ts"] - timedelta(minutes=int(rng.integers(1, 8))),
        "trip_start_ts": trip_start_ts,
        "trip_end_ts": trip_end_ts,
        "cancellation_ts": cancel_ts,
        "status": status,
        "cancellation_party": cancel_party,
        "cancellation_reason": cancel_reason,
        "estimated_fare": round(actual_fare_rub * 0.95, 2),
        "actual_fare": actual_fare_rub if status == "completed" else None,
        "distance_km": distance_km if status == "completed" else None,
        "duration_minutes": int(row["duration_minutes"]) if status == "completed" else None,
        "surge_multiplier": surge,
        "rating": rating,
    }


_ALLOWED_TRIP_COLS: frozenset[str] = frozenset(
    {
        "rider_id",
        "driver_id",
        "city_id",
        "channel_id",
        "booking_ts",
        "trip_start_ts",
        "trip_end_ts",
        "cancellation_ts",
        "status",
        "cancellation_party",
        "cancellation_reason",
        "estimated_fare",
        "actual_fare",
        "distance_km",
        "duration_minutes",
        "surge_multiplier",
        "rating",
    }
)


def _bulk_insert(rows: list[dict], batch: int = 5000) -> None:
    if not rows:
        logger.info("no rows to insert into fct_trips")
        return
    cols = list(rows[0].keys())
    unknown = [c for c in cols if c not in _ALLOWED_TRIP_COLS]
    if unknown:
        raise ValueError(
            f"refusing to insert into fct_trips with unknown columns: {unknown}. "
            "Update _ALLOWED_TRIP_COLS if the schema actually changed."
        )
    col_list = ", ".join(cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    sql = f"INSERT INTO fct_trips ({col_list}) VALUES ({placeholders})"
    with engine.begin() as conn:
        for i in range(0, len(rows), batch):
            conn.execute(text(sql), rows[i : i + batch])
            logger.info(f"inserted {i + min(batch, len(rows) - i)}/{len(rows)}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--parquet", type=Path, default=None, help="Optional path to NYC TLC parquet file")
    p.add_argument("--sample", type=int, default=500_000)
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--users", type=int, default=10_000)
    args = p.parse_args()

    ids = _seed_dim_tables()
    users = _seed_users(args.users)
    logger.info(
        f"dim seeded: cities={len(ids['cities'])} channels={len(ids['channels'])} "
        f"riders={len(users['rider_ids'])} drivers={len(users['driver_ids'])}"
    )

    if args.parquet and args.parquet.exists():
        df = _load_tlc(args.parquet, args.sample)
    else:
        df = _synthesize_tlc_like(args.sample, args.months)

    logger.info(f"base rows: {len(df):,}; building Drivee trips...")
    rows = [
        _synth_trip_row(r._asdict() if hasattr(r, "_asdict") else dict(r), ids, users)
        for r in df.to_dict("records")
    ]

    logger.info(f"bulk inserting {len(rows):,} rows into fct_trips")
    _bulk_insert(rows)
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM fct_trips")).scalar_one()
    logger.info(f"Done. fct_trips row count: {total:,}")


if __name__ == "__main__":
    main()
