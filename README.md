# Trade Monitoring Dashboard

A simulated trade monitoring and anomaly-detection dashboard, built to look and
work like the internal tooling a trading desk's operations/compliance team
would actually use: a live-updating view of order/fill flow across multiple
desks, with rule-based detection of the things that make ops teams nervous —
latency spikes, duplicate fills, reject bursts, and orders stuck mid-lifecycle.
There's no real broker or market data behind it; a background process
generates a continuous, realistic-looking synthetic order stream so the
dashboard always has something live to show.

> **Screenshot:** _add one here after your first local run — `/dashboard/`
> with the feed generator running for a minute or two looks best._

## Features

- **Live orders table** — auto-refreshes every 5s via HTMX, filterable by
  desk/status/symbol, sortable by column, no full-page reloads.
- **Anomaly flags panel** — the four rules below, color-coded by severity,
  with a one-click Acknowledge action (HTMX POST, removed from the list
  in place).
- **Desk summary strip** — per-desk order/reject counts with a visual reject-rate bar.
- **Ack latency chart** — Chart.js line chart of the last 50 orders' ack
  latency, with a threshold line at the MEDIUM-severity cutoff.
- **REST API** (DRF) — the same data the dashboard renders, available as JSON
  for any other consumer.
- **Django admin** — full CRUD over all four models, useful for poking at
  seeded/generated data directly.

## Anomaly rules

Deliberately simple, explainable, threshold/window-based rules — no ML.
An ops reviewer wants a clear answer to "why was this flagged," and these
four cover the classic operational failure modes:

| Rule | Trigger | Severity |
|---|---|---|
| `HIGH_LATENCY` | order ack latency > 2000ms | MEDIUM (> 5000ms → HIGH) |
| `DUPLICATE_FILL` | two fills on the same order, same qty & price, within 500ms | HIGH |
| `REJECT_SPIKE` | > 3 rejected orders from the same desk within a rolling 5-minute window | HIGH |
| `STALE_ORDER` | order stuck in `NEW`/`ACKNOWLEDGED` for > 10 minutes | LOW |

Rules live as pure functions in [`monitoring/rules.py`](monitoring/rules.py)
(unit-tested against hand-built querysets in `test_rules.py`, independent of
the random feed) and are persisted, idempotently, by the `detect_anomalies`
management command.

## Architecture

```
                    ┌─────────────────────┐
                    │   generate_feed     │  synthetic orders/fills/rejects,
                    │ (mgmt command,      │  guarantees each anomaly type's
                    │  long-running loop) │  precondition shows up quickly
                    └──────────┬──────────┘
                               │ writes
                               ▼
   ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐
   │ detect_       │───▶│  PostgreSQL  │◀───│  Django + DRF (web)  │
   │ anomalies     │    │  / SQLite    │    │                      │
   │ (mgmt command,│    │              │    │  monitoring app:     │
   │  --loop)      │    │  Trader      │    │   models / admin /   │
   └───────────────┘    │  Order       │    │   rules / views /    │
                         │  Fill        │    │   api_views / serializers
                         │  AnomalyFlag │    └──────────┬───────────┘
                         └──────────────┘               │ renders
                                                         ▼
                                          ┌──────────────────────────┐
                                          │  Dashboard (templates)   │
                                          │  HTMX polling (5s/10s)   │
                                          │  Chart.js (latency)      │
                                          └──────────────────────────┘
```

`generate_feed` and `detect_anomalies` are independent, long-running
processes (no Celery/task queue — deliberately out of scope; see below).
The Django web process only reads what they've written.

## Tech stack

- **Backend**: Django 6 + Django REST Framework
- **Frontend**: Django templates + HTMX (live partial updates) + Chart.js
  (the one place plain JS talks to the API directly)
- **DB**: PostgreSQL in Docker/deployed mode, SQLite for local dev
- **Deployment target**: AWS EC2, Docker Compose, gunicorn + nginx
- **Python**: 3.12

## Getting started (local dev, SQLite)

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # defaults are fine for local dev (SQLite, DEBUG=True)

python manage.py migrate
python manage.py seed_data
python manage.py createsuperuser   # optional — needed to acknowledge flags from the UI

python manage.py runserver
```

In two more terminals (both long-running):

```bash
python manage.py generate_feed --inject-reject-burst
python manage.py detect_anomalies --loop --interval 10
```

Then open **http://127.0.0.1:8000/dashboard/**.

### Command reference

| Command | Purpose |
|---|---|
| `seed_data` | One-time: creates 10 traders across 5 desks |
| `generate_feed [--duration N] [--inject-reject-burst]` | Continuously creates orders/fills/rejects. `--duration` bounds the run (seconds); omit to run forever. `--inject-reject-burst` fires the first REJECT_SPIKE-triggering burst sooner |
| `detect_anomalies [--loop] [--interval N]` | Scans orders/fills against the four rules and persists `AnomalyFlag` rows (idempotent). `--loop` re-runs every `--interval` seconds (default 10) |

## Running with Docker Compose

```bash
cp .env.example .env   # then edit DB_ENGINE=postgres etc. if needed — compose sets this for you
docker compose up --build
```

Brings up four services: `db` (Postgres), `web` (migrate + seed + gunicorn),
`feed-generator`, and `detector` — the full stack from a clean clone.
Visit **http://localhost:8000/dashboard/**.

For an actual internet-facing deployment (EC2 + nginx in front), see
[`infra/deploy_notes.md`](infra/deploy_notes.md) — documented manual steps,
not automated from this repo.

## REST API

| Endpoint | Description |
|---|---|
| `GET /api/orders/` | List orders — filter with `?desk=` `?status=` `?symbol=`, paginated |
| `GET /api/orders/<order_id>/` | Order detail, including its fills |
| `GET /api/flags/` | List active (unacknowledged) flags — filter with `?severity=` |
| `POST /api/flags/<id>/acknowledge/` | Mark a flag acknowledged (requires a logged-in session) |
| `GET /api/latency-series/` | Last N orders' ack latency + timestamps, for the chart |
| `GET /api/desk-summary/` | Per-desk order/reject counts |

## Tests

```bash
python manage.py test monitoring
```

Model sanity tests (`test_models.py`) and rule-logic tests (`test_rules.py`)
against small hand-built querysets — not the random feed generator, so
they're deterministic.

## Scope / non-goals

This is a portfolio project demonstrating internal-tooling patterns, not a
production trading system. Deliberately not built: real broker/exchange
connectivity, real market data, auth beyond Django's built-in session auth,
a task queue (feed generation and anomaly detection are plain long-running
management commands, which is a perfectly fine architecture at this scale
and avoids Celery/Redis scope creep), or mobile-responsive polish.
