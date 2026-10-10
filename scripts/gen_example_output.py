"""Esegue un run reale del Flow sul fixture e salva l'output come esempio.

Uso:
    uv run python scripts/gen_example_output.py [fixtures/doc_test.json]

Scrive:
  - docs/schema/example_output.json       profilo prodotto dal Flow (ReviewedProfile)
  - docs/schema/example_output.meta.json  come e quando e' stato prodotto

Il run avviene in una directory temporanea, cosi' la cache in cache/ non
viene letta: l'esempio viene sempre da una chiamata LLM vera. Se il run
fallisce o l'output non valida contro ReviewedProfile, non scrive nulla.
Dopo, rigenerare il contratto: uv run python scripts/gen_schema.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from knowflix_engine.config import ENGINE_VERSION, TAXONOMY_VERSION  # noqa: E402
from knowflix_engine.guardrails.evidence import (  # noqa: E402
    locate_evidence,
    set_evidence_sections,
)
from knowflix_engine.main import KnowflixFlow  # noqa: E402
from knowflix_engine.schemas.models import (  # noqa: E402
    SKILL_KINDS,
    ParsedDocument,
    ReviewedProfile,
)

OUT_DIR = ROOT / "docs" / "schema"


def main(argv: list[str]) -> int:
    fixture = (ROOT / (argv[0] if argv else "fixtures/doc_test.json")).resolve()
    parsed = json.loads(fixture.read_text(encoding="utf-8"))

    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)  # cache/ vuota: niente cache hit
        try:
            flow = KnowflixFlow()
            flow.kickoff(inputs={"job_id": parsed["doc_id"], "job_type": "document",
                                 "parsed": parsed})
        finally:
            os.chdir(cwd)

    metrics = flow.state.metrics
    if flow.state.error or metrics.get("cached"):
        print(f"run non utilizzabile come esempio: {flow.state.error or metrics}",
              file=sys.stderr)
        return 1
    profile = ReviewedProfile.model_validate(flow.state.profile)

    # Ricontrollo indipendente dal run: ogni evidence del profilo finale deve
    # stare nella sezione dichiarata in section_kind.
    doc = ParsedDocument(**parsed)
    set_evidence_sections([(s.kind, s.text) for s in doc.sections if s.kind in SKILL_KINDS])
    verified = sum(locate_evidence(s.evidence) == s.section_kind for s in profile.skills)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "example_output.json").write_text(
        json.dumps(flow.state.profile, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n")
    meta = {
        "fixture": fixture.relative_to(ROOT).as_posix(),
        "engine_version": ENGINE_VERSION,
        "model": os.getenv("MODEL", "gemini/gemini-3.6-flash"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seconds": metrics.get("seconds"),
        "skills": len(profile.skills),
        "skills_with_skill_id": sum(s.skill_id is not None for s in profile.skills),
        "taxonomy_version": TAXONOMY_VERSION,
        "taxonomy_coverage": profile.taxonomy_coverage,
        "final_evidence_verified_in_declared_section": verified,
    }
    (OUT_DIR / "example_output.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(meta, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
