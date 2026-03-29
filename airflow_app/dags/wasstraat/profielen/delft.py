"""
Gemeenteprofiel Delft.

Bevat de Delft-specifieke logica voor identificatie van entiteiten:
- Per-entiteit methoden voor bestands-entiteiten (Foto, Tekening, Rapport)
- Projectcode-normalisatie (2-letter + 3-cijfer, bijv. DC016)
- Tekeningcode-normalisatie (letter + 3-cijfer, bijv. B003)
- Rapportnummer-normalisatie (DAR/DAN prefixen)
- Artefactsoort-afleiding uit typevoorwerp
"""
import re
import pandas as pd
import wasstraat.archutils as ut
import shared.const as const
from wasstraat.profielen.conventie import ConventieProfiel


class DelftProfiel(ConventieProfiel):
    """Profiel voor de gemeente Delft."""

    naam = "delft"

    # Delftse projectcodes beginnen met DB, DC, MD, WL, PN, XX, ZM, LL
    # Primair DB (opgravingen) en DC (onderzoeken)
    RE_PROJECTCODE_PREFIX = re.compile(r'^(DB|DC).*', re.M | re.I)
    RE_PROJECTCODE_DIR = re.compile(r'^/((?:DB|DC)\d+).*', re.M | re.I)

    # Bestandsnaam-patronen
    RE_OBJECTFOTO = re.compile(
        r'^([a-zA-Z0-9]+)(_B?P([0-9Xx]+))?_H([a-zA-Z0-9]+)(_([a-zA-Z0-9]+))?_([0-9Xx]+)\.[a-z]{3}$',
        re.M | re.I
    )
    RE_TEKENING = re.compile(
        r'^([a-zA-Z0-9]+)_([ABCDEPT])([a-zA-Z0-9]+)(_LZW)?\.[a-z]{3}$',
        re.M | re.I
    )
    RE_PROJECTFOTO = re.compile(
        r'^([a-zA-Z0-9]+)_([FG])([a-zA-Z0-9]+).*\.[a-z]{3}$',
        re.M | re.I
    )

    # Normalisatie-patronen
    RE_PROJECTCD_NORM = re.compile(r'([a-zA-Z]+)-?([0-9]*)', re.M | re.I)
    RE_TEKENINGCD_NORM = re.compile(r'^([A-Z])([0-9]+)$', re.M | re.I)
    RE_RAPPORTNR_NORM = re.compile(r'^(DAN|DAR)\s*([0-9]+)$', re.M | re.I)

    # Tekening type-mapping
    TEKENING_TYPE_MAP = {
        'A': const.TEK_BOUWTEKENING,
        'B': const.TEK_VELDTEKENING,
        'C': const.TEK_OVERZICHTSTEKENING,
        'D': const.TEK_OBJECTTEKENING,
        'E': const.TEK_UITWERKINGSTEKENING,
        'P': const.TEK_VELDTEKENING_PUBL,
        'T': const.TEK_OBJECTTEKENING_PUBL,
    }

    # Brondata-veldnamen voor rapportcode-fallback
    RAPPORT_VELD_PREFIX_MAP = {
        'DARnr': 'DAR',
        'DANnr': 'DAN',
    }

    # ----------------------------------------------------------
    # Projectcode uit bestandsnaam
    # ----------------------------------------------------------

    def extract_projectcode_uit_bestandsnaam(self, fileName, directory):
        """Haal projectcode uit bestandsnaam met Delftse DB/DC-validatie.

        Als de bestandsnaam niet met DB of DC begint, probeer dan
        de projectcode uit het mappad te halen.
        """
        matchObj = re.match(r'^([a-z0-9]+).*', fileName, re.M | re.I)
        if matchObj:
            projectcd = matchObj.group(1)
            if not self.RE_PROJECTCODE_PREFIX.match(projectcd):
                matchObjDir = self.RE_PROJECTCODE_DIR.match(directory)
                if matchObjDir:
                    projectcd = matchObjDir.group(1)
            return projectcd
        return None

    # ----------------------------------------------------------
    # Per-entiteit methoden — bestands-entiteiten (Type B)
    # ----------------------------------------------------------

    def identificeer_foto(self, doc, projectcd):
        """Identificeer een Foto-record uit een Delftse bestandsnaam.

        Herkent objectfoto's (_H patroon) en projectfoto's (F/G patroon).
        Vult: projectcd, putnr, vondstnr, subnr, fotonr, fototype,
              soort, bestandsoort, artefactsoort.

        Returns:
            Het aangevulde document, of None als niet herkend als foto.
        """
        fileName = doc['fileName']

        # 1. Objectfoto's (bevatten _H)
        matchObj = self.RE_OBJECTFOTO.match(fileName)
        if matchObj:
            doc['projectcd'] = projectcd
            if matchObj.group(3) is not None:
                doc['putnr'] = matchObj.group(3).lstrip("0")
            doc['vondstnr'] = matchObj.group(4).lstrip("0")
            if matchObj.group(6) is not None:
                doc['subnr'] = matchObj.group(6).lstrip("0")
            if matchObj.group(7) is not None:
                doc['fotonr'] = matchObj.group(7).lstrip("0")
            doc['fototype'] = 'H'
            doc['soort'] = 'Foto'
            doc['bestandsoort'] = const.FOTO_OBJECTFOTO
            doc['artefactsoort'] = self.detecteer_artefactsoort(doc['fullFileName'])
            return doc

        # 2. Projectfoto's (F=sfeer, G=opgraving)
        matchObj = self.RE_PROJECTFOTO.match(fileName)
        if matchObj:
            doc['projectcd'] = projectcd
            doc['fotonr'] = matchObj.group(3).lstrip("0")
            doc['soort'] = 'Foto'
            fototype = matchObj.group(2)
            doc['fototype'] = fototype
            if fototype == 'F':
                doc['bestandsoort'] = const.FOTO_SFEERFOTO
            elif fototype == 'G':
                doc['bestandsoort'] = const.FOTO_OPGRAVINGSFOTO
            else:
                doc['bestandsoort'] = const.FOTO_OVERIGE
            return doc

        return None

    def identificeer_tekening(self, doc, projectcd):
        """Identificeer een Tekening-record uit een Delftse bestandsnaam.

        Vult: projectcd, tekeningcd, soort, fototype, bestandsoort.

        Returns:
            Het aangevulde document, of None als niet herkend als tekening.
        """
        matchObj = self.RE_TEKENING.match(doc['fileName'])
        if matchObj:
            doc['projectcd'] = projectcd
            try:
                doc['tekeningcd'] = matchObj.group(2) + str(int(matchObj.group(3))).zfill(3)
            except (ValueError, TypeError):
                doc['tekeningcd'] = matchObj.group(2) + matchObj.group(3)
            doc['soort'] = 'Tekening'
            tektype = matchObj.group(2)
            doc['fototype'] = tektype
            doc['bestandsoort'] = self.TEKENING_TYPE_MAP.get(tektype, const.TEK_OVERIGE)
            return doc

        return None

    def identificeer_rapport(self, doc, projectcd):
        """Identificeer een Rapport-record uit een Delftse bestandsnaam.

        Niet geïmplementeerd via het profiel — rapportherkenning is
        configuratie-driven via rapportcode_prefixen in correcties.yml.

        Returns:
            None (rapportherkenning blijft in parseFotobestanden).
        """
        return None

    # ----------------------------------------------------------
    # Per-entiteit methoden — database-entiteiten (Type A)
    # ----------------------------------------------------------

    def identificeer_artefact(self, doc):
        """Identificeer een Artefact-record.

        Standaard identificatie + Delft-specifieke artefactsoort-afleiding
        uit typevoorwerp-patronen (als artefactsoort nog niet gezet is).
        """
        doc = self._identificeer_standaard(doc)

        # Delft-specifiek: artefactsoort afleiden uit typevoorwerp
        if doc.get('soort') == 'Artefact' and 'artefactsoort' not in doc and 'typevoorwerp' in doc:
            typevoorwerp = doc['typevoorwerp']
            if typevoorwerp == 'Kleipijp':
                doc['artefactsoort'] = 'Kleipijp'
            matchObj = re.match(r'^[a-z]{1,2}(_|-)', typevoorwerp, re.M | re.I)
            if matchObj:
                doc['artefactsoort'] = 'Aardewerk'
            matchObj = re.match(r'^gl(_|-)', typevoorwerp, re.M | re.I)
            if matchObj:
                doc['artefactsoort'] = 'Glas'

        return doc

    def identificeer_tekening_db(self, doc):
        """Identificeer een Tekening-record uit database (niet bestandsnaam).

        Normaliseert tekeningcd naar Delfts formaat: letter + 3-cijfer padding.
        """
        doc = self._identificeer_standaard(doc)
        if 'tekeningcd' in doc:
            doc['tekeningcd'] = ut.sanitize_text(
                doc['tekeningcd'], 'tekeningcd', doc.get('_id')
            ).replace('!', '').replace('-', '')
            doc['tekeningcd'] = self.normaliseer_tekeningcode(doc['tekeningcd'])
        return doc

    def identificeer_rapport_db(self, doc):
        """Identificeer een Rapport-record uit database (niet bestandsnaam).

        Normaliseert rapportnr met Delftse DAR/DAN-conventie.
        """
        doc = self._identificeer_standaard(doc)
        if 'rapportnr' in doc:
            doc['rapportnr'] = str(doc['rapportnr']).replace(' ', '')
            doc['rapportnr'] = self.normaliseer_rapportnr(
                doc['rapportnr'],
                doc.get('brondata', {})
            )
        return doc

    # ----------------------------------------------------------
    # Normalisatie-helpers
    # ----------------------------------------------------------

    def normaliseer_projectcode(self, projectcd):
        """Normaliseer naar Delfts formaat: hoofdletters + 3-cijfer padding.

        Voorbeelden: 'dc-16' → 'DC016', 'DB' → 'DB', 'DB034' → 'DB034'
        """
        matchObj = self.RE_PROJECTCD_NORM.match(projectcd)
        if matchObj:
            deel1 = matchObj.group(1).upper()
            deel2_raw = matchObj.group(2)
            if deel2_raw == '' or deel2_raw is None:
                deel2 = ""
            else:
                deel2 = str(pd.to_numeric(deel2_raw)).zfill(3)
            return deel1 + deel2
        return projectcd

    def normaliseer_tekeningcode(self, tekeningcd):
        """Normaliseer tekeningcode: letter + 3-cijfer padding.

        Voorbeeld: 'B2' → 'B002', 'A15' → 'A015'
        """
        matchObj = self.RE_TEKENINGCD_NORM.match(tekeningcd)
        if matchObj:
            return matchObj.group(1) + str(int(matchObj.group(2))).zfill(3)
        return tekeningcd

    def normaliseer_rapportnr(self, rapportnr, brondata):
        """Normaliseer rapportnummer met Delftse DAR/DAN-conventie.

        Als het rapportnr alleen cijfers bevat, check dan of brondata
        een DARnr of DANnr veld bevat om het prefix te bepalen.
        """
        if str(rapportnr).isdigit():
            if isinstance(brondata, dict):
                for veld, prefix in self.RAPPORT_VELD_PREFIX_MAP.items():
                    if veld in brondata:
                        return prefix + str(int(rapportnr)).zfill(3)
            return ''
        else:
            matchObj = self.RE_RAPPORTNR_NORM.match(rapportnr)
            if matchObj:
                return matchObj.group(1) + str(int(matchObj.group(2))).zfill(3)
        return rapportnr
