import json
from knowflix_engine.schemas.models import ParsedDocument
from knowflix_engine.crews.document_crew.document_crew import DocumentCrew
from knowflix_engine.guardrails.evidence import set_document_context



doc = ParsedDocument(**json.load(open("fixtures/doc_test.json", encoding="utf-8")))
set_document_context("testo che non contiene nulla del documento originale")
result = DocumentCrew().crew().kickoff(inputs={
    "lang": doc.lang,
    "text_summary": doc.text_of(("abstract", "intro", "conclusion")),
    "text_skills": doc.text_of(("method", "results", "discussion")),
})

print(json.dumps(result.pydantic.model_dump(), indent=2, ensure_ascii=False))