# GUJRERA Tracker — Implementation Plan (Compressed)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.
>
> This is a compressed plan at the user's explicit request to accelerate execution. Each task lists files + key code/commands; the executor applies TDD where logical (parser, filter-matching, alert-dispatch) and lighter scaffolding-style commits for boilerplate.

**Goal:** Build the v1 GUJRERA project tracker per [the spec](../specs/2026-05-27-gujrera-tracker-design.md): Python FastAPI backend + Next.js frontend + Python Playwright scraper, sharing a Postgres (or SQLite in local dev) database. Public dashboard + email-subscribed alerts on new approvals. Static admin login.

**Architecture:** Monorepo at repo root. Single Python project (`api/`, `scraper/`, `db/`) at root. Next.js project at `/web/`. Local dev uses SQLite; production points `DATABASE_URL` at Postgres. See spec §6.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic · Pydantic v2 · Playwright (Python) · BeautifulSoup · pytest · Next.js 14 (App Router) · TypeScript · Tailwind · Resend.

---

## Repo layout (locked in)

```
/RERA/
  pyproject.toml          # single Python project
  alembic.ini
  .env.example
  .gitignore
  README.md
  api/                    # FastAPI app
    main.py
    routers/{public.py, subscriptions.py, admin.py, auth.py}
    deps.py
    auth.py
    schemas.py
    settings.py
    email_client.py
    alerts.py             # dispatcher logic
  scraper/                # Python CLI
    __main__.py
    cli.py
    parser.py             # pure HTML→dict, easy to test
    playwright_driver.py
    backfill.py           # Kaggle CSV import
    weekly.py             # orchestrator
    config.py
  db/                     # shared SQLAlchemy
    __init__.py
    models.py
    session.py
    promoter_normalizer.py
  migrations/             # alembic
    env.py
    versions/
  tests/
    api/
    scraper/
    db/
  web/                    # Next.js
    package.json
    app/
      layout.tsx
      page.tsx
      projects/page.tsx
      projects/[regNo]/page.tsx
      subscribe/page.tsx
      subscribe/confirmed/page.tsx
      unsubscribe/page.tsx
      admin/login/page.tsx
      admin/dashboard/page.tsx
      admin/subscriptions/page.tsx
      admin/scrape-runs/page.tsx
      api/auth/login/route.ts
    lib/
      api.ts              # typed API client
      auth.ts             # cookie helpers
    middleware.ts
    tailwind.config.ts
  docs/
    superpowers/
      specs/2026-05-27-gujrera-tracker-design.md
      plans/2026-05-27-gujrera-tracker.md
```

---

## Phase A — Foundation

### Task 1: Repo init + Python project skeleton
- [ ] Files: `pyproject.toml`, `.gitignore`, `README.md`, `.env.example`, empty package `__init__.py` files for `api/`, `scraper/`, `db/`, `tests/`.
- [ ] `pyproject.toml` deps: `fastapi`, `uvicorn[standard]`, `sqlalchemy>=2`, `alembic`, `pydantic>=2`, `pydantic-settings`, `python-jose[cryptography]`, `passlib[bcrypt]`, `httpx`, `python-multipart`, `playwright`, `beautifulsoup4`, `lxml`, `pandas`, `psycopg[binary]`, `resend`. Dev deps: `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`.
- [ ] `git init` + initial commit.

### Task 2: SQLAlchemy models matching schema (spec §7)
- [ ] Create `db/models.py` with `Promoter`, `Project`, `Subscription`, `AlertsSent`, `ScrapeRun`. Use `JSON` (cross-db) not `JSONB`. Use `Integer` PK autoincrement.
- [ ] Create `db/session.py`: engine, sessionmaker, `get_db()` dependency. Driver picked from `DATABASE_URL` (sqlite:// or postgresql+psycopg://).
- [ ] Add `promoter_normalizer.py` with `normalize(name) -> str` (lowercase, collapse whitespace, strip common suffixes).
- [ ] Test: `tests/db/test_models.py` — create one of each row, assert FKs/unique constraints work on SQLite.

### Task 3: Alembic + initial migration
- [ ] `alembic init migrations`, configure `env.py` to read `DATABASE_URL` from env and `target_metadata = Base.metadata`.
- [ ] `alembic revision --autogenerate -m "initial"` → produces `migrations/versions/0001_initial.py`. Verify it creates all 5 tables.
- [ ] Add `alembic upgrade head` to be run on app startup (optional in v1 — manual invocation OK).
- [ ] Smoke: `DATABASE_URL=sqlite:///dev.db alembic upgrade head` creates the file with all tables.

---

## Phase B — API (public reads)

### Task 4: FastAPI app skeleton + settings + health
- [ ] `api/settings.py` with Pydantic `BaseSettings`: `database_url`, `jwt_secret`, `admin_email`, `admin_password_hash`, `resend_api_key`, `web_base_url`, `allowed_origins`.
- [ ] `api/main.py`: instantiate `FastAPI()`, add CORS middleware reading `allowed_origins`, add `GET /healthz → {"ok": true}`. Mount routers (created in later tasks).
- [ ] Test: `tests/api/test_health.py` using `httpx.AsyncClient` against the app: `assert response.status_code == 200`.

### Task 5: Pydantic schemas
- [ ] `api/schemas.py`: `ProjectOut`, `ProjectDetailOut` (includes `raw_payload`), `PromoterOut`, `PaginationMeta`, `Page[T]`, `SubscriptionFilter` (districts, cities, promoters, types, statuses), `SubscriptionCreate`, `LoginIn`, `TokenOut`, `AdminStatsOut`, etc.

### Task 6: GET /districts (static list)
- [ ] In `api/routers/public.py`, hard-code Gujarat's 33 districts as a Python constant (Ahmedabad, Amreli, Anand, Aravalli, Banaskantha, Bharuch, Bhavnagar, Botad, Chhota Udaipur, Dahod, Dang, Devbhoomi Dwarka, Gandhinagar, Gir Somnath, Jamnagar, Junagadh, Kheda, Kutch, Mahisagar, Mehsana, Morbi, Narmada, Navsari, Panchmahal, Patan, Porbandar, Rajkot, Sabarkantha, Surat, Surendranagar, Tapi, Vadodara, Valsad).
- [ ] Endpoint returns `{"districts": [...]}`.
- [ ] Test: `tests/api/test_public.py::test_districts` asserts 33-element array.

### Task 7: GET /projects with filters + pagination
- [ ] In `api/routers/public.py`: query params `district`, `city`, `promoter`, `type`, `status`, `from`, `to`, `q`, `page=1`, `page_size=20` (max 100).
- [ ] Build SQLAlchemy query joining `Project` + `Promoter`. Apply filters conditionally. Order by `registration_date DESC, id DESC`.
- [ ] Return `Page[ProjectOut]` with `items`, `page`, `page_size`, `total`.
- [ ] Test: insert 5 fixture projects across 2 districts, assert filter narrows correctly + pagination math is right.

### Task 8: GET /projects/{rera_reg_no}
- [ ] Look up by `rera_reg_no`. 404 if not found. Return `ProjectDetailOut` (includes `raw_payload`).
- [ ] Test: 200 on existing, 404 on missing.

### Task 9: GET /promoters?q=
- [ ] Case-insensitive substring on normalized name. Limit 20. Return `[{id, name, source_name_raw, project_count}]` (project_count via subquery).
- [ ] Test: 3 promoters, query `q=abc` returns the right ones.

---

## Phase C — API (subscriptions + auth)

### Task 10: Email client (Resend wrapper)
- [ ] `api/email_client.py`: class `EmailClient` with `send(to, subject, html, text)`. Reads `RESEND_API_KEY`. If env unset, **falls back to logging the email to stdout** (for local dev / tests). This is the only "magic" — test it via dependency injection.
- [ ] Test: with fake key, asserts `httpx.AsyncClient` POSTs to `https://api.resend.com/emails` with right payload. Use `respx` for HTTP mocking.

### Task 11: POST /subscriptions + GET /subscriptions/confirm + GET /subscriptions/unsubscribe
- [ ] `api/routers/subscriptions.py`:
  - POST: validate email, generate `confirm_token` + `unsubscribe_token` (secrets.token_urlsafe(32)), insert row, queue confirmation email via `EmailClient`. Return 202.
  - GET confirm: find by token, set `confirmed_at`. Redirect to `{WEB_BASE_URL}/subscribe/confirmed`.
  - GET unsubscribe: find by token, set `unsubscribed_at`. Redirect to `{WEB_BASE_URL}/unsubscribe`.
- [ ] Test: create → confirm → row is confirmed; create → unsubscribe → row marked unsubscribed; bad token → 404.

### Task 12: Admin auth (POST /auth/login → JWT)
- [ ] `api/auth.py`: bcrypt verify against `ADMIN_PASSWORD_HASH`; issue JWT (HS256) with `sub=admin`, `exp=12h`. JWT dep `require_admin` for protected routes.
- [ ] Test: wrong password → 401; right password → token; token decoded gives `sub=admin`; expired token → 401.

### Task 13: Admin endpoints (subscriptions list, scrape-runs list, stats)
- [ ] `api/routers/admin.py`:
  - `GET /admin/subscriptions?status=&q=&page=` — paginated.
  - `GET /admin/scrape-runs?page=` — paginated, ordered by started_at DESC.
  - `GET /admin/stats` — `{total_projects, total_promoters, active_subscriptions, last_successful_scrape, projects_last_30d}`.
- [ ] All gated by `Depends(require_admin)`.
- [ ] Test: unauthenticated → 401; with token → correct payload.

---

## Phase D — Alerts

### Task 14: Alert matching logic (pure function, no I/O)
- [ ] `api/alerts.py`: `match_projects_for_subscription(projects: list[Project], sub: Subscription) -> list[Project]` — applies `filter_json` to candidates. Empty/missing filter dimensions = "any value matches."
- [ ] Test: many filter cases — empty filter matches all, single-district narrows, multi-value union, status excludes.

### Task 15: POST /admin/alerts/dispatch
- [ ] Implements spec §8.2:
  - For each confirmed non-unsubscribed subscription:
    - `cutoff = sub.last_alert_at or epoch`
    - `candidates = projects where source_first_seen_at > cutoff`
    - `matched = match_projects_for_subscription(candidates, sub)`
    - Exclude rows already in `alerts_sent` for this sub (defensive).
    - Split into batches of 50.
    - For each batch: render digest email (helpers in `api/email_render.py`), send via EmailClient, insert AlertsSent rows in same DB tx.
    - Update `sub.last_alert_at = now()` after all batches send OK.
- [ ] Test (the highest-risk code): fixture with 3 subscriptions + 10 new projects, run dispatch, assert correct subset goes to each, no duplicates, alerts_sent has expected rows.

---

## Phase E — Scraper

### Task 16: Scraper CLI skeleton
- [ ] `scraper/__main__.py` + `scraper/cli.py` using `argparse`: subcommand `run --mode={weekly,backfill,district} [--csv=...] [--district=...] [--since=...]`.
- [ ] `scraper/config.py`: reads `DATABASE_URL`, `API_BASE`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SCRAPER_USER_AGENT`.
- [ ] Skeleton just prints args and exits 0. Tested via `pytest tests/scraper/test_cli.py`.

### Task 17: Kaggle backfill
- [ ] `scraper/backfill.py`: `def run_backfill(csv_path: Path) -> ScrapeRunResult`. Uses pandas to read, normalizes columns (column-name mapping at the top of file; if Kaggle dataset columns drift, only this mapping changes). Upserts via SQLAlchemy `insert(...).on_conflict_do_update()` (Postgres) or `INSERT OR REPLACE` (SQLite). Creates ScrapeRun row with `source='kaggle_seed'`.
- [ ] Test: feeds a 5-row CSV fixture, asserts 5 projects + 5 promoters inserted, scrape_run is `success`.

### Task 18: Detail-page parser (pure, against HTML fixture)
- [ ] `scraper/parser.py`: `def parse_project_detail(html: str) -> dict`. Returns dict matching `Project` columns + `raw_payload`. Uses BeautifulSoup with lxml.
- [ ] Capture a real GUJRERA detail page HTML and save as `tests/scraper/fixtures/sample_project.html` (this is a manual step the operator does once via browser "save page as"; for now use a synthetic minimal HTML fixture with key fields, real one swaps in later).
- [ ] Test: parses fixture, asserts all expected fields populated.

### Task 19: Playwright driver
- [ ] `scraper/playwright_driver.py`: async context manager `browser_session()` that spawns chromium, applies stealth, returns a `Page`. `async def search_district(page, district, date_from) -> list[encVar_link]`. `async def fetch_detail(page, link) -> str` (returns HTML). Random delay helper.
- [ ] Cannot fully test without network. Provide a `--dry-run` flag that mocks the page object. Lightweight test: imports cleanly, `search_district` accepts a mock page.

### Task 20: Weekly orchestrator + alert dispatch trigger
- [ ] `scraper/weekly.py`: orchestrates session → for each district → search → for each link → check `rera_reg_no` in DB → if new or stale `content_hash` → fetch detail → parse → upsert. Tracks counts.
- [ ] After successful run: POST `{API_BASE}/admin/alerts/dispatch` with JWT obtained from `{API_BASE}/auth/login`.
- [ ] Test: full workflow with mocked Playwright + httpx, assert API dispatch called once on success path.

---

## Phase F — Web

### Task 21: Next.js scaffold + Tailwind
- [ ] `cd web && npx create-next-app@latest . --typescript --tailwind --app --use-npm --eslint --src-dir=false --import-alias='@/*' --no-turbopack`.
- [ ] Add deps: `@tanstack/react-query`, `zod`, `js-cookie` (or use Next.js `cookies()` only — no extra dep). Keep dep list short.
- [ ] `tailwind.config.ts` with neutral base palette.
- [ ] Test: `npm run build` succeeds.

### Task 22: Typed API client
- [ ] `web/lib/api.ts`: typed `getProjects`, `getProject`, `getPromoters`, `getDistricts`, `createSubscription`, `getAdminStats`, etc. Use `fetch` server-side, no SDK. Reads `process.env.NEXT_PUBLIC_API_BASE`.
- [ ] Types mirror API Pydantic schemas (manually mirrored — OpenAPI codegen deferred to phase 2).

### Task 23: Landing page
- [ ] `web/app/page.tsx`: server component. Calls `getAdminStats` (the public-ish parts) and recent 10 projects. Hero + featured list + CTA "Subscribe".

### Task 24: /projects list with filters
- [ ] `web/app/projects/page.tsx`: server component reads query params, calls `getProjects`. Sidebar filter UI is a client component that pushes query-string changes (uses Next.js `useSearchParams` + `useRouter`).

### Task 25: /projects/[regNo] detail
- [ ] `web/app/projects/[regNo]/page.tsx`: server component. Calls `getProject(regNo)`, renders all fields + link to source URL + "Subscribe to similar" CTA pre-filled with this project's district + type.

### Task 26: Subscribe flow
- [ ] `web/app/subscribe/page.tsx`: form with email + filter builder (district multi-select, type chips, status chips). Posts to API via `createSubscription`. Shows success message.
- [ ] `web/app/subscribe/confirmed/page.tsx` + `web/app/unsubscribe/page.tsx`: simple confirmation pages.

### Task 27: Admin login + middleware + pages
- [ ] `web/app/admin/login/page.tsx`: form posts to `/api/auth/login` (Next.js route handler) which proxies to FastAPI and sets `admin_jwt` HTTP-only cookie.
- [ ] `web/middleware.ts`: on `/admin/*` (excluding `/admin/login`), check `admin_jwt` cookie; if absent → redirect to `/admin/login`.
- [ ] `web/app/admin/dashboard/page.tsx`, `/admin/subscriptions/page.tsx`, `/admin/scrape-runs/page.tsx`: server components calling admin endpoints with the cookie forwarded as Bearer.

---

## Phase G — Polish

### Task 28: CI
- [ ] `.github/workflows/ci.yml`: matrix job → Python (pytest) and Node (npm run build + npm test). Runs on push + PR.

### Task 29: Deploy configs
- [ ] `render.yaml` for the API service (build = `pip install -e . && alembic upgrade head`, start = `uvicorn api.main:app --host 0.0.0.0 --port $PORT`).
- [ ] `web/vercel.json` (probably not needed — Next.js auto-detected).

### Task 30: README + run instructions
- [ ] Top-level README with: prerequisites, local dev (`uv sync`, `alembic upgrade head`, `uvicorn api.main:app --reload`, `cd web && npm run dev`), scraper usage, deploy notes.

---

## Risks specific to execution

- **Windows + Playwright:** browsers download must succeed (`playwright install chromium`). Mitigation: gate scraper integration tests behind an env flag.
- **SQLite vs Postgres divergence:** keep SQL in SQLAlchemy ORM (no raw SQL). The one Postgres-specific thing (`INSERT ... ON CONFLICT`) is wrapped with a dialect check.
- **Resend in tests:** mocked via `respx`; real Resend only fires when `RESEND_API_KEY` is set.
- **Kaggle dataset access:** the operator must download the CSV manually first (the dataset is on Kaggle, no programmatic API without an account). Document this in README.
