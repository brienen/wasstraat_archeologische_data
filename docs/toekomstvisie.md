# Toekomstvisie

!!! warning "Geen beschrijving van de huidige software"
    Deze pagina beschrijft ideeën en ambities voor de verdere ontwikkeling van de Wasstraat. Niets op deze pagina bestaat nu in de code. Wat de Wasstraat vandaag doet, staat in [Architectuur](architectuur/systeem.md), de componentpagina's en [Configuratie](componenten/configuratie.md).

De Wasstraat is gebouwd voor de gemeente Delft en wordt via het innovatieproject van Stichting Reuvens uitgebreid tot een generiek systeem voor andere Nederlandse gemeenten. De ideeën hieronder komen uit het oorspronkelijke ontwerp en uit die uitbreiding.

## Generiek en configureerbaar

**Nu:** tabel- en kolomnamen staan in de harmonisatie-Excel, gemeente-specifieke correcties in `correcties.yml`, en de logica die daar niet in past in een gemeenteprofiel in Python. Een nieuwe artefactsoort of een nieuw objecttype vraagt een codewijziging.

**Ambitie:**

- nieuwe objecttypen en artefactsoorten volledig vanuit de configuratie, zonder wijziging van `meta.py` en `models.py`;
- gemeenteprofielen als configuratie in plaats van Python-klassen, voor de gangbare patronen van bestandsnamen en codes;
- een beheerscherm in de webapplicatie voor de configuratie, met validatie vóór een run, in plaats van het bewerken van Excel- en YAML-bestanden;
- bronnen in andere formaten dan Access en Excel (CSV, XML, GIS-bestanden) via dezelfde stappen.

## Crossviews

Een onderdeel om verbanden tussen bronnen zichtbaar te maken: overeenkomende records uit verschillende databases herkennen (dezelfde vondst in een opgravingsdatabase en een determinatiedatabase), tegenstrijdigheden tussen bronnen tonen en de beheerder laten beslissen over samenvoegen. Op termijn met lerende algoritmen die voorstellen doen op basis van eerder bevestigde koppelingen.

**Nu:** het samenvoegen gebeurt met vaste regels op sleutels (`key`, en bij artefacten `key_subnr` en artefactsoort) in Transform 5; uitzonderingen staan in `artefact_niet_mergen` en kopieën worden uitgesloten met `paden_overslaan` (zie [Transformatie](componenten/transformatie.md#verplaatsen-en-samenvoegen-van-artefacten)).

## Validatie met regels

Een validatielaag waarin per gemeente regels voor de inhoud worden vastgelegd (een datering moet binnen een periode vallen, een diepte binnen redelijke grenzen, een code in de ABR voorkomen), met een rapport van overtredingen per run en een scherm om ze af te handelen.

**Nu:** de pipeline controleert coördinaten, telt records die niet te verwerken zijn, onleesbare databases en mislukte afbeeldingen, en legt dat vast in het verwerkingsrapport (zie [Validatie en kwaliteitscontroles](componenten/validatie.md)).

## Semantisch model en Linked Open Data

Het gegevensmodel uitdrukken in de CIDOC CRM-familie (CRMarchaeo voor opgravingen en contexten, CRMsci voor analyses en dateringen) en aansluiten op het Gemeentelijk Gegevensmodel (GGM), zodat de data als Linked Open Data te publiceren is, met URI's per entiteit en verwijzingen naar externe thesauri. Het [semantische model](diagrammen.md#toekomstbeeld-semantisch-model) schetst die inbedding.

**Nu:** het gegevensmodel is een eigen relationeel model in PostgreSQL (zie [Gegevensmodel](architectuur/gegevensmodel.md)). Van de standaarden wordt alleen de ABR-thesaurus gebruikt: artefacten verwijzen naar ABR-materialen.

## Ontsluiting en uitwisseling

- Export naar DANS e-Depot en aansluiting op Archis.
- Geo-services (WMS/WFS) en GeoJSON-exports op basis van PostGIS.
- Rapportages en analyses buiten de webapplicatie (een datawarehouse of BI-koppeling).
- Een uitgebreidere publieke API dan de huidige endpoints onder `/api/v1/`.

## Zoeken

Zoeken dat beter omgaat met onnauwkeurige termen: synoniemen uit de ABR-thesaurus, spellingsvarianten en historische schrijfwijzen, en zoeken op periode en locatie als facetten.

**Nu:** de webapplicatie zoekt per tabel in Elasticsearch met een `query_string`-query over de tekstkolommen (zie [Zoeken en indexering](componenten/zoeken.md)).

## Beheer van runs

- Het verwerkingsrapport tonen in de webapplicatie, met een overzicht van alle runs uit `Verwerkingsruns`.
- Een opschoonbeleid voor oude rapporten en run-documenten.
- Het kantelen van foto's blijvend maken, zodat een volledige cyclus het niet terugdraait.

Openstaande punten en bekende beperkingen worden bijgehouden als issues op [GitHub](https://github.com/brienen/wasstraat_archeologische_data/issues).
