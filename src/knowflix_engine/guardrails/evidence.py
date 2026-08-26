import re
from difflib import SequenceMatcher

_CTX = {"full_text": ""}


def set_document_context(text: str) -> None:
    _CTX["full_text"] = _norm(text)


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


def evidence_guardrail(output):
    data = output.pydantic
    hay = _CTX["full_text"]
    bad = [s.label for s in data.skills if not _present(s.evidence, hay)]
    if bad:
        return (
            False,
            f"Le evidence di queste competenze non compaiono nel documento: "
            f"{bad}. Copia la frase testuale ESATTA dal testo fornito, "
            f"oppure rimuovi la competenza.",
        )
    return (True, data)