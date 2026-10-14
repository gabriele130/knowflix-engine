"""Lancia un job sul KnowflixFlow deployato su CrewAI AMP e ne attende il risultato.

    uv run python scripts/amp_kickoff.py fixtures/doc_test.json
    uv run python scripts/amp_kickoff.py devserver/samples/tesi_esempio_2.pdf

Legge AMP_URL e AMP_TOKEN da .env. Un PDF viene prima segmentato in locale con
ingest.parser.parse_pdf (richiede pymupdf, gruppo dev): il motore riceve sempre
un ParsedDocument, come dal backend.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

TERMINAL = {"SUCCESS", "COMPLETED", "FAILED", "ERROR", "CANCELLED"}


def load_parsed(path: Path) -> dict:
    if path.suffix.lower() == ".pdf":
        from knowflix_engine.ingest.parser import parse_pdf
        return parse_pdf(str(path), path.stem).model_dump()
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", type=Path, help="ParsedDocument JSON oppure PDF")
    ap.add_argument("--poll", type=float, default=5.0, help="secondi tra due controlli di stato")
    ap.add_argument("--timeout", type=float, default=900.0, help="attesa massima in secondi")
    args = ap.parse_args()

    load_dotenv()
    try:
        base = os.environ["AMP_URL"].rstrip("/")
        token = os.environ["AMP_TOKEN"].strip()
    except KeyError as e:
        sys.exit(f"variabile {e} mancante in .env")

    parsed = load_parsed(args.path)
    inputs = {"job_id": parsed.get("doc_id", ""), "job_type": "document", "parsed": parsed}

    with httpx.Client(base_url=base, headers={"Authorization": f"Bearer {token}"}, timeout=60) as client:
        r = client.post("/kickoff", json={"inputs": inputs})
        r.raise_for_status()
        kickoff_id = r.json()["kickoff_id"]
        print(f"kickoff_id: {kickoff_id}", file=sys.stderr)

        start, last = time.monotonic(), None
        while True:
            r = client.get(f"/status/{kickoff_id}")
            r.raise_for_status()
            status = r.json()
            state = str(status.get("state", "")).upper()
            if state != last:
                print(f"[{time.monotonic() - start:5.0f}s] {state}", file=sys.stderr)
                last = state
            if state in TERMINAL:
                break
            if time.monotonic() - start > args.timeout:
                sys.exit(f"timeout dopo {args.timeout:.0f}s, ultimo stato {state}")
            time.sleep(args.poll)

    result = status.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            pass
    print(json.dumps(result if result is not None else status, indent=2, ensure_ascii=False))
    # il flow termina "SUCCESS" anche quando restituisce un EngineError
    engine_error = isinstance(result, dict) and {"code", "message", "retryable"} <= result.keys()
    return 0 if state in {"SUCCESS", "COMPLETED"} and not engine_error else 1


if __name__ == "__main__":
    sys.exit(main())
