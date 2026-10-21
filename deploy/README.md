# Wasstraat Archeologische Data — live installatie

Deze map bevat alles om de Wasstraat te draaien met de gepubliceerde images van
`ghcr.io/brienen`, zonder de broncode te clonen of iets te bouwen. De rest van de
repository is de ontwikkelomgeving.

```bash
make init          # .env en config/*.env (met gegenereerde wachtwoorden) en de datamappen
# Zet daarna je brondata in data/input/ en controleer .env en wasstraat_config/
make up            # Haal de images op en start alle services
make inloggegevens # Adressen en wachtwoorden van Airflow en de Flask App
```

De volledige handleiding, inclusief eigen data klaarzetten, de eerste verwerking,
bijwerken, backup en restore, staat op
<https://brienen.github.io/wasstraat_archeologische_data/deployment/installatie-met-images/>.

| Bestand of map | Inhoud |
|----------------|--------|
| `docker-compose.yml` | De services, alleen `image:`-regels naar `ghcr.io/brienen/wasstraat-<service>` |
| `.env.example` | Versie, mappen en poorten; kopieer naar `.env` |
| `Makefile` | `make help` toont alle commando's; elk commando is een `docker compose`-aanroep |
| `init-config.sh` | Maakt `config/*.env` aan met unieke wachtwoorden |
| `config/*.env.example` | Sjablonen voor de configuratie van de services |
| `wasstraat_config/` | Harmonisatie-Excel en `correcties.yml` voor de pipeline |
| `data/input/` | Brondata (zie de handleiding voor de mappenstructuur) |
| `data/output/` | Verwerkte media, geserveerd door Apache |
| `data/backup/` | Backups van `make backup` |

Jupyter is een ontwikkelvoorziening van de repository en maakt geen deel uit van de live installatie.
