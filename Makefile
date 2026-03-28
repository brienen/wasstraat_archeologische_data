# ============================================================
# Wasstraat Archeologische Data — Makefile
# ============================================================
#
# Gebruik:
#   make help         Toon alle targets
#
# Ontwikkelen:
#   make install          Maak .venv aan en installeer test-dependencies
#   make test             Draai unit tests
#   make integration      Draai alle integratietests (Docker + Airflow + DAGs)
#   make integration-keep Zelfde, maar laat containers draaien (debugging)
#   make test-all         Draai unit + integratietests
#   make docs             Start MkDocs dev-server
#
# Wasstraat draaien:
#   make app          Start de wasstraat (standaard)
#   make dev          Start in development mode (met hot-reload)
#   make stop         Stop alle containers
#   make backup       Backup Postgres + MongoDB
# ============================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

# --- Python ---
PYTHON := $(shell command -v python3.11 2>/dev/null \
           || command -v python3.12 2>/dev/null \
           || command -v python3.10 2>/dev/null \
           || command -v python3 2>/dev/null)
VENV := .venv
BIN := $(VENV)/bin
PYTEST := $(BIN)/python -m pytest

# --- Docker Compose ---
DC := docker compose 
COMPOSE_TEST := $(DC) -p wasstraat-test -f docker-compose.test.yml
COMPOSE_TEST_DELFT := $(DC) -p wasstraat-test -f docker-compose.test.yml -f docker-compose.test-delft.yml
DT := $(shell date +"%Y-%m-%d_%H-%M-%S")

# --- Init-config: genereer .env uit .env.example als ze nog niet bestaan ---
define init-config
	@if [ -f init-config.sh ]; then bash init-config.sh; fi
endef

# ============================================================
# Installatie (test-omgeving)
# ============================================================

.PHONY: install
install: $(VENV)/bin/activate ## Maak .venv aan en installeer dependencies

$(VENV)/bin/activate: requirements-test.txt
	@echo "➜ Venv aanmaken met $(PYTHON)..."
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip --quiet
	$(BIN)/pip install -r requirements-test.txt --quiet
	@touch $(VENV)/bin/activate
	@echo ""
	@echo "✓ Venv gereed. Activeer met: source $(VENV)/bin/activate"

# ============================================================
# Tests
# ============================================================

.PHONY: test
test: install ## Draai unit tests
	$(PYTEST) tests/unit/ -v

.PHONY: test-quick
test-quick: install ## Draai unit tests (korte output)
	$(PYTEST) tests/unit/ -q

.PHONY: integration
integration: install ## Draai integratietests met synthetische data (SY001 + SY002)
	@echo "➜ Test-omgeving starten (synthetische data)..."
	$(COMPOSE_TEST) up -d mongo-test postgres-test flask-test airflow-test
	@echo "➜ Wachten tot services klaar zijn (pytest doet de rest)..."
	$(PYTEST) tests/integration/ \
		-v -s -m "integration and not delft and not load" --tb=short; \
	EXIT=$$?; \
	echo "➜ Test-omgeving opruimen..."; \
	$(COMPOSE_TEST) down -v; \
	exit $$EXIT

.PHONY: integration-keep
integration-keep: install ## Zelfde als integration maar laat containers draaien
	@echo "➜ Test-omgeving starten (synthetische data)..."
	$(COMPOSE_TEST) up -d
	$(PYTEST) tests/integration/ \
		-v -s -m "integration and not delft" --tb=short
	@echo "➜ Containers draaien nog. Stop met: $(COMPOSE_TEST) down -v"

.PHONY: integration-load
integration-load: install ## Draai volledige pipeline inclusief Load naar PostgreSQL
	@echo "➜ Test-omgeving starten (inclusief Load)..."
	$(COMPOSE_TEST) up -d mongo-test postgres-test flask-test airflow-test
	@echo "➜ Draai Extract + Transform + Load tests..."
	$(PYTEST) tests/integration/test_full_pipeline_synthetic_data.py \
		-v -s -m "integration or load" --tb=short; \
	EXIT=$$?; \
	echo "➜ Test-omgeving opruimen..."; \
	$(COMPOSE_TEST) down -v; \
	exit $$EXIT

.PHONY: integration-delft
integration-delft: install ## Draai integratietests met echte Delftse data (DB034)
	@echo "➜ Test-omgeving starten (Delftse data)..."
	$(COMPOSE_TEST_DELFT) up -d
	@echo "➜ Wachten tot services klaar zijn..."
	$(PYTEST) tests/integration/ \
		-v -s -m delft --tb=short; \
	EXIT=$$?; \
	echo "➜ Test-omgeving opruimen..."; \
	$(COMPOSE_TEST_DELFT) down -v; \
	exit $$EXIT

.PHONY: test-flask
test-flask: install ## Draai Flask smoke tests (start Flask + PostGIS + Redis in Docker)
	@echo "➜ Flask test-omgeving starten..."
	$(COMPOSE_TEST) up -d postgres-test redis-test flask-test
	@echo "➜ Wachten tot Flask klaar is..."
	$(PYTEST) tests/integration/ \
		-v -s -m flask_smoke --tb=short; \
	EXIT=$$?; \
	echo "➜ Flask test-omgeving opruimen..."; \
	$(COMPOSE_TEST) down -v; \
	exit $$EXIT

.PHONY: test-all
test-all: test integration test-flask ## Draai unit + integratie + Flask smoke tests

# ============================================================
# Synthetische data
# ============================================================

.PHONY: synthetic
synthetic: install ## Genereer synthetische voorbeelddata (MDB-bestanden)
	@echo "➜ Synthetische data genereren..."
	JAVA_HOME=$$(brew --prefix openjdk 2>/dev/null || echo "/usr/lib/jvm/java-21-openjdk") \
	PATH="$$(brew --prefix openjdk 2>/dev/null || echo "/usr/lib/jvm/java-21-openjdk")/bin:$$PATH" \
	$(BIN)/python data/synthetic/generatie/generate_synthetic_data.py

# ============================================================
# Documentatie
# ============================================================

.PHONY: docs
docs: install ## Start MkDocs dev-server (localhost:8000)
	@$(BIN)/pip install mkdocs --quiet 2>/dev/null || true
	$(BIN)/mkdocs serve

.PHONY: docs-build
docs-build: install ## Bouw statische documentatie
	@$(BIN)/pip install mkdocs --quiet 2>/dev/null || true
	$(BIN)/mkdocs build

# ============================================================
# Wasstraat — omgevingen
# ============================================================

.PHONY: build
build: ## Bouw alle Docker images opnieuw
	$(init-config)
	$(DC) build postgres airflow flask jupyter apache

.PHONY: build-force
build-force: ## Bouw alle Docker images opnieuw van de grond af aan (geen cache)
	$(init-config)
	$(DC) build --no-cache --pull postgres airflow flask jupyter apache

.PHONY: app
app: ## Start de wasstraat (alle services)
	$(init-config)
	$(DC) up -d

.PHONY: dev
dev: ## Start in development mode (met hot-reload volumes)
	$(init-config)
	$(DC) -f docker-compose.yml -f docker-compose.develop.yml up -d

.PHONY: example
example: ## Start met voorbeelddata
	$(init-config)
	$(DC) -f docker-compose.yml -f docker-compose.example.yml up -d

.PHONY: acc
acc: ## Start in acceptatie-omgeving
	$(init-config)
	$(DC) -f docker-compose.yml -f docker-compose.acc.yml up -d

.PHONY: prod
prod: ## Start in productie-omgeving
	$(init-config)
	$(DC) -f docker-compose.yml -f docker-compose.prod.yml up -d

.PHONY: stop
stop: ## Stop alle containers
	$(DC) stop

.PHONY: start
start: ## Herstart gestopte containers
	$(DC) start

.PHONY: down
down: ## Stop en verwijder alle containers
	$(DC) down

.PHONY: logs
logs: ## Toon live logs van alle services
	$(DC) logs -f

.PHONY: ps
ps: ## Toon status van alle services
	$(DC) ps

# ============================================================
# Backup & Restore
# ============================================================

.PHONY: backup
backup: ## Backup Postgres + MongoDB (naar backup/)
	@echo "Backing up met timestamp $(DT)..."
	$(DC) stop flask airflow
	docker exec -u postgres -w /backup wasstraat_postgres bash -c \
		"pg_dump -v -F t -f postgres_$(DT).tar flask"
	docker exec -w /backup wasstraat_mongo bash -c \
		"mongodump --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$$DB_STAGING?authSource=admin --out mongo_$(DT)"
	docker exec -w /backup wasstraat_mongo bash -c \
		"mongodump --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$$DB_FILES?authSource=admin --out mongo_$(DT)"
	docker exec -w /backup wasstraat_mongo bash -c \
		"mongodump --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$$DB_ANALYSE?authSource=admin --out mongo_$(DT)"
	$(DC) start flask airflow
	@echo "✓ Backup gereed: backup/postgres_$(DT).tar + backup/mongo_$(DT)/"

.PHONY: restore
restore: ## Restore backup (gebruik: make restore TS=2025-01-15_10-30-00)
ifndef TS
	$(error Geef een timestamp op, bijv: make restore TS=2025-01-15_10-30-00)
endif
	@echo "Restoring backup van $(TS)..."
	$(DC) stop flask airflow
	docker exec -u postgres -w /backup wasstraat_postgres bash -c \
		"pg_restore -Ft -c -v -d flask < postgres_$(TS).tar"
	docker exec -w /backup wasstraat_mongo bash -c \
		"mongorestore --drop --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/?authSource=admin mongo_$(TS)"
	$(DC) start flask airflow
	@echo "✓ Restore gereed."

.PHONY: export
export: ## Exporteer Postgres tabellen naar CSV (backup/)
	@echo "Exporting Postgres data naar CSV met timestamp $(DT)..."
	$(DC) stop flask airflow
	docker exec -u postgres -w /backup wasstraat_postgres bash -c "mkdir -p postgres_$(DT)"
	@for table in Def_Vulling Def_Conserveringsproject Def_artefact_conservering \
		Def_DT_Soort_Plant Def_Project Def_Put Def_Spoor Def_Vondst Def_Plaatsing \
		Def_Vlak Def_artefact_abr Def_Doos Def_Standplaats Def_Bruikleen Def_Partij \
		Def_Vindplaats Def_Artefact Def_ABR Def_Stelling Def_DT_Soort_Schelp \
		Def_Bestand Def_DT_Soort_Deel Def_DT_Soort_Staat Def_Monster \
		Def_Monster_Botanie Def_Monster_Schelp; do \
		echo "  Exporting $$table..."; \
		docker exec -u postgres wasstraat_postgres bash -c \
			"psql -t -d flask -c \"COPY public.\\\"$$table\\\" TO '/backup/postgres_$(DT)/$$table.csv' DELIMITER ';' CSV HEADER QUOTE '\"' ESCAPE '\"'; \""; \
	done
	$(DC) start flask airflow
	@echo "✓ Export gereed: backup/postgres_$(DT)/"

# ============================================================
# Release (handmatig — gebruik met zorg)
# ============================================================

.PHONY: release
release: ## Release bouwen en pushen (gebruik: make release VERSION=1.2.3 MSG="Release notes")
ifndef VERSION
	$(error Geef een versie op, bijv: make release VERSION=1.2.3 MSG="Nieuwe features")
endif
ifndef MSG
	$(error Geef een message op, bijv: make release VERSION=1.2.3 MSG="Nieuwe features")
endif
	@echo "VERSION=$(VERSION)" > config/version.env
	git tag -a $(VERSION) -m "$(MSG)"
	git add .
	git commit -m "$(MSG)"
	git push --all
	git push --tags
	docker login
	docker buildx build --no-cache --platform linux/amd64,linux/arm64 \
		--builder mybuilder -f ./services/flask/Dockerfile \
		-t brienen/wasstraat_flask:$(VERSION) --push .

# ============================================================
# Opschonen
# ============================================================

.PHONY: clean
clean: ## Verwijder .venv en caches
	rm -rf $(VENV)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf site/

.PHONY: clean-test-db
clean-test-db: ## Stop en verwijder test-database containers
	$(COMPOSE_TEST) down -v 2>/dev/null || true

# ============================================================
# Help
# ============================================================

.PHONY: help
help: ## Toon deze help
	@echo "Wasstraat Archeologische Data"
	@echo ""
	@echo "Beschikbare targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""
