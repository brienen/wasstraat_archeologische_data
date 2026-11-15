#!/usr/bin/env bash
# Legt de pakketversies van de Flask-, Jupyter- en Airflow-image vast in services/*/constraints.txt.
#
# Bouwt elke image zonder cache en zonder vaste versies (VASTE_VERSIES=0). Pip kiest dan
# de nieuwste versies binnen requirements.txt (Flask, Airflow) of de Dockerfile (Jupyter);
# die versies worden weggeschreven. Voor Flask zijn dat alle pakketten. Jupyter en Airflow
# bouwen voort op een basisimage die haar eigen versies vastlegt; daar komt alleen in
# constraints.txt wat pip bovenop de basisimage installeert of wijzigt, zodat de
# constraints nooit botsen met die van de basisimage.
#
# Het script bouwt alleen eigen images (wasstraat-pakketversies-*) en start alleen tijdelijke
# containers (docker run --rm); draaiende installaties blijven ongemoeid.
# Draai daarna 'make test-all' met opnieuw gebouwde images en commit de constraints alleen
# als alle tests slagen.
#
# Gebruik: bash scripts/leg_pakketversies_vast.sh [flask] [jupyter] [airflow]   (standaard: alle drie)

set -euo pipefail
cd "$(dirname "$0")/.."

TAG=wasstraat-pakketversies
WERKMAP=$(mktemp -d)
trap 'rm -rf "$WERKMAP"' EXIT

kop() {
  # Kopregels voor een constraints-bestand. Args: $1 = image, $2 = waar de grenzen staan
  echo "# Vastgelegde pakketversies voor de $1-image (pip constraints)."
  echo "# Gegenereerd met 'make constraints' op $(date +%Y-%m-%d); niet met de hand bijwerken."
  echo "# De grenzen van de directe pakketten staan in $2."
}

pipFreeze() {
  # Geeft de geïnstalleerde pakketversies van een image. Args: $1 = image
  # Via 'python -m pip': in de Airflow-image vindt Docker voor 'pip' eerst /root/bin/pip,
  # dat de gebruiker airflow niet mag uitvoeren.
  docker run --rm --entrypoint python "$1" -m pip list --format=freeze
}

bouw() {
  # Bouwt een image zonder vaste versies. Args: $1 = service, $2 = tag
  touch "services/$1/constraints.txt"
  docker build --no-cache --pull --build-arg VASTE_VERSIES=0 \
    -f "services/$1/Dockerfile" -t "$2" .
}

legFlaskVast() {
  echo "➜ Flask-image bouwen met de nieuwste versies..."
  bouw flask "$TAG-flask"
  {
    kop Flask services/flask/requirements.txt
    pipFreeze "$TAG-flask"
  } > "$WERKMAP/flask.txt"
  mv "$WERKMAP/flask.txt" services/flask/constraints.txt
  docker image rm "$TAG-flask" > /dev/null
}

legVastBovenopBasis() {
  # Legt alleen vast wat pip bovenop de basisimage (de eerste FROM) installeert of wijzigt.
  # Args: $1 = service, $2 = naam in de kopregels, $3 = waar de grenzen staan
  echo "➜ $2-image bouwen met de nieuwste versies..."
  bouw "$1" "$TAG-$1"
  local basis
  basis=$(sed -n 's/^FROM //p' "services/$1/Dockerfile" | head -1)
  pipFreeze "$basis" | LC_ALL=C sort > "$WERKMAP/basis.txt"
  pipFreeze "$TAG-$1" | LC_ALL=C sort > "$WERKMAP/$1_alles.txt"
  {
    kop "$2" "$3"
    LC_ALL=C comm -13 "$WERKMAP/basis.txt" "$WERKMAP/$1_alles.txt" | sort -f
  } > "$WERKMAP/$1.txt"
  mv "$WERKMAP/$1.txt" "services/$1/constraints.txt"
  docker image rm "$TAG-$1" > /dev/null
}

legJupyterVast() {
  legVastBovenopBasis jupyter Jupyter services/jupyter/Dockerfile
}

legAirflowVast() {
  legVastBovenopBasis airflow Airflow services/airflow/requirements.txt
}

if [ $# -eq 0 ]; then
  set -- flask jupyter airflow
fi

for image in "$@"; do
  case "$image" in
    flask) legFlaskVast ;;
    jupyter) legJupyterVast ;;
    airflow) legAirflowVast ;;
    *) echo "Onbekende image: $image (kies flask, jupyter of airflow)" >&2; exit 1 ;;
  esac
done

echo "✓ Versies vastgelegd. Bekijk de wijzigingen met: git diff services/*/constraints.txt"
echo "  Bouw daarna de test-images opnieuw en draai 'make test-all' (zie docs/testen.md)."
