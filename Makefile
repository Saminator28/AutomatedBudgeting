# Automated Budgeting Tool - Docker Commands

COMPOSE := $(shell if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then echo "docker compose"; elif command -v docker-compose >/dev/null 2>&1; then echo docker-compose; fi)
UNAME_S := $(shell uname -s)
COMPOSE_FILES := -f docker-compose.yml

ifeq ($(UNAME_S),Linux)
COMPOSE_FILES += -f docker-compose.linux.yml
endif

.PHONY: help build up down logs shell clean process aggregate dashboard test models status check-compose check-models

check-compose:
ifeq ($(COMPOSE),)
	@echo "❌ Docker Compose not found."
	@echo "   Install Docker Compose plugin (preferred) or legacy docker-compose."
	@echo "   Then rerun your command."
	@exit 1
endif

# Preflight check: refuse to start the app if any configured Ollama model
# is missing on the host.  See scripts/preflight_models.py.
check-models:
	@command -v python3 >/dev/null 2>&1 || { \
		echo "❌ python3 is required for the model preflight check."; \
		echo "   Install Python 3, or bypass the check with: $(COMPOSE) $(COMPOSE_FILES) up -d"; \
		exit 1; \
	}
	@python3 scripts/preflight_models.py

help:
	@echo "Automated Budgeting Tool - Docker Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make build         - Build Docker images"
	@echo "  make up            - Start all services (blocks if Ollama models missing)"
	@echo "  make down          - Stop all services"
	@echo "  make check-models  - Verify configured Ollama models are installed (host)"
	@echo ""
	@echo "Usage:"
	@echo "  make logs        - View logs"
	@echo "  make shell       - Open shell in app container"
	@echo "  make dashboard   - Open dashboard in browser"
	@echo ""
	@echo "Processing:"
	@echo "  make process MONTH=2025-03  - Process statements for a month"
	@echo "  make aggregate               - Aggregate monthly reports"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean       - Remove containers and volumes"
	@echo "  make test        - Run tests"

build: check-compose
	@echo "🔨 Building Docker images..."
	$(COMPOSE) $(COMPOSE_FILES) build

up: check-compose check-models
	@echo "🚀 Starting services..."
	$(COMPOSE) $(COMPOSE_FILES) up -d
	@echo "✅ Services started!"
	@echo "   Dashboard: http://localhost:8000"
	@echo "   Ollama API: http://localhost:11434"

down: check-compose
	@echo "🛑 Stopping services..."
	$(COMPOSE) $(COMPOSE_FILES) down

logs: check-compose
	$(COMPOSE) $(COMPOSE_FILES) logs -f app

shell: check-compose
	$(COMPOSE) $(COMPOSE_FILES) exec app /bin/bash

clean: check-compose
	@echo "🧹 Cleaning up..."
	$(COMPOSE) $(COMPOSE_FILES) down -v
	docker system prune -f

process: check-compose
ifndef MONTH
	@echo "❌ Error: MONTH not specified"
	@echo "Usage: make process MONTH=2025-03"
else
	@echo "📊 Processing statements for $(MONTH)..."
	$(COMPOSE) $(COMPOSE_FILES) exec app python3 scripts/process_monthly.py --month $(MONTH)
endif

aggregate: check-compose
	@echo "📈 Aggregating monthly reports..."
	$(COMPOSE) $(COMPOSE_FILES) exec app python3 scripts/aggregate_monthly.py

dashboard:
	@echo "🌐 Opening dashboard..."
	@which xdg-open > /dev/null && xdg-open http://localhost:8000 || open http://localhost:8000

test: check-compose
	@echo "🧪 Running tests..."
	$(COMPOSE) $(COMPOSE_FILES) exec app python3 -m pytest tests/

# Pull Ollama models (on host machine, not in Docker)
models:
	@echo "📦 Pulling required Ollama models on HOST machine..."
	@echo "   (Using your existing Ollama installation)"
	ollama pull gemma3:27b
	ollama pull qwen3:32b
	@echo "✅ Models ready!"

# Check status
status: check-compose
	@echo "📊 Service Status:"
	@$(COMPOSE) $(COMPOSE_FILES) ps
