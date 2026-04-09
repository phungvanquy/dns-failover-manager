# DNS Failover Manager

A lightweight, self-hosted tool that monitors server health and automatically updates Cloudflare DNS records to redirect traffic when your primary server goes down.

![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Features

- **Automatic Failover** — Detects when your primary IP is down and switches DNS to the next healthy backup
- **Multiple Check Types** — HTTP, HTTPS, TCP, and ICMP Ping health checks
- **Cloudflare Integration** — Updates DNS A records via the Cloudflare API with retry logic
- **Auto-Revert** — Automatically switches back to the primary IP when it recovers
- **Web Dashboard** — View domain status, manage configurations, and force manual switches
- **Event Logging** — Full audit trail of all failover and revert events

## Quick Start

```bash
# Clone the repo
git clone git@github.com:phungvanquy/dns-failover-manager.git
cd dns-failover-manager

# Setup environment
make setup
# Edit .env with your Cloudflare API token
nano .env

# Start all services
make up

# Open dashboard
open http://localhost:3000
```

## Requirements

- Docker & Docker Compose

That's it. Everything runs in containers.

## Architecture

```
┌──────────────┐      ┌──────────────┐      ┌─────────────────┐
│   React SPA  │◄────►│  FastAPI API  │◄────►│  PostgreSQL DB  │
│  (Vite, TS)  │      │  (Python 3.12)│      │   (via Docker)  │
└──────────────┘      └──────┬───────┘      └─────────────────┘
                             │
                ┌────────────┼────────────┐
                ▼            ▼            ▼
        Health Checker   Cloudflare   Failover
        (async worker)    API Client    Engine
```

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 3000 | React + Vite + Tailwind dashboard |
| Backend | 8000 | FastAPI REST API + health check worker |
| Database | 5432 | PostgreSQL 16 |

## Configuration

Copy `.env.example` to `.env` and configure:

```env
# Required
CLOUDFLARE_API_TOKEN=your_token_here  # Needs Zone.DNS:Edit permission

# Optional (defaults shown)
DEFAULT_CHECK_INTERVAL=30    # Seconds between health checks
FAILURE_THRESHOLD=3          # Consecutive failures before marking DOWN
SUCCESS_THRESHOLD=2          # Consecutive successes before marking UP
```

## API Endpoints

```
GET    /api/domains              List all domains
POST   /api/domains              Create domain + backup IP pool
GET    /api/domains/:id          Get domain details
PUT    /api/domains/:id          Update domain configuration
DELETE /api/domains/:id          Delete domain
POST   /api/domains/:id/switch   Force switch to a specific IP
GET    /api/domains/:id/health   Health status for all IPs
GET    /api/domains/:id/events   Failover event history
GET    /api/health               App health check
```

## Make Commands

```
make help            Show all available commands
make setup           Initial setup (copy .env, build containers)
make up              Start all services
make down            Stop all services
make logs            Follow all logs
make logs-backend    Follow backend logs
make test            Run all tests
make test-v          Run tests (verbose)
make db-reset        Destroy and recreate database
make shell-backend   Open bash in backend container
make db-shell        Open psql shell
make ps              Show running containers
make health          Check API health
make clean           Remove containers and volumes
```

## How It Works

1. **Add a domain** with a primary IP and backup IPs via the dashboard
2. **Health checker** runs every 30s (configurable), testing each IP with your chosen method
3. When an IP fails **3 consecutive checks**, it's marked DOWN
4. If the **active IP is down**, the system automatically:
   - Finds the first healthy backup IP
   - Updates the Cloudflare DNS A record
   - Logs the failover event
5. When the **primary recovers** (2 consecutive successes), auto-reverts if enabled

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), Uvicorn |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Database | PostgreSQL 16 |
| HTTP Client | httpx (async) |
| Containers | Docker, Docker Compose |

## Development

All development happens inside Docker — no local installs needed.

```bash
make up          # Start with hot-reload (backend + frontend)
make test        # Run test suite (69 tests)
make logs        # Watch logs
```

Backend auto-reloads on file changes (Uvicorn `--reload`). Frontend uses Vite HMR.

## License

MIT
