"""
Unit tests voor de Project-configuratie in wasstraat/meta.py.

Controleert dat Project correct geconfigureerd is voor de volledige
ETL-pipeline: harmonisatie, key-generatie, en move naar clean-collectie.
"""
import pytest

from wasstraat.meta import (
    wasstraat_model,
    getKeys,
    HARMONIZE_PIPELINES,
    SET_KEYS_PIPELINES,
    MOVEANDMERGE_MOVE,
    MOVEANDMERGE_MERGE,
)


@pytest.mark.unit
class TestProjectMetaConfiguratie:
    """Test dat Project correct is geconfigureerd in meta.py."""

    def test_project_bestaat_in_model(self):
        """Project moet als entiteit bestaan in wasstraat_model."""
        assert "Project" in wasstraat_model

    def test_project_heeft_harmonize_pipeline(self):
        """Project moet een harmonisatie-pipeline hebben."""
        assert HARMONIZE_PIPELINES in wasstraat_model["Project"]

    def test_project_heeft_set_keys_pipeline(self):
        """Project moet een key-generatie pipeline hebben."""
        assert SET_KEYS_PIPELINES in wasstraat_model["Project"]

    def test_project_in_move_keys(self):
        """Project moet in de MOVE-lijst staan voor transport naar clean-collectie."""
        move_keys = getKeys(MOVEANDMERGE_MOVE)
        assert "Project" in move_keys, (
            f"Project ontbreekt in MOVEANDMERGE_MOVE lijst. "
            f"Zonder deze stap wordt Def_Project niet gevuld in PostgreSQL."
        )

    def test_project_heeft_expliciete_move_flag(self):
        """Project moet een expliciete MOVEANDMERGE_MOVE flag hebben."""
        assert MOVEANDMERGE_MOVE in wasstraat_model["Project"], (
            "Project mist MOVEANDMERGE_MOVE: True in meta.py. "
            "Dit veroorzaakt dat Def_Project leeg blijft in PostgreSQL."
        )


@pytest.mark.unit
class TestProjectHarmonizeFilter:
    """Test dat de harmonisatie-filter voor Project correct is."""

    def _get_match_stage(self):
        """Haal de $match stage op uit de Project harmonize pipeline."""
        pipelines = wasstraat_model["Project"][HARMONIZE_PIPELINES]
        pipeline = pipelines[0]  # eerste (en enige) pipeline
        match_stage = pipeline[0]  # eerste stage is $match
        return match_stage["$match"]

    def test_matcht_opgravingen_tabel(self):
        """De pipeline moet filteren op table='OPGRAVINGEN'."""
        match = self._get_match_stage()
        assert match.get("table") == "OPGRAVINGEN"

    def test_geen_filter_op_projectcode(self):
        """De pipeline mag niet filteren op projectcode — alle codes moeten geaccepteerd worden."""
        match = self._get_match_stage()
        assert "CODE" not in match, (
            f"De harmonize-pipeline filtert op CODE: {match.get('CODE')}. "
            f"Dit voorkomt dat niet-Delftse projecten (SY, etc.) worden verwerkt."
        )


@pytest.mark.unit
class TestProjectKeyGeneratie:
    """Test dat de key-generatie pipeline voor Project correct is."""

    def test_key_pipeline_matcht_op_project_soort(self):
        """De key-pipeline moet filteren op soort='Project'."""
        pipelines = wasstraat_model["Project"][SET_KEYS_PIPELINES]
        pipeline = pipelines[0]
        match_stage = pipeline[0]
        assert match_stage["$match"]["soort"] == "Project"

    def test_key_begint_met_p_prefix(self):
        """De gegenereerde key moet beginnen met 'P' (Project-prefix)."""
        pipelines = wasstraat_model["Project"][SET_KEYS_PIPELINES]
        pipeline = pipelines[0]
        # Zoek de $addFields stage met 'key'
        for stage in pipeline:
            if "$addFields" in stage and "key" in stage["$addFields"]:
                concat = stage["$addFields"]["key"]["$concat"]
                assert concat[0] == "P", (
                    f"Project key-prefix moet 'P' zijn, maar is '{concat[0]}'"
                )
                return
        assert False, "Geen $addFields met 'key' gevonden in de pipeline"
