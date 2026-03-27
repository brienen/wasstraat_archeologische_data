# Sluit-commentaren voor oudere issues

Hieronder per issue het commentaar om te plaatsen bij het sluiten.

---

## #15 — Versies van Records bijhouden

Opgenomen in #61 (Ondersteunen updates / incrementeel laden). De oplossing voor incrementeel laden omvat stabiele sleutels, bestandshash-registratie en upsert-logica, waarmee versiebeheer van records mogelijk wordt. Sluit deze als onderdeel van de bredere aanpak.

---

## #16 — Kwaliteitsattribuut voor alle records

Opgenomen in #62 (Verwerkingsrapport introduceren). Het verwerkingsrapport bevat per objecttype kwaliteitsmeldingen over ontbrekende velden, ongeldige dateringen en onherkenbare patronen. Sluit deze als onderdeel van de rapportage-aanpak.

---

## #22 — Ook Projecten inlezen die wel in de map staan maar niet in DelfIT

Opgenomen in #60 (Delft-specifieke zaken veralgemeniseren) en #57 (Ondersteuning Diverse Sleutelpatronen). De afhankelijkheid van DelfIT als enige projectbron is Delft-specifiek. Met het profielensysteem en de externalisering van Delft-logica wordt dit generiek opgelost. Sluit deze met verwijzing naar #60 en #57.

---

## #26 — DC160 kan niet goed ingelezen worden

Dit is een Delft-specifiek dataprobleem dat wordt afgevangen door de verbeterde error handling (#54) en het verwerkingsrapport (#62). Eventuele correctieregels voor DC160 komen in het Delft-correctiebestand uit #60. Sluit als "won't fix" — wordt via de nieuwe aanpak generiek opgelost.

---

## #35 — Projecten zonder database

Projecten die in DelfIT staan maar geen MDB-bestand hebben worden zichtbaar via het verwerkingsrapport (#62) en de verbeterde error handling (#54). Sluit met verwijzing naar #62 en #54.

---

## #37 — Search aanpassen met voorbeeld gegevens

Wordt opgelost door #58 (Synthetische Voorbeelddata maken). Zodra er synthetische voorbeelddata beschikbaar is, kan de zoekfunctie daarmee gedemonstreerd worden. Sluit met verwijzing naar #58.

---

## #40 — Lijst objectfoto's met Koppeling Onbekend

Foto's met onbekende koppelingen worden zichtbaar via het verwerkingsrapport (#62), dat per objecttype kwaliteitsmeldingen rapporteert. Sluit met verwijzing naar #62.

---

## #46 — Metaalvelden

Dit is een datafout in de mapping van metaalvelden. De correctie hoort thuis in het Delft-correctie/configuratiebestand dat wordt geïntroduceerd in #60 (externalisering Delft-logica). Sluit met verwijzing naar #60.

---

## #47 — Punten Marloes

Issue is bijna 3 jaar oud, heeft geen labels en geen duidelijke beschrijving. Geen activiteit sinds maart 2023. Gesloten als "stale". Mocht dit nog relevant zijn, maak dan een nieuwe issue aan met een duidelijke beschrijving.
