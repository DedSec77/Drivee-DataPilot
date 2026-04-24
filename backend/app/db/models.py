from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class DimCity(Base):
    __tablename__ = "dim_cities"

    city_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    country: Mapped[str] = mapped_column(Text, default="Россия")
    timezone: Mapped[str | None] = mapped_column(Text, nullable=True)


class DimChannel(Base):
    __tablename__ = "dim_channels"

    channel_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    channel_name_ru: Mapped[str | None] = mapped_column(Text, nullable=True)


class DimUser(Base):
    __tablename__ = "dim_users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signup_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    segment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_driver: Mapped[bool] = mapped_column(Boolean, default=False)
    is_rider: Mapped[bool] = mapped_column(Boolean, default=True)
    phone_masked: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_hash: Mapped[str | None] = mapped_column(Text, nullable=True)


class FctTrip(Base):
    __tablename__ = "fct_trips"

    trip_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rider_id: Mapped[int | None] = mapped_column(ForeignKey("dim_users.user_id"), nullable=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("dim_users.user_id"), nullable=True)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("dim_cities.city_id"), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("dim_channels.channel_id"), nullable=True)
    booking_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trip_start_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trip_end_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancellation_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    cancellation_party: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_fare: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    actual_fare: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surge_multiplier: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SavedReport(Base):
    __tablename__ = "saved_reports"

    report_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    nl_question: Mapped[str] = mapped_column(Text, nullable=False)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    chart_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)


class Schedule(Base):
    __tablename__ = "schedules"

    schedule_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    report_id: Mapped[int | None] = mapped_column(
        ForeignKey("saved_reports.report_id", ondelete="CASCADE"), nullable=True
    )
    cron_expr: Mapped[str] = mapped_column(Text, nullable=False)
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    last_run_ts: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class QueryLog(Base):
    __tablename__ = "query_log"

    log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)
    nl_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql_generated: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql_executed: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    guard_verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    exec_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    voting_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
