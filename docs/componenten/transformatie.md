# Transformatie

De transformatie maakt van de ruwe rijen in de staging één samenhangende dataset met sleutels en verwijzingen. Ze bestaat uit vijf taakgroepen in Airflow, die in deze volgorde draaien:

| Volgorde | Taakgroep | Wat | Schrijft |
|----------|-----------|-----|----------|
| 1 | `Transform1_Harmonize_Group` | Harmoniseren: veldnamen van alle bronnen gelijktrekken | `Single_Store` |
| 2 | `Transform2_Enhance_Attributes_Group` | Inhoud opschonen en identificeren | `Single_Store` |
| 3 | `Transform3_Set_Keys_Group` | Samengestelde sleutels | `Single_Store` |
| 4 | `Transform5_Move_And_Merge_Group` | Verplaatsen, samenvoegen, ontbrekende entiteiten aanmaken | `Single_Store_Clean` |
| 5 | `Transform4_Set_References_Group` | Integer-sleutels (`primary_key`) en verwijzingen | `Single_Store_Clean` |

De namen van de taakgroepen zijn ouder dan de volgorde: Transform 5 draait vóór Transform 4. De stappen eromheen en het foutbeleid staan in [Verwerkingspipeline](../architectuur/dataflow.md), de collecties in [MongoDB en Single_Store](singlestore.md) en de configuratie in [Configuratie](configuratie.md).

## Transform 1: harmoniseren

| Taak | Werking |
|------|---------|
| `Controleer_Harmonisatie_Excel` | Geeft een waarschuwing (`configuratie_ongeldig`, in het log en het run-document) voor elke rij in het blad `Objecten` van de harmonisatie-Excel waarvan het object geen soort in `meta.py` is, behalve `Ignore`: zo'n rij harmoniseert niets, en een verouderde rij (zoals de vroegere `Dia`) valt zo op. De run gaat door |
| `FixProjectNames` | Past de `brondata_correcties` uit `correcties.yml` toe op de staging en zet numerieke projectcodes om naar tekst (zie [Configuratie](configuratie.md#31-brondata_correcties)) |
| `fixMonsterProjectcds` | Zet de oude projectcodes van de monsterdatabase om naar de codes uit de projectenlijst |
| `Harmonize_<soort>` | Eén taak per soort uit `meta.py`. Voor de meeste soorten bouwt `harmonizer.py` de aggregatie uit de [harmonisatie-Excel](configuratie.md#4-harmonisatie-excel): welke Access-tabellen bij de soort horen en welke kolom welk veld wordt. Projecten, vindplaatsen, stellingen, standplaatsen, plaatsingen en dozen hebben een vaste pipeline in `meta.py`. Elk document krijgt `soort` en het oorspronkelijke record in `brondata`. Een tabel die meer soorten selecteren, harmoniseert alleen de soort met voorrang (zie [hieronder](#voorrang-bij-een-tabel-die-meer-soorten-selecteren)) |
| `ParseFotobestanden` | Bepaalt voor elk bestand in `Plaatjes` of het een foto, tekening of rapport is, en leidt de nummers af uit de bestandsnaam: via het gemeenteprofiel (`identificeer_foto`, `identificeer_tekening`) en `rapportcode_prefixen` uit `correcties.yml`. Een onherkende naam geeft soort `Bestand`. Een regel in `rapportcode_prefixen` met een onbekend `type` wordt overgeslagen met een waarschuwing `configuratie_ongeldig` (zie [Configuratie](configuratie.md#34-rapportcode_prefixen)) |

Voorbeeld uit de Excel: het putnummer heet in de ene database `PUT` en in de andere `PUTNO`; met `["PUT", "PUTNO"]` op het tabblad van de soort wordt het in beide gevallen het veld `putnr`.

Een kolomlijst wordt een keten van `$ifNull`: de eerste kolom uit de lijst die in de bronrij een waarde heeft, wint. Kolomnamen zijn hoofdlettergevoelig. Een kolomnaam die maar in één tabel voorkomt, zet je achteraan: voor de andere tabellen verandert er dan niets. Zo staan sinds issue 85 op het blad `Artefact` achteraan `Subnummer` (bij `subnr`), `Vondstnummer`, `Putnummer`, `Spoornummer` en `Vlaknummer`: de kolommen van de tabel `Spijkeranalyse Koningsveld` uit DB034 (285 spijkers, als `Metaal` geharmoniseerd via `SPIJKER.*`). Geen andere tabel in de Delftse staging heeft kolommen met die namen (`ONG-lijst` heeft `vondstnummer` met een kleine letter en wordt door geen soort geselecteerd). Met een subnummer worden de spijkers samengevoegd zoals elk artefact met een subnummer: met een ander artefact met hetzelfde project, dezelfde put, vondst en subnummer en dezelfde artefactsoort (in Delft 16 spijkers met een artefact uit de tabel `METAAL`, en 15 spijkers in 6 groepen van 2 tot 4 spijkers met hetzelfde nummer, vooral met vondstnummer 0; 254 spijkers hebben een eigen nummer). Transform 4 vindt de spijkers die eerder zonder subnummer zijn geladen terug op hun hulpsleutel-key (stap 3b in [Incrementeel laden](incrementeel-laden.md#hulpsleutel-uit-de-bronrij-issue-81)).

`harmonizer.py` leest de Excel één keer per taak: `getHarmonizer` en `getHarmonizeAggr` houden het gelezen DataFrame per Excel-pad bij en lezen opnieuw bij `reload=True` of als het bestand sinds het lezen is gewijzigd. Tot issue 87 werd de Excel bij elke aanroep opnieuw gelezen, bij de load (`meta.getVeldnamen`) eenmaal per soort.

### Voorrang bij een tabel die meer soorten selecteren

De taken `Harmonize_<soort>` draaien parallel en schrijven met `$merge` op `_id` (`whenMatched: replace`) naar `Single_Store`. Selecteren de patronen van twee soorten dezelfde Access-tabel, dan won tot issue 89 de taak die het laatst klaar was, en dat verschilde per run. In Delft gebeurde dat met `AW1DeterminatiesJohan`: `Aardewerk` selecteert hem via `AW1.*`, `Artefact` via `Determinaties`. Na de cyclus van 29 oktober 2026 om 17:49 stonden zo 801 aardewerkdeterminaties uit DB034 als `Onbekend` in de webapplicatie, zonder baksel, decoratie en ABR-materiaal, en met een nieuw nummer.

Nu bepaalt elke taak zelf welke tabellen de pipelines op zijn staging-collectie selecteren (`distinct('table', ...)` met de `$match`-fasen van elke pipeline), kiest per tabel die meer pipelines selecteren één soort en slaat in zijn eigen pipeline de tabellen over die een andere soort krijgen (`{$match: {table: {$nin: [...]}}}` vooraan; in de incrementele cyclus na de delta-`$match`). De keuze:

1. de instelling in [`harmonisatie_voorrang`](configuratie.md#36-harmonisatie_voorrang) in `correcties.yml`: tabelnaam → soort, of leeg voor geen enkele soort (codetabellen);
2. anders de voorrangsregel: een specifieke artefactsoort (`Aardewerk`, `Glas`, …) gaat vóór de algemene `Artefact`; verder de volgorde van de soorten in `wasstraat_model` in `meta.py`.

Elke tabel die meer soorten selecteren zonder instelling geeft een waarschuwing `tabel_dubbel_geselecteerd` in het run-document, gemeld door de taak van de gekozen soort; alle besluiten staan in het [verwerkingsrapport](verwerkingsrapport.md). Omdat alle taken dezelfde staging, configuratie en regel gebruiken, nemen ze hetzelfde besluit, in elke volgorde. Alleen pipelines die het `_id` van het staging-document schrijven doen mee (standplaatsen, plaatsingen en dozen maken uit één rij van de magazijnlijst elk een eigen document). De code staat in `wasstraat/harmonisatie_voorrang.py`; per taak kost de bepaling enkele distinct-queries (op de Delftse `Staging_Projecten_Oud` met 22 pipelines ongeveer 2 seconden).

**Codetabellen.** Een lege waarde in `harmonisatie_voorrang` sluit een tabel uit voor elke soort, ook als maar één soort hem selecteert; het besluit staat in het run-document zonder waarschuwing. In Delft geldt dat sinds issue 75 voor de codetabellen `AARDEWERK 1&2 VOORWERP` (kolommen `CODE` en `VOORWERP`, 96 rijen) en `AARDEWERK 1 BAKSEL` (`CODE` en `BAKSEL`, 46 rijen) uit `opgravingDB34.mdb`, die `Aardewerk` via `.*AARDEWERK.*` selecteert. Ze stonden als 142 aardewerkartefacten zonder vondst en zonder subnummer in de webapplicatie. Nu komen ze niet meer in `Single_Store` en `Single_Store_Clean`; in de staging (`Staging_Projecten_Oud`) blijven ze staan als referentiedata. De eerstvolgende volledige cyclus laat hun 142 nummers in `Def_Artefact` vervallen. De Delftse testconfiguratie sluit ze ook uit; de integratietest `test_24b` controleert dat ze in de staging staan en niet in `Single_Store` en `Single_Store_Clean`, `tests/unit/test_harmonisatie_voorrang.py` (klasse `TestCodetabelZonderSoort`) hetzelfde met nagebootste collecties.

## Transform 2: attributen

`Enhance_All_Attributes` (`setAttributes_functions.enhanceAllAttributes`) bewerkt elk document in `Single_Store`:

1. de `projectcode_correcties` uit `correcties.yml`, op de hele collectie;
2. het opschonen van tekstvelden (zoals `typevoorwerp`, `tekeningcd`, `functievoorwerp`, soortnamen);
3. de identificatie door het [gemeenteprofiel](gemeenteprofielen.md): projectcode, tekeningcode en rapportnummer normaliseren (in Delft `dc16` → `DC016`), identificerende nummers omzetten naar getallen, de artefactsoort afleiden;
4. dateringen omzetten naar jaartallen (`vondstdatering_vanaf` en `_tot`, en zo voor spoor en artefact; `archutils.fixDatering` leest onder meer eeuwen en kwarten, Romeinse cijfers en afkortingen van perioden);
5. getallen, ja/nee-velden en datums omzetten;
6. Rijksdriehoek-coördinaten controleren en omrekenen naar WGS84 (zie [Validatie en kwaliteitscontroles](validatie.md#coordinaten));
7. artefacten zonder artefactsoort met een ABR-materiaalcode (veld `materiaalcode`) de artefactsoort geven die bij die code hoort (zie hieronder).

Het gemeenteprofiel wordt één keer per taak geladen, vóór de documenten; een onbekend profiel laat de taak direct falen (de cycli stoppen daar al eerder op, in `Start_Run`). Een document dat niet te verwerken is, blijft ongewijzigd en komt in `_processing_errors`; boven de drempel `AIRFLOW_MAX_VERWERKINGSFOUTEN` / `_PCT` stopt de run. `extract_Imagedata_From_FileNames` vult daarna van foto's de projectcode, het materiaal en de fotosoort aan op basis van hun map, met dezelfde drempel.

**Artefactsoort uit de materiaalcode (issue 86).** Een tabel die de algemene soort `Artefact` harmoniseert (zoals de RAAP-tabel `ARTEFACT` en `Determinaties`), levert geen artefactsoort. Heeft de rij een materiaalcode, dan zoekt `wasstraat/artefactsoort_materiaal.py` de artefactsoort op in de kolommen `ABR-materiaal` en `ABR-submateriaal` van het blad `Objecten` van de harmonisatie-Excel, langs de ABR-thesaurus (de documenten van soort `ABR`). Vanaf het ABR-begrip met de code gaat de zoektocht omhoog naar Materialen; het eerste begrip dat submateriaal (of anders materiaal) van een artefactsoort is, beslist. Is dat één soort, dan is het die (`ODL` Leer, `GLS` Glas, elke steensoort Steen). Delen soorten zonder submateriaal hetzelfde materiaal, dan wint de soort met de naam van het begrip (`MXX` Metaal en `MFE`, `MCU`, `MPB` daaronder: Metaal, niet Munt). Een materiaal dat in de Excel is onderverdeeld (`KER` Keramiek: Aardewerk, Bouwaardewerk of Kleipijp; `OXX` Organisch) is niet eenduidig. Zonder soort kijkt de zoektocht één niveau lager: `OPH` (Hout/Houtskool) heeft `OPHT` (Hout) onder zich en wordt Hout. Een code zonder passende soort (`PYP`, geen ABR-code; `KER`) laat de artefactsoort leeg, zodat het artefact als `Onbekend` wordt geladen; die rijen worden per code geteld en gemeld als waarschuwing `artefactsoort_niet_afgeleid`. De tellingen staan in het run-document onder `tellingen.transform.artefactsoort_uit_materiaalcode`. In Delft gaat het om de 132 rijen van de RAAP-tabel `ARTEFACT`: 66 Leer, 29 Hout, 27 Metaal, 6 Glas en 4 zonder soort (`PYP` en `KER`, elk 2).

## Transform 3: sleutels

`Set_Artefactnr_Unique` bepaalt per project of artefactnummers uniek zijn en of vondstnummers in meer putten voorkomen (vlag `vondstkey_met_putnr`). `mergeRAAPArtefacts` neemt aantal, gewicht en materiaal over uit de `ARTEFACT`-tabellen van RAAP-databases. Daarna geeft `Set_ReferenceKeys_<soort>` elk document zijn sleutels.

De `Set_ReferenceKeys`-taken draaien parallel op dezelfde collectie. Elke taak schrijft daarom alleen de velden die zijn pipeline berekent (de `$addFields`-fasen), niet het hele document, en een soort zonder sleutelpipeline (`Fotokoppel`) doet niets. Tot issue 88 schreef elke taak de documenten volledig terug zoals hij ze had gelezen, en las de lege pipeline van `Fotokoppel` de hele `Single_Store`: afhankelijk van de timing overschreef die taak de net berekende keys van andere soorten met `None` (en de soort van stellingen met `stelling`). Zie [Incrementeel laden](incrementeel-laden.md#verloren-keys-in-transform-3-issue-88).

### Sleutels

Elke entiteit krijgt in Transform 3 (`setReferenceKeys`, pipelines `SET_KEYS_PIPELINES` in `airflow_app/dags/wasstraat/meta.py`) een samengestelde sleutel `key` uit zijn identificerende velden, bijvoorbeeld `PDB034P10V460` voor vondst 460 in put 10 van project DB034, en sleutels naar de entiteiten waarnaar hij verwijst (`key_vondst`, `key_put`, `key_monster`, ...). Transform 4 koppelt op die sleutels (`setReferences`) en kent de integer-sleutels toe (`setPrimaryKeys`, in PostgreSQL `primary_key`).

| Soort | key | Bijzonderheden |
|-------|-----|----------------|
| Project | `P<projectcd>` | |
| Put, Vlak, Spoor, Vulling | `P<project>P<put>[V<vlak>][S<spoor>]...` | Een spoor kan in meer tabellen of databases van een project staan; de key komt dan vaker voor |
| Vondst | `P<project>[P<put>]V<vondst>` | Het putnummer staat erin als het vondstnummer in het project in meer putten voorkomt (vlag `vondstkey_met_putnr`) |
| Artefact | `P<project>[P<put>]V<vondst>A<artefactnr>[S<splitid>]`, samengevoegd op `key_subnr` (zelfde opbouw met het subnummer) en artefactsoort | `key` is meestal leeg (geen artefactnr); in PostgreSQL staat `key_subnr|artefactsoort` in de kolom `key`. Ongeveer twee derde van de Delftse artefacten heeft geen subnummer (determinatietabellen) en dus geen natuurlijke key |
| Monster | `M<monstercd>` | |
| Monster_Botanie, Monster_Schelp | `M<monstercd>ID<Id>` | `Id` is het autonummer van de bronrij; de harmonisatie neemt het niet over, daarom valt Transform 3 terug op `brondata.Id` (Delft) of `brondata.ID` (synthetische data) |
| Standplaats | `S<stelling>V<vak>L<letter>` | Eén document per regel van de magazijnlijst, dus dozen op dezelfde plek hebben dezelfde key |
| Doos | `P<project>D<doos>` | |
| Plaatsing, Vindplaats | geen | |
| Foto, Tekening, Rapport (Bestand) | onder meer `P<project>...S<fotonr>`, `R<rapportnr>` | In PostgreSQL herkend op map en bestandsnaam |

**Hulpsleutel uit de bronrij.** Rijen zonder key of met een key die vaker voorkomt, worden teruggevonden op de identiteit van hun bronrij: `<pad>:<tabel>:<autonummer>` (bijvoorbeeld `projecten/DB034_Koningsveld IV/C Database/opgravingDB34.mdb:AW1DeterminatiesJohan:4`), of een hash van de inhoud als de Access-tabel geen autonummer heeft, en voor een samengevoegd document de lijst van al zijn bronrijen (`delta_transform.getBronsleutel`). Die hulpsleutel wordt afgeleid uit `brondata`, in MongoDB en uit de kolom `brondata` in PostgreSQL. Rijen zonder natuurlijke key krijgen in PostgreSQL een leesbare key met de hulpsleutel (`P<project>[P<put>][V<vondst>]|<artefactsoort>|bron:<hulpsleutel>` voor artefacten, `bron:<hulpsleutel>` voor andere soorten); het veld `key` in MongoDB blijft de natuurlijke key, omdat de verwijzingen daarop koppelen. De natuurlijke key heeft bij het toekennen van de `primary_key` voorrang; de hulpsleutel beslist alleen waar die key ontbreekt of niet uniek is. Zie [Incrementeel laden: hulpsleutel uit de bronrij](incrementeel-laden.md#hulpsleutel-uit-de-bronrij-issue-81) voor de analyse, de dekking en de eerste cyclus op een bestaande installatie.

## Transform 5: verplaatsen en samenvoegen

Transform 5 zet de documenten uit `Single_Store` over naar `Single_Store_Clean`. In de volledige cyclus leegt `Drop_SingleStoreClean` eerst de collectie. Daarna verplaatsen de taken `Move_<soort>` documenten één op één (`merge_functions.moveSoort`), voegen de taken `Merge_<soort>` (Vondst, Artefact, Monster, Tekening, Rapport) documenten met dezelfde sleutel samen (`merge_functions.mergeSoort`), koppelt `MergeFotoinfo` de foto's aan de gegevens uit de fotocatalogus, en maken de taken `Generate_Missing_<soort>` ontbrekende entiteiten aan.

### Verplaatsen en samenvoegen van artefacten

Voor artefacten doen verplaatsen en samenvoegen elk een deel:

| Artefact in `Single_Store` | Stap | Resultaat in `Single_Store_Clean` |
|----------------------------|------|-----------------------------------|
| Met `subnr`, zonder kolom `ARTEFACT` in de bronrij, niet uit een tabel in `ARTEFACT_NOT_MERGE_TABLES` (`ROMEINS AARDEWERK`) en niet uit een project in `artefact_niet_mergen` (`correcties.yml`) | Samenvoegen (`getArtefactMergeVoorwaarde`) | Eén document per `key_subnr` en artefactsoort |
| Alle andere artefacten | Verplaatsen (`getInverseMatchArtefact`) | Eén document per bronrij |

De verplaatsing is precies het complement (`$nor`) van de voorwaarde voor het samenvoegen: elke bronrij komt in één document terecht. Een samengevoegd document heeft de velden van de bronrijen samen (`$mergeObjects`: bij een veld dat in meer bronrijen voorkomt telt de laatste bronrij, ook voor het `_id`), alle bronrijen in `brondata` en hun aantal in `brondata_count`. De artefactsoort wordt vóór het groeperen gelijkgetrokken (leeg, `-` en `onbekend` worden `Onbekend`, spaties aan begin en eind vallen weg; `AGGR_PHASE_ARTEFACTSOORT`), zodat varianten van dezelfde soort bij één `key_subnr` niet als aparte documenten met dezelfde key eindigen.

Zo'n groep kan bestaan uit dezelfde scherf in meer tabellen (Delft DC026: `AARDEWERK 1` en `AARDEWERK 3` met dezelfde inhoud), in kopieën van dezelfde database (DC097: `GLAS`, `LEER`, `HOUT`, `STEEN` en `AARDEWERK 1` in `HHD2.mdb`, `dc79a1.mdb` en `opgravingDC97.mdb`; sinds issue 86 slaat de extractie de tussenversies `HHD2.mdb` en `dc79a1.mdb` over met `paden_overslaan`), in een aparte determinatiedatabase (DB034: `AARDEWERK 1`, `CATALOGUS AW1`, `Huismerken op aardewerk` en `Aardewerk` uit `aardewerk_ivonne_060725.mdb`), of uit meer rijen van één tabel over hetzelfde voorwerp (twee huismerken op één pot). In dat laatste geval (22 groepen met 83 bronrijen in Delft) toont het samengevoegde document de waarden van de laatste rij; de andere rijen staan in `brondata`.

**Tot oktober 2026** had de verplaatsing een eigen lijst met voorwaarden, die ook alle artefacten uit tabellen waarvan de naam niet met `ARTEFACT` begint en alle artefacten zonder artefactsoort verplaatste. Die werden ook samengevoegd; bij een groep van *n* bronrijen bleven daardoor *n* − 1 losse exemplaren naast het samengevoegde document staan, met dezelfde key. In de Delftse productiedata (22 oktober 2026) ging het om 2.433 groepen in DC026, DC097, DB034 en DC093: 3.313 artefacten te veel, die in de webapplicatie en de zoekindex dubbel stonden. In de Delftse testdata (`data/test`) gaat het om 261 groepen van een rij uit `AARDEWERK 1` en een uit `CATALOGUS AW1` (Aardewerk: 4.917 → 4.656, zie de referentie-uitkomst `tests/integration/fixtures/delft_golden_snapshot.json`).

**Eerste volledige cyclus na die wijziging.** De samengevoegde documenten blijven precies zoals ze waren (dezelfde bronrijen, dus dezelfde hulpsleutel), alleen de losse exemplaren vervallen. Transform 4 vindt de samengevoegde artefacten terug op hun hulpsleutel en key; daarna is hun key uniek. Een simulatie op de productie-installatie gaf 29.214 artefacten in plaats van 32.527: geen enkel artefact kreeg een nieuw nummer, 3.313 nummers vervielen. Gebruikersdata op een vervallen exemplaar (bruikleen, conservering) wordt losgekoppeld met een markering en meteen weer gekoppeld aan het samengevoegde artefact, omdat de key in de markering nu uniek is. De incrementele cyclus ruimt de losse exemplaren alleen op voor bestanden in de delta: draai na het bijwerken eerst de volledige cyclus.

**Dubbele keys die blijven.** Artefactkeys komen nu alleen nog dubbel voor bij artefacten die bewust apart blijven (project DC112 uit `artefact_niet_mergen`, 53 artefacten; `ROMEINS AARDEWERK` van DC022, 20) en bij een natuurlijke key (`artefactnr` en `splitid`) die in de brondata zelf dubbel is (DC024 `ARTF_ODL`, 29). De kopieën van de databases van DC024 in de werkmap van Joris (6.663 artefacten die alleen uit die kopieën kwamen) slaat de extractie sinds oktober 2026 over met `paden_overslaan` (zie [Extractie: paden overslaan](extractie.md#paden-overslaan)). De integratietests eisen dat geen artefact met een key uit een merge-groep ook als los document voorkomt (Delft, `test_24a`) en dat in de synthetische data elke key in `Single_Store_Clean` en `Def_Artefact` uniek is (`test_08d`, `test_22d`); `tests/unit/test_merge_artefacten.py` toetst de voorwaarden en bootst verplaatsen en samenvoegen na.

**Tabel `ARTEFACT`.** Tot issue 86 werden de artefacten uit de RAAP-tabel `ARTEFACT` nooit verplaatst (ontwerp van 2022, `ARTEFACT_NOT_MOVE_TABLES`) en kwamen ze niet in `Single_Store_Clean`. Op besluit van de opdrachtgever worden ze nu geladen: ze worden verplaatst zoals elke bronrij met een kolom `ARTEFACT` en krijgen in Transform 2 een artefactsoort uit hun materiaalcode (zie [Transform 2](#transform-2-attributen)). In Delft zijn dat 132 rijen (DC112 103, DC024 28, DC008 1; de 244 rijen uit eerdere tellingen kwamen voor een deel uit de werkmap-kopieën van DC024, die de extractie sinds issue 84 overslaat), met een eigen key `P<project>V<vondst>A<artefactnr>`. In een RAAP-database is `ARTEFACT` de kop van een artefact (artefactnummer, materiaal, totaal aantal en gewicht); de stukken staan in een tabel per materiaal (`ARTF_ODL`, `ARTF_MET`, `ARTF_OPH`, `ARTF_PIJP`, `ARTF_GLS`, `ARTF_KER`, `ARTF_OTE`) met hetzelfde artefactnummer en een `SPLIT_ID`, en `mergeRAAPArtefacts` (Transform 3) zet aantal, gewicht en materiaal van de kop al op die detailrijen. Alle 132 koppen hebben zulke detailrijen (384 in totaal, in hetzelfde bestand). Een artefact uit een RAAP-database staat daardoor twee keer in de webapplicatie: als kop (key zonder `S`) en als stuk(ken) (key met `S<splitid>`); wie artefacten telt, telt de kop en de stukken samen. Dat was de reden voor de uitzondering van 2022.

### Ontbrekende entiteiten aanvullen

Veel opgravingsdatabases hebben geen eigen tabel voor putten of vlakken; die staan alleen als nummer bij sporen, vondsten, tekeningen en foto's. Transform 5 maakt daarom voor elke combinatie die in de data voorkomt een record aan als dat nog niet bestaat:

| Entiteit | Gegenereerd uit | Sleutel |
|----------|-----------------|---------|
| Put | `projectcd` + `putnr` | `P<project>P<put>` |
| Vlak | `projectcd` + `putnr` + `vlaknr` | `P<project>P<put>V<vlak>` |
| Spoor | `projectcd` + `putnr` + `spoornr` | `P<project>P<put>S<spoor>` |
| Vondst | `projectcd` + `putnr` + `vondstnr` | `P<project>[P<put>]V<vondst>` |
| Doos | `projectcd` + `doosnr` van artefacten | `P<project>D<doos>` |

Een gegenereerd record krijgt dezelfde key als een record uit de brondata, zodat alleen echt ontbrekende records worden toegevoegd. Daarom bevat de key van een spoor geen vlak (sporen uit de brondata hebben `vlaknrs`, meervoud) en neemt een gegenereerde vondst de vlag `vondstkey_met_putnr` van de bronrecords over.

Nummer `0` telt niet mee. Gegenereerde records herken je aan `brondata.table` = `generated_put`, `generated_vlak`, enzovoort. Een PUT- of VLAK-tabel in de brondata is dus niet verplicht. Is die er wel, dan gebruikt de pipeline die records (met beschrijving en andere attributen) en genereert alleen wat ontbreekt. De pipelines staan in `meta.py` onder `MOVEANDMERGE_GENERATE_MISSING_PIPELINES`.

## Transform 4: primary_keys en verwijzingen

`Set_PrimaryKey_<soort>` (`references_functions.setPrimaryKeys(stabiel=True)`) geeft elk document in `Single_Store_Clean` een integer-sleutel `ID`, die in PostgreSQL de `primary_key` wordt. Bestaande nummers worden uit PostgreSQL overgenomen: op de `primary_key` uit de bron (ABR), op `_id`, op map en bestandsnaam (bestanden), op een `key` die precies één keer in de tabel staat en daarna op de hulpsleutel uit de bronrij. Sinds issue 89 houdt een rij zonder natuurlijke key (hulpsleutel-key of `key_subnr|artefactsoort`) zijn nummer ook als de artefactsoort in zijn key verandert, bijvoorbeeld door een andere keuze in `harmonisatie_voorrang`. Alleen nieuwe entiteiten krijgen een nummer boven het bestaande maximum. Daardoor blijven links, bruiklenen en de zoekindex geldig, ook na een volledige cyclus. Transform 4 heeft dus in elke DAG een bereikbare PostgreSQL nodig.

Daarna vullen `Set_Reference_<soort>` de verwijzingen (`projectID`, `putID`, `vondstID`, `artefactID`, ...) op basis van de sleutels uit Transform 3, koppelen `Set_Reference_ABR_Materiaal` en `_SubMateriaal` artefacten aan de ABR, en koppelen `Set_Reference_Images_to_Foto1` en `_Foto3` objectfoto's aan hun artefact. Zie [Incrementeel laden](incrementeel-laden.md#uitwerking-in-fase-2) voor de volgorde van het terugvinden en de tellingen.

## Incrementele variant

De incrementele cyclus (`Extract_Transform_Load_Incremental`) gebruikt dezelfde functies en taakgroepen, met `incrementeel=True`. Transform 1 harmoniseert dan alleen de staging-documenten uit nieuwe en gewijzigde bronbestanden en geeft ze het veld `delta_run`; Transform 2 en 3 werken alleen op die documenten (projectbrede stappen op de geraakte projecten). Transform 5 leegt `Single_Store_Clean` niet, maar verplaatst de delta-documenten, voegt alleen de geraakte sleutels opnieuw samen en genereert ontbrekende entiteiten opnieuw voor de geraakte projecten. Transform 4 werkt zoals in de volledige cyclus. De taak `Werk_Geraakte_Projecten_Bij` houdt aan het eind van Transform 1 en 2 bij welke projecten geraakt zijn. Zie [Incrementeel laden](incrementeel-laden.md).

## Losse DAG's per stap

Naast de cycli zijn er DAG's die één stap of een paar stappen draaien, zonder run-document en zonder verwerkingsrapport (overzicht in [Verwerkingspipeline](../architectuur/dataflow.md)). Ze zijn bedoeld om stap voor stap te debuggen: na elke stap kun je de collecties in MongoDB bekijken. De volgorde is die van de volledige cyclus: `Extract_only`, `DAG_Transform1_Harmonize_Only` (leegt `Single_Store` en harmoniseert opnieuw), `DAG_Transform2_Enhance_Attributes_Only`, `DAG_Transform3_Keys_Only`, `DAG_Transform_Move_Only` (leegt `Single_Store_Clean` en vult hem opnieuw), `DAG_Transform4_Refs_Only` en `DAG_Load_Only`.

`DAG_Transform2_Enhance_Attributes_Only` draait alleen Transform 2 op de bestaande `Single_Store`, bijvoorbeeld om een wijziging in het gemeenteprofiel of in `projectcode_correcties` te bekijken. Hij raakt alleen `Single_Store` en `_processing_errors`. Tot issue 87 leegde hij eerst ook `Single_Store_Clean`, een overblijfsel zonder functie (Transform 5 leegt die collectie zelf): daarna had een load niets meer om te laden. Draai na stapsgewijs werken weer de volledige cyclus voordat je de incrementele cyclus gebruikt.

## Configuratie

| Wat | Waar | Zie |
|-----|------|-----|
| Welke tabellen en kolommen bij welke soort horen | Harmonisatie-Excel | [Configuratie: harmonisatie-Excel](configuratie.md#4-harmonisatie-excel) |
| Correcties van brondata en projectcodes, uitzonderingen op het samenvoegen, rapportcodes, voorrang bij een tabel die meer soorten selecteren | `correcties.yml` | [Configuratie: correcties.yml](configuratie.md#3-correctiesyml) |
| Normaliseren van codes en lezen van bestandsnamen | Gemeenteprofiel (`WASSTRAAT_GEMEENTE`) | [Gemeenteprofielen](gemeenteprofielen.md) |
| Drempel op verwerkingsfouten | `AIRFLOW_MAX_VERWERKINGSFOUTEN` en `_PCT` | [Configuratie: Airflow](configuratie.md#23-airflow-airflowenv-airflow_dbenv) |

Na een wijziging in een van deze bestanden draai je de volledige cyclus.
