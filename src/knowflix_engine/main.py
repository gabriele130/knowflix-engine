import json
import logging
import os
import sys
import time

from crewai.flow.flow import Flow, listen, or_, router, start
from pydantic import BaseModel

from knowflix_engine.config import ENGINE_VERSION
from knowflix_engine.crews.document_crew.document_crew import DocumentCrew
from knowflix_engine.guardrails.evidence import set_document_context
from knowflix_engine.schemas.models import ParsedDocument

logger = logging.getLogger(__name__)

# --------------- retry helpers ---------------

_MAX_RETRIES = 3
_BASE_DELAY = 2.0  # seconds


def _is_transient(exc: Exception) -> bool:
    """Return True for errors worth retrying (429, timeout, 5xx)."""
    # 1. Reliable path: inspect numeric status_code when the exception exposes it
    code = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    if isinstance(code, int):
        if code == 429 or 500 <= code < 600:
            return True

    # 2. Fallback: match only unambiguous phrases in the message text
    msg = str(exc).lower()
    if any(tok in msg for tok in ("rate limit", "timeout", "timed out",
                                   "resource_exhausted", "service unavailable",
                                   "server error", "overloaded")):
        return True
    return False


def _call_crew_with_retry(crew, inputs: dict) -> object:
    """Kick off a crew with exponential-backoff retry for transient errors."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return crew.kickoff(inputs=inputs)
        except Exception as exc:
            last_exc = exc
            if not _is_transient(exc):
                raise  # permanent -> bubble up immediately
            delay = _BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "Crew call failed (attempt %d/%d, transient): %s - retrying in %.1fs",
                attempt, _MAX_RETRIES, exc, delay,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(delay)
    # exhausted retries
    raise last_exc  # type: ignore[misc]


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

        # --- CACHE CHECK ---
        os.makedirs("cache", exist_ok=True)
        cache_path = os.path.join("cache", f"{doc.doc_id}_{ENGINE_VERSION}.json")
        
        if os.path.exists(cache_path):
            logger.info("Cache HIT per doc_id: %s (version: %s)", doc.doc_id, ENGINE_VERSION)
            with open(cache_path, "r", encoding="utf-8") as f:
                self.state.profile = json.load(f)
            self.state.metrics = {"cached": True}
            return

        logger.info("Cache MISS per doc_id: %s", doc.doc_id)

        t0 = time.time()
        inputs = {
            "lang": doc.lang,
            "text_summary": doc.text_of(("abstract", "intro", "conclusion")),
            "text_skills": doc.text_of(("method", "results", "discussion")),
        }
        try:
            result = _call_crew_with_retry(DocumentCrew().crew(), inputs)
        except Exception as exc:
            # Permanent error or retries exhausted: degrade gracefully
            logger.error("Crew call failed permanently: %s", exc)
            self.state.warnings.append(f"document crew failed: {exc}")
            self.state.profile = {
                "skills": [],
                "keywords": [],
                "review_notes": f"errore: {exc}",
            }
            self.state.metrics = {
                "seconds": round(time.time() - t0, 1),
                "error": str(exc),
                "failed": True,
            }
            return
        elapsed = time.time() - t0

        self.state.profile = result.pydantic.model_dump()
        usage = getattr(result, "token_usage", None)
        self.state.metrics = {
            "seconds": round(elapsed, 1),
            "usage": usage.model_dump() if hasattr(usage, "model_dump") else str(usage),
            "cached": False,
        }

        # --- SAVE TO CACHE ---
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(self.state.profile, f, indent=2, ensure_ascii=False)

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
        # Skip post-processing on failed profiles to avoid polluting metrics
        if self.state.profile and not self.state.metrics.get("failed"):
            pass  # TODO: linking tassonomia, persistenza, evento di indicizzazione
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
