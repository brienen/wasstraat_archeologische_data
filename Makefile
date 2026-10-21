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
# Wasstraat draaien (ontwikkelomgeving, met broncode-volumes):
#   make app          Start de wasstraat (standaard)
#   make dev          Start in development mode (met hot-reload)
#   make stop         Stop alle containers
#   make backup       Backup Postgres + MongoDB
#
# Publiceren (images voor de live installatie uit deploy/):
#   make publish      Bouw multi-arch images en push naar ghcr.io/brienen
#   make publish PUSH=0 SERVICE=flask   Alleen lokaal bouwen, één service
#   make release VERSION=1.2.3 MSG="..."  Versie taggen, pushen en publiceren
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
COMPOSE_DELFT := $(DC) -f docker-compose.delft.yml
COMPOSE_DELFT_TEST := $(DC) -p wasstraat-delft-test -f docker-compose.delft-test.yml
DT := $(shell date +"%Y-%m-%d_%H-%M-%S")
PG_CONTAINER ?= wasstraat_postgres

# --- Publicatie van images (GitHub Container Registry) ---
# 'make publish' bouwt de eigen images voor linux/amd64 en linux/arm64 en pusht ze naar
# $(REGISTRY)/$(IMAGE_PREFIX)-<service>:<versie> en :latest. Inloggen gebeurt vooraf met
# 'docker login ghcr.io'. Met PUSH=0 bouwt het alleen lokaal, voor dit platform.
# Zie docs/deployment/omgevingen.md.
REGISTRY ?= ghcr.io/brienen
IMAGE_PREFIX ?= wasstraat
# Jupyter is een ontwikkelvoorziening en wordt niet gepubliceerd
IMAGES := airflow flask postgres apache
SERVICE ?= $(IMAGES)
PLATFORMS ?= linux/amd64,linux/arm64
PUSH ?= 1
NO_CACHE ?= 0
BUILDER ?= wasstraat
IMAGE_SOURCE ?= https://github.com/brienen/wasstraat_archeologische_data
# Versie uit config/version.env; init-config.sh maakt dat bestand aan uit version.env.example
VERSION ?= $(strip $(shell sed -n 's/^VERSION=//p' config/version.env config/version.env.example 2>/dev/null | head -1))
ifeq ($(PUSH),1)
PUBLISH_OPTS := --builder $(BUILDER) --platform $(PLATFORMS) --provenance=false --push
PUBLISH_DOEL := bouwen voor $(PLATFORMS) en pushen naar $(REGISTRY) (vooraf: docker login ghcr.io)
else
PUBLISH_OPTS := --load
PUBLISH_DOEL := lokaal bouwen voor dit platform, zonder te pushen
endif
ifeq ($(NO_CACHE),1)
PUBLISH_OPTS += --no-cache --pull
endif

# --- Init-config: genereer .env uit .env.example als ze nog niet bestaan ---
define init-config
	@if [ -f init-config.sh ]; then bash init-config.sh; fi
endef

# --- Wacht tot PostgreSQL en MongoDB verbindingen accepteren (max. 60 s per database) ---
# Nodig direct na 'make start': de containers draaien dan al, maar de databases nog niet.
define wacht-op-databases
	@echo "➜ Wachten tot PostgreSQL en MongoDB klaar zijn..."
	@for i in $$(seq 1 60); do docker exec -u postgres wasstraat_postgres pg_isready -q 2>/dev/null && break; sleep 1; done; \
	docker exec -u postgres wasstraat_postgres pg_isready -q 2>/dev/null || { echo "✗ PostgreSQL is niet bereikbaar" >&2; exit 1; }
	@for i in $$(seq 1 60); do docker exec wasstraat_mongo mongosh --quiet --eval 'db.adminCommand({ping: 1}).ok' >/dev/null 2>&1 && break; sleep 1; done; \
	docker exec wasstraat_mongo mongosh --quiet --eval 'db.adminCommand({ping: 1}).ok' >/dev/null 2>&1 || { echo "✗ MongoDB is niet bereikbaar" >&2; exit 1; }
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
integration: install ## Draai volledige integratietests: Extract + Transform + Load + Flask
	@echo "➜ Test-omgeving starten (synthetische data)..."
	$(COMPOSE_TEST) up -d mongo-test postgres-test redis-test elasticsearch-test airflow-test flask-test apache-test
	@echo "➜ Stap 1: Extract + Transform + Load pipeline..."
	$(PYTEST) tests/integration/ \
		-v -s -m "(integration or load) and not delft" --tb=short; \
	PIPE_EXIT=$$?; \
	echo "➜ Stap 2: Flask smoke tests (vereist geladen PostgreSQL)..."; \
	$(PYTEST) tests/integration/ \
		-v -s -m flask_smoke --tb=short; \
	FLASK_EXIT=$$?; \
	echo "➜ Test-omgeving opruimen..."; \
	$(COMPOSE_TEST) down -v; \
	if [ $$PIPE_EXIT -ne 0 ]; then exit $$PIPE_EXIT; fi; \
	exit $$FLASK_EXIT

.PHONY: integration-keep
integration-keep: install ## Zelfde als integration maar laat containers draaien
	@echo "➜ Test-omgeving starten (synthetische data)..."
	$(COMPOSE_TEST) up -d
	$(PYTEST) tests/integration/ \
		-v -s -m "(integration or load) and not delft" --tb=short
	$(PYTEST) tests/integration/ \
		-v -s -m flask_smoke --tb=short
	@echo "➜ Containers draaien nog. Stop met: $(COMPOSE_TEST) down -v"

.PHONY: integration-pipeline
integration-pipeline: install ## Draai alleen Extract + Transform (zonder Load en Flask)
	@echo "➜ Test-omgeving starten (synthetische data)..."
	$(COMPOSE_TEST) up -d mongo-test postgres-test elasticsearch-test airflow-test flask-test apache-test
	$(PYTEST) tests/integration/ \
		-v -s -m "integration and not delft and not load" --tb=short; \
	EXIT=$$?; \
	echo "➜ Test-omgeving opruimen..."; \
	$(COMPOSE_TEST) down -v; \
	exit $$EXIT

.PHONY: integration-load
integration-load: install ## Draai Extract + Transform + Load (zonder Flask)
	@echo "➜ Test-omgeving starten (inclusief Load)..."
	$(COMPOSE_TEST) up -d mongo-test postgres-test elasticsearch-test airflow-test flask-test apache-test
	$(PYTEST) tests/integration/test_full_pipeline_synthetic_data.py \
		-v -s -m "integration or load" --tb=short; \
	EXIT=$$?; \
	echo "➜ Test-omgeving opruimen..."; \
	$(COMPOSE_TEST) down -v; \
	exit $$EXIT

.PHONY: integration-delft
integration-delft: install ## Draai volledige Delft-integratietests: Extract + Transform + Load + Flask
	@echo "➜ Delft test-omgeving starten (data/test, project DB034)..."
	$(COMPOSE_DELFT_TEST) up -d mongo-test postgres-test redis-test elasticsearch-test airflow-test flask-test apache-test
	@echo "➜ Stap 1: Extract + Transform + Load pipeline..."
	$(PYTEST) tests/integration/ \
		-v -s -m "(delft or delft_load) and not delft_flask" --tb=short; \
	PIPE_EXIT=$$?; \
	echo "➜ Stap 2: Flask smoke tests (vereist geladen PostgreSQL)..."; \
	$(PYTEST) tests/integration/ \
		-v -s -m delft_flask --tb=short; \
	FLASK_EXIT=$$?; \
	echo "➜ Delft test-omgeving opruimen..."; \
	$(COMPOSE_DELFT_TEST) down -v; \
	if [ $$PIPE_EXIT -ne 0 ]; then exit $$PIPE_EXIT; fi; \
	exit $$FLASK_EXIT

.PHONY: integration-delft-pipeline
integration-delft-pipeline: install ## Draai alleen Delft Extract + Transform (zonder Load en Flask)
	@echo "➜ Delft test-omgeving starten (data/test, project DB034)..."
	$(COMPOSE_DELFT_TEST) up -d mongo-test postgres-test elasticsearch-test airflow-test
	$(PYTEST) tests/integration/ \
		-v -s -m "delft and not delft_load and not delft_flask" --tb=short; \
	EXIT=$$?; \
	echo "➜ Delft test-omgeving opruimen..."; \
	$(COMPOSE_DELFT_TEST) down -v; \
	exit $$EXIT

.PHONY: test-flask
test-flask: install ## Draai Flask smoke tests (NB: vereist geladen PostgreSQL, gebruik 'make integration')
	@echo "➜ Flask test-omgeving starten..."
	@echo "⚠  Let op: Flask tests vereisen geladen data. Gebruik 'make integration' voor de volledige suite."
	$(COMPOSE_TEST) up -d postgres-test redis-test elasticsearch-test flask-test apache-test
	@echo "➜ Wachten tot Flask klaar is..."
	$(PYTEST) tests/integration/ \
		-v -s -m flask_smoke --tb=short; \
	EXIT=$$?; \
	echo "➜ Flask test-omgeving opruimen..."; \
	$(COMPOSE_TEST) down -v; \
	exit $$EXIT

.PHONY: test-all
test-all: test integration ## Draai unit tests + volledige integratie (Extract→Transform→Load→Flask)

# ============================================================
# Synthetische data
# ============================================================

.PHONY: synthetic
synthetic: install ## Genereer synthetische voorbeelddata (MDB-bestanden)
	@echo "➜ Synthetische data genereren..."
	$(BIN)/pip install -r data/synthetic/generatie/requirements-synthetic.txt --quiet
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

.PHONY: constraints
constraints: ## Leg nieuwe pakketversies vast voor Flask, Jupyter en Airflow (daarna: make test-all)
	bash scripts/leg_pakketversies_vast.sh

.PHONY: app
app: ## Start de wasstraat (alle services, synthetische data)
	$(init-config)
	$(DC) up -d

.PHONY: delft
delft: ## Start de wasstraat met Delftse data
	$(init-config)
	$(COMPOSE_DELFT) up -d

.PHONY: dev
dev: ## Start in development mode (met hot-reload volumes)
	$(init-config)
	$(DC) -f docker-compose.yml -f docker-compose.develop.yml up -d

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
backup: ## Backup Postgres + MongoDB (naar data/<omgeving>/backup/)
	@echo "Backing up met timestamp $(DT)..."
	$(DC) stop flask airflow
	$(wacht-op-databases)
	docker exec -u postgres -w /backup wasstraat_postgres bash -c \
		"pg_dump -v -F t -f postgres_$(DT).tar flask"
	docker exec -w /backup wasstraat_mongo bash -c \
		"mongodump --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$$DB_STAGING?authSource=admin --out mongo_$(DT)"
	docker exec -w /backup wasstraat_mongo bash -c \
		"mongodump --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$$DB_FILES?authSource=admin --out mongo_$(DT)"
	docker exec -w /backup wasstraat_mongo bash -c \
		"mongodump --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$$DB_ANALYSE?authSource=admin --out mongo_$(DT)"
	$(DC) start flask airflow
	@echo "✓ Backup gereed in data/<omgeving>/backup/: postgres/postgres_$(DT).tar + mongo/mongo_$(DT)/"

.PHONY: restore
restore: ## Restore backup (gebruik: make restore TS=2025-01-15_10-30-00)
ifndef TS
	$(error Geef een timestamp op, bijv: make restore TS=2025-01-15_10-30-00)
endif
	@echo "Restoring backup van $(TS)..."
	$(DC) stop flask airflow
	$(wacht-op-databases)
	docker exec -u postgres -w /backup wasstraat_postgres bash -c \
		"pg_restore -Ft -c -v -d flask < postgres_$(TS).tar"
	docker exec -w /backup wasstraat_mongo bash -c \
		"mongorestore --drop --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/?authSource=admin mongo_$(TS)"
	$(DC) start flask airflow
	@echo "✓ Restore gereed."

.PHONY: export
export: ## Exporteer Postgres tabellen naar CSV (data/<omgeving>/backup/)
	@echo "Exporting Postgres data naar CSV met timestamp $(DT)..."
	$(DC) stop flask airflow
	$(wacht-op-databases)
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
	@echo "✓ Export gereed in data/<omgeving>/backup/postgres/postgres_$(DT)/"

.PHONY: migrate-postgres-data
migrate-postgres-data: ## Eenmalig bij bestaande installaties: zet PostgreSQL-data in het volume (eerst 'make stop')
	bash scripts/postgres/migreer_data_naar_volume.sh $(PG_CONTAINER)

# ============================================================
# Publicatie en release
# ============================================================

.PHONY: publish
publish: ## Bouw en push images naar ghcr.io (opties: SERVICE=flask PUSH=0 NO_CACHE=1 VERSION=1.2.3)
	@test -n "$(VERSION)" || { echo "✗ Geen versie gevonden; zet VERSION=x.y.z in config/version.env" >&2; exit 1; }
	@for s in $(SERVICE); do \
		test -f services/$$s/Dockerfile || { echo "✗ Onbekende service '$$s' (kies uit: $(IMAGES))" >&2; exit 1; }; \
	done
	@if [ "$(PUSH)" = "1" ]; then \
		docker buildx inspect $(BUILDER) >/dev/null 2>&1 || \
		{ echo "➜ Multi-arch builder '$(BUILDER)' aanmaken..."; docker buildx create --name $(BUILDER) --driver docker-container >/dev/null; }; \
	fi
	@echo "➜ Images $(VERSION): $(PUBLISH_DOEL)"
	@for s in $(SERVICE); do \
		echo "➜ $(REGISTRY)/$(IMAGE_PREFIX)-$$s:$(VERSION)"; \
		docker buildx build $(PUBLISH_OPTS) \
			-f services/$$s/Dockerfile \
			-t $(REGISTRY)/$(IMAGE_PREFIX)-$$s:$(VERSION) \
			-t $(REGISTRY)/$(IMAGE_PREFIX)-$$s:latest \
			--label org.opencontainers.image.source=$(IMAGE_SOURCE) \
			--label org.opencontainers.image.version=$(VERSION) \
			--label org.opencontainers.image.licenses=EUPL-1.2 \
			. || exit 1; \
	done
	@echo "✓ Klaar: $(SERVICE) ($(VERSION))"

.PHONY: release
release: ## Versie vastleggen, committen, taggen, pushen en images publiceren (gebruik: make release VERSION=1.2.3 MSG="Release notes")
ifneq ($(origin VERSION),command line)
	$(error Geef een versie op, bijv: make release VERSION=1.2.3 MSG="Nieuwe features")
endif
ifndef MSG
	$(error Geef een message op, bijv: make release VERSION=1.2.3 MSG="Nieuwe features")
endif
	@echo "VERSION=$(VERSION)" > config/version.env.example
	@echo "VERSION=$(VERSION)" > config/version.env
	@sed -i.bak 's/^WASSTRAAT_VERSION=.*/WASSTRAAT_VERSION=$(VERSION)/' deploy/.env.example && rm -f deploy/.env.example.bak
	git add .
	git commit -m "$(MSG)"
	git tag -a $(VERSION) -m "$(MSG)"
	git push --all
	git push --tags
	$(MAKE) publish VERSION=$(VERSION)

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
