from typing import Literal
from pydantic import BaseModel, Field, model_validator

# --- SEZIONI ---

SectionKind = Literal["abstract", "introduction", "methodology", "results",
                      "discussion", "conclusions", "bibliography", "appendix",
                      "other"]

# Sezioni passate alla sintesi e all'estrazione competenze.
# bibliography e appendix sono accettate in ingresso ma escluse da entrambe.
SUMMARY_KINDS: tuple[str, ...] = ("abstract", "introduction", "conclusions")
SKILL_KINDS: tuple[str, ...] = ("methodology", "results", "discussion")


# --- INPUT: contratto con chi fa il preprocessing PyMuPDF ---

class Section(BaseModel):
    kind: SectionKind
    heading: str | None = None
    text: str


class ParsedDocument(BaseModel):
    doc_id: str
    lang: str = "it"
    meta: dict = {}
    sections: list[Section]
    figures: list[dict] = []
    parser_version: str = "1.0"
    bibliography: str = ""

    def text_of(self, kinds: tuple[str, ...]) -> str:
        return "\n\n".join(s.text for s in self.sections if s.kind in kinds)

    def full_text(self) -> str:
        return "\n\n".join(s.text for s in self.sections)


# --- OUTPUT INTERMEDI (output_pydantic delle task LLM) ---

class SummaryOutput(BaseModel):
    one_liner: str = Field(description="Una frase, massimo 25 parole")
    abstract_150: str = Field(description="Sintesi di circa 150 parole")
    keywords: list[str] = Field(description="5-10 termini tecnici specifici")


class ExtractedSkill(BaseModel):
    """Skill come prodotta dall'LLM: section_kind NON e' qui, lo assegna il
    motore dalla sezione in cui l'evidence viene trovata."""
    label: str
    evidence: str = Field(description="Frase testuale esatta dal documento")
    confidence: float


class ExtractedSkills(BaseModel):
    skills: list[ExtractedSkill]


class ReviewDraft(BaseModel):
    """Output della task review, prima dell'assemblaggio deterministico."""
    one_liner: str
    abstract_150: str
    keywords: list[str]
    skills: list[ExtractedSkill]
    rejected: list[str] = []
    review_notes: str = ""


class Skill(BaseModel):
    label: str
    evidence: str = Field(description="Frase testuale esatta dal documento")
    section_kind: SectionKind
    confidence: float
    skill_id: str | None = None


# Non piu' usato dalle crew (sostituito da ExtractedSkills); resta per
# compatibilita' di import.
class SkillsOutput(BaseModel):
    skills: list[Skill]


# --- OUTPUT FINALE ---

class PublicCard(BaseModel):
    """Scheda pubblica. Non popolata in questa versione."""
    abstract: str | None = None


class ReviewedProfile(BaseModel):
    one_liner: str
    abstract_150: str
    keywords: list[str]
    skills: list[Skill]
    rejected: list[str] = []
    review_notes: str = ""
    cover_figure_id: str | None = None
    taxonomy_version: str | None = None
    taxonomy_coverage: float | None = None
    public_card: PublicCard = Field(default_factory=PublicCard)
    engine_version: str | None = None


# --- ERRORI ---

ErrorCode = Literal["invalid_payload", "unsupported_payload_version",
                    "unauthorized", "empty_content", "rate_limited",
                    "provider_unavailable", "timeout", "internal_error"]

RETRYABLE_CODES: frozenset[str] = frozenset(
    {"rate_limited", "provider_unavailable", "timeout"})


class EngineError(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool
    engine_version: str | None = None

    @classmethod
    def of(cls, code: str, message: str) -> "EngineError":
        return cls(code=code, message=message, retryable=code in RETRYABLE_CODES)

    @model_validator(mode="after")
    def _retryable_matches_code(self) -> "EngineError":
        if self.retryable != (self.code in RETRYABLE_CODES):
            raise ValueError(f"retryable={self.retryable} incoerente con code={self.code}")
        return self
