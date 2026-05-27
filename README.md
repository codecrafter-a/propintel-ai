# GUJRERA Tracker

Phase 1 of a real-estate intelligence platform. Scrapes Gujarat RERA project approvals, lets users search them, and emails subscribers when new projects match their saved filter.

See [docs/superpowers/specs/2026-05-27-gujrera-tracker-design.md](docs/superpowers/specs/2026-05-27-gujrera-tracker-design.md) for the full design and [docs/superpowers/plans/2026-05-27-gujrera-tracker.md](docs/superpowers/plans/2026-05-27-gujrera-tracker.md) for the implementation plan.

## Repo layout

```
/api          FastAPI backend (REST API + admin endpoints + alert dispatcher)
/scraper      Python CLI scraper (Playwright + Kaggle backfill)
/db           SQLAlchemy models, session helper, promoter normalizer
/migrations   Alembic migrations
/tests        pytest suite
/web          Next.js frontend (public dashboard + admin pages)
/docs         Specs and plans
```

## Quick start (local dev)

Prereqs: Python 3.11+, Node 20+, [uv](https://github.com/astral-sh/uv), Git. SQLite is used in dev — no Postgres needed locally.

```powershell
# 1. Install Python deps (includes dev tools)
uv sync --all-groups

# 2. Set up local env
Copy-Item .env.example .env

# 3. Create the SQLite dev DB and run migrations
uv run alembic upgrade head

# 4. Start the API
uv run uvicorn api.main:app --reload --port 8000

# 5. (in another shell) start the web
cd web
npm install
npm run dev
```

The API serves at `http://localhost:8000`, the web at `http://localhost:3000`.

## Scraper usage

The scraper is a CLI run manually from the operator's machine (residential IP):

```powershell
# Backfill from the Kaggle CSV (one-time, download manually from
# https://www.kaggle.com/datasets/ethon0426/gujarat-real-estate-project-registered-2017-2022 ):
uv run python -m scraper run --mode=backfill --csv .\data\gujrera-2010-2023.csv

# Weekly delta scrape (drives the GUJRERA search form via Playwright):
uv run python -m scraper run --mode=weekly
```

First-time Playwright setup:

```powershell
uv run playwright install chromium
```

## Tests

```powershell
uv run pytest -q
```

## License

MIT (placeholder — finalize before public launch).
