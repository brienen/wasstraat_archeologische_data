"""
Unit tests voor app/app/models.py

Test model-definities, enum-waarden en polymorphic inheritance.
Gebruikt geen database — alleen klasse-inspectie.
"""
import pytest
import sys
import os

_app_path = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'app')
if os.path.abspath(_app_path) not in sys.path:
    sys.path.insert(0, os.path.abspath(_app_path))
_app_root = os.path.join(os.path.dirname(__file__), '..', '..', 'app')
if os.path.abspath(_app_root) not in sys.path:
    sys.path.insert(0, os.path.abspath(_app_root))


class TestDiscrArtefactsoortEnum:
    """Test de artefactsoort enum waarden."""

    def test_all_expected_types_present(self):
        from models import DiscrArtefactsoortEnum
        expected = [
            'Aardewerk', 'Glas', 'Metaal', 'Hout', 'Steen', 'Leer',
            'Dierlijk_Bot', 'Menselijk_Bot', 'Kleipijp', 'Bouwaardewerk',
            'Munt', 'Schelp', 'Textiel', 'Onbekend'
        ]
        members = [e.name for e in DiscrArtefactsoortEnum]
        for name in expected:
            assert name in members, f"{name} ontbreekt in DiscrArtefactsoortEnum"

    def test_enum_values_are_strings(self):
        from models import DiscrArtefactsoortEnum
        for e in DiscrArtefactsoortEnum:
            assert isinstance(e.value, str)


class TestArtefactPolymorphism:
    """Test dat artefact-subtypes correct polymorphic identity hebben."""

    @pytest.mark.parametrize("model_name,expected_identity", [
        ("Aardewerk", "Aardewerk"),
        ("Glas", "Glas"),
        ("Metaal", "Metaal"),
        ("Hout", "Hout"),
        ("Steen", "Steen"),
        ("Leer", "Leer"),
        ("Dierlijk_Bot", "Dierlijk_Bot"),
        ("Menselijk_Bot", "Menselijk_Bot"),
        ("Kleipijp", "Kleipijp"),
        ("Bouwaardewerk", "Bouwaardewerk"),
        ("Munt", "Munt"),
        ("Schelp", "Schelp"),
        ("Textiel", "Textiel"),
    ])
    def test_artefact_subtype_identity(self, model_name, expected_identity):
        import models
        model_cls = getattr(models, model_name)
        identity = model_cls.__mapper_args__['polymorphic_identity']
        # Identity kan een enum zijn of een string
        if hasattr(identity, 'value'):
            assert identity.value == expected_identity
        else:
            assert identity == expected_identity


class TestBestandPolymorphism:
    """Test dat bestand-subtypes correct polymorphic identity hebben."""

    @pytest.mark.parametrize("model_name", [
        "Objectfoto", "Opgravingsfoto", "Overige_foto", "Sfeerfoto",
        "Veldtekening", "Overzichtstekening", "Objecttekening",
        "Archeologische_Rapportage", "Conserveringsrapport",
    ])
    def test_bestand_subtype_exists(self, model_name):
        import models
        model_cls = getattr(models, model_name)
        assert hasattr(model_cls, '__mapper_args__')
        assert 'polymorphic_identity' in model_cls.__mapper_args__


class TestCoreModels:
    """Test dat kernmodellen de verwachte kolommen hebben."""

    def test_project_has_location(self):
        import models
        assert hasattr(models.Project, 'location')

    def test_project_has_projectcd(self):
        import models
        assert hasattr(models.Project, 'projectcd')

    def test_artefact_has_primary_key(self):
        import models
        assert hasattr(models.Artefact, 'primary_key')

    def test_artefact_has_artefactsoort(self):
        import models
        assert hasattr(models.Artefact, 'artefactsoort')

    def test_vondst_has_vondstnr(self):
        import models
        assert hasattr(models.Vondst, 'vondstnr')

    def test_spoor_has_spoornr(self):
        import models
        assert hasattr(models.Spoor, 'spoornr')

    def test_put_has_putnr(self):
        import models
        assert hasattr(models.Put, 'putnr')

    def test_bestand_has_bestandsoort(self):
        import models
        assert hasattr(models.Bestand, 'bestandsoort')

    def test_abr_has_uri(self):
        import models
        assert hasattr(models.ABR, 'uri')

    def test_abr_has_parent_relationship(self):
        import models
        assert hasattr(models.ABR, 'parentID')


class TestModelImports:
    """Test dat alle modellen importeerbaar zijn."""

    @pytest.mark.parametrize("model_name", [
        "Project", "Put", "Vlak", "Spoor", "Vulling", "Vondst",
        "Artefact", "Bestand", "ABR", "Doos", "Stelling", "Vindplaats",
        "Standplaats", "Plaatsing", "Partij", "Bruikleen", "Monster",
    ])
    def test_model_importable(self, model_name):
        import models
        model_cls = getattr(models, model_name, None)
        assert model_cls is not None, f"Model {model_name} niet gevonden"


@pytest.mark.unit
class TestVerdwenenUitBrondata:
    """Issue 73: bruikleen en conservering blijven bestaan als hun artefact of project verdwijnt."""

    def test_schema_past_bij_verwijzingen_van_de_laadstap(self):
        """Elke verwijzing met beleid LOSKOPPELEN is nullable en heeft de kolommen van de markering.

        De laadstap migreert bestaande tabellen naar dit schema (shared/gebruikersdata.migreerSchema);
        een nieuwe database krijgt het via db.create_all() uit models.py.
        """
        import models
        import shared.gebruikersdata as gebruikersdata
        from sqlalchemy import DateTime, Text
        types = {'TEXT': Text, 'TIMESTAMP': DateTime}
        for verwijzing in gebruikersdata.VERWIJZINGEN:
            tabel = models.Model.metadata.tables[verwijzing['tabel']]
            kolom = tabel.c[verwijzing['kolom']]
            assert [fk.column.table.name for fk in kolom.foreign_keys] == [verwijzing['doel']]
            if verwijzing['beleid'] != gebruikersdata.LOSKOPPELEN:
                continue
            assert kolom.nullable, f"{verwijzing['tabel']}.{verwijzing['kolom']} moet leeg kunnen zijn"
            for naam, sql_type in gebruikersdata.getMarkeringKolommen(verwijzing):
                assert naam in tabel.c, f"{verwijzing['tabel']} mist de kolom {naam}"
                assert isinstance(tabel.c[naam].type, types[sql_type]) and tabel.c[naam].nullable

    def test_partij_blijft_verplicht(self):
        import models
        assert not models.Bruikleen.__table__.c.partijID.nullable

    def test_tekst_verdwenen(self):
        import datetime
        import models
        op = datetime.datetime(2026, 10, 22, 14, 3)
        assert models.tekstVerdwenen('Artefact', 'PSY003P1V1A1|Glas', op) == \
            'Artefact PSY003P1V1A1|Glas verdwenen op 22-10-2026'
        assert models.tekstVerdwenen('Artefact', None, op) == 'Artefact (key onbekend) verdwenen op 22-10-2026'
        assert models.tekstVerdwenen('Project', None, None) == ''

    def test_bruikleen_zonder_artefact(self):
        import datetime
        import models
        op = datetime.datetime(2026, 10, 22)
        bruikleen = models.Bruikleen(datum_uitgeleend=datetime.date(2026, 10, 1),
                                     artefact_verdwenen_key='PSY003P1V1A1|Glas', artefact_verdwenen_op=op,
                                     project_verdwenen_key='PSY003', project_verdwenen_op=op)
        assert bruikleen.verdwenen() == ('Artefact PSY003P1V1A1|Glas verdwenen op 22-10-2026; '
                                       'Project PSY003 verdwenen op 22-10-2026')
        assert repr(bruikleen).startswith('Artefact PSY003P1V1A1|Glas verdwenen op 22-10-2026 aan: ')
        assert models.Bruikleen(datum_uitgeleend=datetime.date(2026, 10, 1)).verdwenen() == ''

    def test_markering_bij_verwijderen_in_de_webapplicatie(self):
        """modelevents.markeerBruiklenen vult de markering als een gebruiker een artefact of project verwijdert.

        Alleen de functie wordt geladen: modelevents registreert bij het importeren een
        listener op alle sessies, die andere tests zou beïnvloeden.
        """
        import ast
        import datetime
        import models
        pad = os.path.join(os.path.dirname(__file__), '..', '..', 'app', 'app', 'modelevents.py')
        with open(pad) as f:
            boom = ast.parse(f.read())
        functie = next(n for n in boom.body if isinstance(n, ast.FunctionDef) and n.name == 'markeerBruiklenen')
        ns = {'Artefact': models.Artefact, 'datetime': datetime}
        exec(compile(ast.Module(body=[functie], type_ignores=[]), pad, 'exec'), ns)

        bruikleen = models.Bruikleen(datum_uitgeleend=datetime.date(2026, 10, 1))
        artefact = models.Artefact(key='PSY001P1V1A1|Glas', bruiklenen=[bruikleen])
        ns['markeerBruiklenen'](artefact)
        assert bruikleen.artefact_verdwenen_key == 'PSY001P1V1A1|Glas'
        assert isinstance(bruikleen.artefact_verdwenen_op, datetime.datetime)
        assert bruikleen.project_verdwenen_key is None

        project = models.Project(key='PSY001', bruiklenen=[bruikleen])
        ns['markeerBruiklenen'](project)
        assert bruikleen.project_verdwenen_key == 'PSY001'
