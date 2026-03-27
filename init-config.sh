#!/usr/bin/env bash
#
# init-config.sh — Genereer config/*.env bestanden uit .env.example templates
#
# Dit script wordt automatisch aangeroepen door de Makefile als er nog geen
# .env bestanden bestaan. Het genereert unieke, willekeurige wachtwoorden
# zodat elke installatie eigen credentials heeft.
#
# Gebruik:
#   ./init-config.sh          # Genereer alleen ontbrekende .env bestanden
#   ./init-config.sh --force  # Overschrijf alle .env bestanden (let op!)
#

set -euo pipefail

CONFIG_DIR="$(cd "$(dirname "$0")" && pwd)/config"
FORCE=false

if [[ "${1:-}" == "--force" ]]; then
    FORCE=true
    echo "⚠️  Force-modus: alle .env bestanden worden opnieuw gegenereerd!"
fi

# --- Wachtwoord generator ---
generate_password() {
    # 24 karakters, alfanumeriek (veilig voor gebruik in URLs en env vars)
    local pw
    pw=$(dd if=/dev/urandom bs=256 count=1 2>/dev/null | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c 24)
    printf '%s' "$pw"
}

# --- Controleer of er iets te doen is ---
MISSING=0
for example in "$CONFIG_DIR"/*.env.example; do
    target="${example%.example}"
    if [[ ! -f "$target" ]]; then
        MISSING=$((MISSING + 1))
    fi
done

if [[ "$FORCE" == "false" && "$MISSING" -eq 0 ]]; then
    # Alle .env bestanden bestaan al, niets te doen
    exit 0
fi

echo "🔧 Configuratie initialiseren..."

# --- Genereer consistente wachtwoorden ---
# Deze wachtwoorden worden gedeeld tussen meerdere .env bestanden
PW_POSTGRES=$(generate_password)
PW_FLASK_DB=$(generate_password)
PW_MONGO=$(generate_password)
PW_REDIS=$(generate_password)
PW_JUPYTER=$(generate_password)
PW_FLASK_SECRET=$(generate_password)
PW_AIRFLOW_ADMIN=$(generate_password)

# --- Vervang placeholders in elk .env.example bestand ---
process_example() {
    local example="$1"
    local target="${example%.example}"
    local filename
    filename=$(basename "$target")

    if [[ "$FORCE" == "false" && -f "$target" ]]; then
        echo "  ⏭️  $filename bestaat al, overgeslagen"
        return
    fi

    # Kopieer example als basis
    cp "$example" "$target"

    # Vervang placeholder-wachtwoorden op basis van het bestand
    # Portable sed in-place: werkt op zowel macOS (BSD sed) als Linux (GNU sed)
    _sed_inplace() { sed -i.bak "$@" && rm -f "${@: -1}.bak"; }

    case "$filename" in
        postgres.env)
            _sed_inplace "s/airflow_secret_42/$PW_POSTGRES/g" "$target"
            _sed_inplace "s/flask_secret_42/$PW_FLASK_DB/g" "$target"
            ;;
        airflow_db.env)
            _sed_inplace "s/airflow_secret_42/$PW_POSTGRES/g" "$target"
            ;;
        mongo.env)
            _sed_inplace "s/mongo_secret_42/$PW_MONGO/g" "$target"
            ;;
        redis.env)
            _sed_inplace "s/redis_secret_42/$PW_REDIS/g" "$target"
            ;;
        flask.env)
            _sed_inplace "s/wijzig_deze_geheime_sleutel/$PW_FLASK_SECRET/g" "$target"
            ;;
        airflow.env)
            _sed_inplace "s/SECURITY__ADMIN_PASSWORD=admin/SECURITY__ADMIN_PASSWORD=$PW_AIRFLOW_ADMIN/g" "$target"
            ;;
        jupyter.env)
            _sed_inplace "s/jupyter_secret_42/$PW_JUPYTER/g" "$target"
            ;;
        # elasticsearch.env en version.env hebben geen wachtwoorden
    esac

    echo "  ✅ $filename aangemaakt"
}

for example in "$CONFIG_DIR"/*.env.example; do
    process_example "$example"
done

echo ""
echo "✅ Configuratie gereed! Gegenereerde credentials:"
echo "   PostgreSQL (airflow):  $PW_POSTGRES"
echo "   PostgreSQL (flask):    $PW_FLASK_DB"
echo "   MongoDB:               $PW_MONGO"
echo "   Redis:                 $PW_REDIS"
echo "   Jupyter:               $PW_JUPYTER"
echo "   Airflow admin:         $PW_AIRFLOW_ADMIN"
echo "   Flask secret key:      $PW_FLASK_SECRET"
echo ""
echo "💡 Bewaar deze wachtwoorden of bekijk ze in config/*.env"
echo "   Om opnieuw te genereren: ./init-config.sh --force"
