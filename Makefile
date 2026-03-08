# Automated Budgeting Tool - Docker Commands

.PHONY: help build up down logs shell clean process dashboard test

help:
	@echo "Automated Budgeting Tool - Docker Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make build       - Build Docker images"
	@echo "  make up          - Start all services"
	@echo "  make down        - Stop all services"
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

build:
	@echo "🔨 Building Docker images..."
	docker-compose build

up:
	@echo "🚀 Starting services..."
	docker-compose up -d
	@echo "✅ Services started!"
	@echo "   Dashboard: http://localhost:8000"
	@echo "   Ollama API: http://localhost:11434"

down:
	@echo "🛑 Stopping services..."
	docker-compose down

logs:
	docker-compose logs -f app

shell:
	docker-compose exec app /bin/bash

clean:
	@echo "🧹 Cleaning up..."
	docker-compose down -v
	docker system prune -f

process:
ifndef MONTH
	@echo "❌ Error: MONTH not specified"
	@echo "Usage: make process MONTH=2025-03"
else
	@echo "📊 Processing statements for $(MONTH)..."
	docker-compose exec app python3 scripts/process_monthly.py --month $(MONTH)
endif

aggregate:
	@echo "📈 Aggregating monthly reports..."
	docker-compose exec app python3 scripts/aggregate_monthly.py

dashboard:
	@echo "🌐 Opening dashboard..."
	@which xdg-open > /dev/null && xdg-open http://localhost:8000 || open http://localhost:8000

test:
	@echo "🧪 Running tests..."
	docker-compose exec app python3 -m pytest tests/

# Pull Ollama models (on host machine, not in Docker)
models:
	@echo "📦 Pulling required Ollama models on HOST machine..."
	@echo "   (Using your existing Ollama installation)"
	ollama pull gemma3:27b
	ollama pull qwen3:32b
	@echo "✅ Models ready!"

# Check status
status:
	@echo "📊 Service Status:"
	@docker-compose ps
