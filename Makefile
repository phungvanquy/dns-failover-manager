.PHONY: help up down restart build logs test test-v lint shell-backend shell-frontend db-shell db-reset clean setup

# Default target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Setup ──────────────────────────────────────────
setup: ## Initial setup: copy .env and build containers
	@test -f .env || cp .env.example .env
	@echo "✅ .env ready (edit CLOUDFLARE_API_TOKEN before starting)"
	docker compose build

# ─── Docker Compose ─────────────────────────────────
up: ## Start all services in background
	docker compose up -d

up-logs: ## Start all services with log output
	docker compose up

down: ## Stop all services
	docker compose down

restart: ## Restart all services
	docker compose restart

build: ## Rebuild all containers
	docker compose build

build-no-cache: ## Rebuild all containers without cache
	docker compose build --no-cache

# ─── Logs ───────────────────────────────────────────
logs: ## Show logs for all services (follow)
	docker compose logs -f

logs-backend: ## Show backend logs (follow)
	docker compose logs -f backend

logs-frontend: ## Show frontend logs (follow)
	docker compose logs -f frontend

logs-db: ## Show database logs (follow)
	docker compose logs -f db

# ─── Testing ────────────────────────────────────────
test: ## Run all tests
	docker compose exec db psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='dns_failover_test'" | grep -q 1 || \
		docker compose exec db psql -U postgres -c "CREATE DATABASE dns_failover_test;"
	docker compose run --rm backend python -m pytest tests/ --tb=short -q

test-v: ## Run all tests (verbose)
	docker compose exec db psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='dns_failover_test'" | grep -q 1 || \
		docker compose exec db psql -U postgres -c "CREATE DATABASE dns_failover_test;"
	docker compose run --rm backend python -m pytest tests/ -v --tb=short

test-file: ## Run specific test file (usage: make test-file FILE=tests/test_crud.py)
	docker compose run --rm backend python -m pytest $(FILE) -v --tb=short

# ─── Shell Access ───────────────────────────────────
shell-backend: ## Open bash in backend container
	docker compose exec backend bash

shell-frontend: ## Open sh in frontend container
	docker compose exec frontend sh

db-shell: ## Open psql in database container
	docker compose exec db psql -U postgres -d dns_failover

# ─── Database ───────────────────────────────────────
db-reset: ## Destroy and recreate database (WARNING: deletes all data)
	docker compose down
	rm -rf data/postgres
	docker compose up -d
	@echo "⏳ Waiting for services..."
	@sleep 5
	@echo "✅ Database reset complete"

# ─── Cleanup ────────────────────────────────────────
clean: ## Remove all containers, volumes, and images
	docker compose down -v --rmi local
	@echo "✅ Cleaned up"

clean-all: ## Remove everything including cached layers
	docker compose down -v --rmi all --remove-orphans
	docker system prune -f
	@echo "✅ Full cleanup done"

# ─── Status ─────────────────────────────────────────
ps: ## Show running containers
	docker compose ps

health: ## Check API health
	@curl -sf http://localhost:8000/api/health && echo "" || echo "❌ Backend not responding"
