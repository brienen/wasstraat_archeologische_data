"""
Unit tests voor wasstraat/harmonizer.py

Test de opbouw van MongoDB aggregation pipelines op basis van
het Excel-configuratiebestand (Wasstraat_Config_HarmonizeV3.xlsx).
"""
import pytest
import os
import pandas as pd
import ast
import copy

from unittest.mock import patch

import wasstraat.harmonizer as harmonizer
from wasstraat.harmonizer import (
    getAggrTables, getKolomValues, getAttributes, initAttributes,
    createAggr, loadHarmonizer, getHarmonizeAggr
)


# ============================================================
# getKolomValues — genereert $ifNull-keten voor fallback-kolommen
# ============================================================

class TestGetKolomValues:

    def test_single_column(self):
        result = getKolomValues(["PUT"])
        assert result == "$brondata.PUT"

    def test_two_columns(self):
        result = getKolomValues(["PUT", "PUTNO"])
        assert result == {"$ifNull": ["$brondata.PUT", "$brondata.PUTNO"]}

    def test_three_columns(self):
        result = getKolomValues(["PUT", "PUTNO", "PUTNUMMER"])
        assert result["$ifNull"][0] == "$brondata.PUT"
        assert result["$ifNull"][1]["$ifNull"][0] == "$brondata.PUTNO"

    def test_empty_list(self):
        result = getKolomValues([])
        assert result is None


# ============================================================
# getAggrTables — genereert regex-match voor tabelnamen
# ============================================================

class TestGetAggrTables:

    def test_single_pattern_include(self):
        root = {}
        result = getAggrTables(root, '["^SPOREN$"]', True)
        assert "table" in result
        # Moet een gecompileerde regex zijn
        assert hasattr(result["table"], "pattern")

    def test_multiple_patterns_include(self):
        root = {}
        result = getAggrTables(root, '["^SPOREN$", "^SPOOR$"]', True)
        assert "$or" in result
        assert len(result["$or"]) == 2

    def test_single_pattern_exclude(self):
        root = {}
        result = getAggrTables(root, '[".*backup.*"]', False)
        assert "table" in result
        assert "$not" in result["table"]

    def test_empty_list_include(self):
        root = {}
        result = getAggrTables(root, '[]', True)
        assert "table" in result
        assert "$in" in result["table"]


# ============================================================
# loadHarmonizer — laadt het volledige Excel-configuratiebestand
# ============================================================

def _load_harmonizer_df():
    """Laad het harmonizer-dataframe uit het echte configuratiebestand."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data", "test", "wasstraat_config", "Wasstraat_Config_HarmonizeV3.xlsx"
    )
    if not os.path.exists(config_path):
        return None
    return loadHarmonizer()

# Module-level cache
_HARMONIZER_DF = None


def _get_harmonizer_df():
    global _HARMONIZER_DF
    if _HARMONIZER_DF is None:
        _HARMONIZER_DF = _load_harmonizer_df()
    return _HARMONIZER_DF


class TestLoadHarmonizer:

    def _get_df(self):
        df = _get_harmonizer_df()
        assert df is not None, "Wasstraat_Config_HarmonizeV3.xlsx niet gevonden — skip"
        return df

    def test_returns_dataframe(self):
        assert isinstance(self._get_df(), pd.DataFrame)

    def test_has_required_columns(self):
        df = self._get_df()
        for col in ["Object", "Tabellen", "aggr"]:
            assert col in df.columns

    def test_contains_known_objects(self):
        df = self._get_df()
        objects = set(df["Object"])
        for expected in ["Vondst", "Spoor", "Put", "Artefact", "Aardewerk", "Glas"]:
            assert expected in objects, f"{expected} ontbreekt in Objecten"

    def test_aggr_is_list(self):
        """Elke aggregation pipeline moet een lijst van stages zijn."""
        df = self._get_df()
        for _, row in df.iterrows():
            assert isinstance(row["aggr"], list), f"aggr van {row['Object']} is geen list"
            assert len(row["aggr"]) >= 4, f"aggr van {row['Object']} heeft te weinig stages"

    def test_aggr_has_match_and_merge(self):
        """Elke pipeline begint met $match en eindigt met $merge."""
        df = self._get_df()
        for _, row in df.iterrows():
            aggr = row["aggr"]
            assert "$match" in aggr[0], f"{row['Object']}: eerste stage is geen $match"
            assert "$merge" in aggr[-1], f"{row['Object']}: laatste stage is geen $merge"

    def test_artefact_child_has_addfields_with_soort(self):
        """Artefact-kinderen (Aardewerk, Glas, etc.) moeten 'soort' in $addFields hebben."""
        df = self._get_df()
        children = df[df["Object"] == "Aardewerk"]
        assert len(children) == 1
        aggr = children.iloc[0]["aggr"]
        soort_found = any(
            "$addFields" in stage and "soort" in stage["$addFields"]
            for stage in aggr
        )
        assert soort_found, "Aardewerk-pipeline mist 'soort' in $addFields"

    def test_inherited_artefact_has_parent_fields(self):
        """Aardewerk-pipeline moet overgeërfde velden van Artefact bevatten."""
        df = self._get_df()
        aardewerk = df[df["Object"] == "Aardewerk"].iloc[0]["aggr"]
        addfields_count = sum(1 for stage in aardewerk if "$addFields" in stage)
        assert addfields_count >= 2, "Aardewerk heeft te weinig $addFields (verwacht overerving)"


# ============================================================
# getHarmonizeAggr — ophalen van pipeline per objecttype
# ============================================================

class TestGetHarmonizeAggr:

    def test_valid_object(self):
        aggr = getHarmonizeAggr("Vondst", reload=True)
        assert isinstance(aggr, list)
        assert len(aggr) >= 4

    def test_invalid_object_returns_error(self):
        """Niet-bestaand object moet een exception geven."""
        try:
            getHarmonizeAggr("NietBestaandObject", reload=True)
            assert False, "Verwachtte een exception maar die kwam niet"
        except Exception:
            pass  # verwacht

    def test_artefact_child_has_artefactsoort(self):
        """Artefact-kinderen krijgen een extra $addFields met artefactsoort."""
        aggr = getHarmonizeAggr("Aardewerk", reload=True)
        artefact_stages = [
            s for s in aggr
            if "$addFields" in s and "artefactsoort" in s.get("$addFields", {})
        ]
        assert len(artefact_stages) > 0, "Aardewerk mist artefactsoort $addFields"

    def test_twee_aanroepen_leveren_dezelfde_pipeline(self, monkeypatch):
        """De pipeline in het (gecachete) DataFrame krijgt er per aanroep geen fase bij."""
        bron = [{'$match': {'table': 'AARDEWERK'}}, {'$addFields': {'x': 1}},
                {'$merge': {'into': 'Single_Store', 'on': '_id'}}]
        df = pd.DataFrame({'Object': ['Aardewerk'], 'aggr': [copy.deepcopy(bron)]})
        monkeypatch.setattr(harmonizer, 'loadHarmonizer', lambda: df)
        harmonizer.resetHarmonizer()
        try:
            eerste = harmonizer.getHarmonizeAggr('Aardewerk')
            tweede = harmonizer.getHarmonizeAggr('Aardewerk')
        finally:
            # Het nep-DataFrame mag niet in de cache blijven voor de volgende tests
            harmonizer.resetHarmonizer()

        assert eerste == tweede
        assert sum(1 for fase in tweede if 'artefactsoort' in fase.get('$addFields', {})) == 1
        assert tweede[-1] == bron[-1]
        assert df['aggr'].values[0] == bron


# ============================================================
# Cache van de harmonisatie-Excel (issue 87)
# ============================================================

def _nepHarmonizer():
    """Klein DataFrame zoals loadHarmonizer het oplevert."""
    return pd.DataFrame({'Object': ['Ignore', 'Vondst'],
                         'aggr': [[{'$match': {}}, {'$merge': {}}], [{'$match': {}}, {'$merge': {}}]]})


class TestHarmonizerCache:
    """De Excel wordt per pad één keer gelezen; reload=True en een ander pad lezen opnieuw."""

    def setup_method(self):
        harmonizer.resetHarmonizer()

    def teardown_method(self):
        harmonizer.resetHarmonizer()

    def test_twee_aanroepen_lezen_de_excel_een_keer(self):
        with patch.object(harmonizer.pd, 'read_excel', wraps=pd.read_excel) as lezen:
            eerste = getHarmonizeAggr("Vondst")
            tweede = getHarmonizeAggr("Spoor")
            derde = getHarmonizeAggr("Vondst")
        assert lezen.call_count == 1
        assert eerste == derde and tweede != eerste

    def test_reload_leest_opnieuw(self):
        with patch.object(harmonizer.pd, 'read_excel', wraps=pd.read_excel) as lezen:
            getHarmonizeAggr("Vondst")
            getHarmonizeAggr("Vondst", reload=True)
            getHarmonizeAggr("Vondst")
        assert lezen.call_count == 2

    def test_meegegeven_dataframe_gebruikt_de_cache_niet(self, monkeypatch):
        gelezen = []
        monkeypatch.setattr(harmonizer, 'loadHarmonizer', lambda: gelezen.append(1) or _nepHarmonizer())
        aggr = getHarmonizeAggr('Vondst', df=_nepHarmonizer())
        assert aggr == [{'$match': {}}, {'$merge': {}}]
        assert gelezen == []

    def test_ander_pad_leest_opnieuw(self, monkeypatch, tmp_path):
        """Tests wisselen het Excel-pad (bijv. de Delftse Excel): elk pad heeft zijn eigen cache."""
        paden = []
        monkeypatch.setattr(harmonizer, 'loadHarmonizer', lambda: paden.append(harmonizer.AIRFLOW_WASSTRAAT_CONFIG) or _nepHarmonizer())
        a, b = tmp_path / 'a.xlsx', tmp_path / 'b.xlsx'
        a.write_text('a')
        b.write_text('b')
        for pad in [a, b, a, b]:
            monkeypatch.setattr(harmonizer, 'AIRFLOW_WASSTRAAT_CONFIG', str(pad))
            harmonizer.getHarmonizer()
        assert paden == [str(a), str(b)]

    def test_gewijzigd_bestand_wordt_opnieuw_gelezen(self, monkeypatch, tmp_path):
        gelezen = []
        monkeypatch.setattr(harmonizer, 'loadHarmonizer', lambda: gelezen.append(1) or _nepHarmonizer())
        pad = tmp_path / 'config.xlsx'
        pad.write_text('x')
        monkeypatch.setattr(harmonizer, 'AIRFLOW_WASSTRAAT_CONFIG', str(pad))
        harmonizer.getHarmonizer()
        os.utime(pad, (1, 1))
        harmonizer.getHarmonizer()
        harmonizer.getHarmonizer()
        assert len(gelezen) == 2


# ============================================================
# Objecten die geen soort zijn (issue 87)
# ============================================================

class TestOnbekendeObjecten:
    """Rijen in het blad Objecten die geen soort in meta.wasstraat_model zijn, worden gemeld."""

    def setup_method(self):
        harmonizer.resetHarmonizer()

    def teardown_method(self):
        harmonizer.resetHarmonizer()

    def test_ignore_en_soorten_tellen_niet(self):
        df = pd.DataFrame({'Object': ['Ignore', 'Vondst', 'Dia', 'Aardewerk', 'Dia', 'Oud_Object']})
        assert harmonizer.getOnbekendeObjecten(df) == ['Dia', 'Oud_Object']

    def test_testconfiguratie_zonder_onbekende_objecten_behalve_dia(self):
        """De test-Excel: alleen een rij Dia kan nog over zijn (verouderd, wordt uit de Excel gehaald)."""
        assert set(harmonizer.getOnbekendeObjecten()) <= {'Dia'}

    def test_controle_meldt_waarschuwing_per_object(self, monkeypatch, caplog):
        import logging
        import wasstraat.foutbeleid as foutbeleid
        meldingen = []
        monkeypatch.setattr(harmonizer, 'getHarmonizer', lambda reload=False: pd.DataFrame({'Object': ['Ignore', 'Put', 'Dia']}))
        monkeypatch.setattr(foutbeleid, 'meld', lambda *a, **k: meldingen.append((a, k)))
        with caplog.at_level(logging.WARNING, logger="airflow.task"):
            assert harmonizer.controleerObjecten() == ['Dia']
        assert len(meldingen) == 1
        (niveau, soort, tekst), kwargs = meldingen[0]
        assert (niveau, soort) == (foutbeleid.NIVEAU_WAARSCHUWING, foutbeleid.SOORT_CONFIGURATIE_ONGELDIG)
        assert 'Dia' in tekst and 'wordt niet gebruikt' in tekst
        assert kwargs['details']['object'] == 'Dia' and kwargs['details']['blad'] == 'Objecten'
        assert 'Object Dia in het blad Objecten' in caplog.text

    def test_controle_zonder_onbekende_objecten_meldt_niets(self, monkeypatch):
        import wasstraat.foutbeleid as foutbeleid
        meldingen = []
        monkeypatch.setattr(harmonizer, 'getHarmonizer', lambda reload=False: pd.DataFrame({'Object': ['Ignore', 'Put']}))
        monkeypatch.setattr(foutbeleid, 'meld', lambda *a, **k: meldingen.append((a, k)))
        assert harmonizer.controleerObjecten() == []
        assert meldingen == []


class TestGeenAfhankelijkheidVanSamenvoegen:
    """De kolom Samenvoegen van het blad Objecten wordt niet gebruikt (issue 87) en mag ontbreken."""

    def test_harmonizer_zonder_kolom_samenvoegen(self, monkeypatch, tmp_path):
        bron = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                            "data", "test", "wasstraat_config", "Wasstraat_Config_HarmonizeV3.xlsx")
        bladen = pd.read_excel(bron, sheet_name=None)
        bladen['Objecten'] = bladen['Objecten'].drop(columns=['Samenvoegen'], errors='ignore')
        doel = tmp_path / 'zonder_samenvoegen.xlsx'
        with pd.ExcelWriter(doel) as schrijver:
            for naam, blad in bladen.items():
                blad.to_excel(schrijver, sheet_name=naam, index=False)
        monkeypatch.setattr(harmonizer, 'AIRFLOW_WASSTRAAT_CONFIG', str(doel))
        harmonizer.resetHarmonizer()
        try:
            assert getHarmonizeAggr('Vondst') == getHarmonizeAggr('Vondst', df=loadHarmonizer())
            assert not hasattr(harmonizer, 'getObjects') and not hasattr(harmonizer, 'getMergeWith')
        finally:
            harmonizer.resetHarmonizer()
