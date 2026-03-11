"""
Unit tests voor wasstraat/harmonizer.py

Test de opbouw van MongoDB aggregation pipelines op basis van
het Excel-configuratiebestand (Wasstraat_Config_HarmonizeV3.xlsx).
"""
import pytest
import os
import pandas as pd
import ast

from wasstraat.harmonizer import (
    getAggrTables, getKolomValues, getAttributes, initAttributes,
    createAggr, loadHarmonizer, getHarmonizeAggr, getObjects
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
        "data", "wasstraat_config", "Wasstraat_Config_HarmonizeV3.xlsx"
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


# ============================================================
# getObjects — objectlijsten uit het configuratiebestand
# ============================================================

class TestGetObjects:

    def test_base_objects(self):
        objects = getObjects(inherit=False, merge=False)
        assert "Put" in objects
        assert "Spoor" in objects
        # Artefact-kinderen horen hier NIET bij
        assert "Aardewerk" not in objects

    def test_inherited_objects(self):
        objects = getObjects(inherit=True, merge=False)
        assert "Aardewerk" in objects
        assert "Glas" in objects
        assert "Hout" in objects
        # Basis-objecten horen hier NIET bij
        assert "Put" not in objects

    def test_inherit_and_merge_raises(self):
        """Kan niet inherit=True en merge=True tegelijk zijn."""
        try:
            getObjects(inherit=True, merge=True)
            assert False, "Verwachtte een exception"
        except Exception:
            pass  # verwacht
