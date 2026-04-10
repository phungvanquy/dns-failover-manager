# DNS Failover Manager

A lightweight web application to manage automatic domain failover using the Cloudflare DNS API.

---

## 🎯 Goal

Self-hosted tool that monitors server health and automatically updates Cloudflare DNS A records to redirect traffic from a failed primary IP to the next healthy backup IP — with a web dashboard for visibility and manual control.

---

## 📁 Project Structure

```
dns-failover-manager/
├── docker-compose.yml          # 3 services: backend, frontend, db
├── .env                        # Runtime secrets (NOT committed)
├── .env.example                # Template for .env
├── .gitignore
├── CLAUDE.md                   # This file — project memory
│
├── backend/
│   ├── Dockerfile              # Python 3.12-slim + iputils-ping + curl
│   ├── requirements.txt        # FastAPI, SQLAlchemy, httpx, apscheduler, etc.
│   └── app/
│       ├── __init__.py
│       ├── main.py             # FastAPI app, lifespan (DB init + health check worker)
│       ├── config.py           # Pydantic Settings from env vars
│       ├── database.py         # Async SQLAlchemy engine + session factory
│       ├── models.py           # ORM: Domain, BackupIP, HealthStatus, FailoverEvent, HealthCheckLog
│       ├── schemas.py          # Pydantic request/response schemas
│       ├── cloudflare.py       # Cloudflare API client (list records, update A record, retry logic)
│       ├── health_checker.py   # Background worker: ping/tcp/http checks, failover/revert logic
│       └── routers/
│           ├── __init__.py
│           └── domains.py      # CRUD + force switch + health + events endpoints
│
└── frontend/
    ├── Dockerfile              # Node 20-alpine
    ├── package.json            # React 18, Vite, Tailwind CSS, TypeScript
    ├── tsconfig.json
    ├── vite.config.ts          # Proxy /api → backend:8000
    ├── tailwind.config.js
    ├── postcss.config.js
    ├── index.html
    └── src/
        ├── main.tsx            # React root (wrapped with ToastProvider)
        ├── App.tsx             # Main layout: domain card list + add/edit form + activity log
        ├── api.ts              # Fetch wrapper (get/post/put/del) with error detail extraction
        ├── types.ts            # TypeScript interfaces (Domain, BackupIP, HealthStatus, FailoverEvent)
        └── components/
            ├── DomainForm.tsx   # Add/edit form — fields adapt per check_type, client-side validation
            ├── DomainRow.tsx    # Domain card with status, IPs, force switch dropdown, monitoring toggle
            ├── Toast.tsx        # Toast notification system (error/success popups)
            └── ActivityLog.tsx  # Collapsible event log panel (failover/revert/manual switch history)
```

---

## 🐳 Docker Services

| Service | Image | Port | Notes |
|---|---|---|---|
| `db` | postgres:16-alpine | 5432 | Health check via `pg_isready`, persistent volume `postgres_data` |
| `backend` | ./backend (Python 3.12) | 8000 | Uvicorn `--reload`, volume-mounted `./backend:/app` |
| `frontend` | ./frontend (Node 20) | 3000 | Vite dev server with HMR, proxies `/api` to `backend:8000` |

**Commands:**
- `docker compose up -d` — start all services
- `docker compose down -v` — stop + wipe DB volume (**required when schema changes**)
- `docker compose logs backend --tail 30` — check backend logs
- `docker compose restart backend` — restart after .env changes

---

## ⚙️ What's Implemented (Current State)

### ✅ Backend API
- **CRUD** for domains: `GET/POST/PUT/DELETE /api/domains`, `GET /api/domains/:id`
- **Force switch**: `POST /api/domains/:id/switch` — updates Cloudflare DNS then DB
- **Monitoring toggle**: `POST /api/domains/:id/monitoring` — pause/resume health checks per domain
- **Health status**: `GET /api/domains/:id/health`
- **Event log**: `GET /api/domains/:id/events` (per domain), `GET /api/events?limit=50` (global)
- **App health**: `GET /api/health`
- Auto-discovers `record_id` from Cloudflare when not provided (on create + on switch)

### ✅ Cloudflare Integration (`cloudflare.py`)
- Auth via Bearer token (`CLOUDFLARE_API_TOKEN` env var)
- `list_dns_records(zone_id, name)` — find A records
- `get_record_id(zone_id, domain_name)` — auto-discover record ID
- `update_dns_record(zone_id, record_id, domain_name, ip, ttl)` — update A record
- Exponential backoff retry on 429/5xx, max 3 attempts

### ✅ Health Check Worker (`health_checker.py`)
- Background `asyncio` loop started in FastAPI lifespan (NOT APScheduler — uses simple `asyncio.sleep` loop)
- Runs every `DEFAULT_CHECK_INTERVAL` seconds (default: 30)
- Only checks domains with `monitoring_enabled=true`
- Check methods per `check_type`:
  - **ping** — `ping -c 3 -W 3 <ip>`, 12s timeout
  - **tcp** — `asyncio.open_connection(ip, port)`, 3s timeout
  - **http/https** — `httpx.get()` with `Host` header, 5s timeout, checks status code
- Thresholds: 3 consecutive failures → DOWN, 2 consecutive successes → UP
- **Failover**: if active IP is DOWN, switch to first healthy IP in priority order via Cloudflare
- **Auto-revert**: if `auto_revert=true` and primary comes back healthy, switch back
- Per-domain `asyncio.Lock` prevents concurrent failover

### ✅ Cleanup Worker
- Background `asyncio` loop runs every `CLEANUP_INTERVAL_HOURS` (default: 6h)
- Deletes `health_check_log` entries older than `LOG_RETENTION_DAYS` (default: 7)
- Deletes `failover_events` older than `EVENT_RETENTION_DAYS` (default: 30)

### ✅ Frontend Dashboard
- **Card layout** — each domain as a card (not table, avoids overflow/clipping issues)
- **Modal form** — DomainForm renders as a centered modal popup with dark overlay backdrop (not inline at top of page)
- **DomainForm** — adaptive form: shows endpoint+status for HTTP/HTTPS, port for TCP, info banner for Ping
- **IP descriptions** — optional description field for primary IP and each backup IP; shown as small gray text below each IP on all devices (mobile-friendly, no hover required); `title` attribute kept for desktop hover tooltip
- **DomainRow** — shows domain name, active/primary/backup IPs with descriptions, health status (🟢/🔴), force switch dropdown
- **Force Switch** — click-outside-to-close dropdown with IP list, health indicators, labels (active/primary/backup#), IP descriptions
- **Monitoring Toggle** — Pause/Resume button per domain; paused domains show PAUSED badge and dimmed card
- **Success toasts** — green toast notifications for all successful actions (create/update/delete domain, force switch, pause/resume monitoring)
- **Activity Log** — collapsible panel showing recent failover/revert/manual switch events with domain name, IPs, time ago
- **Responsive design** — mobile-first: stacking layouts on small screens (`grid-cols-1` → `sm:grid-cols-2` → `md:grid-cols-4`), wrapping header buttons, scrollable modal, `break-all` on IPs
- **Favicon** — 🌐 emoji as browser tab icon via inline SVG data URI
- Polls `/api/domains` + `/api/domains/:id/health` + `/api/events` every 10s

---

## 🗄️ Database Schema

```
domains: id, name(unique), zone_id, record_id, primary_ip, primary_ip_description(nullable),
         active_ip, auto_revert, check_type, check_endpoint, check_port, check_interval,
         expected_status, ttl, monitoring_enabled, created_at, updated_at

backup_ips: id, domain_id(FK), ip, priority, description(nullable), created_at

health_status: id, domain_id(FK), ip, is_healthy, consecutive_failures,
               consecutive_successes, last_checked, last_status_change

failover_events: id, domain_id(FK), old_ip, new_ip, reason, created_at

health_check_log: id, domain_id(FK), ip, check_type, success, response_time_ms,
                  error_message, created_at
```

**Note:** `check_port` field exists in model/schema/types but was added after initial migration.
Schema changes require `docker compose down -v` to recreate tables (no Alembic migrations set up yet).

---

## 🔧 Environment Variables (.env)

```
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=dns_failover
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/dns_failover
CLOUDFLARE_API_TOKEN=<your_token>
DEFAULT_CHECK_INTERVAL=30
FAILURE_THRESHOLD=3
SUCCESS_THRESHOLD=2
LOG_LEVEL=INFO
LOG_RETENTION_DAYS=7
EVENT_RETENTION_DAYS=30
CLEANUP_INTERVAL_HOURS=6
```

---

## ⚠️ Known Gotchas & Patterns

1. **Schema changes** → must `docker compose down -v` (no Alembic yet), wipes all data
2. **SQLAlchemy async refresh** → after `db.commit()`, always call `await db.refresh(obj)` THEN `await db.refresh(obj, ["relationship"])` — otherwise server-default columns (`created_at`, `updated_at`) cause `MissingGreenlet` errors
3. **Frontend overflow** → never use `overflow-hidden` on containers with dropdowns; current UI uses card layout with `z-50` popover + click-outside-to-close pattern
4. **Form field visibility** → `DomainForm` conditionally shows fields based on `check_type`: endpoint+status for http/https, port for tcp, nothing extra for ping
5. **Health status init** → new domains get `is_healthy=true` for all IPs; actual status only updates after the health check worker runs (first cycle takes ~30s + check time)
6. **record_id auto-discovery** → if `record_id` is null, it's auto-fetched from Cloudflare on domain create and on force switch; stored in DB once discovered
7. **Hot reload** → backend (Uvicorn `--reload`) and frontend (Vite HMR) pick up file changes automatically; `.env` changes require `docker compose restart backend`
8. **Docker only** → no local Python/Node installs; everything runs in containers
9. **Health status unique constraint** → `UNIQUE(domain_id, ip)` on `health_status`; IPs are deduplicated on create/update to avoid constraint violations
10. **Flush before insert** → when updating domain backup IPs, `await db.flush()` after DELETE before inserting new health_status rows
11. **Frontend validation** → DomainForm validates domain name format, IP addresses, zone/record ID format (32-char hex), port ranges, intervals before submission
12. **Toast notifications** → all API errors AND success messages shown to user via toast popups (bottom-right, auto-dismiss 5s); error detail extracted from response body
13. **Teleport proxy** → `vite.config.ts` uses `allowedHosts: true`; all services share `teleport-network` external Docker network
14. **IP descriptions** → optional `description` on backup IPs and `primary_ip_description` on domains; displayed as sub-text below each IP (visible on mobile without hover); also available as `title` tooltip on desktop

---

## 🚀 Not Yet Implemented

- [ ] Alembic migrations (currently using `create_all` on startup)
- [ ] Notifications (Telegram / Slack / Email / webhook)
- [ ] Domain detail page with check history graph
- [ ] Global settings page in UI
- [ ] Per-domain check interval (worker currently uses global interval)
- [ ] Production Nginx config / multi-stage Docker builds
- [ ] Tests
