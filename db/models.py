"""SQLAlchemy models for the GUJRERA tracker.

Cross-DB: uses ``JSON`` (not Postgres-specific ``JSONB``) and ``DateTime(timezone=True)``
so the schema works on both SQLite (local dev) and Postgres (production).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Single declarative base for all models."""


# --- Allowed enum-ish values (enforced via CheckConstraint, not SQL ENUM) ---
PROJECT_TYPES = ("residential", "commercial", "plotted", "mixed", "unknown")
PROJECT_STATUSES = ("registered", "suspended", "completed", "expired", "unknown")
SCRAPE_SOURCES = ("kaggle_seed", "playwright_weekly", "playwright_manual")
SCRAPE_STATUSES = ("running", "success", "failed")


class Promoter(Base):
    __tablename__ = "promoters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    source_name_raw: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    projects: Mapped[list[Project]] = relationship(back_populates="promoter")

    __table_args__ = (
        UniqueConstraint("name", name="uq_promoters_name"),
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rera_reg_no: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    promoter_id: Mapped[int] = mapped_column(
        ForeignKey("promoters.id"), nullable=False
    )

    district: Mapped[str] = mapped_column(String, nullable=False)
    city_taluka: Mapped[str | None] = mapped_column(String, nullable=True)

    project_type: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    status: Mapped[str] = mapped_column(String, nullable=False, default="unknown")

    unit_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    project_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    project_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    source_detail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    source_first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    promoter: Mapped[Promoter] = relationship(back_populates="projects")

    __table_args__ = (
        UniqueConstraint("rera_reg_no", name="uq_projects_rera_reg_no"),
        CheckConstraint(
            f"project_type IN {PROJECT_TYPES}", name="ck_projects_project_type"
        ),
        CheckConstraint(
            f"status IN {PROJECT_STATUSES}", name="ck_projects_status"
        ),
        Index("ix_projects_district", "district"),
        Index("ix_projects_registration_date", "registration_date"),
        Index("ix_projects_promoter_id", "promoter_id"),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    filter_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    unsubscribe_token: Mapped[str] = mapped_column(String, nullable=False)
    confirm_token: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_alert_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unsubscribed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    alerts: Mapped[list[AlertsSent]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("unsubscribe_token", name="uq_subscriptions_unsubscribe_token"),
        UniqueConstraint("confirm_token", name="uq_subscriptions_confirm_token"),
        Index("ix_subscriptions_email", "email"),
        Index(
            "ix_subscriptions_active", "confirmed_at", "unsubscribed_at"
        ),
    )


class AlertsSent(Base):
    __tablename__ = "alerts_sent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    subscription: Mapped[Subscription] = relationship(back_populates="alerts")
    project: Mapped[Project] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "project_id", name="uq_alerts_sent_sub_proj"
        ),
    )


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    projects_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    projects_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    error_log: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"source IN {SCRAPE_SOURCES}", name="ck_scrape_runs_source"
        ),
        CheckConstraint(
            f"status IN {SCRAPE_STATUSES}", name="ck_scrape_runs_status"
        ),
    )
