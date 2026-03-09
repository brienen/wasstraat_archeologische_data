#!/usr/bin/env bash
# =================================================================
# Maak een Python venv aan voor het draaien van de Wasstraat tests.
#
# Gebruik:
#   ./tests/setup_venv.sh          # maakt .venv aan
#   source .venv/bin/activate      # activeer de venv
#   python -m pytest tests/unit/ -v
# =================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv"

# Zoek Python 3.11+ (of val terug op python3)
PYTHON=""
for candidate in python3.11 python3.12 python3.10 python3; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "FOUT: Geen Python 3 gevonden. Installeer Python 3.11+ eerst."
    exit 1
fi

echo "=== Wasstraat test-omgeving instellen ==="
echo "Python: $($PYTHON --version)"
echo "Venv:   $VENV_DIR"
echo ""

# --- Maak venv aan als die nog niet bestaat ---
if [ ! -d "$VENV_DIR" ]; then
    echo "➜ Venv aanmaken..."
    $PYTHON -m venv "$VENV_DIR"
else
    echo "➜ Venv bestaat al, dependencies updaten..."
fi

# --- Activeer en installeer ---
source "$VENV_DIR/bin/activate"

echo "➜ pip upgraden..."
pip install --upgrade pip --quiet

echo "➜ Test-dependencies installeren..."
pip install -r "$PROJECT_DIR/requirements-test.txt" --quiet

echo ""
echo "=== Venv is gereed ==="
echo ""
echo "Activeer met:"
echo "  source .venv/bin/activate"
echo ""
echo "Unit tests draaien:"
echo "  python -m pytest tests/unit/ -v"
echo ""
echo "Integratietests draaien:"
echo "  ./tests/run_integration.sh"
