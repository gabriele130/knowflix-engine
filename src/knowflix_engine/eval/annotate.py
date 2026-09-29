import json
import os
import sys
import yaml
from pathlib import Path
from knowflix_engine.schemas.models import ParsedDocument

def main():
    if len(sys.argv) < 2:
        print("Uso: python annotate.py <percorso/a/parsed_document.json>")
        sys.exit(1)
        
    doc_path = sys.argv[1]
    with open(doc_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    doc = ParsedDocument(**data)
    
    golden_dir = Path("eval/golden")
    golden_dir.mkdir(parents=True, exist_ok=True)
    
    out_yaml = golden_dir / f"{doc.doc_id}.yaml"
    
    skeleton = {
        "doc_id": doc.doc_id,
        "expected_skills": [
            {
                "skill_id": "example-skill",
                "evidence": "Inserisci qui la frase esatta",
                "tier": "core" # o bonus
            }
        ]
    }
    
    if not out_yaml.exists():
        with open(out_yaml, "w", encoding="utf-8") as f:
            yaml.dump(skeleton, f, allow_unicode=True, sort_keys=False)
        print(f"Creato scheletro in {out_yaml}")
    else:
        print(f"File {out_yaml} esistente. Nessuna modifica.")
        
    print("\n--- TESTO PER ANNOTAZIONE (Method & Results) ---\n")
    print(doc.text_of(("method", "results")))
    print("\n------------------------------------------------\n")

if __name__ == "__main__":
    main()
