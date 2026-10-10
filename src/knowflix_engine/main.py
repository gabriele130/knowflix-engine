import json
import logging
import os
import sys
import time
from typing import Callable

from crewai.flow.flow import Flow, listen, or_, router, start
from pydantic import BaseModel, ValidationError

from knowflix_engine.config import (
    ENGINE_VERSION,
    SUPPORTED_PARSER_VERSIONS,
    TAXONOMY_VERSION,
)
from knowflix_engine.cover import pick_cover
from knowflix_engine.crews.document_crew.document_crew import DocumentCrew
from knowflix_engine.crews.scout_crew.scout_crew import ScoutCrew
from knowflix_engine.guardrails.evidence import (
    locate_evidence,
    set_document_context,
    set_evidence_sections,
)
from knowflix_engine.schemas.models import (
    RETRYABLE_CODES,
    SKILL_KINDS,
    SUMMARY_KINDS,
    EngineError,
    ParsedDocument,
    ReviewDraft,
    ReviewedProfile,
    Skill,
)
from knowflix_engine.taxonomy import link_profile, taxonomy_coverage

logger = logging.getLogger(__name__)

# --------------- errori e retry ---------------

_MAX_RETRIES = 3
_BASE_DELAY = 2.0  # seconds

_MESSAGE_CODES = (
    # (codice, frasi non ambigue nel messaggio), in ordine di priorita'
    ("unauthorized", ("unauthorized", "authentication", "invalid api key",
                      "api key not valid", "permission denied")),
    ("rate_limited", ("rate limit", "resource_exhausted", "too many requests")),
    ("timeout", ("timeout", "timed out")),
    ("provider_unavailable", ("service unavailable", "server error", "overloaded",
                              "connection error", "failed to connect")),
)


def classify_error(exc: Exception) -> str:
    """Mappa un'eccezione del provider/crew su un codice di EngineError."""
    # 1. Reliable path: inspect numeric status_code when the exception exposes it
    code = getattr(exc, "status_code", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    if isinstance(code, int):
        if code in (401, 403):
            return "unauthorized"
        if code == 429:
            return "rate_limited"
        if code in (408, 504):
            return "timeout"
        if 500 <= code < 600:
            return "provider_unavailable"

    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, ConnectionError):
        return "provider_unavailable"

    # 2. Fallback: match only unambiguous phrases in the message text
    msg = str(exc).lower()
    for error_code, phrases in _MESSAGE_CODES:
        if any(p in msg for p in phrases):
            return error_code
    return "internal_error"


def _is_transient(exc: Exception) -> bool:
    """Return True for errors worth retrying (rate limit, timeout, provider down)."""
    return classify_error(exc) in RETRYABLE_CODES


def _call_crew_with_retry(crew, inputs: dict,
                          before_attempt: Callable[[], None] | None = None) -> object:
    """Kick off a crew with exponential-backoff retry for transient errors."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        if before_attempt:
            before_attempt()
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


def assemble_profile(draft: ReviewDraft, cover_figure_id: str | None = None) -> dict:
    """ReviewDraft (LLM) -> ReviewedProfile, con section_kind assegnato dal motore.

    section_kind e' la sezione di input in cui l'evidence viene trovata, mai
    un valore generato dal modello.
    """
    skills = []
    for s in draft.skills:
        kind = locate_evidence(s.evidence)
        if kind is None:  # il guardrail su review lo impedisce: qui e' un bug
            raise ValueError(f"evidence non localizzabile per la skill {s.label!r}")
        skills.append(Skill(label=s.label, evidence=s.evidence,
                            section_kind=kind, confidence=s.confidence))
    return ReviewedProfile(
        one_liner=draft.one_liner,
        abstract_150=draft.abstract_150,
        keywords=draft.keywords,
        skills=skills,
        rejected=draft.rejected,
        review_notes=draft.review_notes,
        cover_figure_id=cover_figure_id,
    ).model_dump()


# --------------- progress ---------------

# Valore emesso al termine di ciascuno dei tre task della crew; 0 all'avvio.
_TASK_PROGRESS = (33, 66, 100)


class EngineState(BaseModel):
    job_id: str = ""
    job_type: str = "document"
    parsed: dict | None = None
    company_raw: dict | None = None
    profile: dict | None = None
    error: dict | None = None      # EngineError serializzato; esclusivo con profile
    progress: int | None = None    # ultimo valore emesso: 0 / 33 / 66 / 100
    warnings: list[str] = []
    metrics: dict = {}


class KnowflixFlow(Flow[EngineState]):
    # Callback opzionale invocata a ogni avanzamento: on_progress(0|33|66|100).
    on_progress: Callable[[int], None] | None = None

    # ---- helpers ----

    def _emit_progress(self, value: int) -> None:
        # monotono: un retry che riparte dal primo task non fa tornare indietro
        if self.state.progress is not None and value <= self.state.progress:
            return
        self.state.progress = value
        if self.on_progress:
            self.on_progress(value)

    def _run_crew(self, crew, inputs: dict):
        done = {"tasks": 0}

        def reset() -> None:
            done["tasks"] = 0

        def on_task_done(_output) -> None:
            done["tasks"] += 1
            self._emit_progress(_TASK_PROGRESS[min(done["tasks"], 3) - 1])

        crew.task_callback = on_task_done
        self._emit_progress(0)
        return _call_crew_with_retry(crew, inputs, before_attempt=reset)

    def _fail(self, code: str, message: str, t0: float | None = None) -> None:
        err = EngineError.of(code, message)
        logger.error("job %s failed [%s]: %s", self.state.job_id, code, message)
        self.state.error = err.model_dump()
        self.state.profile = None
        self.state.warnings.append(f"{code}: {message}")
        self.state.metrics = {"failed": True, "error_code": code, "error": message}
        if t0 is not None:
            self.state.metrics["seconds"] = round(time.time() - t0, 1)

    def _validate_document(self) -> None:
        parsed = self.state.parsed
        if not isinstance(parsed, dict):
            self._fail("invalid_payload", "parsed mancante o non e' un oggetto JSON")
            return
        # parser_version assente: accettato (il backend oggi non lo invia).
        # Si rifiuta solo un valore presente e non supportato.
        version = parsed.get("parser_version")
        if version is not None and version not in SUPPORTED_PARSER_VERSIONS:
            self._fail("unsupported_payload_version",
                       f"parser_version {version!r} non supportata "
                       f"(supportate: {', '.join(SUPPORTED_PARSER_VERSIONS)})")
            return
        try:
            doc = ParsedDocument(**parsed)
        except ValidationError as exc:
            details = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                                for e in exc.errors())
            self._fail("invalid_payload", details)
            return
        if not doc.text_of(SUMMARY_KINDS + SKILL_KINDS).strip():
            self._fail("empty_content",
                       "nessun testo nelle sezioni usate dal motore "
                       f"({', '.join(SUMMARY_KINDS + SKILL_KINDS)})")

    def _validate_company(self) -> None:
        raw = self.state.company_raw
        if not isinstance(raw, dict):
            self._fail("invalid_payload", "company_raw mancante o non e' un oggetto JSON")
        elif not any(isinstance(v, str) and v.strip() for v in raw.values()):
            self._fail("empty_content", "company_raw non contiene campi testuali")

    # ---- flow ----

    @start()
    def ingest(self):
        if self.state.job_type == "document":
            self._validate_document()
        elif self.state.job_type == "company":
            self._validate_company()
        else:
            self._fail("invalid_payload", f"job_type {self.state.job_type!r} non supportato")
        return "ingested"

    @router(ingest)
    def dispatch(self, previous_result):
        return self.state.job_type

    @listen("document")
    def run_document(self):
        if self.state.error:
            return
        doc = ParsedDocument(**self.state.parsed)
        # le evidence sono ammesse solo nelle sezioni date all'estrazione
        set_evidence_sections([(s.kind, s.text) for s in doc.sections
                               if s.kind in SKILL_KINDS])

        # --- CACHE CHECK ---
        os.makedirs("cache", exist_ok=True)
        cache_path = os.path.join("cache", f"{doc.doc_id}_{ENGINE_VERSION}.json")

        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            try:
                self.state.profile = ReviewedProfile.model_validate(cached).model_dump()
                logger.info("Cache HIT per doc_id: %s (version: %s)", doc.doc_id, ENGINE_VERSION)
                self.state.metrics = {"cached": True}
                self._emit_progress(0)
                self._emit_progress(100)
                return
            except ValidationError:
                logger.warning("Cache non valida per doc_id %s: ignorata", doc.doc_id)

        logger.info("Cache MISS per doc_id: %s", doc.doc_id)

        t0 = time.time()
        inputs = {
            "lang": doc.lang,
            "text_summary": doc.text_of(SUMMARY_KINDS),
            "text_skills": doc.text_of(SKILL_KINDS),
        }
        try:
            result = self._run_crew(DocumentCrew().crew(), inputs)
            self.state.profile = assemble_profile(result.pydantic, pick_cover(doc.figures))
        except Exception as exc:
            self._fail(classify_error(exc), str(exc), t0)
            return
        elapsed = time.time() - t0

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
        if self.state.error:
            return
        company_raw = self.state.company_raw
        text_company = "\n".join(
            f"{k}: {v}" for k, v in company_raw.items() if isinstance(v, str)
        )
        set_document_context(text_company)

        inputs = {
            "lang": company_raw.get("lang", "it"),
            "text_company": text_company,
        }

        t0 = time.time()
        try:
            result = self._run_crew(ScoutCrew().crew(), inputs)
            self.state.profile = assemble_profile(result.pydantic)
        except Exception as exc:
            self._fail(classify_error(exc), str(exc), t0)
            return
        elapsed = time.time() - t0

        usage = getattr(result, "token_usage", None)
        self.state.metrics = {
            "seconds": round(elapsed, 1),
            "usage": usage.model_dump() if hasattr(usage, "model_dump") else str(usage),
            "cached": False,
        }

    @listen(or_(run_document, run_company))
    def finalize(self):
        """Ritorna il ReviewedProfile, oppure l'EngineError se il job e' fallito."""
        if self.state.error:
            return self.state.error

        profile = self.state.profile
        if profile is None:  # nessun errore ma nessun profilo: stato incoerente
            self._fail("internal_error", "nessun profilo prodotto e nessun errore registrato")
            return self.state.error

        degraded = (
            self.state.metrics.get("failed")
            or not profile.get("skills")
        )
        if not degraded:
            profile = link_profile(profile)
            profile["taxonomy_coverage"] = taxonomy_coverage(profile["skills"])
        else:
            profile["taxonomy_coverage"] = None
        profile["taxonomy_version"] = TAXONOMY_VERSION
        self.state.profile = ReviewedProfile.model_validate(profile).model_dump()
        # TODO: persistenza, evento di indicizzazione
        return self.state.profile


def kickoff():
    path = sys.argv[1] if len(sys.argv) > 1 else "fixtures/doc_test.json"
    parsed = json.load(open(path, encoding="utf-8"))

    flow = KnowflixFlow()
    flow.kickoff(inputs={
        "job_id": parsed.get("doc_id", ""),
        "job_type": "document",
        "parsed": parsed,
    })

    if flow.state.error:
        print(json.dumps({"error": flow.state.error}, indent=2, ensure_ascii=False))
        print("METRICHE:", flow.state.metrics)
        sys.exit(1)
    print(json.dumps(flow.state.profile, indent=2, ensure_ascii=False))
    print("METRICHE:", flow.state.metrics)


def plot():
    KnowflixFlow().plot()


if __name__ == "__main__":
    kickoff()
