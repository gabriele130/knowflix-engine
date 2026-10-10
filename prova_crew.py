import json
from knowflix_engine.schemas.models import SKILL_KINDS, SUMMARY_KINDS, ParsedDocument
from knowflix_engine.crews.document_crew.document_crew import DocumentCrew
from knowflix_engine.guardrails.evidence import set_document_context



doc = ParsedDocument(**json.load(open("fixtures/doc_test.json", encoding="utf-8")))
set_document_context("testo che non contiene nulla del documento originale")
result = DocumentCrew().crew().kickoff(inputs={
    "lang": doc.lang,
    "text_summary": doc.text_of(SUMMARY_KINDS),
    "text_skills": doc.text_of(SKILL_KINDS),
})

print(json.dumps(result.pydantic.model_dump(), indent=2, ensure_ascii=False))