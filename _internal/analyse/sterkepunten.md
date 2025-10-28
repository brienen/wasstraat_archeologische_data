# Sterke Punten

De Wasstraat beschikt over een aantal fundamentele sterke punten die haar onderscheiden als archeologisch dataverwerkingsplatform:

## Praktische Oorsprong

Het platform is ontstaan uit een echte behoefte: verwerking van meer dan 1000 opgravingen in de gemeente Delft. Dit betekent dat de architectuur direct gericht is op concrete, wereldse problemen in plaats van theoretische idealen. Deze praktische basis heeft geleid tot een systeem dat daadwerkelijk werkt in een operationele omgeving.

## Open Source en Transparantie

De Wasstraat is gepubliceerd onder de EUPL-licentie, wat samenwerking en transparantie faciliteert. Dit maakt het platform geschikt voor:
- Verificatie en audit door externe partijen
- Bijdragen van andere organisaties
- Hergebruik in andere contexten
- Vertrouwen van erfgoedbeheerders

## Format-Agnostisch Ontwerp

Het systeem accepteert diverse invoerformaten zonder strikte vereisten aan de structuur van inkomende data:
- Flexibele inname van XML, JSON, CSV en proprietaire formaten
- Geen noodzaak voor voorafgaande gegevensopschoning
- Adaptatie aan bestaande datastromen in gemeenten

## Behoud van Originele Data

Ruwe data wordt altijd intact bewaard in de centrale dataopslag. Dit zorgt voor:
- Tracering en audit trail
- Mogelijkheid tot herverwerking met nieuwe regels
- Volledige data provenance
- Bescherming tegen ongewenste transformaties

## Polymorf Datamodel via SingleStore

De kern van het systeem is een geavanceerde metadatering-aanpak die via SingleStore diverse gegevensstructuren kan beheren zonder ze naar een strikte schema te dwingen. Dit maakt het platform flexibel voor:
- Heterogene databronnen
- Incrementele schema-evolutie
- Verschillende interpretaties van dezelfde fenomenen
- Coëxistentie van meerdere datamodellen

## Integratie met Gemeentelijk Gegevensmodel

De Wasstraat is niet geïsoleerd, maar ingebed in de bredere informatie-architectuur via integratie met het Gemeentelijk Gegevensmodel (GGM) van Delft. Dit garandeert:
- Samenhang met andere gemeentelijke datasets
- Voldoen aan governance-frameworks
- Hergebruik van standaardiseerde definities
- Interoperabiliteit met lokale systemen

## Cross-Collection Linking

Unieke mogelijkheid om archeologische data te verbinden met andere erfgoeinformatie:
- Monumentenregisters
- Bouwhistorie
- Topografische kaarten
- Andere culturele datasets

Deze verbindingen creëren meerwaarde voor onderzoeks- en beleidsdoeleinden.

## Crossviews Innovatie

Een onderscheidende feature voor het visualiseren van relaties tussen verschillende databronnen. Dit stelt onderzoekers in staat om:
- Inconsistenties tussen bronnen te identificeren
- Validatie uit meerdere invalshoeken uit te voeren
- Complexe relaties te begrijpen
- Data-kwaliteit te verbeteren

## Zelf-Lerende Componenten

Delen van het systeem kunnen zich aanpassen aan patronen in de data:
- Verbeterde generieke verwerking zonder handmatige aanpassingen
- Automatische detectie van gegevenspatronen
- Vermindering van hardcoded Delft-specifieke logica
- Stappensgewijze verbetering van dataomgang

## Fulltext-Zoekfunctionaliteit

Doorzoeken van heterogene data zonder strikte schemastructuur:
- Zoeken op tekstuele content over alle bronnnen heen
- Snelle relevantie-ranking
- Ondersteuning voor complexe zoekvragen
- Gebruiksvriendelijk onderzoeksinterface

## Modulaire Architectuur

Duidelijke scheiding van verantwoordelijkheden:
- **Extractie-laag**: Format-specifieke lezers
- **Transformatie-laag**: Regelgebaseerde verwerking
- **Opslag-laag**: Polyglot persistence (MongoDB, PostgreSQL)
- **Output-laag**: Presentatie en uitvoer

Deze modulariteit bevordert:
- Testbaarheid
- Hergebruik van componenten
- Parallelle ontwikkeling
- Onderhoudbaarheid

## Aansluiting op Nationale Standaarden

Verbinding met nationale erfgoeïnfrastructuur:
- **ABR** (Archeologisch Basis Register): standaardisering van begrippen
- **Archis**: landelijke archeologische database
- Compatibiliteit met CIDOC CRM semantische standaard

Dit zorgt voor integratie in een groter ecosysteem en vermindert isolatie.
