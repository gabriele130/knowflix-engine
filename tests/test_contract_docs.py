"""La documentazione del contratto in docs/ deve combaciare con il codice.

Se uno di questi test fallisce: uv run python scripts/gen_schema.py
"""
import importlib.util
import json
from pathlib import Path

import pytest

from knowflix_engine.schemas.models import ReviewedProfile

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("gen_schema", ROOT / "scripts" / "gen_schema.py")
gen_schema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen_schema)


def test_every_model_field_is_documented():
    assert gen_schema.check_meanings() == []


@pytest.mark.parametrize("name", sorted(gen_schema.SCHEMAS))
def test_json_schema_matches_model(name):
    path = gen_schema.SCHEMA_DIR / name
    assert path.exists(), f"{path} mancante: eseguire scripts/gen_schema.py"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == gen_schema.SCHEMAS[name].model_json_schema(), (
        f"{name} non combacia con il modello: eseguire scripts/gen_schema.py")


def test_generated_docs_are_up_to_date():
    stale = [str(p.relative_to(ROOT)) for p in gen_schema.stale_files()]
    assert stale == [], f"documentazione obsoleta {stale}: eseguire scripts/gen_schema.py"


def test_example_output_matches_current_contract():
    path = gen_schema.SCHEMA_DIR / "example_output.json"
    if not path.exists():
        pytest.skip("example_output.json assente: eseguire scripts/gen_example_output.py")
    ReviewedProfile.model_validate_json(path.read_text(encoding="utf-8"))
