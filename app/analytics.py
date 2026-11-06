"""Small, privacy-conscious LOKG-IR usage analytics backed by SQLite/Postgres.

Not a unique-person counter: anonymous random browser cookie, HMAC'd per UTC day.
No IP addresses, user-agent strings, passwords or auth cookies are persisted.
"""
from __future__ import annotations

import csv
import hmac
import io
import logging
import re
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import (
    Column, Date, DateTime, Float, Index, Integer, MetaData, String, Table,
    create_engine, delete, distinct, func, insert, select,
)
from sqlalchemy.engine import URL

from .config import Settings

logger = logging.getLogger(__name__)
COOKIE_NAME = "lokg_demo_visitor"
COOKIE_MAX_AGE = 60 * 24 * 60 * 60
COOKIE_RE = re.compile(r"^[a-f0-9]{32}$")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)[\s.\-]?(?:\d[\s.\-]?){8,10}(?!\d)")
SPACE_RE = re.compile(r"\s+")

metadata = MetaData()
events = Table(
    "lokg_usage_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("kind", String(12), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("event_date", Date, nullable=False),
    Column("visitor_day_hash", String(64), nullable=True),
    Column("query_text", String(160), nullable=True),
    Column("search_mode", String(20), nullable=True),
    Column("result_count", Integer, nullable=True),
    Column("latency_ms", Float, nullable=True),
    Column("item_id", String(64), nullable=True),
    Index("idx_lokg_events_date_kind", "event_date", "kind"),
    Index("idx_lokg_events_visitor_date", "visitor_day_hash", "event_date"),
)


def cleaned_query(query: str) -> str | None:
    """Clip length, remove control chars and mask common accidental identifiers."""
    query = SPACE_RE.sub(" ", str(query or "").strip())
    if not query:
        return None
    query = EMAIL_RE.sub("[email]", query)
    query = PHONE_RE.sub("[phone]", query)
    query = "".join(ch for ch in query if ch.isprintable())
    return query[:160] or None


def to_sqlalchemy_url(raw: str) -> str:
    """Select psycopg3 explicitly for URLs supplied by hosted Postgres providers."""
    raw = (raw or "").strip()
    if raw.startswith("postgres://"):
        return "postgresql+psycopg://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw[len("postgresql://"):]
    return raw


class Analytics:
    def __init__(self, cfg: Settings):
        self.enabled = cfg.analytics_enabled
        self.cfg = cfg
        self.engine = None
        self.prune_lock = Lock()
        self.last_prune = datetime.min.replace(tzinfo=timezone.utc)
        if not self.enabled:
            return
        url = to_sqlalchemy_url(cfg.database_url)
        if not url:
            raise RuntimeError("ANALYTICS_ENABLED=true requires DATABASE_URL")
        if url.startswith("sqlite"):
            if cfg.production and not cfg.analytics_allow_sqlite_production:
                raise RuntimeError("Render Free cannot persist SQLite; use external Postgres, or a paid persistent disk with ANALYTICS_ALLOW_SQLITE_PRODUCTION=true")
            if url.startswith("sqlite:///") and not url.endswith(":memory:"):
                db_path = Path(url.removeprefix("sqlite:///"))
                db_path.parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(url, connect_args={"check_same_thread": False}, pool_pre_ping=True)
        else:
            self.engine = create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2, pool_recycle=1800, connect_args={"connect_timeout": 10})
        metadata.create_all(self.engine)
        # Supabase exposes the public schema via an optional Data API.
        # RLS without read policies blocks anonymous API access; the server DB owner
        # continues to read/write through the private PostgreSQL connection.
        if self.engine.dialect.name == 'postgresql':
            with self.engine.begin() as conn:
                conn.exec_driver_sql('ALTER TABLE lokg_usage_events ENABLE ROW LEVEL SECURITY')
        self.prune_old(force=True)

    def _cookie_id(self, request: Request) -> str | None:
        value = request.cookies.get(COOKIE_NAME, "")
        return value if COOKIE_RE.fullmatch(value) else None

    def set_visitor_cookie(self, request: Request, response: JSONResponse) -> str | None:
        if not self.enabled:
            return None
        cookie_id = self._cookie_id(request)
        if cookie_id:
            return cookie_id
        cookie_id = secrets.token_hex(16)
        response.set_cookie(
            COOKIE_NAME, cookie_id, max_age=COOKIE_MAX_AGE,
            httponly=True, secure=self.cfg.production, samesite="lax", path="/",
        )
        return cookie_id

    def _hash_for_day(self, cookie_id: str | None, now: datetime) -> str | None:
        if not cookie_id:
            return None
        raw = f"{now.date().isoformat()}:{cookie_id}".encode("ascii")
        return hmac.new(self.cfg.analytics_secret.encode("utf-8"), raw, sha256).hexdigest()

    def prune_old(self, force=False):
        if not self.enabled:
            return
        now = datetime.now(timezone.utc)
        if not force and (now - self.last_prune).total_seconds() < 24 * 3600:
            return
        with self.prune_lock:
            if not force and (now - self.last_prune).total_seconds() < 24 * 3600:
                return
            cutoff = now.date() - timedelta(days=self.cfg.analytics_retention_days)
            with self.engine.begin() as conn:
                conn.execute(delete(events).where(events.c.event_date < cutoff))
            self.last_prune = now

    def _add(self, kind, visitor_id=None, query=None, mode=None, result_count=None, latency_ms=None, item_id=None, throttle_seconds=0):
        if not self.enabled:
            return False
        now = datetime.now(timezone.utc)
        self.prune_old()
        visitor_hash = self._hash_for_day(visitor_id, now)
        with self.engine.begin() as conn:
            if throttle_seconds and visitor_hash:
                previous = conn.execute(
                    select(events.c.id).where(
                        events.c.kind == kind,
                        events.c.visitor_day_hash == visitor_hash,
                        events.c.created_at >= now - timedelta(seconds=throttle_seconds),
                    ).limit(1)
                ).first()
                if previous:
                    return False
            conn.execute(insert(events).values(
                kind=kind, created_at=now, event_date=now.date(),
                visitor_day_hash=visitor_hash,
                query_text=cleaned_query(query) if self.cfg.analytics_store_queries and kind == "search" else None,
                search_mode=mode, result_count=result_count,
                latency_ms=latency_ms, item_id=item_id,
            ))
        return True

    def record_visit(self, visitor_id):
        # Double-loaded tabs and very frequent reloads should not inflate the counter.
        return self._add("visit", visitor_id=visitor_id, throttle_seconds=30)

    def record_search(self, request: Request, query: str, mode: str, total: int, latency: float, offset: int):
        if not query.strip() or offset != 0:
            return False
        return self._add("search", visitor_id=self._cookie_id(request), query=query,
                         mode=mode, result_count=total, latency_ms=latency)

    def record_click(self, request: Request, item_id: str):
        return self._add("click", visitor_id=self._cookie_id(request), item_id=item_id)

    def _count(self, conn, kind=None, since=None):
        q = select(func.count()).select_from(events)
        if kind is not None:
            q = q.where(events.c.kind == kind)
        if since is not None:
            q = q.where(events.c.event_date >= since)
        return int(conn.scalar(q) or 0)

    def public(self):
        if not self.enabled:
            return {"enabled": False, "visits": None, "searches": None, "visits_today": None,
                    "unique_browsers_today": None}
        today = datetime.now(timezone.utc).date()
        with self.engine.connect() as conn:
            return {
                "enabled": True,
                "visits": self._count(conn, "visit"),
                "searches": self._count(conn, "search"),
                "visits_today": self._count(conn, "visit", today),
                "unique_browsers_today": int(conn.scalar(
                    select(func.count(distinct(events.c.visitor_day_hash))).where(
                        events.c.kind == "visit", events.c.event_date == today,
                        events.c.visitor_day_hash.is_not(None))) or 0),
                "timezone": "UTC",
                "counting": "Browser visits (30-second deduplication); not unique people.",
            }

    def admin_report(self, days=30):
        if not self.enabled:
            return {"enabled": False, "message": "Chưa bật ANALYTICS_ENABLED hoặc chưa cấu hình DATABASE_URL."}
        start = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
        with self.engine.connect() as conn:
            by_day = conn.execute(
                select(events.c.event_date, events.c.kind, func.count().label("n"))
                .where(events.c.event_date >= start)
                .group_by(events.c.event_date, events.c.kind)
                .order_by(events.c.event_date)
            ).all()
            daily = {str(start + timedelta(days=i)): {"date": str(start + timedelta(days=i)), "visits": 0, "searches": 0, "clicks": 0} for i in range(days)}
            for dt, kind, n in by_day:
                key = str(dt)
                field = {"visit": "visits", "search": "searches", "click": "clicks"}.get(kind)
                if field:
                    daily[key][field] = int(n)
            top_queries = conn.execute(
                select(events.c.query_text, func.count().label("n"))
                .where(events.c.kind == "search", events.c.event_date >= start, events.c.query_text.is_not(None))
                .group_by(events.c.query_text)
                .order_by(func.count().desc(), events.c.query_text).limit(15)
            ).all()
            modes = conn.execute(
                select(events.c.search_mode, func.count().label("n"))
                .where(events.c.kind == "search", events.c.event_date >= start)
                .group_by(events.c.search_mode).order_by(func.count().desc())
            ).all()
            popular_items = conn.execute(
                select(events.c.item_id, func.count().label("n"))
                .where(events.c.kind == "click", events.c.event_date >= start, events.c.item_id.is_not(None))
                .group_by(events.c.item_id).order_by(func.count().desc()).limit(15)
            ).all()
            unique_visitors_today = int(conn.scalar(
                select(func.count(distinct(events.c.visitor_day_hash))).where(
                    events.c.kind == "visit",
                    events.c.event_date == datetime.now(timezone.utc).date(),
                    events.c.visitor_day_hash.is_not(None)
                )) or 0)
            no_results = int(conn.scalar(
                select(func.count()).select_from(events).where(
                    events.c.kind == "search", events.c.event_date >= start,
                    events.c.result_count == 0,
                )) or 0)
        summary = {k: sum(d[k] for d in daily.values()) for k in ("visits", "searches", "clicks")}
        summary["no_results"] = no_results
        summary["unique_browsers_today"] = unique_visitors_today
        summary["no_result_rate_pct"] = round(100 * no_results / summary["searches"], 1) if summary["searches"] else 0
        return {"enabled": True, "period_days": days, "timezone": "UTC", "summary": summary,
                "daily": list(daily.values()),
                "top_queries": [{"query": q, "count": int(n)} for q, n in top_queries],
                "modes": [{"mode": m or "unknown", "count": int(n)} for m, n in modes],
                "popular_items": [{"item_id": it, "count": int(n)} for it, n in popular_items],
                "privacy": "No raw IP, user-agent or names stored. Browser IDs HMAC'd and rotated daily. Terms sanitized; retention limited.",
                "retention_days": self.cfg.analytics_retention_days,
                }

    def report_csv(self, days=30):
        report = self.admin_report(days)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date_utc", "visits", "searches", "clicks"])
        if report.get("enabled"):
            for row in report["daily"]:
                writer.writerow([row["date"], row["visits"], row["searches"], row["clicks"]])
        return "\ufeff" + output.getvalue()
