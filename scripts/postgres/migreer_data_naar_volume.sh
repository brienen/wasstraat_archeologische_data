#!/usr/bin/env bash
#
# migreer_data_naar_volume.sh — Kopieer PostgreSQL-data uit een bestaande
# container naar het Docker-volume (eenmalig, bij bestaande installaties).
#
# Achtergrond: PGDATA stond op /data/postgres, terwijl het volume op
# /var/lib/postgresql/data was gekoppeld. De database stond daardoor in de
# container zelf en ging verloren zodra Docker Compose de container opnieuw
# aanmaakte. Het volume is nu op /data/postgres gekoppeld. Dit script zet de
# bestaande data in het volume, vóórdat de container met de nieuwe
# configuratie opnieuw wordt aangemaakt. De oude container wordt niet gewijzigd.
#
# Gebruik:
#   make stop
#   make migrate-postgres-data                 # of: bash scripts/postgres/migreer_data_naar_volume.sh [container]
#   make app                                   # of: make delft
#

set -euo pipefail

CONTAINER="${1:-wasstraat_postgres}"
OUD_VOLUMEPAD="/var/lib/postgresql/data"
NIEUW_VOLUMEPAD="/data/postgres"

fout() { echo "❌ $*" >&2; exit 1; }

# Geeft de naam van het volume dat op het opgegeven pad in de container hangt
volumeOpPad() {
    docker container inspect -f "{{range .Mounts}}{{if eq .Destination \"$1\"}}{{.Name}}{{end}}{{end}}" "$CONTAINER"
}

# Geeft de waarde van een omgevingsvariabele uit de containerconfiguratie
containerEnv() {
    docker container inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$CONTAINER" | sed -n "s/^$1=//p" | tail -1
}

docker container inspect "$CONTAINER" >/dev/null 2>&1 \
    || fout "Container '$CONTAINER' bestaat niet. Er is niets te migreren."

if [[ "$(docker container inspect -f '{{.State.Running}}' "$CONTAINER")" == "true" ]]; then
    fout "Container '$CONTAINER' draait nog. Stop eerst alle containers met 'make stop'."
fi

if [[ -n "$(volumeOpPad "$NIEUW_VOLUMEPAD")" ]]; then
    echo "✅ '$CONTAINER' gebruikt het volume al op $NIEUW_VOLUMEPAD. Er is niets te migreren."
    exit 0
fi

VOLUME="$(volumeOpPad "$OUD_VOLUMEPAD")"
[[ -n "$VOLUME" ]] || fout "Geen volume gevonden op $OUD_VOLUMEPAD in '$CONTAINER'. Migreer handmatig."

# Het image van de container zelf dient als hulpcontainer: zelfde PostgreSQL-versie en gebruikers
IMAGE="$(docker container inspect -f '{{.Image}}' "$CONTAINER")"
inVolume() {
    docker run --rm -v "$VOLUME:/doel" --entrypoint bash "$IMAGE" -c "$1"
}

if inVolume 'test -f /doel/PG_VERSION'; then
    echo "✅ De data staat al in volume '$VOLUME'. Er is niets te migreren."
    exit 0
fi

BRON="$(containerEnv PGDATA)"
[[ -n "$BRON" ]] || BRON="$(containerEnv DATADIR)"
[[ -n "$BRON" ]] || fout "Kan de datamap van '$CONTAINER' niet bepalen (geen PGDATA of DATADIR). Migreer handmatig."

docker cp "$CONTAINER:$BRON/PG_VERSION" - >/dev/null 2>&1 \
    || fout "Geen PostgreSQL-data gevonden in '$CONTAINER:$BRON'. Er is niets te migreren."

if [[ -n "$(inVolume 'ls -A /doel')" ]]; then
    fout "Volume '$VOLUME' is niet leeg. Migratie afgebroken om niets te overschrijven."
fi

echo "🔧 Kopiëren van $CONTAINER:$BRON naar volume '$VOLUME'..."
docker cp "$CONTAINER:$BRON" - \
    | docker run --rm -i -v "$VOLUME:/doel" --entrypoint tar "$IMAGE" -x --strip-components=1 -C /doel
inVolume 'chown -R postgres:postgres /doel && chmod 750 /doel'

# Controle: evenveel bestanden en mappen in bron en volume
AANTAL_BRON=$(docker cp "$CONTAINER:$BRON" - | tar -t | grep -vcE '^[^/]+/?$' || true)
AANTAL_DOEL=$(inVolume 'find /doel -mindepth 1 | wc -l' | tr -d ' ')
if [[ "$AANTAL_BRON" != "$AANTAL_DOEL" ]]; then
    fout "Controle mislukt: $AANTAL_BRON items in de bron, $AANTAL_DOEL in het volume. Start de containers NIET opnieuw aan; de oude container is ongewijzigd."
fi

echo "✅ Migratie gereed: $AANTAL_DOEL bestanden en mappen staan in volume '$VOLUME'."
echo "   Start nu met 'make app' of 'make delft'. Docker Compose maakt de PostgreSQL-container"
echo "   dan opnieuw aan met het volume op $NIEUW_VOLUMEPAD."
