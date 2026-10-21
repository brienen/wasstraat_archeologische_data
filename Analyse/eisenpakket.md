# Eisenpakket Wasstraat — afspraken, eisen en stand van zaken

Laatst bijgewerkt: 2026-10-21 (Apache als voordeur gepubliceerd; Delftse testomgeving met mediavolume op schijf en eigen Elasticsearch; GitHub-issues bijgewerkt). Dit document bundelt de afspraken en eisen die in de sessies van 20 en 21 oktober 2026 zijn uitgesproken, plus de stand van zaken en de bekende vervolgpunten. Het is het geheugen voor volgende sessies: CLAUDE.md verwijst ernaar en vraagt om het bij te houden. De map `Analyse/` staat in `.gitignore`, maar dit bestand is daarvan uitgezonderd en staat in de repo.

## 1. Werkafspraken

- **Geen commits en geen pushes door Claude.** Werk wordt hooguit voorbereid: wijzigingen stagen, commitbericht in `.git/WASSTRAAT_COMMIT_MSG`, en de commando's `git commit -F .git/WASSTRAAT_COMMIT_MSG` en `git push` in losse codeblokken. De gebruiker voert ze zelf uit.
- **Commitberichten zonder verwijzing naar Claude:** geen Co-Authored-By-regel, geen vermelding in de tekst, geen bestandsnaam `CLAUDE.md` erin. Commits gaan onder de naam van de gebruiker.
- **Werk in de huidige branch** (`Paths_Names_Restructure`), geen nieuwe branches. Alles belandt in de hoofdmap, niet in worktrees; parallelle sessies leveren patches of werken in disjuncte bestanden.
- **Nederlands** in code-commentaar, docstrings, documentatie en commitberichten; camelCase-functies, geen type hints (CLAUDE.md).
- **De echte installatie beschermen.** De containers `wasstraat_*` (zonder `_test`) zijn de productie-installatie van de gebruiker. Tests draaien uitsluitend via `docker compose -p wasstraat-test -f docker-compose.test.yml` of `-p wasstraat-delft-test -f docker-compose.delft-test.yml`, met het slot `/tmp/wasstraat-docker.lock` als meerdere sessies Docker gebruiken. Nooit `make app`, `make delft`, `make down`, `make stop` of `make start` vanuit een sessie.
- **Na wijzigingen altijd `make test-all`** (unit + integratie), en bij wijzigingen die de Delftse uitvoer raken ook `make integration-delft` met een opnieuw vastgelegde referentie-uitkomst (`tests/integration/fixtures/delft_golden_snapshot.json`), met uitleg per verschil.
- **Autonoom werken** als de gebruiker dat vraagt: fasen door agents laten uitvoeren, elke fase zelf reviewen (codereview + tests), zonder tussenvragen; het resultaat gestaged klaarzetten.

## 2. Producteisen

### 2.1 Installeerbaar op een schone omgeving

- Een verse kloon moet met `make app` werken zonder verborgen afhankelijkheden. Vereisten staan in README en `docs/aan-de-slag.md`: Docker, GNU Make en bash (macOS: Xcode Command Line Tools), Windows via WSL 2, Python 3.10 t/m 3.12 alleen voor de tests.
- Pakketversies van de Flask- en Jupyter-image liggen vast in `services/*/constraints.txt`; bijwerken met `make constraints`.
- Alle wachtwoorden worden gegenereerd door `init-config.sh`, inclusief de Flask-beheerder (`FLASK_ADMIN_PASSWORD`) en het Jupyter-token.
- PostgreSQL-data staat in het Docker-volume (`PGDATA` en volume beide op `/data/postgres`). Oude installaties migreren met `make migrate-postgres-data`.
- De documentatie beschrijft de werkelijke stack en de werkelijke DAG-namen; verouderde doelen (`make prod`, `make acc`, `make example`) zijn verwijderd.

### 2.2 Incrementeel laden (issue 61)

Ontwerp en status: `docs/componenten/incrementeel-laden.md`.

- DAG `Extract_Transform_Load_Incremental` verwerkt alleen nieuwe, gewijzigde en verwijderde bronbestanden; de volledige cyclus blijft bestaan.
- Registratie van bronbestanden in PostgreSQL (`Def_Bronbestand`, vingerafdruk grootte/mtime/sha256); run-document in MongoDB (`Verwerkingsruns`), één actieve run tegelijk.
- MongoDB blijft staan als werkgeheugen; geraakte entiteiten worden opnieuw samengesteld uit `Single_Store`.
- Stabiele `primary_key`s: bestaande nummers uit PostgreSQL worden hergebruikt (artefacten via `key_subnr|artefactsoort` in de kolom `key`).
- Load als upsert met verwijderen van verdwenen rijen; gebruikerstabellen (bruiklenen, conservering) blijven staan. Elasticsearch per tabel bijgewerkt.
- Ingebruikname: eerst één volledige cyclus (registratie van alle bestanden, sha256 over alle data, artefactsleutels), daarna incrementeel. Na wijzigingen in de harmonisatie-Excel, `correcties.yml`, het gemeenteprofiel of de pipelinecode opnieuw de volledige cyclus.

### 2.3 Publicatie en live-installatie

- `make publish` bouwt de images airflow, flask, postgres en apache multi-arch (amd64 + arm64) en pusht ze naar `ghcr.io/brienen/wasstraat-<service>` met de versie uit `config/version.env` en `latest`. Vooraf `docker login ghcr.io` met een classic personal access token met scope `write:packages`. `make release` legt de versie vast, commit, tagt, pusht en publiceert.
- De map `deploy/` is de live-installatie voor andere gemeenten: een compose die volledig op de gepubliceerde images draait (geen build, geen broncode-volumes), een eigen Makefile (init, up, update, backup, restore, cycli), configuratiesjablonen en de harmonisatie-Excel. Handleiding: `docs/deployment/installatie-met-images.md`.
- **Jupyter hoort niet in de publicatieversie.** Het blijft een ontwikkelvoorziening in de repo.
- Deze repository is daarmee uitsluitend de ontwikkelomgeving.
- **Apache is de voordeur (eis van 2026-10-21).** Apache serveert de bestanden onder `/archeomedia` zelf uit de uitvoermap en stuurt alle overige verzoeken door naar Flask (reverse proxy). Flask bevat alleen de logica en de links naar de bestanden en staat achter Apache; Flask hoeft geen eigen hostpoort te hebben. De webapplicatie verwijst naar afbeeldingen met relatieve paden `/archeomedia/...`, dus zonder deze opzet blijven foto's leeg. Dit geldt voor de ontwikkelomgeving en voor `deploy/`. Gerealiseerd op 2026-10-21: poort 5052 is het adres van de webapplicatie, Flask heeft geen hostpoort meer (alleen `make dev` opent 5051 voor debuggen), `WASSTRAAT_PORT_FLASK` is uit `deploy/.env.example` verdwenen, en de testomgevingen hebben een `apache-test` als voordeur van de smoke tests. Uitwerking: CLAUDE.md (sectie Publicatie en live installatie) en `docs/deployment/omgevingen.md`.
- Packages op GitHub staan na de eerste publicatie standaard privé; de gebruiker zet ze zelf op Public (github.com/brienen, tabblad Packages).

## 3. Stand van zaken op 2026-10-21

| Onderwerp | Stand |
|---|---|
| Schone installatie | Gefixt en gecommit (`47aad92`) |
| Incrementeel laden | Gebouwd, getest en gecommit (`b76f6af`) |
| Fotokoppeling Transform 2 | Gefixt en gecommit (`81efba3`); de laadstap las `artefactID` daarna nog niet voor alle rijen (steekproef van tien documenten), gefixt op 2026-10-21 met tests |
| Eigen installatie van de gebruiker | Volledige cyclus gedraaid op 2026-10-21 (9.600 bronbestanden geregistreerd); na de laadstap-fix 1.232 foto's gekoppeld aan 430 artefacten, lijst "Artefacten met foto" gevuld |
| `make publish` en `deploy/` | Gebouwd en gecommit (`81efba3`); versie 1.0.1 gepubliceerd op ghcr.io, op 2026-10-21 (middag) opnieuw gepubliceerd onder 1.0.1 inclusief Apache als voordeur en de laadstap-fix |
| Apache als voordeur | Gebouwd, getest en gecommit (`f5fb594`); eigen installatie opnieuw gebouwd en gestart (webapplicatie op poort 5052, 5051 dicht); images opnieuw gepubliceerd als 1.0.1 |
| Delftse referentie-uitkomst | Opnieuw vastgelegd na kopregel-fix (+50 munten), &-fix (+96 aardewerk) en fotokoppeling (Put 275, Vondst 3060) |
| Delftse testomgeving met Elasticsearch | Toegevoegd op 2026-10-21 (`elasticsearch-test`, container `wasstraat_elasticsearch_delft_test`): `DAG_Load_Only` moet er volledig slagen en een test vergelijkt per tabel Elasticsearch met PostgreSQL |
| Delftse testomgeving | Het tmpfs-mediavolume van 4 GB uit de Apache-wijziging liep vol (rapporten circa 5 GB), waardoor 93 van de 541 bestanden stil onverwerkt bleven; op 2026-10-21 vervangen door een schijfvolume op `/output/archeomedia` (map in de Airflow-image), met een grens op onverwerkte bestanden in de Delftse extractietest |

Uitvoeringsplan v2 (maart 2026): #61 (incrementeel laden) is uitgevoerd en op 2026-10-21 gesloten; #57 (profielensysteem) bleek al in maart gerealiseerd (commit 8b88c73) en is eveneens gesloten. #54 (foutafhandeling), #62 (verwerkingsrapport) en #64 (technische documentatie) staan open met een stand-van-zakenreactie van 2026-10-21; #63 en #65 (documentatie) staan ongewijzigd open. Het plan in Obsidian en in `Analyse/wasstraat-v2-plan.md` beschrijft nog de stand van maart. De bekende beperkingen hieronder zijn op 2026-10-21 als GitHub-issues #70 t/m #80 vastgelegd; nieuwe punten horen daar ook als issue.

## 4. Bekende beperkingen en vervolgpunten

- **Lockduur van de upsert (#79):** elke incrementele run vergelijkt alle rijen van alle tabellen onder exclusieve locks; bij Delft naar schatting minuten (niet gemeten). Draai buiten kantooruren of beperk de upsert later tot de delta.
- **Volledige cyclus (#71)** nummert de sleutels opnieuw en leegt bruiklenen en conservering; alleen de incrementele cyclus bewaart die.
- **Afgeleide velden (#72)** van de webapplicatie (aantal foto's, dateringen) worden na een incrementele run niet herberekend.
- **Bruikleen van een verdwenen artefact (#73)** blijft staan; de FK blijft dan ongeldig en wordt in het run-document gemeld.
- **Tekstvelden met een regeleinde (#74)** krijgen in de staging de extra kolommen midden in het veld (bestaande beperking van de export per regel).
- **Codetabellen (#75)** zoals "AARDEWERK 1&2 VOORWERP" en "AARDEWERK 1 BAKSEL" worden als aardewerk geharmoniseerd; configuratievraag voor de harmonisatie-Excel.
- **Standplaatsen (#76)** houden projectcode "DB34"; de identificatie laat de projectcode daar bewust ongemoeid.
- **Databaseverbinding inclusief wachtwoord in het log (#77)**, in `shared/database.py` en `shared/fulltext.py`.
- **Jupyter-image (#78)** mist het pakket `roman` en heeft een Elasticsearch-client 9.x bij een server 8.17.
- **Airflow-image (#80):** de extra pakketten liggen nog niet vast; apt-retries in de Dockerfiles zouden verse builds robuuster maken.
- **Documentatie (#64):** architectuurdiagrammen en hun tekst noemen nog Django, Vue en Oracle; het advies over schrijfrechten op Linux is niet getest; de Delftse Flask-test voor de projectlijst slaat zichzelf over (login nodig).
- **Docker-onderhoud:** vier oude testvolumes van `wasstraat-test` kunnen weg.
- **Extractie slikt fouten bij afbeeldingen in (#70):** mislukte bestanden blijven stil op `processed: False`; ontdekt bij het volle mediavolume op 2026-10-21.

## 5. Vindplaatsen

- Ontwerp incrementeel laden: `docs/componenten/incrementeel-laden.md`
- Installatie met images: `docs/deployment/installatie-met-images.md`, `deploy/README.md`
- Omgevingen, publicatie, migratie: `docs/deployment/omgevingen.md`
- Testen: `docs/testen.md`
- Projectnotities en vergaderingen: Obsidian `01_Projects/Wasstraat/`
- Open issues: `gh issue list --repo brienen/wasstraat_archeologische_data`
