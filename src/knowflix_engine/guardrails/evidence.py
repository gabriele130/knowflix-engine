import re
from difflib import SequenceMatcher

# Segmenti su cui le evidence vengono cercate: (section_kind, testo normalizzato).
# Un'evidence deve stare dentro UN segmento: non puo' scavalcare due sezioni.
_CTX: dict[str, list[tuple[str, str]]] = {"segments": []}


def set_evidence_sections(sections: list[tuple[str, str]]) -> None:
    """Imposta le sezioni (kind, testo) in cui le evidence sono ammesse."""
    _CTX["segments"] = [(kind, _norm(text)) for kind, text in sections]


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


def evidence_guardrail(output):
    data = output.pydantic
    bad = [s.label for s in data.skills if locate_evidence(s.evidence) is None]
    if bad:
        return (
            False,
            f"Le evidence di queste competenze non compaiono nel documento: "
            f"{bad}. Copia la frase testuale ESATTA dal testo fornito, "
            f"oppure rimuovi la competenza.",
        )
    return (True, data)
