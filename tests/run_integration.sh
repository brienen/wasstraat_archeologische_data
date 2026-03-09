#!/usr/bin/env bash
# =================================================================
# Integratietests voor de Wasstraat
#
# Start de test-databases, draait de integratietests en ruimt op.
#
# Gebruik:
#   ./tests/run_integration.sh
#
# Vereist:
#   - Docker (voor MongoDB + PostgreSQL testcontainers)
#   - Python venv met pytest + pymongo (zie tests/setup_venv.sh)
# =================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"

echo "=== Wasstraat integratietests ==="
echo ""

# --- 0. Controleer venv ---
if [ -f "$VENV_DIR/bin/activate" ]; then
    echo "➜ Venv activeren ($VENV_DIR)..."
    source "$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
    # Windows Git Bash
    echo "➜ Venv activeren ($VENV_DIR)..."
    source "$VENV_DIR/Scripts/activate"
else
    echo "⚠ Geen venv gevonden. Maak er een aan met:"
    echo "    ./tests/setup_venv.sh"
    echo ""
    echo "Ga door met systeem-Python..."
fi

# Controleer of pytest beschikbaar is
if ! python -m pytest --version &>/dev/null; then
    echo "FOUT: pytest niet gevonden. Draai eerst: ./tests/setup_venv.sh"
    exit 1
fi

# --- 1. Start test-databases ---
echo "➜ Test-databases starten..."
docker compose -f "$PROJECT_DIR/docker-compose.test.yml" up -d

echo "➜ Wachten tot MongoDB beschikbaar is..."
for i in $(seq 1 30); do
    if docker exec wasstraat_mongo_test mongosh --eval "db.adminCommand('ping')" \
        -u testroot -p testpass --authenticationDatabase admin \
        --quiet 2>/dev/null | grep -q "ok"; then
        echo "  MongoDB is gereed."
        break
    fi
    # Fallback voor mongo 4.x (geen mongosh)
    if docker exec wasstraat_mongo_test mongo --eval "db.adminCommand('ping')" \
        -u testroot -p testpass --authenticationDatabase admin \
        --quiet 2>/dev/null | grep -q "ok"; then
        echo "  MongoDB is gereed."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  FOUT: MongoDB niet bereikbaar na 30 seconden."
        docker compose -f "$PROJECT_DIR/docker-compose.test.yml" logs mongo-test
        exit 1
    fi
    sleep 1
done

echo "➜ Wachten tot PostgreSQL beschikbaar is..."
for i in $(seq 1 30); do
    if docker exec wasstraat_postgres_test pg_isready -U testuser -d wasstraat_test --quiet 2>/dev/null; then
        echo "  PostgreSQL is gereed."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  FOUT: PostgreSQL niet bereikbaar na 30 seconden."
        docker compose -f "$PROJECT_DIR/docker-compose.test.yml" logs postgres-test
        exit 1
    fi
    sleep 1
done

echo ""

# --- 2. Draai tests ---
echo "➜ Integratietests draaien..."
cd "$PROJECT_DIR"

export MONGO_TEST_URI="mongodb://testroot:testpass@localhost:27117/"
export DB_STAGING="Arch_Staging_Test"
export DB_ANALYSE="Arch_Analyse_Test"
export PYTHONPATH="${PROJECT_DIR}/airflow_app/dags:${PROJECT_DIR}:${PYTHONPATH:-}"

python -m pytest tests/integration/ -v -m integration --tb=short "$@"
TEST_EXIT=$?

echo ""

# --- 3. Opruimen ---
echo "➜ Test-databases stoppen en opruimen..."
docker compose -f "$PROJECT_DIR/docker-compose.test.yml" down -v

echo ""
if [ $TEST_EXIT -eq 0 ]; then
    echo "=== ALLE INTEGRATIETESTS GESLAAGD ==="
else
    echo "=== ER ZIJN INTEGRATIETESTS GEFAALD ==="
fi

exit $TEST_EXIT
