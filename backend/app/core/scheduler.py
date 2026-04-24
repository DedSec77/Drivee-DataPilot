from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.db.session import raw_psycopg

SCHEDULED_DIR = Path("/app/data/scheduled_reports")

scheduler: BackgroundScheduler = BackgroundScheduler(timezone="Europe/Moscow")


def _job_id(schedule_id: int) -> str:
    return f"sched-{schedule_id}"


def _run_saved_report(schedule_id: int, report_id: int, destination: str) -> None:
    try:
        run_saved_report_now(report_id, destination, schedule_id=schedule_id)
    except Exception as e:
        logger.error(f"[scheduler] cron tick failed schedule_id={schedule_id} report_id={report_id}: {e}")


def run_saved_report_now(
    report_id: int,
    destination: str,
    *,
    schedule_id: int | None = None,
) -> dict:
    with raw_psycopg() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT sql_text, title FROM saved_reports WHERE report_id = %s",
            (report_id,),
        )
        row = cur.fetchone()
        if not row:
            raise FileNotFoundError(f"saved report {report_id} not found")
        sql_text, title = row
        cur.execute(sql_text)
        cols = [c.name for c in cur.description] if cur.description else []
        rows = cur.fetchall() if cur.description else []

    SCHEDULED_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = SCHEDULED_DIR / f"report{report_id}-{ts}.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(r)
    logger.info(f"[scheduler] '{title}' -> {path.name} ({len(rows)} rows) · destination={destination}")

    if schedule_id is not None:
        try:
            with raw_psycopg() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE schedules SET last_run_ts = now() WHERE schedule_id = %s",
                        (schedule_id,),
                    )
                conn.commit()
        except Exception as e:
            logger.warning(f"[scheduler] failed to update last_run_ts for schedule_id={schedule_id}: {e}")

    return {
        "filename": path.name,
        "rows": len(rows),
        "size_bytes": path.stat().st_size,
        "download_url": f"/files/scheduled/{path.name}",
    }


def list_scheduled_runs(report_id: int | None = None, limit: int = 50) -> list[dict]:
    if not SCHEDULED_DIR.exists():
        return []
    files = sorted(SCHEDULED_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if report_id is not None:
        files = [p for p in files if p.name.startswith(f"report{report_id}-")]
    out: list[dict] = []
    for p in files[:limit]:
        st = p.stat()
        created = datetime.fromtimestamp(st.st_mtime, tz=UTC)
        out.append(
            {
                "filename": p.name,
                "size_bytes": st.st_size,
                "created_at": created.isoformat().replace("+00:00", "Z"),
                "download_url": f"/files/scheduled/{p.name}",
            }
        )
    return out


def delete_scheduled_run(filename: str) -> bool:
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError(f"invalid filename: {filename!r}")
    if not filename.endswith(".csv"):
        raise ValueError("only .csv files can be deleted here")

    target = (SCHEDULED_DIR / filename).resolve()
    root = SCHEDULED_DIR.resolve()

    try:
        target.relative_to(root)
    except ValueError as e:
        raise ValueError(f"filename escapes scheduled_reports: {filename!r}") from e

    if not target.exists():
        return False
    target.unlink()
    return True


def register_schedule(schedule_id: int, report_id: int, cron_expr: str, destination: str) -> None:
    scheduler.add_job(
        _run_saved_report,
        trigger=CronTrigger.from_crontab(cron_expr),
        args=[schedule_id, report_id, destination],
        id=_job_id(schedule_id),
        replace_existing=True,
    )


def unregister_schedule(schedule_id: int) -> bool:
    try:
        scheduler.remove_job(_job_id(schedule_id))
        return True
    except JobLookupError:
        logger.debug(f"[scheduler] unregister schedule_id={schedule_id}: job not present")
        return False


def hydrate_from_db() -> int:
    try:
        with raw_psycopg() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT schedule_id, report_id, cron_expr, destination "
                "FROM schedules "
                "WHERE is_active = true AND report_id IS NOT NULL"
            )
            rows = cur.fetchall()
    except Exception as e:
        logger.warning(f"[scheduler] hydrate skipped (db not ready?): {e}")
        return 0

    n_ok = 0
    for schedule_id, report_id, cron_expr, destination in rows:
        try:
            register_schedule(schedule_id, report_id, cron_expr, destination)
            n_ok += 1
        except Exception as e:
            logger.warning(f"[scheduler] hydrate skip schedule_id={schedule_id} (cron={cron_expr!r}): {e}")
    if n_ok:
        logger.info(f"[scheduler] hydrated {n_ok} schedule(s) from DB")
    return n_ok


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
        logger.info("[scheduler] started")
        hydrate_from_db()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
