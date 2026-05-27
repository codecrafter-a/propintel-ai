"""Smoke tests for the SQLAlchemy models — constraints, FKs, defaults."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import AlertsSent, Project, Promoter, ScrapeRun, Subscription


def _make_promoter(db: Session, name: str = "abc builders") -> Promoter:
    p = Promoter(name=name, source_name_raw="ABC Builders Pvt Ltd")
    db.add(p)
    db.flush()
    return p


def _make_project(db: Session, promoter: Promoter, reg_no: str = "PR/GJ/X/Y/Z/010126") -> Project:
    proj = Project(
        rera_reg_no=reg_no,
        name="Sample Project",
        promoter_id=promoter.id,
        district="Ahmedabad",
        city_taluka="Ahmedabad",
        project_type="residential",
        status="registered",
        registration_date=date(2026, 1, 1),
        content_hash="deadbeef",
        raw_payload={"foo": "bar"},
    )
    db.add(proj)
    db.flush()
    return proj


def test_create_promoter_and_project(db: Session) -> None:
    p = _make_promoter(db)
    proj = _make_project(db, p)
    db.commit()

    assert proj.id is not None
    assert proj.promoter_id == p.id
    assert proj.raw_payload == {"foo": "bar"}
    assert proj.created_at is not None
    assert proj.source_first_seen_at is not None


def test_unique_promoter_name(db: Session) -> None:
    _make_promoter(db, "dup")
    db.commit()
    db.add(Promoter(name="dup", source_name_raw="other"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_unique_rera_reg_no(db: Session) -> None:
    p = _make_promoter(db)
    _make_project(db, p, "PR/SAME/01")
    db.commit()
    db.add(
        Project(
            rera_reg_no="PR/SAME/01",
            name="Other",
            promoter_id=p.id,
            district="X",
            project_type="residential",
            status="registered",
            content_hash="x",
            raw_payload={},
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_check_constraint_project_type(db: Session) -> None:
    p = _make_promoter(db)
    db.commit()
    bad = Project(
        rera_reg_no="PR/CHK/01",
        name="Bad",
        promoter_id=p.id,
        district="X",
        project_type="banana",  # not in PROJECT_TYPES
        status="registered",
        content_hash="x",
        raw_payload={},
    )
    db.add(bad)
    with pytest.raises(IntegrityError):
        db.commit()


def test_subscription_alert_unique(db: Session) -> None:
    p = _make_promoter(db)
    proj = _make_project(db, p)
    sub = Subscription(
        email="a@b.com",
        filter_json={"districts": ["Ahmedabad"]},
        unsubscribe_token="u1",
        confirm_token="c1",
        confirmed_at=datetime.now(timezone.utc),
    )
    db.add(sub)
    db.commit()

    db.add(AlertsSent(subscription_id=sub.id, project_id=proj.id))
    db.commit()
    # Duplicate (sub, proj) blocked
    db.add(AlertsSent(subscription_id=sub.id, project_id=proj.id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_scrape_run_status_check(db: Session) -> None:
    db.add(
        ScrapeRun(
            source="kaggle_seed",
            status="totally-not-real",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()


def test_scrape_run_happy_path(db: Session) -> None:
    sr = ScrapeRun(source="kaggle_seed", status="running")
    db.add(sr)
    db.commit()
    sr.status = "success"
    sr.projects_inserted = 5
    db.commit()
    assert sr.id is not None
    assert sr.projects_inserted == 5
