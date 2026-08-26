import json
import sys
import time

from crewai.flow.flow import Flow, listen, or_, router, start
from pydantic import BaseModel

from knowflix_engine.crews.document_crew.document_crew import DocumentCrew
from knowflix_engine.guardrails.evidence import set_document_context
from knowflix_engine.schemas.models import ParsedDocument


class EngineState(BaseModel):
    job_id: str = ""
    job_type: str = "document"
    parsed: dict | None = None
    company_raw: dict | None = None
    profile: dict | None = None
    warnings: list[str] = []
    metrics: dict = {}


class KnowflixFlow(Flow[EngineState]):

    @start()
    def ingest(self):
        if self.state.job_type == "document":
            ParsedDocument(**self.state.parsed)
        return "ingested"

    @router(ingest)
    def dispatch(self, previous_result):
        return self.state.job_type

    @listen("document")
    def run_document(self):
        doc = ParsedDocument(**self.state.parsed)
        set_document_context(doc.full_text())

        t0 = time.time()
        result = DocumentCrew().crew().kickoff(inputs={
            "lang": doc.lang,
            "text_summary": doc.text_of(("abstract", "intro", "conclusion")),
            "text_skills": doc.text_of(("method", "results", "discussion")),
        })
        elapsed = time.time() - t0

        self.state.profile = result.pydantic.model_dump()
        usage = getattr(result, "token_usage", None)
        self.state.metrics = {
            "seconds": round(elapsed, 1),
            "usage": usage.model_dump() if hasattr(usage, "model_dump") else str(usage),
        }

    @listen("company")
    def run_company(self):
        self.state.profile = {
            "skills": [],
            "keywords": [],
            "review_notes": "scout non ancora implementato",
        }
        self.state.warnings.append("ramo company: stub")

    @listen(or_(run_document, run_company))
    def finalize(self):
        # TODO: linking tassonomia, persistenza, evento di indicizzazione
        return self.state.profile


def kickoff():
    path = sys.argv[1] if len(sys.argv) > 1 else "fixtures/doc_test.json"
    parsed = json.load(open(path, encoding="utf-8"))

    flow = KnowflixFlow()
    flow.kickoff(inputs={
        "job_id": parsed["doc_id"],
        "job_type": "document",
        "parsed": parsed,
    })

    print(json.dumps(flow.state.profile, indent=2, ensure_ascii=False))
    print("METRICHE:", flow.state.metrics)


def plot():
    KnowflixFlow().plot()


if __name__ == "__main__":
    kickoff()