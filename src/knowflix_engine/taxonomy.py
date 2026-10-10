"""Linking deterministico skill -> tassonomia.

Nessun LLM: solo normalizzazione, lookup su sinonimi e fuzzy-match
(SequenceMatcher), come richiesto dall'invariante in CLAUDE.md §6.4.
"""
import re
from difflib import SequenceMatcher

_FUZZY_THRESHOLD = 0.85

# Tassonomia statica minima: skill_id canonico -> label + sinonimi noti.
# Estendere qui aggiungendo nuove voci, senza toccare la logica di matching.
TAXONOMY: dict[str, dict] = {
    "tax-python": {
        "label": "Python",
        "synonyms": ["python"],
    },
    "tax-data-analysis": {
        "label": "Data Analysis",
        "synonyms": ["pandas", "analisi dati", "data analysis", "numpy", "scipy"],
    },
    "tax-machine-learning": {
        "label": "Machine Learning",
        "synonyms": [
            "machine learning", "apprendimento automatico",
            "apprendimento supervisionato", "classificazione supervisionata",
            "scikit-learn", "random forest", "support vector machine",
            "gradient boosting",
        ],
    },
    "tax-signal-processing": {
        "label": "Signal Processing",
        "synonyms": [
            "elaborazione segnali", "analisi vibrazionale", "trasformata di fourier",
            "filtro passa-banda", "pre-processamento segnali",
        ],
    },
    "tax-feature-engineering": {
        "label": "Feature Engineering",
        "synonyms": ["selezione feature", "feature selection", "mutua informazione"],
    },
    "tax-model-validation": {
        "label": "Model Validation",
        "synonyms": ["validazione modello", "cross-validation", "validazione incrociata"],
    },
    "tax-sql": {
        "label": "SQL",
        "synonyms": ["sql", "query sql", "database oracle"],
    },
    "tax-data-visualization": {
        "label": "Data Visualization",
        "synonyms": ["grafana", "cruscotto", "dashboard", "influxdb"],
    },
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _candidates(entry: dict) -> list[str]:
    return [entry["label"], *entry.get("synonyms", [])]


def _best_match(label: str) -> str | None:
    norm_label = _norm(label)
    if not norm_label:
        return None

    # 1. match esatto (case/whitespace insensitive) su label canonica o sinonimo
    for skill_id, entry in TAXONOMY.items():
        if norm_label in (_norm(c) for c in _candidates(entry)):
            return skill_id

    # 2. fuzzy match deterministico, soglia conservativa
    best_id, best_score = None, 0.0
    for skill_id, entry in TAXONOMY.items():
        for c in _candidates(entry):
            score = SequenceMatcher(None, norm_label, _norm(c)).ratio()
            if score > best_score:
                best_score, best_id = score, skill_id

    return best_id if best_score >= _FUZZY_THRESHOLD else None


def link_profile(profile: dict) -> dict:
    """Assegna skill_id alle skill del profilo via lookup statico.

    Non modifica confidence/evidence/label: aggiunge solo skill_id
    (None se non c'e' match sopra soglia).
    """
    linked_skills = []
    for skill in profile.get("skills", []):
        skill = dict(skill)
        skill["skill_id"] = _best_match(skill.get("label", ""))
        linked_skills.append(skill)

    linked_profile = dict(profile)
    linked_profile["skills"] = linked_skills
    return linked_profile


def taxonomy_coverage(skills: list[dict]) -> float | None:
    """Quota di skill con skill_id non nullo; None se non ci sono skill."""
    if not skills:
        return None
    return round(sum(1 for s in skills if s.get("skill_id")) / len(skills), 3)
