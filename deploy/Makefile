# ============================================================
# Wasstraat Archeologische Data — live installatie uit gepubliceerde images
# ============================================================
#
# Elk commando is een 'docker compose'-aanroep in deze map; docker-compose.yml en .env
# worden automatisch gelezen. Typ 'make help' voor een overzicht.
#
# Eerste keer:  make init  →  brondata klaarzetten  →  make up  →  make inloggegevens
# Bijwerken:    make backup  →  WASSTRAAT_VERSION in .env aanpassen  →  make update
# ============================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

DC := docker compose
DT := $(shell date +"%Y-%m-%d_%H-%M-%S")

# Lees de mappen uit .env (zelfde standaardwaarden als docker-compose.yml)
define lees-env
	set -a; [ -f .env ] && . ./.env; set +a; \
	INPUT="$${WASSTRAAT_INPUT:-./data/input}"; OUTPUT="$${WASSTRAAT_OUTPUT:-./data/output}"; \
	BACKUP="$${WASSTRAAT_BACKUP:-./data/backup}"; CONFIG="$${WASSTRAAT_CONFIG:-./wasstraat_config}"
endef

# Wacht tot PostgreSQL en MongoDB verbindingen accepteren (max. 60 s per database)
define wacht-op-databases
	@echo "➜ Wachten tot PostgreSQL en MongoDB klaar zijn..."
	@for i in $$(seq 1 60); do $(DC) exec -T -u postgres postgres pg_isready -q 2>/dev/null && break; sleep 1; done; \
	$(DC) exec -T -u postgres postgres pg_isready -q 2>/dev/null || { echo "✗ PostgreSQL is niet bereikbaar" >&2; exit 1; }
	@for i in $$(seq 1 60); do $(DC) exec -T mongo mongosh --quiet --eval 'db.adminCommand({ping: 1}).ok' >/dev/null 2>&1 && break; sleep 1; done; \
	$(DC) exec -T mongo mongosh --quiet --eval 'db.adminCommand({ping: 1}).ok' >/dev/null 2>&1 || { echo "✗ MongoDB is niet bereikbaar" >&2; exit 1; }
endef

# ============================================================
# Installeren en starten
# ============================================================

.PHONY: init
init: ## Maak .env, config/*.env (met gegenereerde wachtwoorden) en de datamappen aan
	@[ -f .env ] || { cp .env.example .env; echo "✓ .env aangemaakt uit .env.example; controleer de versie, mappen en poorten"; }
	@bash init-config.sh
	@$(lees-env); \
	mkdir -p "$$INPUT"/{projecten,projectenlijst,magazijnlijst,fotolijst,monsterdatabase,rapporten,referentietabellen} \
	         "$$OUTPUT/archeomedia" "$$BACKUP"/{postgres,mongo} "$$CONFIG" && \
	chmod -R a+rwX "$$OUTPUT" "$$BACKUP" 2>/dev/null; \
	echo "✓ Mappen gereed: brondata in $$INPUT, configuratie in $$CONFIG"

.PHONY: pull
pull: ## Haal de images van de versie uit .env op
	$(DC) pull

.PHONY: up
up: init ## Start alle services (haalt ontbrekende images op)
	$(DC) up -d
	@echo "✓ Gestart. Status: make ps, logs: make logs, inloggen: make inloggegevens"

.PHONY: update
update: ## Werk bij naar de versie in .env: images ophalen en gewijzigde containers vervangen (eerst: make backup)
	$(DC) pull
	$(DC) up -d
	@echo "✓ Bijgewerkt. Oude images opruimen: docker image prune"

.PHONY: stop
stop: ## Stop alle containers
	$(DC) stop

.PHONY: start
start: ## Start gestopte containers
	$(DC) start

.PHONY: restart
restart: ## Herstart alle containers
	$(DC) restart

.PHONY: down
down: ## Stop en verwijder de containers (de data in de volumes blijft bestaan)
	$(DC) down

.PHONY: ps
ps: ## Toon de status van alle services
	$(DC) ps

.PHONY: logs
logs: ## Toon live logs van alle services (of één: make logs S=airflow)
	$(DC) logs -f $(S)

.PHONY: inloggegevens
inloggegevens: ## Toon de adressen en wachtwoorden van Airflow en de Flask App
	@set -a; [ -f .env ] && . ./.env; set +a; \
	echo "Airflow     http://localhost:$${WASSTRAAT_PORT_AIRFLOW:-8080}   admin / $$(sed -n 's/^SECURITY__ADMIN_PASSWORD=//p' config/airflow.env 2>/dev/null)"; \
	echo "Flask App   http://localhost:$${WASSTRAAT_PORT_APACHE:-5052}   admin / $$(sed -n 's/^FLASK_ADMIN_PASSWORD=//p' config/flask.env 2>/dev/null)   (via Apache; media onder /archeomedia)"

# ============================================================
# Verwerken
# ============================================================

.PHONY: volledige-cyclus
volledige-cyclus: ## Start de volledige verwerking in Airflow (DAG Extract_Transform_Load_Full_Cycle)
	$(DC) exec -T airflow airflow dags unpause Extract_Transform_Load_Full_Cycle
	$(DC) exec -T airflow airflow dags trigger Extract_Transform_Load_Full_Cycle
	@echo "✓ Gestart. Volg de voortgang in Airflow (Graph-weergave)."

.PHONY: incrementeel
incrementeel: ## Verwerk alleen nieuwe, gewijzigde en verwijderde bronbestanden (DAG Extract_Transform_Load_Incremental)
	$(DC) exec -T airflow airflow dags unpause Extract_Transform_Load_Incremental
	$(DC) exec -T airflow airflow dags trigger Extract_Transform_Load_Incremental
	@echo "✓ Gestart. Volg de voortgang in Airflow (Graph-weergave)."

# ============================================================
# Backup en restore
# ============================================================

.PHONY: backup
backup: ## Backup van PostgreSQL en MongoDB naar de backupmap (Flask en Airflow staan even stil)
	@echo "➜ Backup met tijdstempel $(DT)..."
	$(DC) stop flask airflow
	$(wacht-op-databases)
	$(DC) exec -T -u postgres -w /backup postgres bash -c \
		"pg_dump -v -F t -f postgres_$(DT).tar \$$FLASK_PGDATABASE"
	$(DC) exec -T -w /backup mongo bash -c \
		"mongodump --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$$DB_STAGING?authSource=admin --out mongo_$(DT)"
	$(DC) exec -T -w /backup mongo bash -c \
		"mongodump --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$$DB_FILES?authSource=admin --out mongo_$(DT)"
	$(DC) exec -T -w /backup mongo bash -c \
		"mongodump --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/\$$DB_ANALYSE?authSource=admin --out mongo_$(DT)"
	$(DC) start flask airflow
	@echo "✓ Backup gereed in de backupmap: postgres/postgres_$(DT).tar en mongo/mongo_$(DT)/"

.PHONY: restore
restore: ## Zet een backup terug (gebruik: make restore TS=2026-01-15_10-30-00)
ifndef TS
	$(error Geef een tijdstempel op, bijv: make restore TS=2026-01-15_10-30-00)
endif
	@echo "➜ Backup van $(TS) terugzetten..."
	$(DC) stop flask airflow
	$(wacht-op-databases)
	$(DC) exec -T -u postgres -w /backup postgres bash -c \
		"pg_restore -Ft -c -v -d \$$FLASK_PGDATABASE < postgres_$(TS).tar"
	$(DC) exec -T -w /backup mongo bash -c \
		"mongorestore --drop --uri mongodb://\$$MONGO_INITDB_ROOT_USERNAME:\$$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/?authSource=admin mongo_$(TS)"
	$(DC) start flask airflow
	@echo "✓ Restore gereed."

# ============================================================
# Help
# ============================================================

.PHONY: help
help: ## Toon deze help
	@echo "Wasstraat Archeologische Data — live installatie"
	@echo ""
	@echo "Beschikbare commando's:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
