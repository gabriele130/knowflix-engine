import re
from difflib import SequenceMatcher

# Segmenti su cui le evidence vengono cercate: (section_kind, testo normalizzato).
# Un'evidence deve stare dentro UN segmento: non puo' scavalcare due sezioni.
_CTX: dict = {
    "segments": [],
    "failures": {},  # guardrail -> tentativi respinti nel kickoff corrente
    "dropped": [],   # competenze scartate per evidence non verificata
}

GUARDRAIL_MAX_RETRIES = 2


def set_evidence_sections(sections: list[tuple[str, str]]) -> None:
    """Imposta le sezioni (kind, testo) in cui le evidence sono ammesse."""
    _CTX["segments"] = [(kind, _norm(text)) for kind, text in sections]
    reset_evidence_attempts()


def reset_evidence_attempts() -> None:
    """Azzera contatori e scarti: va chiamato prima di ogni kickoff della crew."""
    _CTX["failures"] = {}
    _CTX["dropped"] = []


def dropped_skills() -> list[str]:
    """Competenze scartate dal guardrail all'ultimo tentativo, con motivo."""
    return list(_CTX["dropped"])


def set_document_context(text: str) -> None:
    """Contesto a segmento unico (kind "other"), es. il ramo company."""
    set_evidence_sections([("other", text)])


def _norm(s: str) -> str:
    s = s.replace("-\n", "").replace("\n", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def _present(needle: str, hay: str, threshold: float = 0.90) -> bool:
    n = _norm(needle)
    if not n or len(n) < 10:
        return False
    if n in hay:
        return True
    win = len(n)
    step = max(1, win // 2)
    for i in range(0, max(1, len(hay) - win), step):
        if SequenceMatcher(None, n, hay[i:i + win]).ratio() >= threshold:
            return True
    return False


def locate_evidence(evidence: str) -> str | None:
    """section_kind del primo segmento che contiene l'evidence, None se assente."""
    for kind, hay in _CTX["segments"]:
        if _present(evidence, hay):
            return kind
    return None


def _feedback(bad) -> str:
    return (
        f"Le evidence di queste competenze non compaiono nel documento: "
        f"{[s.label for s in bad]}. Ogni evidence deve essere una frase copiata ESATTAMENTE "
        f"da una sola sezione del testo fornito: non unire frasi di sezioni "
        f"diverse, non riassumere, non tradurre. Se nel testo non c'e' una "
        f"frase che dimostri la competenza, rimuovi la competenza."
    )


def evidence_guardrail(output):
    data = output.pydantic
    bad = [s for s in data.skills if locate_evidence(s.evidence) is None]
    if bad:
        return (False, _feedback(bad))
    return (True, data)


class EvidenceGuardrail:
    """evidence_guardrail con esito finale non distruttivo.

    Per i primi max_retries tentativi rifiuta l'output come evidence_guardrail,
    chiedendo all'agente di correggere le citazioni. All'ultimo tentativo,
    invece di far fallire l'intero job, rimuove le sole competenze con
    evidence non verificata e le registra in dropped_skills(). La verifica non
    e' allentata: nessuna evidence non trovata arriva al profilo.
    """

    def __init__(self, name: str, max_retries: int = GUARDRAIL_MAX_RETRIES):
        self.name = name
        self.max_retries = max_retries

    def __call__(self, output):
        data = output.pydantic
        bad = [s for s in data.skills if locate_evidence(s.evidence) is None]
        failures = _CTX["failures"]
        if not bad:
            failures.pop(self.name, None)
            return (True, output)
        if failures.get(self.name, 0) < self.max_retries:
            failures[self.name] = failures.get(self.name, 0) + 1
            return (False, _feedback(bad))

        # ultimo tentativo: si scartano le competenze non verificate
        failures.pop(self.name, None)
        bad_ids = {id(s) for s in bad}
        kept = data.model_copy(
            update={"skills": [s for s in data.skills if id(s) not in bad_ids]})
        _CTX["dropped"].extend(
            f"{s.label}: evidence non trovata nel testo" for s in bad)
        # crewai tiene il TaskOutput, non il dato restituito: e il task
        # successivo legge raw come contesto
        output.pydantic = kept
        output.raw = kept.model_dump_json()
        output.json_dict = None
        return (True, output)
