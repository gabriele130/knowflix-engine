import json
import os
import yaml
from pathlib import Path

from knowflix_engine.main import KnowflixFlow
from knowflix_engine.guardrails.evidence import _present, _norm

def run_eval():
    golden_dir = Path("eval/golden")
    if not golden_dir.exists():
        print("Cartella eval/golden non trovata.")
        return

    results = []
    
    total_expected = 0
    total_produced = 0
    total_matched = 0
    total_core_expected = 0
    total_core_matched = 0
    
    total_evidence_extracted = 0
    total_evidence_present = 0

    print(f"{'DOC_ID':<15} | {'PREC':<5} | {'REC':<5} | {'F1':<5} | {'CORE REC':<8} | {'EVIDENCE %':<10}")
    print("-" * 65)

    for golden_file in golden_dir.glob("*.yaml"):
        with open(golden_file, "r", encoding="utf-8") as f:
            golden_data = yaml.safe_load(f)
            
        doc_id = golden_data["doc_id"]
        expected_skills = golden_data.get("expected_skills", [])
        
        # Cerca il parsed document corrispondente
        # Assumiamo che si chiami <doc_id>.json o simile, cerchiamolo in fixtures
        parsed_path = Path(f"fixtures/{doc_id}.json")
        if not parsed_path.exists():
            print(f"Skipping {doc_id}: parsed document non trovato in fixtures/")
            continue
            
        with open(parsed_path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
            
        # Run flow
        flow = KnowflixFlow()
        flow.kickoff(inputs={
            "job_id": doc_id,
            "job_type": "document",
            "parsed": parsed,
        })
        
        profile = flow.state.profile or {}
        produced_skills = profile.get("skills", [])
        
        # Recupera full text per check evidence
        full_text = "\n\n".join(s["text"] for s in parsed.get("sections", []))
        hay = _norm(full_text)
        
        expected_ids = set(s.get("skill_id") for s in expected_skills)
        produced_ids = set(s.get("skill_id") for s in produced_skills if s.get("skill_id"))
        core_expected_ids = set(s.get("skill_id") for s in expected_skills if s.get("tier") == "core")
        
        matched = expected_ids.intersection(produced_ids)
        core_matched = core_expected_ids.intersection(produced_ids)
        
        tp = len(matched)
        fp = len(produced_ids) - tp
        fn = len(expected_ids) - tp
        
        prec = tp / len(produced_ids) if produced_ids else 0.0
        rec = tp / len(expected_ids) if expected_ids else 0.0
        f1 = 2 * (prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        
        core_rec = len(core_matched) / len(core_expected_ids) if core_expected_ids else 0.0
        
        evidence_present = 0
        for ps in produced_skills:
            if _present(ps.get("evidence", ""), hay):
                evidence_present += 1
                
        ev_perc = (evidence_present / len(produced_skills) * 100) if produced_skills else 0.0
        
        print(f"{doc_id:<15} | {prec:.2f} | {rec:.2f} | {f1:.2f} | {core_rec:.2f}     | {ev_perc:.1f}%")
        
        results.append({
            "doc_id": doc_id,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "core_recall": core_rec,
            "evidence_present_perc": ev_perc
        })
        
        total_expected += len(expected_ids)
        total_produced += len(produced_ids)
        total_matched += tp
        total_core_expected += len(core_expected_ids)
        total_core_matched += len(core_matched)
        
        total_evidence_extracted += len(produced_skills)
        total_evidence_present += evidence_present

    print("-" * 65)
    
    agg_prec = total_matched / total_produced if total_produced else 0.0
    agg_rec = total_matched / total_expected if total_expected else 0.0
    agg_f1 = 2 * (agg_prec * agg_rec) / (agg_prec + agg_rec) if (agg_prec + agg_rec) > 0 else 0.0
    agg_core_rec = total_core_matched / total_core_expected if total_core_expected else 0.0
    agg_ev_perc = (total_evidence_present / total_evidence_extracted * 100) if total_evidence_extracted else 0.0
    
    print(f"{'AGGREGATE':<15} | {agg_prec:.2f} | {agg_rec:.2f} | {agg_f1:.2f} | {agg_core_rec:.2f}     | {agg_ev_perc:.1f}%")

    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    run_eval()
