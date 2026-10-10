import glob
import json
import statistics
import sys
import os

from knowflix_engine.main import KnowflixFlow
from knowflix_engine.config import get_pricing_table

def calculate_cost(usage, model):
    pricing = get_pricing_table()
    if model not in pricing:
        return None
        
    if not usage:
        return None
        
    # CrewAI token usage might come as dict or json string
    if isinstance(usage, str):
        try:
            usage = json.loads(usage.replace("'", '"'))
        except Exception:
            return None
            
    if not isinstance(usage, dict):
        return None
        
    p_tokens = usage.get("prompt_tokens", 0)
    c_tokens = usage.get("completion_tokens", 0)
    
    cost_in = (p_tokens / 1_000_000) * pricing[model]["input"]
    cost_out = (c_tokens / 1_000_000) * pricing[model]["output"]
    return cost_in + cost_out


def run_batch(pattern: str = "fixtures/*.json"):
    model_in_use = os.getenv("MODEL", "gemini/gemini-3.6-flash")
    rows = []
    
    for path in sorted(glob.glob(pattern)):
        parsed = json.load(open(path, encoding="utf-8"))
        flow = KnowflixFlow()
        try:
            flow.kickoff(inputs={"job_id": parsed["doc_id"],
                                 "job_type": "document", "parsed": parsed})
            m = flow.state.metrics
            ok = flow.state.error is None
            n_skills = len(flow.state.profile["skills"]) if ok else 0
            
            row = {"doc": parsed["doc_id"], "sec": m.get("seconds"),
                   "usage": m.get("usage"), "skills": n_skills, "ok": ok}
                   
            if not ok:
                row["err"] = flow.state.error
            elif not m.get("cached"):
                cost = calculate_cost(m.get("usage"), model_in_use)
                if cost is not None:
                    row["cost"] = cost
                    
            rows.append(row)
        except Exception as e:
            rows.append({"doc": parsed["doc_id"], "ok": False, "err": str(e)[:120]})

        print(rows[-1])

    ok = [r for r in rows if r["ok"]]
    if ok:
        secs = [r["sec"] for r in ok if r.get("sec") is not None]
        print(f"\n--- {len(ok)}/{len(rows)} riusciti")
        if secs:
            print(f"secondi: mediana {statistics.median(secs)}, max {max(secs)}")
        print(f"competenze estratte: mediana {statistics.median([r['skills'] for r in ok])}")
        
        costs = [r["cost"] for r in ok if "cost" in r]
        if costs:
            med_cost = statistics.median(costs)
            max_cost = max(costs)
            print(f"\n--- Costi (Modello: {model_in_use})")
            print(f"Costo per elaborato: mediana ${med_cost:.4f}, max ${max_cost:.4f}")
            print(f"Proiezioni mensili:")
            print(f"  -    100 elaborati: ${med_cost * 100:.2f}")
            print(f"  -  1.000 elaborati: ${med_cost * 1000:.2f}")
            print(f"  - 10.000 elaborati: ${med_cost * 10000:.2f}")
        else:
            print(f"\n--- Costi: Modello '{model_in_use}' non presente in tabella prezzi o cache hit totali. Nessuna stima.")

    json.dump(rows, open("metriche.json", "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)
    return rows


if __name__ == "__main__":
    run_batch(sys.argv[1] if len(sys.argv) > 1 else "fixtures/*.json")
