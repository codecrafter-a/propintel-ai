# GUJRERA Project Tracker — v1 Design

**Date:** 2026-05-27
**Status:** Draft for user review
**Owner:** anupama.mishra@mindtrace.com

## 1. Goal

A web app that tracks Gujarat RERA (GUJRERA) project approvals and emails subscribers when new projects matching their filter are approved. Targets investors, brokers, and buyers via a single generic filter + alert system.

This is **Phase 1** of a broader real-estate intelligence platform. Maps, AI scoring, builder reputation, multi-state expansion, document mirroring, paid plans, WhatsApp/push notifications, mobile, and real-time scraping are **explicitly deferred** to later specs.

## 2. Non-goals (v1)

- Maps or any visual / geospatial UI
- Geocoding (no lat/lng)
- Price data, ROI prediction, AI growth scores
- Builder reputation analytics
- Document download / PDF mirroring
- WhatsApp, SMS, or push notifications
- Mobile app
- Multi-state coverage (Gujarat only)
- Paid plans, billing, persona-tagged dashboards
- Real-time scraping or hosted cron
- Residential-proxy infrastructure
- End-user signup / login

## 3. Users

Anyone visiting the site can:
- Browse and filter the project list without an account
- Subscribe an email to receive alerts when new projects matching a filter are approved
- Confirm subscription via a one-click magic link in the confirmation email
- Unsubscribe via a link in any alert email

The operator (admin) can log in to a static admin area with credentials from environment variables. Admin can view subscriptions, scrape runs, and overall stats. There are no other admin features in v1.

## 4. Data source

### 4.1 Source reality (from recon)

- Real portal is `https://gujrerar1.gujarat.gov.in/` (RERA 1.0). `gujrera.gujarat.gov.in` is a marketing shell.
- Public project search is at `/searchProject`. Detail pages are at `/viewProjectDetailPage?encVar=<opaque>`. The `encVar` token is server-encrypted, so we cannot enumerate by ID — we must drive the search form to discover links.
- No public JSON API, no CSV/Excel bulk download.
- The host **refuses connections from datacenter/cloud IPs** (active WAF / IP-reputation block). Scraping requires either a residential IP or a residential proxy.
- No CAPTCHA observed on the public search itself.
- Filters available on the search form: project name, RERA reg number, promoter/builder, city, district.
- Detail pages expose: RERA reg no, promoter contact, project type, district, taluka, units, project start/end dates, status, approved-plan PDFs.

### 4.2 v1 ingestion strategy

- **Backfill:** import the Kaggle dataset `ethon0426/gujarat-real-estate-project-registered-2017-2022` ("Gujarat Real Estate Project Registered 2010–2023", last updated Oct 2024). One-shot CSV import, idempotent on `rera_reg_no`. This seeds the database with historical projects so the dashboard is useful from day one.
- **Ongoing updates:** a Python CLI scraper using Playwright + BeautifulSoup that the operator runs **manually from their laptop, roughly weekly**. The scraper drives the public search form per (district × registration-date-window) combination, harvests `encVar` links, fetches detail pages, parses them, and upserts into the database. Because it runs from a residential IP (the operator's home internet), it does not hit the cloud-IP block.
- **Alert latency promised to users:** "you will see new approvals within a week of them appearing on GUJRERA." Not real-time. This is acceptable because RERA approvals are not second-by-second time-sensitive and Phase 2 will introduce a hosted scraper with residential proxies for daily cadence.

## 5. Tech stack

- **Web (frontend + admin UI):** Next.js 14 (App Router), TypeScript. Deployed to Vercel free tier.
- **API:** FastAPI + SQLAlchemy + Alembic + Pydantic, Python 3.11+. Deployed to Render free tier.
- **Scraper:** Python + Playwright + BeautifulSoup, packaged as a CLI in the same repo as the API. Run from the operator's laptop.
- **Database:** PostgreSQL on Neon free tier.
- **Email:** Resend (3,000 emails/month free).
- **Auth:** FastAPI issues a JWT on `POST /auth/login` for a single admin user defined by `ADMIN_EMAIL` and `ADMIN_PASSWORD_HASH` env vars. Next.js middleware checks the JWT cookie on `/admin/*` routes.
- **Repo layout:** monorepo with `/web`, `/api`, `/scraper`, `/shared` (schema docs and ER diagrams), and `/docs`. Separate deploy configs per service.

## 6. Architecture

Three processes share one Postgres database.

```
+-----------------------------+      +------------------------------+
|  /web  (Next.js, Vercel)    |      |  /scraper  (Python CLI,       |
|  - Public dashboard         |      |   runs on operator laptop)    |
|  - Subscribe form           |      |  - Playwright + bs4           |
|  - Admin pages (/admin/*)   |      |  - One-shot CLI               |
|  - No DB access; calls API  |      |  - Writes directly to DB      |
+--------------+--------------+      +---------------+---------------+
               | HTTPS (JSON)                        | psycopg
               v                                     v
+----------------------------------------------------------------------+
|  /api  (FastAPI, Render free tier)                                    |
|  - REST endpoints: /projects, /subscriptions, /admin/*                |
|  - JWT auth for admin                                                 |
|  - Alert dispatcher (POST /admin/alerts/dispatch called by scraper)   |
+----------------------------+------------------------------------------+
                             | SQLAlchemy
                             v
                  +---------------------+           +------------------+
                  | Postgres (Neon)     |           | Resend API       |
                  |  - projects         |           | (transactional   |
                  |  - promoters        |           |  email)          |
                  |  - subscriptions    | <---------+                  |
                  |  - alerts_sent      |           +------------------+
                  |  - scrape_runs      |
                  +---------------------+
```

### 6.1 Key architectural choices

1. **Scraper writes to DB directly**, not through the API. Bulk inserts over HTTP would be wasteful; the scraper is trusted code we own.
2. **Scraper signals new data via `POST /admin/alerts/dispatch`** at the end of a successful run. This keeps all email-sending logic in the API where it can be tested and observed.
3. **Next.js never touches Postgres.** All data flow is `web → api → db`. The same API can later serve a mobile app or third-party integration.
4. **Monorepo, separate deploys.** One git history, shared OpenAPI-generated TypeScript types for the web client.

## 7. Data model

```sql
promoters
  id                bigserial primary key
  name              text not null              -- normalized (lowercased, whitespace-collapsed)
  source_name_raw   text not null              -- as it appears on RERA
  created_at        timestamptz not null default now()
  unique (name)

projects
  id                       bigserial primary key
  rera_reg_no              text not null unique
  name                     text not null
  promoter_id              bigint not null references promoters(id)
  district                 text not null
  city_taluka              text
  project_type             text not null check (project_type in ('residential','commercial','plotted','mixed','unknown'))
  status                   text not null check (status in ('registered','suspended','completed','expired','unknown'))
  unit_count               integer
  registration_date        date
  project_start_date       date
  project_end_date         date
  source_detail_url        text                -- the encVar URL
  source_first_seen_at     timestamptz not null default now()
  source_last_seen_at      timestamptz not null default now()
  content_hash             text not null        -- SHA256 of parsed payload
  raw_payload              jsonb not null
  created_at               timestamptz not null default now()
  updated_at               timestamptz not null default now()

  index on (district)
  index on (registration_date desc)
  index on (promoter_id)

subscriptions
  id                  bigserial primary key
  email               text not null
  confirmed_at        timestamptz                -- null = unconfirmed; rows >7 days unconfirmed are pruned
  filter_json         jsonb not null              -- {districts:[], cities:[], promoters:[], types:[], statuses:[]}
  unsubscribe_token   text not null unique
  confirm_token       text not null unique
  created_at          timestamptz not null default now()
  last_alert_at       timestamptz
  unsubscribed_at     timestamptz                 -- null = active

  index on (email)
  index on (confirmed_at, unsubscribed_at)

alerts_sent
  id                bigserial primary key
  subscription_id   bigint not null references subscriptions(id) on delete cascade
  project_id        bigint not null references projects(id)
  sent_at           timestamptz not null default now()
  unique (subscription_id, project_id)

scrape_runs
  id                   bigserial primary key
  started_at           timestamptz not null default now()
  finished_at          timestamptz
  source               text not null check (source in ('kaggle_seed','playwright_weekly','playwright_manual'))
  projects_inserted    integer not null default 0
  projects_updated     integer not null default 0
  status               text not null check (status in ('running','success','failed'))
  error_log            text
```

### 7.1 Notes

- `content_hash` enables cheap change detection: scraper recomputes hash from parsed payload; if unchanged, only `source_last_seen_at` is bumped.
- `raw_payload` (jsonb) preserves the parsed scrape so new fields can be derived later without re-scraping.
- `alerts_sent` is the single source of truth that prevents duplicate emails — the unique constraint enforces it at the DB level.
- Promoter name normalization happens in app code (lowercased, collapsed whitespace, common-suffix stripping like "Pvt Ltd"). Raw name is preserved in `source_name_raw`.
- Unconfirmed subscriptions older than 7 days are pruned by a periodic admin task to keep the table clean (out of scope for v1 — manual deletion via SQL is fine).

## 8. Component design

### 8.1 Scraper (`/scraper`)

**CLI:**
```
python -m scraper run --mode=weekly
python -m scraper run --mode=backfill --csv=path/to/kaggle.csv
python -m scraper run --mode=district --district="Ahmedabad" --since=2026-04-01
```

**Workflow (weekly mode):**
1. Insert `scrape_runs` row with `status='running'`, `source='playwright_weekly'`.
2. For each of Gujarat's 33 districts, drive `/searchProject` form: set district filter, set registration-date-from = (today − 30 days), submit, paginate results.
3. For each result row: extract `encVar` link, fetch detail page, parse fields into a normalized dict, compute `content_hash`.
4. Upsert into `projects` by `rera_reg_no`. If the row exists and `content_hash` matches, only `source_last_seen_at` is updated. Otherwise insert/update and bump `projects_inserted` or `projects_updated`.
5. On completion: POST to `{API_BASE}/admin/alerts/dispatch` with a JWT obtained via `/auth/login` using the admin credentials in the scraper's env.
6. Update `scrape_runs` with `status='success'`, counts, `finished_at`.

**Workflow (backfill mode):** read CSV with pandas, normalize column names, bulk-upsert by `rera_reg_no`. No alert dispatch (these are not "new" projects).

**Resilience:**
- Each page fetch is wrapped in retry: 3 attempts with exponential backoff (1s, 4s, 16s).
- Each project upsert commits independently (`session.commit()` per project), so a mid-run failure leaves partial progress that the next run will skip via `content_hash`.
- Playwright runs headless by default; `--headed` flag for debugging.
- Random delays (1–3 seconds) between page fetches to be polite.
- User-Agent set to a real Chrome string; `playwright-stealth` to reduce fingerprinting.

**Configuration (env vars):**
- `DATABASE_URL` — Postgres connection string
- `API_BASE` — e.g. `https://api.gujrera-tracker.example.com`
- `ADMIN_EMAIL`, `ADMIN_PASSWORD` — to obtain a JWT for the dispatch call
- `SCRAPER_USER_AGENT` (optional override)

### 8.2 API (`/api`)

**Public endpoints (no auth):**
- `GET /projects?district=&city=&promoter=&type=&status=&from=&to=&q=&page=1&page_size=20`
  Returns paginated project list, ordered by `registration_date DESC`. `q` is a substring search over project name + promoter name.
- `GET /projects/{rera_reg_no}` — full detail including `raw_payload`.
- `GET /promoters?q=` — substring search, returns up to 20 matches (for autocomplete).
- `GET /districts` — static array of Gujarat's 33 districts.
- `POST /subscriptions` — body `{email, filter}`. Creates row with `confirmed_at=null`, generates `confirm_token` and `unsubscribe_token`, sends confirmation email via Resend. Returns 202.
- `GET /subscriptions/confirm?token=` — sets `confirmed_at=now()`. Renders a small HTML success page (or redirects to `/subscribe/confirmed` on the web).
- `GET /subscriptions/unsubscribe?token=` — sets `unsubscribed_at=now()`. Renders / redirects similarly.

**Admin endpoints (JWT in `Authorization: Bearer ...` header):**
- `POST /auth/login` — body `{email, password}`. Checks against `ADMIN_EMAIL` and `ADMIN_PASSWORD_HASH` (bcrypt). On success returns `{access_token, expires_in}`.
- `GET /admin/subscriptions` — paginated list with status filter (confirmed / unconfirmed / unsubscribed) and email substring search.
- `GET /admin/scrape-runs` — paginated list, most recent first.
- `GET /admin/stats` — counts: total projects, total promoters, active subscriptions, last successful scrape, projects added in last 30 days.
- `POST /admin/alerts/dispatch` — called by the scraper at end of run. Logic:
  1. For each confirmed, non-unsubscribed subscription:
     - `cutoff = subscription.last_alert_at or '1970-01-01'`
     - Candidate projects: `source_first_seen_at > cutoff`.
     - Filter candidates by `subscription.filter_json`.
     - Exclude `(subscription_id, project_id)` already in `alerts_sent` (defensive — the cutoff should already cover this, but the unique constraint is the real guard).
     - If matches remain: split into batches of 50 projects, send one digest email per batch via Resend, insert `alerts_sent` rows in the same transaction. Update `subscription.last_alert_at` to `now()` only after all batches send successfully.

**Error responses:** consistent shape `{error: {code: string, message: string, details?: object}}`. 4xx for user errors, 5xx for bugs.

### 8.3 Web (`/web`)

**Public pages:**
- `/` — landing. Hero copy, count of tracked projects, list of the 10 most recent approvals, prominent "Subscribe to alerts" CTA.
- `/projects` — searchable list. Filters in a left sidebar: district (multi-select), city (multi-select, dependent on district), project type (chips), status (chips), date range, free-text search. Right pane shows paginated cards with reg no, name, promoter, district, registration date, status badge. Clicking a card opens detail.
- `/projects/[regNo]` — detail page. All fields, link out to the original GUJRERA detail page (`source_detail_url`), "Subscribe to similar" button that pre-fills the subscription form with this project's district + type.
- `/subscribe` — form: email + filter builder (same controls as the `/projects` filter sidebar). Submit → calls `POST /subscriptions`. Shows "check your email" confirmation.
- `/subscribe/confirmed` — landing after clicking confirm link.
- `/unsubscribe` — landing after clicking unsub link.

**Admin pages (under `/admin/*`):**
- `/admin/login` — email + password form. Posts to a Next.js route handler `/api/auth/login` which proxies to FastAPI's `POST /auth/login`, receives the JWT, and sets it as an `HttpOnly; Secure; SameSite=Lax` cookie named `admin_jwt`.
- `/admin/dashboard` — stats from `GET /admin/stats`.
- `/admin/subscriptions` — table view with filter/search and CSV export.
- `/admin/scrape-runs` — table view, click a row to see `error_log`.

**Auth flow:** Next.js middleware on `/admin/*` (except `/admin/login`) checks for a valid `admin_jwt` cookie; missing/expired → redirect to `/admin/login`. For data fetches inside admin pages, Next.js server components read the cookie and forward it to FastAPI as `Authorization: Bearer <jwt>`. The browser never sees the token directly.

**Styling:** Tailwind. No design system in v1; use a minimal, professional look. Mobile-responsive but optimized for desktop (the primary use case is investors at a computer).

## 9. Alerts engine

The alert digest email contains:
- Subject: `[GUJRERA Tracker] N new projects matching your filter`
- Body (HTML + plaintext):
  - A short greeting
  - List of matched projects: name, promoter, district, registration date, link to the detail page on our site
  - A "View all matching projects" link to the filtered `/projects` page
  - An unsubscribe link at the bottom

Single digest per subscriber per dispatch run, not one email per project. This bounds the blast radius if matching has a bug.

If a subscription matches more than 50 new projects in one run (rare), the email is split into multiple parts to stay within Resend's per-email size limit.

## 10. Error handling & observability

- **API:** FastAPI exception handlers map known exceptions to `4xx` with the error shape above. Unhandled exceptions return `500` with a request ID; full traceback goes to logs.
- **Scraper:** every Playwright action is retried as described. Any uncaught exception writes to `scrape_runs.error_log` (truncated to 8 KB) and the process exits non-zero so the operator notices.
- **Email:** Resend client calls are wrapped in try/except. Failures are logged but do **not** roll back the `alerts_sent` insert — we accept the small risk that a user misses one alert rather than risk a replay storm.
- **Logs:** structured JSON to stdout (FastAPI), structured JSON to stdout + a local file (scraper).
- **Monitoring (v1):** none beyond logs and Render's built-in metrics. UptimeRobot or similar can be added in Phase 2.

## 11. Testing strategy

- **API:** pytest + httpx async client. Ephemeral Postgres via testcontainers (or a dedicated test schema if testcontainers is slow on Windows). Unit tests for the filter-matching logic in the alert dispatcher (highest-risk code). Integration tests for each endpoint covering happy path + one error case.
- **Scraper:** parser tested against saved HTML fixtures captured from a real GUJRERA detail page (no live network in tests). Integration test that runs `--mode=backfill` against a 10-row CSV fixture against a real Postgres test DB.
- **Web:** Playwright smoke tests for `/`, `/projects`, `/subscribe` (asserts the page renders and key elements exist). No deep component tests in v1.
- **CI:** GitHub Actions runs `pytest` and `npm test` on every push. No deploy automation in v1 — Vercel and Render auto-deploy on push to `main`.

## 12. Deployment

- **`/web`:** Vercel project pointing at the `/web` subdirectory of the monorepo. Env vars: `NEXT_PUBLIC_API_BASE`. Auto-deploys on push to `main`.
- **`/api`:** Render Web Service pointing at `/api`. Env vars: `DATABASE_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH`, `JWT_SECRET`, `RESEND_API_KEY`, `WEB_BASE_URL`, `ALLOWED_ORIGINS`. Auto-deploys on push to `main`. Migrations via Alembic run on startup.
- **`/scraper`:** not deployed. Run locally with `uv run python -m scraper run --mode=weekly`. The operator's laptop must have Playwright browsers installed (`playwright install chromium`).
- **DB:** Neon project, one Postgres database, free tier. Connection string shared by API and scraper.

## 13. Phased rollout (post-v1, out of scope for this spec)

Each item below would get its own design spec when prioritized:

- **Phase 2a — Hosted weekly scraper.** Move the scraper to a VPS with a residential proxy (BrightData / Smartproxy). Cron weekly. Eliminates the "operator must remember to run it" toil.
- **Phase 2b — Geocoding + map view.** Best-effort geocode addresses (Nominatim) and add a Leaflet/MapLibre view of projects.
- **Phase 2c — Document mirroring.** Download approved-plan PDFs to Supabase Storage; full-text search on extracted text.
- **Phase 2d — Builder reputation analytics.** Aggregate delays, suspensions, complaints (where exposed by RERA).
- **Phase 3 — AI scoring.** Growth score, risk score, ROI prediction. Requires price-trend data we don't yet have.
- **Phase 3 — WhatsApp + push notifications.** Twilio or AiSensy.
- **Phase 4 — Multi-state.** MahaRERA, KRERA, TGRERA, etc. Each state has a different portal; each is its own scraper plugin.
- **Phase 4 — Paid plans.** Stripe + persona-tagged dashboards (Investor / Broker / Builder views).

## 14. Open risks

- **GUJRERA WAF behavior may change.** If the portal starts blocking residential IPs or adds CAPTCHA, the scraper breaks. Mitigation: keep the parser pure-function and easy to swap; budget for residential proxies in Phase 2.
- **Kaggle dataset quality unknown.** Column count, field names, and completeness are not directly verifiable yet. Mitigation: the backfill step is non-blocking — if the dataset is poor, we still have the weekly scrape adding fresh data, and the dashboard's value grows over time.
- **Filter-matching edge cases.** Promoter names from RERA are inconsistent ("ABC Builders Pvt Ltd" vs "ABC Builders Private Limited" vs "Abc Builders"). Normalization heuristics will miss some matches. Mitigation: expose raw + normalized names in admin so the operator can spot issues.
- **Email deliverability.** Resend is good, but new domains can land in spam. Mitigation: warm up sending, set up SPF/DKIM/DMARC on the sending domain, monitor bounce/complaint rate.
- **Render free-tier cold starts.** The API may sleep after inactivity, adding latency to the first request. Acceptable for v1; upgrade to Render Starter ($7/month) if it bothers users.

## 15. Success criteria for v1

- Operator can run `python -m scraper run --mode=backfill --csv=...` and see >5,000 projects in the database afterwards.
- Operator can run `python -m scraper run --mode=weekly` end-to-end without manual intervention, completing in under 60 minutes on a typical home connection. (Estimate assumes ~200–500 new/changed projects across all 33 districts per week × ~3s polite delay per detail-page fetch ≈ 10–25 min, plus search-form pagination overhead.)
- Visitor can land on `/`, filter projects to a specific district + project type, and see results in under 2 seconds.
- Visitor can subscribe an email, click the confirmation link, and receive a digest email after the next scrape run.
- Operator can log in to `/admin`, see subscription count and last scrape status.
- No raw stack traces or 500 errors visible to end users.
