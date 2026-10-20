#!/usr/bin/env bash
# Legt de pakketversies van de Flask- en Jupyter-image vast in services/*/constraints.txt.
#
# Bouwt elke image zonder cache en zonder vaste versies (VASTE_VERSIES=0). Pip kiest dan
# de nieuwste versies binnen requirements.txt (Flask) of de Dockerfile (Jupyter); die
# versies worden weggeschreven. Draai daarna 'make test-all' met opnieuw gebouwde images
# en commit de constraints alleen als alle tests slagen.
#
# Gebruik: bash scripts/leg_pakketversies_vast.sh [flask] [jupyter]   (standaard: beide)

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
    docker run --rm --entrypoint pip "$TAG-flask" list --format=freeze
  } > "$WERKMAP/flask.txt"
  mv "$WERKMAP/flask.txt" services/flask/constraints.txt
  docker image rm "$TAG-flask" > /dev/null
}

legJupyterVast() {
  echo "➜ Jupyter-image bouwen met de nieuwste versies..."
  bouw jupyter "$TAG-jupyter"
  # Alleen wat pip bovenop de (vastgezette) basisimage installeert of wijzigt
  local basis
  basis=$(sed -n 's/^FROM //p' services/jupyter/Dockerfile | head -1)
  docker run --rm --entrypoint pip "$basis" list --format=freeze | LC_ALL=C sort > "$WERKMAP/basis.txt"
  docker run --rm --entrypoint pip "$TAG-jupyter" list --format=freeze | LC_ALL=C sort > "$WERKMAP/jupyter_alles.txt"
  {
    kop Jupyter services/jupyter/Dockerfile
    LC_ALL=C comm -13 "$WERKMAP/basis.txt" "$WERKMAP/jupyter_alles.txt" | sort -f
  } > "$WERKMAP/jupyter.txt"
  mv "$WERKMAP/jupyter.txt" services/jupyter/constraints.txt
  docker image rm "$TAG-jupyter" > /dev/null
}

if [ $# -eq 0 ]; then
  set -- flask jupyter
fi

for image in "$@"; do
  case "$image" in
    flask) legFlaskVast ;;
    jupyter) legJupyterVast ;;
    *) echo "Onbekende image: $image (kies flask of jupyter)" >&2; exit 1 ;;
  esac
done

echo "✓ Versies vastgelegd. Bekijk de wijzigingen met: git diff services/*/constraints.txt"
echo "  Bouw daarna de test-images opnieuw en draai 'make test-all' (zie docs/testen.md)."
