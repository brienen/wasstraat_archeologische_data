#!/usr/bin/env python3
"""Genereer de architectuurdiagrammen van de documentatie als SVG.

De diagrammen beschrijven de werkelijke opbouw van de Wasstraat (Apache als voordeur,
Flask, Airflow, PostgreSQL met PostGIS, MongoDB, Elasticsearch, Redis). Ze worden
met de hand opgemaakt in dit script, zodat een wijziging in de architectuur een
wijziging in de tekst hieronder is en de SVG's daarna opnieuw gemaakt kunnen worden:

    python3 docs/assets/diagrams/genereer_diagrammen.py

Het script gebruikt alleen de standaardbibliotheek en schrijft naar
docs/assets/images/: systeem-architectuur.svg, dataflow-pipeline.svg,
componenten-model.svg en gegevensmodel.svg. Na het schrijven controleert het of
elk bestand geldige XML is.
"""
import os
import xml.dom.minidom
from xml.sax.saxutils import escape

UITVOERMAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'images')

LETTERTYPE = "Lato, 'Helvetica Neue', Arial, sans-serif"

# Kleuren per soort onderdeel (vulling, rand)
KLEUREN = {
    'verwerking': ('#e9f7ef', '#1e8449'),   # pipeline, Airflow
    'opslag': ('#fdf2e9', '#ba4a00'),       # databases
    'web': ('#eaf2fb', '#2471a3'),          # Apache, Flask, browser
    'host': ('#fef9e7', '#9a7d0a'),         # bestanden en configuratie op de host
    'gebruiker': ('#f4f6f7', '#566573'),    # mensen en externe partijen
    'beheer': ('#f5eef8', '#7d3c98'),       # run-document, foutbeleid, gebruikersdata
    'kader': ('#ffffff', '#99a3a4'),        # groepskader
    'tabel': ('#eaf2fb', '#2471a3'),        # tabel van de pipeline
    'gebruikerstabel': ('#f5eef8', '#7d3c98'),
    'koppeltabel': ('#fbf7fc', '#7d3c98'),
    'administratie': ('#f2f3f4', '#707b7c'),
}


class Diagram:
    """Eenvoudige opbouw van een SVG met kaders, teksten en pijlen."""

    def __init__(self, breedte, hoogte, titel):
        self.breedte = breedte
        self.hoogte = hoogte
        self.titel = titel
        self.delen = []

    def kader(self, x, y, b, h, soort, titel=None, regels=(), gestippeld=False, titelgrootte=13,
              afgerond=8, uitlijning='midden'):
        vul, rand = KLEUREN[soort]
        streep = ' stroke-dasharray="6 4"' if gestippeld else ''
        self.delen.append(
            f'<rect x="{x}" y="{y}" width="{b}" height="{h}" rx="{afgerond}" ry="{afgerond}" '
            f'fill="{vul}" stroke="{rand}" stroke-width="1.6"{streep}/>')
        tx = x + b / 2 if uitlijning == 'midden' else x + 10
        anker = 'middle' if uitlijning == 'midden' else 'start'
        ty = y + 20
        if titel:
            self.delen.append(
                f'<text x="{tx}" y="{ty}" text-anchor="{anker}" font-size="{titelgrootte}" '
                f'font-weight="bold" fill="#1c2833">{escape(titel)}</text>')
            ty += 17
        for regel in regels:
            code = regel.startswith('`')
            tekst = regel.replace('`', '')
            familie = ' font-family="Menlo, Consolas, monospace"' if code else ''
            grootte = 10.5 if code else 11.5
            self.delen.append(
                f'<text x="{tx}" y="{ty}" text-anchor="{anker}" font-size="{grootte}"{familie} '
                f'fill="#283747">{escape(tekst)}</text>')
            ty += 15

    def groep(self, x, y, b, h, label, soort='kader'):
        vul, rand = KLEUREN[soort]
        self.delen.append(
            f'<rect x="{x}" y="{y}" width="{b}" height="{h}" rx="12" ry="12" fill="{vul}" '
            f'fill-opacity="0.55" stroke="{rand}" stroke-width="1.2" stroke-dasharray="4 3"/>')
        self.delen.append(
            f'<text x="{x + 12}" y="{y + 18}" font-size="12.5" font-weight="bold" '
            f'fill="{rand}">{escape(label)}</text>')

    def pijl(self, punten, label=None, labelpositie=None, gestippeld=False, kleur='#4d5656',
             dubbel=False, labelanker='middle'):
        pad = ' '.join(f'{x},{y}' for x, y in punten)
        streep = ' stroke-dasharray="5 4"' if gestippeld else ''
        begin = ' marker-start="url(#pijlbegin)"' if dubbel else ''
        self.delen.append(
            f'<polyline points="{pad}" fill="none" stroke="{kleur}" stroke-width="1.5"{streep}'
            f'{begin} marker-end="url(#pijl)"/>')
        if label:
            if labelpositie is None:
                (x1, y1), (x2, y2) = punten[0], punten[1]
                labelpositie = ((x1 + x2) / 2, (y1 + y2) / 2 - 5)
            lx, ly = labelpositie
            self.delen.append(
                f'<text x="{lx}" y="{ly}" text-anchor="{labelanker}" font-size="10.5" font-style="italic" '
                f'fill="#4d5656" stroke="#ffffff" stroke-width="3" paint-order="stroke">{escape(label)}</text>')

    def tekst(self, x, y, inhoud, grootte=11.5, vet=False, anker='start', kleur='#283747', cursief=False):
        gewicht = ' font-weight="bold"' if vet else ''
        stijl = ' font-style="italic"' if cursief else ''
        self.delen.append(
            f'<text x="{x}" y="{y}" text-anchor="{anker}" font-size="{grootte}"{gewicht}{stijl} '
            f'fill="{kleur}">{escape(inhoud)}</text>')

    def legenda(self, x, y, items, kop=True):
        if kop:
            self.tekst(x, y, 'Legenda', vet=True, grootte=12)
        for i, (soort, label) in enumerate(items):
            vul, rand = KLEUREN[soort]
            yy = y + 12 + i * 20
            self.delen.append(f'<rect x="{x}" y="{yy}" width="22" height="13" rx="3" fill="{vul}" '
                              f'stroke="{rand}" stroke-width="1.4"/>')
            self.tekst(x + 30, yy + 11, label, grootte=11)

    def svg(self):
        kop = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.breedte}" height="{self.hoogte}" '
            f'viewBox="0 0 {self.breedte} {self.hoogte}" font-family="{LETTERTYPE}" '
            f'role="img" aria-label="{escape(self.titel)}">\n'
            f'<title>{escape(self.titel)}</title>\n'
            '<defs>\n'
            '<marker id="pijl" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
            'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#4d5656"/></marker>\n'
            '<marker id="pijlbegin" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
            'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#4d5656"/></marker>\n'
            '</defs>\n'
            f'<rect x="0" y="0" width="{self.breedte}" height="{self.hoogte}" fill="#ffffff"/>\n'
            f'<text x="24" y="34" font-size="19" font-weight="bold" fill="#1c2833">{escape(self.titel)}</text>\n'
        )
        return kop + '\n'.join(self.delen) + '\n</svg>\n'

    def schrijf(self, naam):
        pad = os.path.join(UITVOERMAP, naam)
        inhoud = self.svg()
        xml.dom.minidom.parseString(inhoud.encode('utf-8'))  # faalt bij ongeldige XML
        with open(pad, 'w', encoding='utf-8') as f:
            f.write(inhoud)
        print(f'Geschreven: {os.path.normpath(pad)}')


# ============================================================
# 1. Systeemarchitectuur
# ============================================================

def systeemArchitectuur():
    d = Diagram(1200, 800, 'Systeemarchitectuur van de Wasstraat')

    # Gebruikers
    d.kader(330, 62, 300, 46, 'gebruiker', 'Beheerder', ['Airflow-webinterface, poort 8080'])
    d.kader(820, 62, 300, 46, 'gebruiker', 'Gebruiker (browser)', ['webapplicatie, poort 5052'])

    # Host
    d.groep(20, 140, 260, 510, 'Host (mappen en bestanden)', 'host')
    d.kader(36, 172, 228, 80, 'host', 'Brondata  /input', ['Access-databases, Excel,', "foto's, tekeningen, rapporten", '(alleen gelezen)'])
    d.kader(36, 268, 228, 64, 'host', 'wasstraat_config/', ['harmonisatie-Excel', 'correcties.yml'])
    d.kader(36, 348, 228, 64, 'host', 'config/*.env', ['instellingen en wachtwoorden', '(init-config.sh)'])
    d.kader(36, 428, 228, 64, 'host', 'Backupmap', ['make backup: pg_dump', 'en mongodump'])
    d.kader(36, 540, 228, 90, 'host', 'Uitvoermap  /output', ['archeomedia/: elk bestand in', 'drie formaten', 'rapporten/: verwerkingsrapporten'])

    # Airflow
    d.groep(310, 140, 400, 330, 'Airflow 2.10.5  (wasstraat_airflow)', 'verwerking')
    d.kader(330, 172, 360, 52, 'verwerking', 'Extractie', ['importMDB.sh (mdbtools, mongoimport), afbeeldingen'])
    d.kader(330, 236, 360, 52, 'verwerking', 'Transform 1 tot en met 5', ['harmoniseren, attributen, sleutels, samenvoegen'])
    d.kader(330, 300, 360, 52, 'verwerking', 'Laden en indexeren', ['psycopg2 naar PostgreSQL, Elasticsearch per tabel'])
    d.kader(330, 364, 360, 86, 'beheer', 'Run-document en foutbeleid', ['Start_Run, Markeer_Run_Mislukt,', 'Controleer_Databases, Controleer_Afbeeldingen,', 'Verwerkingsrapport'])

    # Web
    d.groep(780, 140, 380, 330, 'Webapplicatie', 'web')
    d.kader(800, 172, 340, 70, 'web', 'Apache 2.4  (voordeur, poort 5052)', ['/archeomedia: bestanden uit de uitvoermap', 'al het overige: reverse proxy naar Flask'])
    d.kader(800, 290, 340, 86, 'web', 'Flask + Flask-AppBuilder', ['gunicorn, poort 5051 (geen hostpoort)', 'lijsten, kaart, zoeken, REST-API,', 'bruiklenen en conservering invoeren'])

    # Opslag
    d.groep(310, 500, 850, 150, 'Opslag', 'opslag')
    d.kader(330, 532, 230, 98, 'opslag', 'MongoDB 7.0', ['Arch_Staging, Arch_Files,', 'Arch_Analyse: Single_Store,', 'Single_Store_Clean,', 'Verwerkingsruns'])
    d.kader(580, 532, 230, 98, 'opslag', 'PostgreSQL 18 + PostGIS 3.6', ['database flask: Def_-tabellen,', 'Def_Bronbestand', 'database airflow: metadata'])
    d.kader(830, 532, 160, 98, 'opslag', 'Elasticsearch 8.17', ['index per', 'Def_-tabel'])
    d.kader(1010, 532, 130, 98, 'opslag', 'Redis 7.2', ['cache van de', 'webapplicatie'])

    # Pijlen: beheerder en gebruiker
    d.pijl([(480, 108), (480, 140)], 'bedienen', (520, 128))
    d.pijl([(970, 108), (970, 172)], 'HTTP :5052', (1012, 132))
    # Host naar Airflow
    d.pijl([(264, 212), (330, 198)], 'lezen', (296, 196))
    d.pijl([(264, 300), (330, 262)], 'lezen', (300, 270))
    d.pijl([(264, 380), (310, 380)])
    # Airflow naar de uitvoermap
    d.pijl([(330, 440), (296, 440), (296, 585), (264, 585)], 'schrijven', (292, 520), labelanker='end')
    # Apache en Flask
    d.pijl([(970, 242), (970, 290)], 'proxy', (1000, 270))
    d.pijl([(1140, 207), (1178, 207), (1178, 668), (150, 668), (150, 630)], 'Apache leest /archeomedia uit de uitvoermap (alleen-lezen)', (700, 662))
    # Airflow naar opslag
    d.pijl([(420, 470), (420, 532)], 'staging, transformatie', (432, 492), labelanker='start')
    d.pijl([(600, 470), (660, 532)])
    d.pijl([(660, 470), (880, 532)], 'laden en indexeren', (812, 492))
    # Flask naar opslag
    d.pijl([(860, 376), (860, 440), (760, 440), (760, 532)], 'lezen en schrijven', (812, 433))
    d.pijl([(930, 376), (930, 532)])
    d.pijl([(1075, 376), (1075, 532)])

    d.legenda(24, 700, [('host', 'mappen op de host'), ('verwerking', 'verwerking (Airflow)'),
                        ('web', 'webapplicatie'), ('opslag', 'opslag')])
    d.legenda(220, 700, [('beheer', 'run-document en foutbeleid'), ('gebruiker', 'gebruikers')], kop=False)
    d.tekst(470, 712, 'Alleen Apache (5052) en Airflow (8080) hoeven van buiten bereikbaar te zijn. Flask, Elasticsearch', grootte=11)
    d.tekst(470, 728, 'en Redis hebben in de live installatie geen hostpoort; PostgreSQL en MongoDB luisteren daar', grootte=11)
    d.tekst(470, 744, "standaard alleen op 127.0.0.1. Flask schrijft gekantelde foto's terug in archeomedia/.", grootte=11)
    d.tekst(470, 760, 'In de ontwikkelomgeving draait daarnaast Jupyter Lab (poort 8888) voor analyses.', grootte=11)
    d.schrijf('systeem-architectuur.svg')


# ============================================================
# 2. Verwerkingspipeline (volledige cyclus)
# ============================================================

def verwerkingspipeline():
    d = Diagram(1180, 1200, 'Verwerkingspipeline: de volledige cyclus')
    d.tekst(24, 56, 'DAG Extract_Transform_Load_Full_Cycle; de incrementele cyclus volgt dezelfde stappen voor alleen de gewijzigde bronbestanden.', grootte=12)

    stappen = [
        ('0  Start_Run', ['run-document aanmaken (soort volledig);', 'faalt als er al een run actief is'], 'beheer'),
        ('1  Drop_All_Databases', ['MongoDB legen, behalve Verwerkingsruns'], 'verwerking'),
        ('2  Extract_Group', ['importMDB.sh per invoermap, ABR en extra projecten,', "afbeeldingen; Controleer_Databases en _Afbeeldingen"], 'verwerking'),
        ('3  Transform 1: harmoniseren', ['FixProjectNames, Harmonize_<soort>,', 'ParseFotobestanden'], 'verwerking'),
        ('4  Transform 2: attributen', ['Enhance_All_Attributes (gemeenteprofiel),', 'extract_Imagedata_From_FileNames'], 'verwerking'),
        ('5  Transform 3: sleutels', ['Set_ReferenceKeys_<soort>: key, key_<soort>'], 'verwerking'),
        ('6  Transform 5: verplaatsen en samenvoegen', ['Move_<soort>, Merge_<soort>, MergeFotoinfo,', 'Generate_Missing_<soort>'], 'verwerking'),
        ('7  Transform 4: primary_keys en verwijzingen', ['Set_PrimaryKey_<soort> (stabiel),', 'Set_Reference_<soort>'], 'verwerking'),
        ('8  Laden en indexeren', ['LoadToDatabase_postgres (atomic swap),', 'Index_<tabel>, Index_Klaar (all_done)'], 'verwerking'),
        ('9  Registreer_Bronbestanden', ['vingerafdrukken vastleggen, run afgerond'], 'beheer'),
        ('10  Verwerkingsrapport', ['all_done, ook na een fout; daarna', 'End_ETL_full_cycle (status van de DAG)'], 'beheer'),
    ]
    x, b, h, tussen, y0 = 380, 420, 64, 18, 104
    posities = []
    for i, (titel, regels, soort) in enumerate(stappen):
        y = y0 + i * (h + tussen)
        d.kader(x, y, b, h, soort, titel, regels, uitlijning='links')
        posities.append(y)
        if i > 0:
            d.pijl([(x + b / 2, y - tussen), (x + b / 2, y)])

    def midden(i):
        return posities[i] + h / 2

    # Invoer links
    d.groep(20, 70, 300, 730, 'Invoer en configuratie', 'host')
    invoer = [
        (2, 'Invoermappen  /input', ['Access-databases, Excel, afbeeldingen'], 'host'),
        (3, 'Harmonisatie-Excel', ['tabellen en kolommen per soort'], 'host'),
        (4, 'Gemeenteprofiel', ['WASSTRAAT_GEMEENTE'], 'host'),
        (6, 'correcties.yml', ['paden_overslaan, brondata_ en projectcode_,', 'artefact_niet_mergen, rapportcode_prefixen'], 'host'),
    ]
    for i, titel, regels, soort in invoer:
        y = midden(i) - 28
        d.kader(36, y, 268, 56 if len(regels) == 1 else 66, soort, titel, regels)
        d.pijl([(304, midden(i)), (x, midden(i))])
    d.tekst(36, midden(7) - 4, 'correcties.yml werkt in stap 2', grootte=10.5, cursief=True)
    d.tekst(36, midden(7) + 10, '(paden_overslaan, rapportcode_prefixen),', grootte=10.5, cursief=True)
    d.tekst(36, midden(7) + 24, '3 (brondata_correcties, rapportcode_prefixen),', grootte=10.5, cursief=True)
    d.tekst(36, midden(7) + 38, '4 (projectcode_correcties) en 6 (artefact_niet_mergen)', grootte=10.5, cursief=True)

    # Opslag rechts
    d.groep(860, 70, 300, 944, 'Gegevens', 'opslag')
    uitvoer = [
        (0, 'Verwerkingsruns', ['run-document, meldingen, tellingen'], 'beheer'),
        (2, 'Staging en mediamap', ['Arch_Staging, Filenames, Plaatjes,', 'output/archeomedia'], 'opslag'),
        (3, 'Single_Store', ['geharmoniseerd door Transform 1,', 'aangevuld door Transform 2 en 3'], 'opslag'),
        (6, 'Single_Store_Clean', ['verplaatst en samengevoegd,', 'met key, ID en verwijzingen'], 'opslag'),
        (8, 'PostgreSQL en Elasticsearch', ['Def_-tabellen (gebruikersdata blijft),', 'afgeleide velden, index per tabel'], 'opslag'),
        (9, 'Def_Bronbestand', ['registratie voor de incrementele cyclus'], 'opslag'),
        (10, 'output/rapporten', ['verwerkingsrapport (JSON en Markdown)'], 'opslag'),
    ]
    for i, titel, regels, soort in uitvoer:
        y = midden(i) - 30
        d.kader(876, y, 268, 60, soort, titel, regels)
        d.pijl([(x + b, midden(i)), (876, midden(i))])
    # PostgreSQL levert de bestaande primary_keys aan Transform 4
    d.pijl([(1010, midden(8) - 30), (1010, midden(7) + 8), (x + b + 4, midden(7) + 8)], 'bestaande primary_keys', (1000, midden(7) + 24), labelanker='end')

    # Foutbeleid
    yb = y0 + len(stappen) * (h + tussen) + 4
    d.kader(20, yb, 820, 108, 'beheer', 'Foutbeleid', [
        'Markeer_Run_Mislukt (trigger_rule one_failed) bewaakt alle taken behalve de Index-taken: een cruciale fout zet de run op mislukt.',
        'Waarschuwingen (onleesbare database, mislukte afbeelding, verwerkingsfout, mislukte index) komen in het run-document;',
        'boven de drempels AIRFLOW_MAX_* worden ze cruciaal. Elke taak meldt zijn fout via on_failure_callback.',
        'Het verwerkingsrapport draait altijd als laatste en vat de run samen.',
    ], uitlijning='links')
    d.kader(20, yb + 120, 1140, 66, 'verwerking', 'Incrementele cyclus (Extract_Transform_Load_Incremental)', [
        'Start_Run, Bepaal_Delta, Opruimen_Oude_Records, Extract (delta), Transform 1, 2, 3, 5 en 4 (delta), Load_Upsert, Index_<tabel>, Index_Klaar, Registreer_Run, Verwerkingsrapport',
    ], uitlijning='links')
    d.schrijf('dataflow-pipeline.svg')


# ============================================================
# 3. Componentenmodel
# ============================================================

def componentenModel():
    d = Diagram(1180, 800, 'Componentenmodel: de code van de Wasstraat')

    # Airflow-image
    d.groep(20, 56, 700, 520, 'Airflow-image (airflow_app/)', 'verwerking')
    d.kader(40, 88, 660, 52, 'verwerking', 'DAG-bestanden  dags/DAG_*.py', ['volledige cyclus, incrementele cyclus, DAG_Load_Only, deelstappen voor debuggen'])
    d.kader(40, 160, 660, 52, 'verwerking', 'Taakgroepen  dags/tasks_*.py', ['extract, transform1 tot en met 5, load_to_database_and_index, verwerkingsrun'])
    d.pijl([(370, 140), (370, 160)])
    d.groep(40, 232, 660, 324, 'Verwerkingslogica  dags/wasstraat/', 'verwerking')
    d.kader(56, 262, 200, 136, 'verwerking', 'Extractie', ['`image_import.py`', '`paden_overslaan.py`', '`controle_extractie.py`', '`extract_referentietabellen.py`', '`extract_extra_projects.py`'])
    d.kader(270, 262, 210, 136, 'verwerking', 'Transformatie', ['`meta.py`  `harmonizer.py`', '`harmonize_functions.py`', '`setAttributes_functions.py`', '`references_functions.py`', '`merge_functions.py`', '`delta_transform.py`'])
    d.kader(494, 262, 190, 136, 'verwerking', 'Laden', ['`loadToDatabase_functions.py`', 'atomic swap (loadAll)', 'upsert (loadIncrementeel)', 'gebruikersdata,', 'afgeleide velden'])
    d.kader(56, 412, 300, 128, 'beheer', 'Run, registratie en foutbeleid', ['`verwerkingsrun.py`  `foutbeleid.py`', '`verwerkingsrapport.py`', '`bronbestanden.py`  `opruimen.py`', '`mongoUtils.py`'])
    d.kader(370, 412, 314, 128, 'verwerking', 'Gemeenteprofielen  profielen/', ['`ConventieProfiel` (basis)', '`DelftProfiel`', '`VoorbeeldProfiel`', 'keuze met WASSTRAAT_GEMEENTE'])
    d.pijl([(370, 212), (370, 232)])

    # Scripts
    d.kader(40, 596, 330, 96, 'verwerking', 'Importscripts  airflow_app/scripts/', ['`importMDB.sh (mdbtools, mongoimport)`', '`csv_kolommen.py  paden_overslaan.py`', 'aangeroepen door Extract_Data_From_<map>'])
    d.pijl([(150, 556), (150, 596)])

    # Gedeeld
    d.kader(400, 596, 320, 128, 'host', 'Gedeelde code  shared/', ['`config.py` (alle instellingen)  `const.py`', '`database.py`  `fulltext.py`', '`gebruikersdata.py`  `image_util.py`', '`logutils.py`  `afbeeldingen/document.png`', 'in beide images'])
    d.pijl([(560, 556), (560, 596)])

    # Flask-image
    d.groep(760, 56, 400, 520, 'Flask-image (app/)', 'web')
    d.kader(780, 88, 360, 52, 'web', 'app.py', ['Flask-AppBuilder, ProxyFix, cache, Elasticsearch'])
    d.kader(780, 156, 360, 70, 'web', 'models.py', ['SQLAlchemy-modellen van alle Def_-tabellen;', 'db.create_all() maakt de tabellen aan'])
    d.kader(780, 242, 360, 70, 'web', 'views.py  baseviews.py  api.py', ['lijsten, detailpagina\'s, formulieren,', 'REST-API onder /api/v1/'])
    d.kader(780, 328, 360, 52, 'web', 'search.py  filters.py  interface.py', ['zoeken in Elasticsearch, index bijwerken'])
    d.kader(780, 396, 360, 70, 'web', 'init.py  beheerder.py  foto_util.py', ['zoekindex en afgeleide velden bij het starten,', 'beheerder admin, foto\'s kantelen'])
    d.kader(780, 482, 360, 70, 'web', 'fab_addon_geoalchemy/', ['eigen uitbreiding voor', 'geometriekolommen (kaart)'])
    d.pijl([(960, 576), (960, 650), (720, 650)], 'gebruikt', (850, 644))

    # Configuratie
    d.kader(40, 716, 330, 70, 'host', 'Configuratie van de pipeline', ['harmonisatie-Excel, correcties.yml', '(wasstraat_config/), config/*.env'])
    d.pijl([(370, 751), (385, 751), (385, 556)], 'gelezen door de pipeline', (392, 740), labelanker='start')
    d.kader(780, 712, 380, 70, 'opslag', 'PostgreSQL', ['de laadstap leest de kolommen van de tabellen', 'die models.py heeft laten aanmaken'])
    d.pijl([(684, 330), (740, 330), (740, 747), (780, 747)], 'laden', (746, 736), labelanker='start')
    d.schrijf('componenten-model.svg')


# ============================================================
# 4. Gegevensmodel
# ============================================================

def gegevensmodel():
    d = Diagram(1400, 910, 'Gegevensmodel in PostgreSQL (database flask)')
    b, h = 200, 58

    def tabel(x, y, naam, regels, soort='tabel', hoogte=h, breedte=b, gestippeld=False):
        d.kader(x, y, breedte, hoogte, soort, naam, regels, titelgrootte=12.5, afgerond=4, gestippeld=gestippeld)

    # Project als balk
    d.kader(40, 62, 1320, 46, 'tabel', 'Def_Project', ['projectcode, naam, jaar, locatie (PostGIS), aantal_artefacten; vrijwel elke tabel verwijst ernaar met projectID'], titelgrootte=13, afgerond=4)

    # Rij 1
    tabel(180, 150, 'Def_Vindplaats', ['projectcd als tekst'])
    tabel(420, 150, 'Def_Put', ['projectID'])
    tabel(1150, 150, 'Def_Bronbestand', ['registratie van bronbestanden'], 'administratie')

    # Rij 2
    tabel(180, 250, 'Def_Vlak', ['projectID, putID'])
    tabel(420, 250, 'Def_Spoor', ['projectID, putID, vlakID'])
    tabel(660, 250, 'Def_Vondst', ['projectID, putID, spoorID'])
    tabel(900, 250, 'Def_Monster', ['projectID, putID, spoorID,', 'vondstID, doosID'], hoogte=70)
    tabel(1150, 250, 'Def_Monster_Schelp', ['monsterID, dt_soort_schelpID'])

    # Rij 3
    tabel(180, 360, 'Def_Vulling', ['projectID, putID, spoorID'])
    tabel(420, 360, 'Def_Bestand', ['bestandsoort: foto, tekening,', 'rapport; projectID, artefactID'], hoogte=70)
    tabel(660, 360, 'Def_Artefact', ['artefactsoort: 14 soorten;', 'projectID, putID, vondstID, doosID'], hoogte=70)
    tabel(900, 360, 'Def_Monster_Botanie', ['monsterID, dt_soort_plantID,', 'dt_soort_deelID, dt_soort_staatID'], hoogte=70)
    tabel(1150, 360, 'Def_DT_Soort_Schelp', ['referentielijst'])

    # Rij 4
    tabel(180, 480, 'Def_Stelling', ['magazijnlijst'])
    tabel(420, 480, 'Def_Doos', ['projectID, stellingID'])
    tabel(660, 480, 'Def_ABR', ['ABR-thesaurus; parentID'])
    tabel(900, 480, 'Def_DT_Soort_Plant', ['referentielijst'], breedte=150)
    tabel(1070, 480, 'Def_DT_Soort_Deel', ['referentielijst'], breedte=150)
    tabel(1240, 480, 'Def_DT_Soort_Staat', ['referentielijst'], breedte=140)

    # Rij 5: depot zonder verwijzingen
    tabel(180, 580, 'Def_Standplaats', ['stelling, vak, volgletter'])
    tabel(420, 580, 'Def_Plaatsing', ['regel van de magazijnlijst'])

    # Gebruikerstabellen
    d.groep(160, 700, 1220, 120, 'Gebruikerstabellen: ingevoerd in de webapplicatie, blijven staan bij elke cyclus', 'beheer')
    tabel(180, 735, 'Def_Bruikleen', ['partijID, artefactID, projectID;', 'markering *_verdwenen_key/_op'], 'gebruikerstabel', hoogte=70)
    tabel(420, 735, 'Def_Partij', ['naam, adres, contactpersoon'], 'gebruikerstabel')
    tabel(660, 735, 'Def_Conserveringsproject', ['uitvoerderID'], 'gebruikerstabel')
    tabel(900, 735, 'Def_artefact_conservering', ['conservering_id, artefact_id;', 'markering artefact_verdwenen_*'], 'koppeltabel', hoogte=70, gestippeld=True)
    tabel(1150, 735, 'Def_artefact_abr', ['artefact_id, abr_materiaal_id', '(extra ABR-materialen)'], 'koppeltabel', hoogte=70, gestippeld=True)

    # Verwijzingen binnen de opgraving
    d.pijl([(520, 150), (520, 108)])                      # Put -> Project (als voorbeeld)
    d.pijl([(380, 279), (420, 279)][::-1])                # Spoor -> Vlak
    d.pijl([(280, 250), (280, 226), (470, 226), (470, 208)])  # Vlak -> Put
    d.pijl([(520, 250), (520, 208)])                      # Spoor -> Put
    d.pijl([(660, 279), (620, 279)])                      # Vondst -> Spoor
    d.pijl([(280, 360), (280, 338), (450, 338), (450, 308)])  # Vulling -> Spoor
    d.pijl([(760, 360), (760, 308)])                      # Artefact -> Vondst
    d.pijl([(900, 285), (860, 285)])                      # Monster -> Vondst
    d.pijl([(1000, 360), (1000, 320)])                    # Botanie -> Monster
    d.pijl([(1150, 279), (1100, 279)])                    # Schelp -> Monster
    d.pijl([(1250, 308), (1250, 360)])                    # Schelp -> DT_Soort_Schelp
    d.pijl([(620, 380), (660, 380)])                      # Bestand -> Artefact
    d.pijl([(760, 430), (760, 480)])                      # Artefact -> ABR
    d.pijl([(700, 430), (700, 446), (540, 446), (540, 480)])  # Artefact -> Doos
    d.pijl([(960, 320), (960, 342), (884, 342), (884, 464), (590, 464), (590, 480)])  # Monster -> Doos
    d.pijl([(420, 509), (380, 509)])                      # Doos -> Stelling
    d.pijl([(975, 430), (975, 480)])                      # Botanie -> Plant
    d.pijl([(1060, 430), (1140, 480)])                    # Botanie -> Deel
    d.pijl([(1095, 418), (1300, 480)])                    # Botanie -> Staat
    # ABR verwijst naar zichzelf (ouder)
    d.pijl([(860, 500), (885, 500), (885, 524), (860, 524)])

    # Gebruikerstabellen
    d.pijl([(380, 765), (420, 765)][::-1])                # Bruikleen -> Partij
    d.pijl([(660, 765), (620, 765)])                      # Conservering -> Partij
    d.pijl([(900, 765), (860, 765)])                      # koppel -> Conservering

    d.kader(40, 836, 22, 13, 'tabel')
    d.tekst(70, 847, 'tabel van de pipeline (LOAD_TABELLEN)', grootte=11)
    d.kader(330, 836, 22, 13, 'gebruikerstabel')
    d.tekst(360, 847, 'gebruikerstabel', grootte=11)
    d.kader(480, 836, 22, 13, 'koppeltabel', gestippeld=True)
    d.tekst(510, 847, 'koppeltabel', grootte=11)
    d.kader(610, 836, 22, 13, 'administratie')
    d.tekst(640, 847, 'administratie van de pipeline', grootte=11)
    d.tekst(860, 847, 'Pijl: verwijzing (foreign key) naar de tabel waar de pijl naar wijst.', grootte=11)
    d.tekst(40, 872, 'Verwijzingen naar Def_Project en Def_Put en vanuit de gebruikerstabellen naar Def_Artefact, Def_Project en Def_ABR staan als kolomnaam in de kaders.', grootte=11)
    d.tekst(40, 888, 'Verdwijnt zo\'n rij uit de brondata, dan wordt de verwijzing losgekoppeld met een markering; koppelrijen van Def_artefact_abr worden verwijderd.', grootte=11)
    d.schrijf('gegevensmodel.svg')


if __name__ == '__main__':
    os.makedirs(UITVOERMAP, exist_ok=True)
    systeemArchitectuur()
    verwerkingspipeline()
    componentenModel()
    gegevensmodel()
