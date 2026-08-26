from typing import Literal
from pydantic import BaseModel, Field


# --- INPUT: contratto con chi fa il preprocessing PyMuPDF ---

class Section(BaseModel):
    kind: Literal["abstract", "intro", "method", "results",
                  "discussion", "conclusion", "other"]
    heading: str | None = None
    text: str


class ParsedDocument(BaseModel):
    doc_id: str
    lang: str = "it"
    meta: dict = {}
    sections: list[Section]
    figures: list[dict] = []

    def text_of(self, kinds: tuple[str, ...]) -> str:
        return "\n\n".join(s.text for s in self.sections if s.kind in kinds)

    def full_text(self) -> str:
        return "\n\n".join(s.text for s in self.sections)


# --- OUTPUT ---

class SummaryOutput(BaseModel):
    one_liner: str = Field(description="Una frase, massimo 25 parole")
    abstract_150: str = Field(description="Sintesi di circa 150 parole")
    keywords: list[str] = Field(description="5-10 termini tecnici specifici")


class Skill(BaseModel):
    label: str
    evidence: str = Field(description="Frase testuale esatta dal documento")
    section_kind: str
    confidence: float
    skill_id: str | None = None


class SkillsOutput(BaseModel):
    skills: list[Skill]


class ReviewedProfile(BaseModel):
    one_liner: str
    abstract_150: str
    keywords: list[str]
    skills: list[Skill]
    rejected: list[str] = []
    review_notes: str = ""