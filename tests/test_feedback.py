import json

from knowflix_engine.feedback import log_correction


def test_log_correction_appends_jsonl(tmp_path):
    path = str(tmp_path / "feedback" / "corrections.jsonl")

    log_correction("doc1", "skills[0].label", "ML", "Machine Learning", note="troppo generico", path=path)
    log_correction("doc1", "keywords", ["a"], ["a", "b"], path=path)

    with open(path, "r", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    assert len(lines) == 2
    assert lines[0]["doc_id"] == "doc1"
    assert lines[0]["field"] == "skills[0].label"
    assert lines[0]["original"] == "ML"
    assert lines[0]["corrected"] == "Machine Learning"
    assert lines[0]["note"] == "troppo generico"
    assert "timestamp" in lines[0]
    assert lines[1]["corrected"] == ["a", "b"]
