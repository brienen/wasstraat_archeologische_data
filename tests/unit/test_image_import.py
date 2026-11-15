"""
Unit tests voor de extractie van afbeeldingen (wasstraat/image_import.py, issue 70).

Test met een nagebootste MongoDB (tests/unit/nep_mongo.py) en een nagebootste
image_util.adjustAndSaveFile die per bestand slaagt, niets opslaat, een gewone
fout geeft of een onherstelbare fout (vol volume, geen schrijfrechten):

- de status per bestand in Filenames (verwerkt, overgeslagen, mislukt);
- een vol volume als harde fout die de taak direct stopt;
- de tellingen en de drempel van de taak Controleer_Afbeeldingen, ook in het
  run-document van de incrementele cyclus;
- het opruimen van openstaande entries van verdwenen bestanden.
"""
import errno
import logging
import os
import sys
import types
from datetime import datetime, timedelta

import pytest
from bson import ObjectId

# Mock shared.image_util (wordt geïmporteerd door image_import.py, vereist PIL/pdf2image/magic)
if "shared.image_util" not in sys.modules:
    sys.modules["shared.image_util"] = types.ModuleType("shared.image_util")

import shared.config as config
import wasstraat.verwerkingsrun as verwerkingsrun
import wasstraat.image_import as image_import
from tests.unit.nep_mongo import NepClient


FOTO_MAP = '/input/projecten/SY001/L Fotos'


def foto(naam):
    return f'{FOTO_MAP}/{naam}'


def verpakAlsImageUtil(err):
    """Verpak een fout zoals image_util dat doet: twee keer 'raise Exception(...) from err'."""
    try:
        try:
            raise err
        except Exception as binnen:
            raise Exception(f"Onbekende fout bij het in grid plaatsen van image, met tekst: {binnen}") from binnen
    except Exception as midden:
        try:
            raise Exception(f"Onbekende fout bij het bewaren van image, met tekst: {midden}") from midden
        except Exception as buiten:
            return buiten


class NepAdjustAndSaveFile:
    """Nabootsing van image_util.adjustAndSaveFile; het gedrag hangt af van de bestandsnaam.

    - 'kapot' in de naam: gewone fout (onleesbaar bestand)
    - 'vol' in de naam: OSError ENOSPC (vol volume)
    - 'rechten_uit' in de naam: PermissionError op de uitvoermap
    - 'rechten_in' in de naam: PermissionError op het bronbestand
    - 'Sfeerfoto' in de naam: niets opgeslagen (None)
    - anders: geslaagd (een ObjectId)
    """

    def __init__(self, media):
        self.media = media
        self.aanroepen = []

    def __call__(self, fullfilename, fs, collection):
        self.aanroepen.append(fullfilename)
        naam = os.path.basename(fullfilename)
        if 'kapot' in naam:
            raise verpakAlsImageUtil(ValueError(f"cannot identify image file '{fullfilename}'"))
        if 'vol' in naam:
            raise verpakAlsImageUtil(OSError(errno.ENOSPC, 'No space left on device'))
        if 'rechten_uit' in naam:
            raise verpakAlsImageUtil(PermissionError(errno.EACCES, 'Permission denied', os.path.join(self.media, 'SY001', naam)))
        if 'rechten_in' in naam:
            raise verpakAlsImageUtil(PermissionError(errno.EACCES, 'Permission denied', fullfilename))
        if 'Sfeerfoto' in naam:
            return None
        return ObjectId()


@pytest.fixture
def nep_client(monkeypatch):
    """Vervang MongoClient en GridFS door een in-memory nabootsing."""
    client = NepClient()
    monkeypatch.setattr(image_import.pymongo, 'MongoClient', lambda *args, **kwargs: client)
    monkeypatch.setattr(verwerkingsrun, '_getClient', lambda: client)
    monkeypatch.setattr(image_import.gridfs, 'GridFS', lambda db: 'nep-gridfs')
    return client


@pytest.fixture
def media(tmp_path, monkeypatch):
    """Tijdelijke AIRFLOW_OUTPUT_MEDIA."""
    pad = tmp_path / 'archeomedia'
    monkeypatch.setattr(config, 'AIRFLOW_OUTPUT_MEDIA', str(pad))
    return str(pad)


@pytest.fixture
def adjust(media, monkeypatch):
    """Nagebootste adjustAndSaveFile."""
    nep = NepAdjustAndSaveFile(media)
    monkeypatch.setattr(image_import.image_util, 'adjustAndSaveFile', nep, raising=False)
    return nep


# Standaarddrempel uit shared/config.py (AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN en _PCT)
STANDAARD_MAX_MISLUKT = 10
STANDAARD_MAX_MISLUKT_PCT = 1.0


@pytest.fixture(autouse=True)
def standaardDrempel(monkeypatch):
    """Elke test begint met de standaarddrempel; een test die een andere wil, zet die zelf."""
    zetDrempel(monkeypatch, STANDAARD_MAX_MISLUKT, STANDAARD_MAX_MISLUKT_PCT)


def zetDrempel(monkeypatch, aantal=None, pct=None):
    """Zet de drempel in shared.config, zoals een omgevingsvariabele dat bij het starten doet."""
    if aantal is not None:
        monkeypatch.setattr(config, 'AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN', aantal)
    if pct is not None:
        monkeypatch.setattr(config, 'AIRFLOW_MAX_MISLUKTE_AFBEELDINGEN_PCT', pct)


def filenames(client):
    return client[config.DB_FILES][config.COLL_FILENAMES]


def vulFilenames(client, namen, **extra):
    """Zet bestanden in Filenames zoals getAndStoreImageFilenames (iter op volgorde, processed False)."""
    col = filenames(client)
    start = col.count_documents({})
    for i, naam in enumerate(namen):
        col.insert_one(dict({'iter': start + i, 'filename': foto(naam), 'processed': False}, **extra))
    return col


def docs(client):
    return {os.path.basename(d['filename']): d for d in filenames(client).find({})}


# ============================================================
# Status per bestand
# ============================================================

@pytest.mark.unit
class TestStatusPerBestand:
    """importImages legt per bestand eenduidig vast of het verwerkt, overgeslagen of mislukt is."""

    def test_geslaagd_bestand_is_verwerkt(self, nep_client, adjust):
        vulFilenames(nep_client, ['SY001_F001.jpg'])
        tellingen = image_import.importImages(0, 1)
        doc = docs(nep_client)['SY001_F001.jpg']
        assert doc['processed'] is True
        assert isinstance(doc['verwerkt_op'], datetime)
        assert 'overgeslagen' not in doc and 'fout' not in doc
        assert tellingen == {'verwerkt': 1, 'overgeslagen': 0, 'mislukt': 0}

    def test_fout_legt_melding_en_tijdstip_vast_en_gaat_door(self, nep_client, adjust):
        vulFilenames(nep_client, ['SY001_F001.jpg', 'SY001_kapot.jpg', 'SY001_F003.jpg'])
        tellingen = image_import.importImages(0, 1)
        d = docs(nep_client)
        assert d['SY001_kapot.jpg']['processed'] is False
        assert 'cannot identify image file' in d['SY001_kapot.jpg']['fout']
        assert isinstance(d['SY001_kapot.jpg']['fout_op'], datetime)
        assert 'verwerkt_op' not in d['SY001_kapot.jpg']
        assert d['SY001_F001.jpg']['processed'] is True and d['SY001_F003.jpg']['processed'] is True
        assert tellingen == {'verwerkt': 2, 'overgeslagen': 0, 'mislukt': 1}

    def test_lange_foutmelding_wordt_afgekapt(self, nep_client, adjust, monkeypatch):
        vulFilenames(nep_client, ['SY001_kapot.jpg'])
        monkeypatch.setattr(image_import, 'MAX_LENGTE_FOUT', 20)
        image_import.importImages(0, 1)
        assert len(docs(nep_client)['SY001_kapot.jpg']['fout']) == 20

    def test_sfeerfoto_is_overgeslagen_met_reden(self, nep_client, adjust):
        vulFilenames(nep_client, ['Sfeerfoto_SY001.jpg'])
        tellingen = image_import.importImages(0, 1)
        doc = docs(nep_client)['Sfeerfoto_SY001.jpg']
        assert doc['processed'] is True
        assert doc['overgeslagen'] == image_import.OVERGESLAGEN_GEEN_AFBEELDING
        assert isinstance(doc['verwerkt_op'], datetime)
        assert tellingen['overgeslagen'] == 1

    @pytest.mark.parametrize("naam", ['SY001_F002.tif', 'SY001_F002.pdf'])
    def test_tif_of_pdf_met_jpg_versie_is_overgeslagen(self, nep_client, adjust, naam):
        vulFilenames(nep_client, [naam, 'SY001_F002.jpg'])
        tellingen = image_import.importImages(0, 1)
        d = docs(nep_client)
        assert d[naam]['processed'] is True
        assert d[naam]['overgeslagen'] == image_import.OVERGESLAGEN_JPG_AANWEZIG
        assert foto(naam) not in adjust.aanroepen
        assert d['SY001_F002.jpg']['processed'] is True and 'overgeslagen' not in d['SY001_F002.jpg']
        assert tellingen == {'verwerkt': 1, 'overgeslagen': 1, 'mislukt': 0}

    def test_tif_zonder_jpg_versie_wordt_verwerkt(self, nep_client, adjust):
        vulFilenames(nep_client, ['SY001_F002.tif'])
        image_import.importImages(0, 1)
        doc = docs(nep_client)['SY001_F002.tif']
        assert doc['processed'] is True and 'overgeslagen' not in doc

    def test_nieuwe_poging_wist_eerdere_fout(self, nep_client, adjust):
        col = vulFilenames(nep_client, ['SY001_F001.jpg'], fout='eerdere fout', fout_op=datetime(2026, 10, 20))
        image_import.importImages(0, 1)
        doc = col.find_one({})
        assert doc['processed'] is True
        assert 'fout' not in doc and 'fout_op' not in doc

    def test_verwerkte_bestanden_worden_niet_opnieuw_verwerkt(self, nep_client, adjust):
        vulFilenames(nep_client, ['SY001_F001.jpg'], processed=True)
        vulFilenames(nep_client, ['SY001_F002.jpg'])
        image_import.importImages(0, 1)
        assert adjust.aanroepen == [foto('SY001_F002.jpg')]

    @pytest.mark.parametrize("aantal, blokken", [(7, 3), (2, 8), (16, 8)])
    def test_blokken_verwerken_elk_bestand_precies_een_keer(self, nep_client, adjust, aantal, blokken):
        vulFilenames(nep_client, [f'SY001_F{i:03d}.jpg' for i in range(aantal)])
        for index in range(blokken):
            image_import.importImages(index, blokken)
        assert sorted(adjust.aanroepen) == sorted(foto(f'SY001_F{i:03d}.jpg') for i in range(aantal))
        assert filenames(nep_client).count_documents(image_import.FILTER_VERWERKT) == aantal


# ============================================================
# Onherstelbare fouten
# ============================================================

@pytest.mark.unit
class TestOnherstelbareFouten:
    """Een vol volume of een niet-schrijfbare uitvoermap stopt de taak direct."""

    def test_vol_volume_stopt_de_taak_direct(self, nep_client, adjust, media):
        vulFilenames(nep_client, ['SY001_F001.jpg', 'SY001_vol.jpg', 'SY001_F003.jpg'])
        with pytest.raises(image_import.OnherstelbareFout) as exc:
            image_import.importImages(0, 1)
        melding = str(exc.value)
        assert 'volume is vol' in melding and media in melding and 'SY001_vol.jpg' in melding
        d = docs(nep_client)
        assert d['SY001_F001.jpg']['processed'] is True
        # Het bestand met de fout krijgt de foutmelding; het volgende bestand is niet meer geprobeerd
        assert d['SY001_vol.jpg']['processed'] is False and 'No space left on device' in d['SY001_vol.jpg']['fout']
        assert foto('SY001_F003.jpg') not in adjust.aanroepen
        assert d['SY001_F003.jpg']['processed'] is False and 'fout' not in d['SY001_F003.jpg']

    def test_onherstelbare_fout_wordt_niet_verpakt(self, nep_client, adjust):
        """De algemene foutafhandeling van importImages mag de OnherstelbareFout niet in een gewone Exception verpakken."""
        vulFilenames(nep_client, ['SY001_vol.jpg'])
        with pytest.raises(Exception) as exc:
            image_import.importImages(0, 1)
        assert type(exc.value) is image_import.OnherstelbareFout

    def test_geen_schrijfrechten_op_uitvoermap_stopt_de_taak(self, nep_client, adjust):
        vulFilenames(nep_client, ['SY001_rechten_uit.jpg', 'SY001_F002.jpg'])
        with pytest.raises(image_import.OnherstelbareFout) as exc:
            image_import.importImages(0, 1)
        assert 'geen schrijfrechten' in str(exc.value)
        assert foto('SY001_F002.jpg') not in adjust.aanroepen

    def test_geen_leesrechten_op_bronbestand_is_gewone_fout(self, nep_client, adjust):
        vulFilenames(nep_client, ['SY001_rechten_in.jpg', 'SY001_F002.jpg'])
        tellingen = image_import.importImages(0, 1)
        assert tellingen == {'verwerkt': 1, 'overgeslagen': 0, 'mislukt': 1}
        assert 'Permission denied' in docs(nep_client)['SY001_rechten_in.jpg']['fout']

    @pytest.mark.parametrize("nummer", [errno.ENOSPC, errno.EROFS, getattr(errno, 'EDQUOT', errno.ENOSPC)])
    def test_onherstelbare_errnos_in_geneste_oorzaak(self, nummer):
        err = verpakAlsImageUtil(OSError(nummer, os.strerror(nummer)))
        oorzaak = image_import.vindOnherstelbareOorzaak(err)
        assert isinstance(oorzaak, OSError) and oorzaak.errno == nummer

    @pytest.mark.parametrize("err", [
        ValueError("cannot identify image file"),
        OSError("image file is truncated"),
        FileNotFoundError(errno.ENOENT, 'No such file or directory', '/input/projecten/x.jpg'),
        PermissionError(errno.EACCES, 'Permission denied'),
    ])
    def test_gewone_fouten_zijn_niet_onherstelbaar(self, media, err):
        assert image_import.vindOnherstelbareOorzaak(verpakAlsImageUtil(err)) is None

    def test_uitvoermap_moet_echt_de_uitvoermap_zijn(self, media):
        """Een pad dat alleen met dezelfde tekens begint (archeomedia_oud) telt niet als uitvoermap."""
        err = PermissionError(errno.EACCES, 'Permission denied', media + '_oud/x.jpg')
        assert image_import.vindOnherstelbareOorzaak(err) is None
        err = PermissionError(errno.EACCES, 'Permission denied', media)
        assert image_import.vindOnherstelbareOorzaak(err) is err


# ============================================================
# Tellingen en drempel (Controleer_Afbeeldingen)
# ============================================================

def vulAlleStatussen(client, nu=None):
    """Filenames met twee verwerkte, twee overgeslagen, twee mislukte en een onverwerkt bestand."""
    nu = nu if nu else datetime(2026, 10, 21, 12, 0)
    col = filenames(client)
    col.insert_many([
        {'iter': 0, 'filename': foto('a.jpg'), 'processed': True, 'verwerkt_op': nu},
        {'iter': 1, 'filename': foto('b.jpg'), 'processed': True, 'verwerkt_op': nu},
        {'iter': 2, 'filename': foto('c.tif'), 'processed': True, 'verwerkt_op': nu,
         'overgeslagen': image_import.OVERGESLAGEN_JPG_AANWEZIG},
        {'iter': 3, 'filename': foto('Sfeerfoto.jpg'), 'processed': True, 'verwerkt_op': nu,
         'overgeslagen': image_import.OVERGESLAGEN_GEEN_AFBEELDING},
        {'iter': 4, 'filename': foto('z_kapot.jpg'), 'processed': False, 'fout': 'kapot', 'fout_op': nu},
        {'iter': 5, 'filename': foto('y_kapot.jpg'), 'processed': False, 'fout': 'ook kapot', 'fout_op': nu},
        {'iter': 6, 'filename': foto('x_open.jpg'), 'processed': False},
    ])
    return col


@pytest.mark.unit
class TestTellingenEnDrempel:
    """telAfbeeldingStatussen, bepaalDrempel en de taak controleerAfbeeldingen."""

    @pytest.mark.parametrize("totaal, aantal, pct, verwacht", [
        (541, 10, 1.0, 10),        # Delftse testdata: het vaste aantal telt
        (100000, 10, 1.0, 1000),   # grote verzameling: het percentage telt
        (100000, 10, 0, 10),
        (50, 0, 0, 0),             # elke fout is te veel
        (0, 10, 1.0, 10),
    ])
    def test_drempel_is_grootste_van_aantal_en_percentage(self, totaal, aantal, pct, verwacht):
        assert image_import.bepaalDrempel(totaal, aantal, pct) == verwacht

    def test_drempel_komt_uit_config(self, monkeypatch):
        """De drempel staat in shared/config.py, net als de andere drempels (tests/unit/test_config.py)."""
        zetDrempel(monkeypatch, 7, 2.5)
        assert image_import.leesDrempels() == (7, 2.5)
        assert not hasattr(image_import, 'leesGetalUitOmgeving')

    def test_tellingen_per_status(self, nep_client):
        col = vulAlleStatussen(nep_client)
        tellingen = image_import.telAfbeeldingStatussen(col)
        assert {k: tellingen[k] for k in ['totaal', 'verwerkt', 'overgeslagen', 'mislukt', 'onverwerkt']} == \
            {'totaal': 7, 'verwerkt': 2, 'overgeslagen': 2, 'mislukt': 2, 'onverwerkt': 1}
        assert tellingen['overgeslagen_per_reden'] == {image_import.OVERGESLAGEN_JPG_AANWEZIG: 1,
                                                       image_import.OVERGESLAGEN_GEEN_AFBEELDING: 1}
        # Voorbeelden: de niet-verwerkte bestanden op naam gesorteerd, met foutmelding
        assert [os.path.basename(v['filename']) for v in tellingen['voorbeelden']] == \
            ['x_open.jpg', 'y_kapot.jpg', 'z_kapot.jpg']
        assert tellingen['voorbeelden'][1]['fout'] == 'ook kapot'

    def test_aantal_voorbeelden_is_begrensd(self, nep_client, monkeypatch):
        monkeypatch.setattr(image_import, 'MAX_VOORBEELDEN', 2)
        col = vulAlleStatussen(nep_client)
        assert len(image_import.telAfbeeldingStatussen(col)['voorbeelden']) == 2

    def test_alles_verwerkt_logt_alleen_informatie(self, nep_client, caplog):
        vulFilenames(nep_client, ['a.jpg'], processed=True, verwerkt_op=datetime(2026, 10, 21))
        with caplog.at_level(logging.INFO, logger='airflow.task'):
            image_import.controleerAfbeeldingen()
        assert 'Controle afbeeldingen: 1 bestanden, 1 verwerkt' in caplog.text
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_onder_drempel_waarschuwing_met_lijst(self, nep_client, caplog):
        vulAlleStatussen(nep_client)
        with caplog.at_level(logging.INFO, logger='airflow.task'):
            image_import.controleerAfbeeldingen()
        waarschuwingen = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert len(waarschuwingen) == 1
        assert '3 afbeeldingen en rapporten niet verwerkt (2 mislukt, 1 onverwerkt)' in waarschuwingen[0]
        assert 'z_kapot.jpg: kapot' in waarschuwingen[0]
        assert 'x_open.jpg: niet verwerkt (geen foutmelding)' in waarschuwingen[0]

    def test_boven_drempel_faalt_de_taak(self, nep_client, monkeypatch):
        vulAlleStatussen(nep_client)
        zetDrempel(monkeypatch, aantal=2)
        with pytest.raises(image_import.OnherstelbareFout) as exc:
            image_import.controleerAfbeeldingen()
        melding = str(exc.value)
        assert '3 van de 7' in melding and 'drempel van 2' in melding
        assert 'y_kapot.jpg: ook kapot' in melding
        assert image_import.OMGEVING_MAX_MISLUKT in melding

    def test_precies_op_drempel_faalt_niet(self, nep_client, monkeypatch):
        vulAlleStatussen(nep_client)
        zetDrempel(monkeypatch, aantal=3)
        image_import.controleerAfbeeldingen()

    def test_percentage_verhoogt_de_drempel(self, nep_client, monkeypatch):
        vulAlleStatussen(nep_client)
        zetDrempel(monkeypatch, aantal=0)
        zetDrempel(monkeypatch, pct=50)    # 50% van 7 = 3
        image_import.controleerAfbeeldingen()
        zetDrempel(monkeypatch, pct=40)    # 40% van 7 = 2
        with pytest.raises(image_import.OnherstelbareFout):
            image_import.controleerAfbeeldingen()

    def test_onverwerkte_bestanden_tellen_mee(self, nep_client, monkeypatch):
        vulFilenames(nep_client, ['a.jpg', 'b.jpg'])
        zetDrempel(monkeypatch, aantal=1)
        with pytest.raises(image_import.OnherstelbareFout) as exc:
            image_import.controleerAfbeeldingen()
        assert '0 mislukt, 2 onverwerkt' in str(exc.value)

    def test_volledige_cyclus_heeft_geen_run_document_nodig(self, nep_client):
        vulAlleStatussen(nep_client)
        image_import.controleerAfbeeldingen(incrementeel=False)
        assert verwerkingsrun.huidigeRun(verplicht=False) is None

    def test_import_gevolgd_door_controle(self, nep_client, adjust, monkeypatch):
        """Van import tot controle: één mislukt bestand blijft onder de standaarddrempel, nul is te veel."""
        vulFilenames(nep_client, ['SY001_F001.jpg', 'SY001_kapot.jpg', 'Sfeerfoto_1.jpg', 'SY001_F002.tif',
                                  'SY001_F002.jpg'])
        for index in range(2):
            image_import.importImages(index, 2)
        image_import.controleerAfbeeldingen()
        zetDrempel(monkeypatch, aantal=0)
        with pytest.raises(image_import.OnherstelbareFout):
            image_import.controleerAfbeeldingen()


@pytest.mark.unit
class TestTellingenIncrementeel:
    """In de incrementele cyclus komen de tellingen in het run-document."""

    def test_tellingen_in_run_document_alleen_van_deze_run(self, nep_client, adjust):
        # Uit een eerdere run: verwerkt en overgeslagen vóór de start van deze run, één nog mislukt
        lang_geleden = datetime(2026, 1, 1)
        vulFilenames(nep_client, ['oud_1.jpg', 'oud_2.jpg'], processed=True, verwerkt_op=lang_geleden)
        vulFilenames(nep_client, ['oud.tif'], processed=True, verwerkt_op=lang_geleden,
                     overgeslagen=image_import.OVERGESLAGEN_JPG_AANWEZIG)
        vulFilenames(nep_client, ['oud_kapot.jpg'], fout='kapot', fout_op=lang_geleden)
        verwerkingsrun.startRun(verwerkingsrun.SOORT_INCREMENTEEL)
        # Nieuw in deze run
        vulFilenames(nep_client, ['SY003_F001.jpg', 'SY003_F002.jpg'])
        image_import.importImages(0, 1)

        image_import.controleerAfbeeldingen(incrementeel=True)

        tellingen = verwerkingsrun.huidigeRun()['tellingen']['afbeeldingen']
        assert {k: tellingen[k] for k in ['totaal', 'verwerkt', 'overgeslagen', 'mislukt', 'onverwerkt']} == \
            {'totaal': 3, 'verwerkt': 2, 'overgeslagen': 0, 'mislukt': 1, 'onverwerkt': 0}
        assert tellingen['drempel'] == STANDAARD_MAX_MISLUKT
        assert tellingen['boven_drempel'] is False
        assert [os.path.basename(v['filename']) for v in tellingen['voorbeelden']] == ['oud_kapot.jpg']
        assert 'kapot' in tellingen['voorbeelden'][0]['fout']

    def test_tellingen_in_run_document_ook_als_controle_faalt(self, nep_client, adjust, monkeypatch):
        verwerkingsrun.startRun(verwerkingsrun.SOORT_INCREMENTEEL)
        vulFilenames(nep_client, ['SY003_kapot.jpg', 'SY003_F002.jpg'])
        image_import.importImages(0, 1)
        zetDrempel(monkeypatch, aantal=0)
        with pytest.raises(image_import.OnherstelbareFout):
            image_import.controleerAfbeeldingen(incrementeel=True)
        tellingen = verwerkingsrun.huidigeRun()['tellingen']['afbeeldingen']
        assert tellingen['mislukt'] == 1 and tellingen['verwerkt'] == 1
        assert tellingen['boven_drempel'] is True and tellingen['drempel'] == 0

    def test_incrementeel_vereist_actieve_run(self, nep_client):
        with pytest.raises(Exception, match='Geen actieve verwerkingsrun'):
            image_import.controleerAfbeeldingen(incrementeel=True)


@pytest.mark.unit
class TestOpenstaandeEntriesVanVerdwenenBestanden:
    """voegImageFilenamesToe ruimt openstaande entries op van bestanden die niet meer bestaan."""

    def test_verdwenen_openstaand_bestand_verwijderd(self, nep_client, tmp_path):
        bestaand = tmp_path / 'SY003_bestaat.jpg'
        bestaand.write_bytes(b'jpg')
        col = filenames(nep_client)
        col.insert_many([
            {'iter': 0, 'filename': '/input/projecten/SY003/L Fotos/SY003_weg.jpg', 'processed': False, 'fout': 'kapot'},
            {'iter': 1, 'filename': str(bestaand), 'processed': False, 'fout': 'kapot'},
            {'iter': 2, 'filename': '/input/projecten/SY001/L Fotos/SY001_F001.jpg', 'processed': True},
        ])
        image_import.voegImageFilenamesToe([])
        assert sorted(d['filename'] for d in col.find({})) == sorted(
            [str(bestaand), '/input/projecten/SY001/L Fotos/SY001_F001.jpg'])

    def test_nieuwe_entries_blijven_staan(self, nep_client):
        """De nieuwe paden worden ná het opruimen toegevoegd (in de unit test bestaan ze niet op schijf)."""
        image_import.voegImageFilenamesToe(['/input/projecten/SY003/L Fotos/SY003_F001.jpg'])
        assert filenames(nep_client).count_documents({'processed': False}) == 1
