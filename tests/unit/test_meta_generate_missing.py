"""
Unit tests voor de 'generate missing'-pipelines in wasstraat/meta.py.

Transform5 maakt Put, Vlak, Spoor, Vondst en Doos aan voor elk putnr, vlaknr
enzovoort dat in de data voorkomt maar geen eigen record heeft. Bronnen zonder
PUT- of VLAK-tabel (de synthetische data, de meeste Delftse projecten) krijgen
hun putten en vlakken alleen via deze stap.

Van 2023-03 tot 2026-10 stond in deze pipelines "＄ne" (volbreedte-dollarteken,
U+FF04) in plaats van "$ne". MongoDB ziet dat niet als operator, waardoor de
stap stilletjes niets opleverde. Na herstel bleken nog drie fouten die al die
tijd verborgen waren: mergeMissing crashte als een soort nog geen enkel record
had, en gegenereerde vondsten en sporen kregen een andere key dan de bestaande.
"""
import types

import pytest

from wasstraat.meta import (
    wasstraat_model,
    getKeys,
    getGenerateMissingPipelines,
    MOVEANDMERGE_GENERATE_MISSING_PIPELINES,
)


def verzamelSleutels(obj):
    """Verzamel recursief alle dictionary-sleutels uit een pipeline-structuur.

    Args:
        obj: Dict, lijst of scalaire waarde uit wasstraat_model

    Returns:
        Lijst met alle sleutels (strings) die in de structuur voorkomen
    """
    sleutels = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            sleutels.append(k)
            sleutels.extend(verzamelSleutels(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            sleutels.extend(verzamelSleutels(item))
    return sleutels


@pytest.mark.unit
class TestOperatorTekens:
    """Alle MongoDB-operatoren in meta.py moeten een gewoon dollarteken hebben."""

    @pytest.mark.parametrize("soort", sorted(wasstraat_model.keys()))
    def test_sleutels_zijn_ascii(self, soort):
        """Geen sleutel mag niet-ASCII-tekens bevatten, zoals een volbreedte-dollarteken."""
        foute = [k for k in verzamelSleutels(wasstraat_model[soort])
                 if isinstance(k, str) and not k.isascii()]
        assert not foute, (
            f"{soort} bevat sleutels met niet-ASCII-tekens: {[ascii(k) for k in foute]}. "
            f"MongoDB herkent bijvoorbeeld '\\uff04ne' niet als operator; gebruik '$ne'."
        )

    @pytest.mark.parametrize("soort", getKeys(MOVEANDMERGE_GENERATE_MISSING_PIPELINES))
    def test_generate_missing_pipelines_zijn_ascii(self, soort):
        """De samengestelde generate-missing pipelines bevatten alleen ASCII-sleutels."""
        for pipeline in getGenerateMissingPipelines(soort):
            foute = [k for k in verzamelSleutels(pipeline)
                     if isinstance(k, str) and not k.isascii()]
            assert not foute, f"{soort}: niet-ASCII-sleutels {[ascii(k) for k in foute]}"


@pytest.mark.unit
class TestGenerateMissingPipelines:
    """De generate-missing pipelines moeten nulwaarden filteren met $ne."""

    @pytest.mark.parametrize("soort,veld", [
        ("Put", "putnr"),
        ("Vlak", "vlaknr"),
        ("Spoor", "spoornr"),
        ("Vondst", "vondstnr"),
        ("Doos", "doosnr"),
    ])
    def test_filter_op_nul_gebruikt_ne(self, soort, veld):
        """De tweede $match-stage filtert het nummerveld met {'$ne': 0}."""
        pipeline = wasstraat_model[soort][MOVEANDMERGE_GENERATE_MISSING_PIPELINES][0]
        filters = [stage["$match"][veld] for stage in pipeline
                   if "$match" in stage and isinstance(stage["$match"].get(veld), dict)
                   and "$exists" not in stage["$match"][veld]]
        assert filters == [{"$ne": 0}], (
            f"{soort}: verwacht filter {{'$ne': 0}} op {veld}, gevonden {filters}"
        )

    def test_put_en_vlak_worden_gegenereerd(self):
        """Put en Vlak moeten een generate-missing pipeline hebben."""
        soorten = getKeys(MOVEANDMERGE_GENERATE_MISSING_PIPELINES)
        assert "Put" in soorten
        assert "Vlak" in soorten

    @pytest.mark.parametrize("soort", ["Put", "Vlak"])
    def test_gegenereerde_pipeline_zet_key(self, soort):
        """De samengestelde pipeline eindigt met de key-generatie van de soort."""
        pipeline = getGenerateMissingPipelines(soort)[0]
        velden = [k for stage in pipeline for k in stage.get("$addFields", {})]
        assert "key" in velden
        assert "key_project" in velden


def _groupStage(soort):
    """Geef de $group-stage van de generate-missing pipeline van een soort."""
    pipeline = wasstraat_model[soort][MOVEANDMERGE_GENERATE_MISSING_PIPELINES][0]
    return next(stage["$group"] for stage in pipeline if "$group" in stage)


def _projectStage(soort):
    """Geef de $project-stage van de generate-missing pipeline van een soort."""
    pipeline = wasstraat_model[soort][MOVEANDMERGE_GENERATE_MISSING_PIPELINES][0]
    return next(stage["$project"] for stage in pipeline if "$project" in stage)


@pytest.mark.unit
class TestGegenereerdeKeysGelijkAanBestaande:
    """Een gegenereerd record moet dezelfde key krijgen als een bestaand record,
    anders ontstaan dubbele vondsten en sporen in plaats van alleen ontbrekende."""

    def test_vondst_neemt_vondstkey_met_putnr_mee(self):
        """aggr_key_vondst gebruikt vondstkey_met_putnr; de generator moet die doorgeven."""
        assert "vondstkey_met_putnr" in _groupStage("Vondst")
        assert "vondstkey_met_putnr" in _projectStage("Vondst")

    def test_spoor_groepeert_niet_op_vlaknr(self):
        """Sporen uit de brondata hebben vlaknrs (meervoud) en dus geen vlak in de key."""
        assert "vlaknr" not in _groupStage("Spoor")["_id"]
        assert "vlaknr" not in _projectStage("Spoor")


class NepCollectie:
    """Minimale vervanger van een pymongo-collectie voor mergeMissing."""

    def __init__(self, aggregate_resultaat=None, docs=None):
        self.aggregate_resultaat = aggregate_resultaat or []
        self.docs = docs or []
        self.ingevoegd = []
        self.database = types.SimpleNamespace(client=types.SimpleNamespace(close=lambda: None))

    def aggregate(self, aggr, **kwargs):
        return iter([dict(d) for d in self.aggregate_resultaat])

    def find(self, query, *args, **kwargs):
        return [dict(d) for d in self.docs if all(d.get(k) == v for k, v in query.items())]

    def bulk_write(self, operaties):
        self.ingevoegd.extend(op._doc for op in operaties)


@pytest.mark.unit
class TestMergeMissing:
    """mergeMissing voegt alleen records in waarvan de key nog niet bestaat."""

    GEGENEREERD = [
        {"key": "PSY001P1", "soort": "Put", "projectcd": "SY001", "putnr": 1},
        {"key": "PSY001P2", "soort": "Put", "projectcd": "SY001", "putnr": 2},
    ]

    def _draai(self, monkeypatch, bestaande_docs):
        import wasstraat.merge_functions as merge_functions
        analyse = NepCollectie(aggregate_resultaat=self.GEGENEREERD)
        clean = NepCollectie(docs=bestaande_docs)
        monkeypatch.setattr(merge_functions, "getAnalyseCollection", lambda: analyse)
        monkeypatch.setattr(merge_functions, "getAnalyseCleanCollection", lambda: clean)
        merge_functions.mergeMissing("Put")
        return sorted(d["key"] for d in clean.ingevoegd)

    def test_alles_ingevoegd_als_soort_nog_niet_bestaat(self, monkeypatch):
        """Zonder PUT-tabel bestaat nog geen enkele Put: alle gegenereerde worden ingevoegd."""
        assert self._draai(monkeypatch, []) == ["PSY001P1", "PSY001P2"]

    def test_alleen_ontbrekende_ingevoegd(self, monkeypatch):
        """Een Put die al bestaat (uit een PUT-tabel) wordt niet nogmaals ingevoegd."""
        bestaand = [{"_id": 1, "key": "PSY001P1", "soort": "Put", "putnr": 1, "beschrijving": "uit PUT-tabel"}]
        assert self._draai(monkeypatch, bestaand) == ["PSY001P2"]
