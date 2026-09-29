import sys
import json
import os
from pathlib import Path
from knowflix_engine.ingest.parser import parse_pdf

def main():
    if len(sys.argv) < 3:
        print("Uso: python -m knowflix_engine.ingest <input.pdf> <output.json>")
        sys.exit(1)
        
    pdf_path = sys.argv[1]
    out_path = sys.argv[2]
    
    if not os.path.exists(pdf_path):
        print(f"Errore: file {pdf_path} non trovato.")
        sys.exit(1)
        
    doc_id = Path(pdf_path).stem
    parsed_doc = parse_pdf(pdf_path, doc_id)
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(parsed_doc.model_dump(), f, indent=2, ensure_ascii=False)
        
    print(f"Creato: {out_path}")

if __name__ == "__main__":
    main()
