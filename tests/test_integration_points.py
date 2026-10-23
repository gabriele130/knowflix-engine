"""Punti dell'integrazione: guardrail su review, section_kind, enum sezioni,
tassonomia, progress, errori, public_card. Nessuna chiamata LLM: le crew
sono sostituite da FakeCrew."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from knowflix_engine import main
from knowflix_engine.config import ENGINE_VERSION, TAXONOMY_VERSION
from knowflix_engine.crews.document_crew.document_crew import DocumentCrew
from knowflix_engine.crews.scout_crew.scout_crew import ScoutCrew
from knowflix_engine.guardrails.evidence import (
    make_evidence_guardrail,
    dropped_skills,
    evidence_guardrail,
    locate_evidence,
    set_evidence_sections,
)
from knowflix_engine.main import KnowflixFlow, assemble_profile, classify_error
from knowflix_engine.schemas.models import (
    SKILL_KINDS,
    SUMMARY_KINDS,
    EngineError,
    ExtractedSkill,
    ParsedDocument,
    ReviewDraft,
    ReviewedProfile,
    Section,
    Skill,
)

METHOD_TEXT = "Il pre-processamento dei segnali e' stato implementato in Python con NumPy."
RESULTS_TEXT = "Il classificatore random forest ha raggiunto una accuratezza del 94 per cento."
BIBLIO_TEXT = "Breiman L. Random forests. Machine Learning, 2001."
APPENDIX_TEXT = "Appendice A: listato completo dello script di acquisizione dati."


def make_doc(**overrides) -> dict:
    doc = {
        "doc_id": "it_test",
        "lang": "it",
        "parser_version": "2.0",
        "sections": [
            {"kind": "abstract", "text": "Manutenzione predittiva di motori asincroni."},
            {"kind": "introduction", "text": "Il problema dei guasti ai cuscinetti."},
            {"kind": "methodology", "text": METHOD_TEXT},
            {"kind": "results", "text": RESULTS_TEXT},
            {"kind": "conclusions", "text": "Il sistema anticipa i guasti."},
            {"kind": "bibliography", "text": BIBLIO_TEXT},
            {"kind": "appendix", "text": APPENDIX_TEXT},
        ],
    }
    doc.update(overrides)
    return doc


def make_draft(skills=None) -> ReviewDraft:
    if skills is None:
        skills = [
            ExtractedSkill(label="Python", confidence=0.9,
                           evidence="implementato in Python con NumPy"),
            ExtractedSkill(label="Classificazione con alberi", confidence=0.8,
                           evidence="Il classificatore random forest ha raggiunto"),
        ]
    return ReviewDraft(one_liner="Manutenzione predittiva.", abstract_150="Sintesi.",
                       keywords=["manutenzione predittiva"], skills=skills)


class FakeCrew:
    """Simula la crew: invoca task_callback ai confini dei tre task."""

    def __init__(self, draft=None, exc=None, fail_at_task=0):
        self.draft = draft if draft is not None else make_draft()
        self.exc, self.fail_at_task = exc, fail_at_task
        self.task_callback = None
        self.inputs = []

    def kickoff(self, inputs):
        self.inputs.append(inputs)
        for i in range(3):
            if self.exc is not None and i == self.fail_at_task:
                raise self.exc
            self.task_callback(MagicMock())
        return SimpleNamespace(pydantic=self.draft, token_usage=None)


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # cache/ vuota e isolata per ogni test
    monkeypatch.setattr(main.time, "sleep", lambda s: None)


def run_flow(parsed=None, crew=None, job_type="document", company_raw=None, cls=DocumentCrew):
    crew = crew or FakeCrew()
    events = []
    target = "DocumentCrew" if cls is DocumentCrew else "ScoutCrew"
    with patch(f"knowflix_engine.main.{target}") as crew_cls:
        crew_cls.return_value.crew.return_value = crew
        flow = KnowflixFlow(on_progress=events.append)
        result = flow.kickoff(inputs={"job_id": "j1", "job_type": job_type,
                                      "parsed": parsed, "company_raw": company_raw})
    return flow, result, events, crew


# --- 1. GUARDRAIL SUL PROFILO FINALE ---

@pytest.mark.parametrize("crew_cls, task_name", [(DocumentCrew, "review"),
                                                 (ScoutCrew, "review_company")])
def test_review_task_has_evidence_guardrail(crew_cls, task_name):
    task = getattr(crew_cls(), task_name)()
    assert task.guardrail.__name__.startswith("evidence_guardrail_")
    assert task.guardrail_max_retries == task.guardrail.max_retries == 2


@pytest.mark.parametrize("crew_cls, task_name", [(DocumentCrew, "review"),
                                                 (ScoutCrew, "review_company")])
def test_guardrail_survives_crewai_guardrail_event(crew_cls, task_name):
    # crewai emette questo evento a ogni controllo e fa getsource() sul
    # guardrail: un oggetto chiamabile qui fa fallire il job
    from crewai.events.types.llm_guardrail_events import LLMGuardrailStartedEvent
    task = getattr(crew_cls(), task_name)()
    event = LLMGuardrailStartedEvent(guardrail=task.guardrail, retry_count=0)
    assert event.guardrail_type == "function"


def _bad_draft():
    return make_draft([
        ExtractedSkill(label="Python", confidence=0.9,
                       evidence="implementato in Python con NumPy"),
        ExtractedSkill(label="Rotoscoping", confidence=0.7,
                       evidence="gli animatori dello studio ricalcavano il girato dal vero"),
    ])


def test_evidence_guardrail_retries_then_drops_unverified_skills():
    set_evidence_sections([("methodology", METHOD_TEXT)])
    guard = make_evidence_guardrail("review")
    for _ in range(guard.max_retries):  # tentativi con feedback all'agente
        ok, msg = guard(SimpleNamespace(pydantic=_bad_draft(), raw="", json_dict=None))
        assert ok is False and "Rotoscoping" in msg
    out = SimpleNamespace(pydantic=_bad_draft(), raw="", json_dict=None)
    ok, result = guard(out)  # ultimo tentativo: pota invece di fallire
    assert ok is True and result is out
    assert [s.label for s in out.pydantic.skills] == ["Python"]
    assert "Rotoscoping" not in out.raw and "Python" in out.raw
    assert dropped_skills() == ["Rotoscoping: evidence non trovata nel testo"]


def test_evidence_guardrail_counter_resets_with_new_document():
    set_evidence_sections([("methodology", METHOD_TEXT)])
    guard = make_evidence_guardrail("review")
    guard(SimpleNamespace(pydantic=_bad_draft(), raw="", json_dict=None))
    set_evidence_sections([("methodology", METHOD_TEXT)])
    ok, _ = guard(SimpleNamespace(pydantic=_bad_draft(), raw="", json_dict=None))
    assert ok is False  # nuovo kickoff: si riparte dai retry, non dalla potatura
    assert dropped_skills() == []


def test_dropped_skills_end_in_rejected_not_in_skills():
    class DroppingCrew(FakeCrew):
        def kickoff(self, inputs):
            result = super().kickoff(inputs)
            guard = make_evidence_guardrail("review", max_retries=0)
            out = SimpleNamespace(pydantic=_bad_draft(), raw="", json_dict=None)
            guard(out)
            return SimpleNamespace(pydantic=out.pydantic, token_usage=None)

    flow, result, _, _ = run_flow(make_doc(), crew=DroppingCrew())
    assert [s["label"] for s in result["skills"]] == ["Python"]
    assert "Rotoscoping: evidence non trovata nel testo" in result["rejected"]
    assert flow.state.metrics["dropped_skills"] == 1
    assert flow.state.error is None


def test_guardrail_rejects_evidence_rewritten_by_reviewer():
    set_evidence_sections([("methodology", METHOD_TEXT)])
    draft = make_draft([ExtractedSkill(label="Python", confidence=0.9,
                                       evidence="ha sviluppato software scientifico in Python")])
    ok, msg = evidence_guardrail(SimpleNamespace(pydantic=draft))
    assert ok is False and "Python" in msg


def test_guardrail_accepts_verbatim_review_output():
    set_evidence_sections([("methodology", METHOD_TEXT), ("results", RESULTS_TEXT)])
    ok, data = evidence_guardrail(SimpleNamespace(pydantic=make_draft()))
    assert ok is True


# --- 2. SECTION_KIND VINCOLATO ---

def test_skill_rejects_invented_section_kind():
    with pytest.raises(ValidationError):
        Skill(label="x", evidence="y" * 20, section_kind="metodologia", confidence=1.0)


def test_llm_output_has_no_section_kind():
    assert "section_kind" not in ExtractedSkill.model_fields


def test_section_kind_comes_from_input_section():
    set_evidence_sections([("methodology", METHOD_TEXT), ("results", RESULTS_TEXT)])
    profile = assemble_profile(make_draft())
    kinds = {s["label"]: s["section_kind"] for s in profile["skills"]}
    assert kinds == {"Python": "methodology", "Classificazione con alberi": "results"}


def test_section_kind_end_to_end_ignores_cached_invented_value():
    flow, result, _, _ = run_flow(make_doc())
    assert [s["section_kind"] for s in result["skills"]] == ["methodology", "results"]


def test_stale_cache_with_invented_section_kind_is_ignored():
    from knowflix_engine.config import ENGINE_VERSION
    import os
    os.makedirs("cache")
    bad = {"one_liner": "x", "abstract_150": "x", "keywords": [],
           "skills": [{"label": "a", "evidence": METHOD_TEXT,
                       "section_kind": "metodologia", "confidence": 1.0}]}
    path = main.cache_path_for(ParsedDocument(**make_doc()))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bad, f)
    flow, result, _, crew = run_flow(make_doc())
    assert len(crew.inputs) == 1  # cache scartata, crew eseguita
    assert flow.state.metrics["cached"] is False


# --- 3. ENUM SEZIONI KNOWFLIX ---

def test_section_enum_is_knowflix():
    expected = ["abstract", "introduction", "methodology", "results", "discussion",
                "conclusions", "bibliography", "appendix", "other"]
    for kind in expected:
        Section(kind=kind, text="t")
    for old in ("intro", "method", "conclusion"):
        with pytest.raises(ValidationError):
            Section(kind=old, text="t")


def test_bibliography_and_appendix_excluded_from_extraction():
    assert not {"bibliography", "appendix"} & set(SKILL_KINDS + SUMMARY_KINDS)
    _, _, _, crew = run_flow(make_doc())
    sent = crew.inputs[0]
    for text in (BIBLIO_TEXT, APPENDIX_TEXT):
        assert text not in sent["text_skills"] and text not in sent["text_summary"]
    assert METHOD_TEXT in sent["text_skills"] and RESULTS_TEXT in sent["text_skills"]


def test_evidence_from_bibliography_or_appendix_is_rejected():
    doc = ParsedDocument(**make_doc())
    set_evidence_sections([(s.kind, s.text) for s in doc.sections if s.kind in SKILL_KINDS])
    assert locate_evidence(BIBLIO_TEXT) is None
    assert locate_evidence(APPENDIX_TEXT) is None


# --- 4. TASSONOMIA ---

def test_profile_exposes_taxonomy_version_and_coverage():
    _, result, _, _ = run_flow(make_doc())
    assert result["taxonomy_version"] == TAXONOMY_VERSION
    # "Python" e' in tassonomia, "Classificazione con alberi" no
    assert [s["skill_id"] for s in result["skills"]] == ["tax-python", None]
    assert result["taxonomy_coverage"] == 0.5


def test_coverage_is_null_without_skills_and_link_not_called():
    with patch("knowflix_engine.main.link_profile") as link:
        _, result, _, _ = run_flow(make_doc(), FakeCrew(draft=make_draft([])))
    link.assert_not_called()
    assert result["taxonomy_coverage"] is None
    assert result["taxonomy_version"] == TAXONOMY_VERSION


# --- 5. PROGRESS ---

def test_progress_emitted_at_task_boundaries():
    flow, _, events, _ = run_flow(make_doc())
    assert events == [0, 33, 66, 100]
    assert flow.state.progress == 100


def test_cache_ignored_when_same_doc_id_has_new_content():
    run_flow(make_doc())
    resegmented = make_doc()
    resegmented["sections"][2]["kind"] = "discussion"  # stesso doc_id, parser diverso
    _, _, _, crew = run_flow(resegmented)
    assert len(crew.inputs) == 1


def test_progress_on_cache_hit():
    run_flow(make_doc())
    _, _, events, crew = run_flow(make_doc())
    assert crew.inputs == [] and events == [0, 100]


def test_progress_stops_where_task_fails():
    flow, _, events, _ = run_flow(make_doc(), FakeCrew(exc=ValueError("boom"), fail_at_task=1))
    assert events == [0, 33]
    assert flow.state.error["code"] == "internal_error"


def test_progress_is_monotonic_across_retries():
    crew = FakeCrew(exc=Exception("rate limit exceeded"), fail_at_task=2)
    calls = {"n": 0}
    original = crew.kickoff

    def flaky(inputs):  # primo tentativo fallisce dopo 2 task, il secondo riesce
        calls["n"] += 1
        if calls["n"] == 2:
            crew.exc = None
        return original(inputs)

    crew.kickoff = flaky
    _, result, events, _ = run_flow(make_doc(), crew)
    assert events == [0, 33, 66, 100]
    assert "error" not in result


# --- 6. ERRORI ---

class _HTTPError(Exception):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status_code = status


@pytest.mark.parametrize("exc, code", [
    (_HTTPError(401), "unauthorized"),
    (_HTTPError(403), "unauthorized"),
    (Exception("Invalid API key provided"), "unauthorized"),
    (_HTTPError(429), "rate_limited"),
    (Exception("RESOURCE_EXHAUSTED: quota"), "rate_limited"),
    (_HTTPError(503), "provider_unavailable"),
    (Exception("Failed to connect to OpenAI API: Connection error."), "provider_unavailable"),
    (_HTTPError(504), "timeout"),
    (TimeoutError("read"), "timeout"),
    (Exception("Request timed out"), "timeout"),
    (Exception("Task failed guardrail validation after 2 retries"), "internal_error"),
    (Exception("un errore 500 nudo non basta"), "internal_error"),
])
def test_classify_error(exc, code):
    assert classify_error(exc) == code


@pytest.mark.parametrize("code, retryable", [
    ("invalid_payload", False), ("unsupported_payload_version", False),
    ("unauthorized", False), ("empty_content", False), ("rate_limited", True),
    ("provider_unavailable", True), ("timeout", True), ("internal_error", False),
])
def test_error_retryable_flag(code, retryable):
    assert EngineError.of(code, "m").retryable is retryable
    with pytest.raises(ValidationError):
        EngineError(code=code, message="m", retryable=not retryable)


def _assert_error_result(flow, result, code):
    assert result == flow.state.error
    assert set(result) == {"code", "message", "retryable", "engine_version"}
    assert result["engine_version"] == ENGINE_VERSION
    assert result["code"] == code
    assert flow.state.profile is None
    with pytest.raises(ValidationError):  # non e' un ReviewedProfile
        ReviewedProfile.model_validate(result)


def test_crew_failure_returns_error_not_partial_profile():
    flow, result, _, _ = run_flow(make_doc(), FakeCrew(exc=_HTTPError(401)))
    _assert_error_result(flow, result, "unauthorized")
    assert result["retryable"] is False


def test_transient_failure_after_retries_is_retryable():
    crew = FakeCrew(exc=_HTTPError(503))
    flow, result, _, _ = run_flow(make_doc(), crew)
    _assert_error_result(flow, result, "provider_unavailable")
    assert result["retryable"] is True
    assert len(crew.inputs) == main._MAX_RETRIES


def test_invalid_payload():
    doc = make_doc(sections=[{"kind": "intro", "text": "vecchio enum"}])
    flow, result, _, crew = run_flow(doc)
    _assert_error_result(flow, result, "invalid_payload")
    assert "sections.0.kind" in result["message"]
    assert crew.inputs == []


def test_unsupported_payload_version():
    flow, result, _, crew = run_flow(make_doc(parser_version="1.0"))
    _assert_error_result(flow, result, "unsupported_payload_version")
    assert crew.inputs == []


def test_missing_parser_version_is_accepted():
    doc = make_doc()
    del doc["parser_version"]
    flow, result, _, crew = run_flow(doc)
    assert flow.state.error is None
    assert len(crew.inputs) == 1
    ReviewedProfile.model_validate(result)


def test_finalize_without_profile_returns_internal_error():
    flow = KnowflixFlow()
    flow.state.profile = None
    result = flow.finalize()
    assert result["code"] == "internal_error" and result["retryable"] is False
    assert flow.state.profile is None


def test_empty_content():
    doc = make_doc(sections=[{"kind": "bibliography", "text": BIBLIO_TEXT},
                             {"kind": "methodology", "text": "   "}])
    flow, result, _, crew = run_flow(doc)
    _assert_error_result(flow, result, "empty_content")
    assert crew.inputs == []


def test_company_without_text_is_empty_content():
    flow, result, _, _ = run_flow(job_type="company", company_raw={"employees": 12},
                                  cls=ScoutCrew)
    _assert_error_result(flow, result, "empty_content")


def test_company_branch_section_kind_is_other():
    raw = {"descrizione": "Sviluppiamo software di manutenzione predittiva in Python."}
    draft = make_draft([ExtractedSkill(label="Python", confidence=0.9,
                                       evidence="software di manutenzione predittiva in Python")])
    _, result, events, _ = run_flow(job_type="company", company_raw=raw,
                                    crew=FakeCrew(draft=draft), cls=ScoutCrew)
    assert result["skills"][0]["section_kind"] == "other"
    assert events == [0, 33, 66, 100]


# --- 7. PUBLIC_CARD ---

def test_public_card_present_but_not_populated():
    _, result, _, _ = run_flow(make_doc())
    assert result["public_card"] == {"abstract": None}
    ReviewedProfile.model_validate(result)


def test_profile_reports_engine_version():
    _, result, _, _ = run_flow(make_doc())
    assert result["engine_version"] == ENGINE_VERSION
