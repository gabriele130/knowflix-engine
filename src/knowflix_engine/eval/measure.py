import glob
import json
import statistics
import sys

from knowflix_engine.main import KnowflixFlow


def run_batch(pattern: str = "fixtures/*.json"):
    rows = []
    for path in sorted(glob.glob(pattern)):
        parsed = json.load(open(path, encoding="utf-8"))
        flow = KnowflixFlow()
        try:
            flow.kickoff(inputs={"job_id": parsed["doc_id"],
                                 "job_type": "document", "parsed": parsed})
            m = flow.state.metrics
            n_skills = len(flow.state.profile.get("skills", []))
            rows.append({"doc": parsed["doc_id"], "sec": m.get("seconds"),
                         "usage": m.get("usage"), "skills": n_skills, "ok": True})
        except Exception as e:
            rows.append({"doc": parsed["doc_id"], "ok": False, "err": str(e)[:120]})

        print(rows[-1])

    ok = [r for r in rows if r["ok"]]
    if ok:
        secs = [r["sec"] for r in ok]
        print(f"\n--- {len(ok)}/{len(rows)} riusciti")
        print(f"secondi: mediana {statistics.median(secs)}, max {max(secs)}")
        print(f"competenze estratte: mediana {statistics.median([r['skills'] for r in ok])}")

    json.dump(rows, open("metriche.json", "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    return rows


if __name__ == "__main__":
    run_batch(sys.argv[1] if len(sys.argv) > 1 else "fixtures/*.json")