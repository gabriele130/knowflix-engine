"""Logging delle correzioni umane sui profili, in formato JSONL.

Ogni chiamata appende una riga: nessuna lettura/scrittura concorrente da
gestire oltre l'append atomico del filesystem, nessun LLM coinvolto.
"""
import json
import os
from datetime import datetime, timezone

FEEDBACK_PATH = os.path.join("feedback", "corrections.jsonl")


def log_correction(
    doc_id: str,
    field: str,
    original,
    corrected,
    note: str = "",
    path: str = FEEDBACK_PATH,
) -> None:
    """Appende una correzione umana al file JSONL di feedback."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "doc_id": doc_id,
        "field": field,
        "original": original,
        "corrected": corrected,
        "note": note,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
