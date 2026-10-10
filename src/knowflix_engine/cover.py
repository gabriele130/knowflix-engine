"""Scoring deterministico delle figure per selezionare la cover del documento.

Nessun LLM: punteggio calcolato da attributi geometrici gia' estratti dal
parser (area_ratio, has_caption). Stessa logica deterministica richiesta
per il linking di tassonomia (CLAUDE.md §6.4).
"""

_AREA_WEIGHT = 0.7
_CAPTION_WEIGHT = 0.3


def score_figure(figure: dict) -> float:
    """Punteggio 0..1: figure grandi e con didascalia sono cover migliori."""
    area_ratio = min(max(figure.get("area_ratio") or 0.0, 0.0), 1.0)
    has_caption = bool(figure.get("has_caption"))
    score = area_ratio * _AREA_WEIGHT + (_CAPTION_WEIGHT if has_caption else 0.0)
    return round(score, 3)


def pick_cover(figures: list[dict]) -> str | None:
    """Ritorna l'id della figura con punteggio piu' alto, None se nessuna qualifica."""
    best_id, best_score = None, 0.0
    for figure in figures:
        score = score_figure(figure)
        if score > best_score:
            best_score, best_id = score, figure.get("id")
    return best_id
