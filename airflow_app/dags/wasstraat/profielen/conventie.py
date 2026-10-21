"""
Standaard gemeenteprofiel: directe velden, geen transformatie.

Dit is het basisprofiel dat velden uit brondata direct overneemt.
Gemeente-specifieke profielen erven hiervan en overschrijven alleen
de methoden die afwijkend gedrag nodig hebben.

De conventie is: als brondata al de juiste veldnamen bevat,
hoeft er niets afgeleid of getransformeerd te worden.

Elke entiteit heeft een identificeer_{soort}(doc) methode die:
1. Controleert of de identificerende velden bestaan
2. Ze normaliseert (projectcd, integers)
3. Ontbrekende velden afleidt indien mogelijk
4. Het document teruggeeft met alle identificerende velden gevuld

Voor de bestands-entiteiten (Foto, Tekening, Rapport) heet die methode
identificeer_{soort}_db(doc): de naam zonder _db is daar gereserveerd voor
de bestandsnaam-parser identificeer_{soort}(doc, projectcd) die
parseFotobestanden() aanroept.
"""
import re
import wasstraat.archutils as ut
import shared.const as const


class ConventieProfiel:
    """Standaard profiel: directe referenties, geen afleiding."""

    naam = "conventie"

    # Expliciet: welke velden identificeren welk entiteitstype.
    # 'verplicht': moet aanwezig zijn voor een geldige key.
    # 'optioneel': wordt meegenomen in de key als het bestaat.
    # 'integer': identificerende velden die als integer genormaliseerd worden.
    IDENTIFICERENDE_VELDEN = {
        'Project':     {'verplicht': ['projectcd'],                                         'integer': []},
        'Put':         {'verplicht': ['projectcd', 'putnr'],                                'integer': ['putnr']},
        'Vlak':        {'verplicht': ['projectcd', 'vlaknr'],       'optioneel': ['putnr'], 'integer': ['putnr', 'vlaknr']},
        'Spoor':       {'verplicht': ['projectcd', 'spoornr'],      'optioneel': ['putnr', 'vlaknr'], 'integer': ['putnr', 'vlaknr', 'spoornr']},
        'Vulling':     {'verplicht': ['projectcd', 'vullingnr'],    'optioneel': ['putnr', 'vlaknr', 'spoornr'], 'integer': ['putnr', 'vlaknr', 'spoornr', 'vullingnr']},
        'Vondst':      {'verplicht': ['projectcd', 'vondstnr'],     'optioneel': ['putnr'], 'integer': ['putnr', 'vondstnr']},
        'Artefact':    {'verplicht': ['projectcd', 'artefactnr'], 'optioneel': ['putnr', 'vondstnr', 'splitid'], 'integer': ['putnr', 'vondstnr', 'artefactnr', 'subnr']},
        'Monster':     {'verplicht': ['projectcd', 'monstercd'],                                         'integer': []},
        'Doos':        {'verplicht': ['doosnr'],                    'optioneel': ['projectcd'],           'integer': ['doosnr']},
        'Foto':        {'verplicht': ['projectcd'],                 'optioneel': ['putnr', 'vondstnr', 'subnr', 'fotonr'], 'integer': ['putnr', 'vondstnr', 'subnr', 'fotonr']},
        'Tekening':    {'verplicht': ['projectcd', 'tekeningcd'],                           'integer': []},
        'Rapport':     {'verplicht': ['rapportnr'],                 'optioneel': ['projectcd'],                     'integer': []},
        'Standplaats': {'verplicht': ['stelling'],                  'optioneel': ['vaknr', 'volgletter'], 'integer': []},
    }

    # ----------------------------------------------------------
    # Dispatcher
    # ----------------------------------------------------------

    # Bestands-entiteiten: identificeer_<soort> is hier de bestandsnaam-parser
    # (Type B, twee argumenten); de dispatcher gebruikt identificeer_<soort>_db.
    BESTANDS_ENTITEITEN = tuple(soort.lower() for soort in const.BESTANDSOORTEN)

    def identificeer(self, soort, doc):
        """Vul en normaliseer de identificerende velden voor een entiteit.

        Roept de juiste per-entiteit methode aan. Als er geen specifieke
        methode bestaat voor het soort, wordt de standaard-methode gebruikt.

        Voor Foto, Tekening en Rapport (const.BESTANDSOORTEN) is dat
        identificeer_<soort>_db(doc). De methode zonder _db is voor die
        soorten de bestandsnaam-parser met twee argumenten; die hier kiezen
        gaf voor elke foto een TypeError in Transform 2, waardoor foto's hun
        ongenormaliseerde projectcode en tekstnummers hielden en nooit aan
        een artefact gekoppeld werden.

        Args:
            soort: entiteitstype (bijv. 'Put', 'Vondst', 'Artefact', 'Foto')
            doc: MongoDB-document met brondata-velden

        Returns:
            Het document met genormaliseerde identificerende velden.
        """
        method_name = f'identificeer_{soort.lower()}'
        if soort.lower() in self.BESTANDS_ENTITEITEN:
            method_name += '_db'
        method = getattr(self, method_name, None)
        if method:
            return method(doc)
        return self._identificeer_standaard(doc)

    def _identificeer_standaard(self, doc):
        """Standaard identificatie: normaliseer projectcd + converteer integers."""
        if 'projectcd' in doc and doc['projectcd']:
            doc['projectcd'] = self.normaliseer_projectcode(doc['projectcd'])
        self._converteer_integers(doc)
        return doc

    def _converteer_integers(self, doc):
        """Converteer bekende numerieke identificatievelden naar integers."""
        for veld in ['putnr', 'vondstnr', 'spoornr', 'vlaknr', 'artefactnr', 'subnr', 'doosnr']:
            if veld in doc:
                ut.convertToInt(doc, veld, True)
        if 'fotonr' in doc:
            ut.convertToInt(doc, 'fotonr', False)

    # ----------------------------------------------------------
    # Per-entiteit methoden — database-entiteiten (Type A)
    # Standaard: normaliseer projectcd + converteer integers.
    # Subklassen overschrijven indien nodig.
    # ----------------------------------------------------------

    def identificeer_project(self, doc):
        """Identificeer een Project-record."""
        if 'projectcd' in doc and doc['projectcd']:
            doc['projectcd'] = self.normaliseer_projectcode(doc['projectcd'])
        return doc

    def identificeer_put(self, doc):
        """Identificeer een Put-record: projectcd + putnr."""
        return self._identificeer_standaard(doc)

    def identificeer_vlak(self, doc):
        """Identificeer een Vlak-record: projectcd + putnr? + vlaknr."""
        return self._identificeer_standaard(doc)

    def identificeer_spoor(self, doc):
        """Identificeer een Spoor-record: projectcd + putnr? + vlaknr? + spoornr."""
        return self._identificeer_standaard(doc)

    def identificeer_vulling(self, doc):
        """Identificeer een Vulling-record: projectcd + putnr? + vlaknr? + spoornr? + vullingnr."""
        return self._identificeer_standaard(doc)

    def identificeer_vondst(self, doc):
        """Identificeer een Vondst-record: projectcd + putnr? + vondstnr."""
        return self._identificeer_standaard(doc)

    def identificeer_artefact(self, doc):
        """Identificeer een Artefact-record: projectcd + vondstnr + artefactnr + putnr? + splitid?."""
        return self._identificeer_standaard(doc)

    def identificeer_monster(self, doc):
        """Identificeer een Monster-record: projectcd + monstercd."""
        return self._identificeer_standaard(doc)

    def identificeer_doos(self, doc):
        """Identificeer een Doos-record: doosnr + projectcd?."""
        return self._identificeer_standaard(doc)

    def identificeer_standplaats(self, doc):
        """Identificeer een Standplaats-record: stelling + vaknr? + volgletter?."""
        return doc

    # ----------------------------------------------------------
    # Per-entiteit methoden — bestands-entiteiten uit de database (Type A)
    # Aangeroepen door identificeer() voor Foto, Tekening en Rapport, voor
    # records uit de harmonisatie én voor de records die parseFotobestanden()
    # uit bestandsnamen heeft gemaakt. Subklassen overschrijven indien nodig.
    # ----------------------------------------------------------

    def identificeer_foto_db(self, doc):
        """Identificeer een Foto-record uit de database (niet uit de bestandsnaam).

        Standaard: normaliseer projectcd + converteer putnr, vondstnr, subnr
        en fotonr naar integers. Daardoor krijgt een foto dezelfde
        key_foto1/key_foto3 als het artefact waar hij bij hoort.
        """
        return self._identificeer_standaard(doc)

    def identificeer_tekening_db(self, doc):
        """Identificeer een Tekening-record uit de database: projectcd + tekeningcd."""
        doc = self._identificeer_standaard(doc)
        if 'tekeningcd' in doc:
            doc['tekeningcd'] = self.normaliseer_tekeningcode(doc['tekeningcd'])
        return doc

    def identificeer_rapport_db(self, doc):
        """Identificeer een Rapport-record uit de database: rapportnr + projectcd?."""
        doc = self._identificeer_standaard(doc)
        if 'rapportnr' in doc:
            doc['rapportnr'] = self.normaliseer_rapportnr(doc['rapportnr'], doc.get('brondata', {}))
        return doc

    # ----------------------------------------------------------
    # Per-entiteit methoden — bestands-entiteiten uit de bestandsnaam (Type B)
    # Aangeroepen door parseFotobestanden(), niet door identificeer().
    # Standaard: geen afleiding. Return None = niet herkend.
    # DelftProfiel overschrijft deze met regex-parsing.
    # ----------------------------------------------------------

    def identificeer_foto(self, doc, projectcd):
        """Identificeer een Foto-record uit een bestandsnaam.

        Standaard: geen herkenning. Return None.

        Args:
            doc: MongoDB-document met 'fileName' en 'fullFileName'
            projectcd: eerder geëxtraheerde projectcode

        Returns:
            Het aangevulde document, of None als niet herkend.
        """
        return None

    def identificeer_tekening(self, doc, projectcd):
        """Identificeer een Tekening-record uit een bestandsnaam.

        Standaard: geen herkenning. Return None.
        """
        return None

    def identificeer_rapport(self, doc, projectcd):
        """Identificeer een Rapport-record uit een bestandsnaam.

        Standaard: geen herkenning. Return None.
        """
        return None

    # ----------------------------------------------------------
    # Projectcode uit bestandsnaam
    # ----------------------------------------------------------

    def extract_projectcode_uit_bestandsnaam(self, fileName, directory):
        """Haal de projectcode uit een bestandsnaam.

        Standaard: pak het eerste alfanumerieke deel van de bestandsnaam.
        Geen prefix-validatie — accepteer elke projectcode.

        Args:
            fileName: bestandsnaam (bijv. 'DC001_H123_456_001.jpg')
            directory: mappad van het bestand

        Returns:
            Projectcode als string, of None als niet herkend.
        """
        matchObj = re.match(r'^([a-z0-9]+).*', fileName, re.M | re.I)
        if matchObj:
            return matchObj.group(1)
        return None

    # ----------------------------------------------------------
    # Artefactsoort uit bestandspad
    # ----------------------------------------------------------

    def detecteer_artefactsoort(self, fullFileName):
        """Bepaal het artefactsoort op basis van het bestandspad.

        Standaard: keyword-matching op het volledige pad.
        Dit is generiek en niet gemeente-specifiek.

        Args:
            fullFileName: volledig pad inclusief mapnaam

        Returns:
            Artefactsoort-constante, of const.ARTF_ONBEKEND.
        """
        strFN = str(fullFileName).lower()
        if 'bouwaardewerk' in strFN:
            return const.ARTF_BOUWAARDEWERK
        elif 'aardewerk' in strFN or 'pijpaard' in strFN:
            return const.ARTF_AARDEWERK
        elif 'bot' in strFN and 'menselijk' in strFN:
            return const.ARTF_MENSELIJK_BOT
        elif 'bot' in strFN and 'dierlijk' in strFN:
            return const.ARTF_DIELRIJK_BOT
        elif 'glas' in strFN:
            return const.ARTF_GLAS
        elif 'leer' in strFN:
            return const.ARTF_LEER
        elif 'steen' in strFN:
            return const.ARTF_STEEN
        elif 'kleipijp' in strFN:
            return const.ARTF_KLEIPIJP
        elif 'hout/' in strFN:
            return const.ARTF_HOUT
        elif 'metaal' in strFN:
            return const.ARTF_METAAL
        elif 'munt' in strFN:
            return const.ARTF_MUNT
        elif 'schelp' in strFN:
            return const.ARTF_SCHELP
        elif 'textiel' in strFN:
            return const.ARTF_TEXTIEL
        return const.ARTF_ONBEKEND

    # ----------------------------------------------------------
    # Normalisatie-helpers (gebruikt door per-entiteit methoden)
    # ----------------------------------------------------------

    def normaliseer_projectcode(self, projectcd):
        """Normaliseer een projectcode. Standaard: passthrough."""
        return projectcd

    def normaliseer_tekeningcode(self, tekeningcd):
        """Normaliseer een tekeningcode. Standaard: passthrough."""
        return tekeningcd

    def normaliseer_rapportnr(self, rapportnr, brondata):
        """Normaliseer een rapportnummer. Standaard: passthrough."""
        return rapportnr
