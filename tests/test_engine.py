import json
import os
import pytest
from unittest.mock import patch, MagicMock

from knowflix_engine.main import KnowflixFlow, _is_transient
from knowflix_engine.guardrails.evidence import evidence_guardrail, set_document_context
from knowflix_engine.schemas.models import ParsedDocument
from knowflix_engine.config import ENGINE_VERSION

# --- 1. TEST GUARDRAIL EVIDENCE ---

def test_evidence_guardrail_present():
    set_document_context("Questo è un testo che parla di machine learning e analisi dati.")
    
    mock_output = MagicMock()
    mock_output.pydantic.skills = [
        MagicMock(label="Machine Learning", evidence="parla di machine learning")
    ]
    
    is_valid, result = evidence_guardrail(mock_output)
    assert is_valid is True
    assert result == mock_output.pydantic

def test_evidence_guardrail_absent():
    set_document_context("Questo è un testo che parla di machine learning e analisi dati.")
    
    mock_output = MagicMock()
    skill_mock = MagicMock(label="Deep Learning", evidence="utilizzo di reti neurali profonde")
    mock_output.pydantic.skills = [skill_mock]
    
    is_valid, result = evidence_guardrail(mock_output)
    assert is_valid is False
    assert "reti neurali profonde" not in result
    assert "Deep Learning" in result

def test_evidence_guardrail_paraphrased():
    set_document_context("Abbiamo utilizzato un algoritmo di foresta casuale per la classificazione.")
    
    mock_output = MagicMock()
    # La frase è parafrasata (Random Forest vs foresta casuale), quindi il fuzzy match sotto soglia dovrebbe fallire
    skill_mock = MagicMock(label="Random Forest", evidence="abbiamo impiegato il modello random forest per classificare")
    mock_output.pydantic.skills = [skill_mock]
    
    is_valid, result = evidence_guardrail(mock_output)
    assert is_valid is False

# --- 2. TEST CACHE HIT/MISS ---

@pytest.fixture
def mock_parsed_doc():
    return {
        "doc_id": "test_cache_01",
        "lang": "it",
        "sections": [
            {"kind": "abstract", "text": "Testo di prova per la cache"}
        ],
        "figures": []
    }

def test_cache_miss_and_hit(mock_parsed_doc, tmp_path):
    # Setup
    flow = KnowflixFlow()
    flow.state.job_id = "test_cache_01"
    flow.state.job_type = "document"
    flow.state.parsed = mock_parsed_doc
    
    cache_dir = tmp_path / "cache"
    cache_file = cache_dir / f"test_cache_01_{ENGINE_VERSION}.json"
    
    with patch("knowflix_engine.main.os.makedirs") as mock_makedirs, \
         patch("knowflix_engine.main.os.path.join", return_value=str(cache_file)), \
         patch("knowflix_engine.main.DocumentCrew") as mock_crew:
        
        # Mocking LLM crew
        mock_crew_instance = MagicMock()
        mock_crew.return_value.crew.return_value = mock_crew_instance
        
        mock_result = MagicMock()
        mock_result.pydantic.model_dump.return_value = {"skills": [{"label": "Test"}]}
        mock_crew_instance.kickoff.return_value = mock_result
        
        # MISS
        assert not cache_file.exists()
        flow.run_document()
        
        assert flow.state.metrics.get("cached") is False
        assert flow.state.profile == {"skills": [{"label": "Test"}]}
        mock_crew_instance.kickoff.assert_called_once()
        
        # Create cache file manually to simulate save (since we mocked path but not open in main)
        # Wait, the main.py open will write to the mocked path natively if we just patch os.path.join? No, os.path.join returns string.
        # Actually, main.py uses standard open with cache_path. So it WILL write to tmp_path / cache / ...
        
    assert cache_file.exists()
    
    # HIT
    flow_hit = KnowflixFlow()
    flow_hit.state.job_id = "test_cache_01"
    flow_hit.state.job_type = "document"
    flow_hit.state.parsed = mock_parsed_doc
    
    with patch("knowflix_engine.main.os.path.join", return_value=str(cache_file)), \
         patch("knowflix_engine.main.DocumentCrew") as mock_crew_hit:
        
        flow_hit.run_document()
        
        assert flow_hit.state.metrics.get("cached") is True
        assert flow_hit.state.profile == {"skills": [{"label": "Test"}]}
        mock_crew_hit.assert_not_called()

# --- 3. TEST RESILIENZA (Extra coverage per il fix) ---

def test_transient_error_detection():
    class MockResponse:
        status_code = 429
    
    class MockError(Exception):
        response = MockResponse()
        
    assert _is_transient(MockError("API Error")) is True
    
    assert _is_transient(Exception("rate limit exceeded")) is True
    assert _is_transient(Exception("un errore 500 nudo non basta")) is False
    assert _is_transient(Exception("server error occorso")) is True

