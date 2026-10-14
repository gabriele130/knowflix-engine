"""Server di prova per il KnowflixFlow: carichi un documento, vedi il risultato.

Solo per uso locale: nessuna autenticazione, si lega a 127.0.0.1.

    uv run python devserver/server.py            # http://127.0.0.1:8765
    uv run python devserver/server.py --port 9000

Dietro un antivirus che ispeziona l'HTTPS (es. Norton) le chiamate al
provider falliscono con CERTIFICATE_VERIFY_FAILED; in quel caso:

    uv run --native-tls --with truststore python devserver/server.py

Accetta un PDF (segmentato con ingest.parser.parse_pdf) oppure un JSON gia'
nel formato ParsedDocument (es. fixtures/doc_test.json). I job sono eseguiti
uno alla volta: il contesto del guardrail evidence e' globale al modulo.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import sys
import tempfile
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)  # cache/ relativa alla root del progetto, come per `crewai run`

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

try:  # usa l'archivio certificati di sistema se disponibile (vedi docstring)
    import truststore
    truststore.inject_into_ssl()
    TLS_STORE = "sistema (truststore)"
except ImportError:
    TLS_STORE = "certifi"

from knowflix_engine.config import ENGINE_VERSION, TAXONOMY_VERSION  # noqa: E402
from knowflix_engine.main import KnowflixFlow  # noqa: E402
from knowflix_engine.schemas.models import (  # noqa: E402
    SKILL_KINDS,
    SUMMARY_KINDS,
    EngineError,
)

MAX_UPLOAD = 50 * 1024 * 1024
# documenti di prova serviti dal pulsante "Prova con..." (nome pubblico -> file)
SAMPLES = {
    "tesi_esempio.pdf": Path(__file__).resolve().parent / "samples" / "tesi_esempio.pdf",
    "doc_test.json": ROOT / "fixtures" / "doc_test.json",
}
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
WORK: queue.Queue[str] = queue.Queue()


def _update(job_id: str, **fields) -> None:
    with JOBS_LOCK:
        JOBS[job_id].update(fields)


def _section_summary(parsed: dict) -> list[dict]:
    """Cosa ha trovato il parser: utile per capire perche' mancano competenze."""
    out = []
    for s in parsed.get("sections", []) if isinstance(parsed, dict) else []:
        if not isinstance(s, dict):
            continue
        kind = s.get("kind")
        use = ("competenze" if kind in SKILL_KINDS else
               "sintesi" if kind in SUMMARY_KINDS else "ignorata")
        out.append({"kind": kind, "heading": s.get("heading"),
                    "chars": len(s.get("text") or ""), "use": use})
    return out


def _to_parsed(filename: str, body: bytes, doc_id: str) -> dict:
    """PDF o JSON -> dict ParsedDocument. Solleva ValueError con messaggio leggibile."""
    if filename.lower().endswith(".pdf") or body[:5] == b"%PDF-":
        from knowflix_engine.ingest.parser import parse_pdf
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "upload.pdf"
            path.write_bytes(body)
            try:
                return parse_pdf(str(path), doc_id).model_dump()
            except Exception as exc:
                raise ValueError(f"PDF non leggibile: {exc}") from exc
    try:
        parsed = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"il file non e' ne' un PDF ne' un JSON valido: {exc}") from exc
    if isinstance(parsed, dict):
        parsed.setdefault("doc_id", doc_id)
    return parsed


def worker() -> None:
    while True:
        job_id = WORK.get()
        with JOBS_LOCK:
            job = dict(JOBS[job_id])
        _update(job_id, status="running", started_at=time.time())
        t0 = time.time()
        try:
            flow = KnowflixFlow(on_progress=lambda v: _update(job_id, progress=v))
            flow.kickoff(inputs={"job_id": job_id, "job_type": "document",
                                 "parsed": job["parsed"]})
            st = flow.state
            _update(job_id,
                    status="failed" if st.error else "done",
                    result=st.profile, error=st.error,
                    cached=bool(st.metrics.get("cached")),
                    usage=st.metrics.get("usage"),
                    seconds=round(time.time() - t0, 1))
        except Exception as exc:  # il Flow non dovrebbe sollevare: e' un bug
            traceback.print_exc()
            _update(job_id, status="failed",
                    error=EngineError.of("internal_error", f"{type(exc).__name__}: {exc}").model_dump(),
                    seconds=round(time.time() - t0, 1))
        finally:
            WORK.task_done()


def _public(job: dict) -> dict:
    out = {k: v for k, v in job.items() if k != "parsed"}
    out["queue_position"] = (
        sum(1 for j in JOBS.values() if j["status"] == "queued" and j["created_at"] < job["created_at"])
        if job["status"] == "queued" else 0)
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "KnowflixDev/1.0"

    def log_message(self, fmt, *args):  # meno rumore: crewai stampa gia' molto
        if not self.path.startswith("/api/jobs/"):
            sys.stderr.write("[devserver] " + (fmt % args) + "\n")

    def _send(self, status: int, payload, content_type="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(
            payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path.startswith("/samples/"):
            name = path.rsplit("/", 1)[-1]
            src = SAMPLES.get(name)
            if src is None or not src.exists():
                return self._send(404, {"detail": f"esempio {name} non disponibile"})
            ctype = "application/pdf" if name.endswith(".pdf") else "application/json"
            return self._send(200, src.read_bytes(), ctype)
        if path == "/api/info":
            return self._send(200, {
                "engine_version": ENGINE_VERSION,
                "taxonomy_version": TAXONOMY_VERSION,
                "model": os.getenv("MODEL", "gemini/gemini-3.6-flash"),
                "tls_store": TLS_STORE,
                "summary_kinds": list(SUMMARY_KINDS),
                "skill_kinds": list(SKILL_KINDS),
            })
        m = re.fullmatch(r"/api/jobs/([0-9a-f]{32})", path)
        if m:
            with JOBS_LOCK:
                job = JOBS.get(m.group(1))
                return self._send(200, _public(job)) if job else self._send(404, {"detail": "job non trovato"})
        self._send(404, {"detail": "non trovato"})

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/api/jobs":
            return self._send(404, {"detail": "non trovato"})
        length = int(self.headers.get("Content-Length") or 0)
        if not 0 < length <= MAX_UPLOAD:
            return self._send(413, {"detail": f"file vuoto o oltre {MAX_UPLOAD // 2**20} MB"})
        body = self.rfile.read(length)
        filename = (parse_qs(url.query).get("filename") or ["documento"])[0]
        doc_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).stem)[:80] or "documento"

        job_id = uuid.uuid4().hex
        job = {"id": job_id, "filename": filename, "doc_id": doc_id,
               "status": "queued", "progress": None, "result": None, "error": None,
               "created_at": time.time()}
        try:
            job["parsed"] = _to_parsed(filename, body, doc_id)
        except ValueError as exc:
            job.update(status="failed", parsed=None,
                       error=EngineError.of("invalid_payload", str(exc)).model_dump())
        job["sections"] = _section_summary(job["parsed"])
        with JOBS_LOCK:
            JOBS[job_id] = job
        if job["status"] == "queued":
            WORK.put(job_id)
        with JOBS_LOCK:
            self._send(202, _public(JOBS[job_id]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    threading.Thread(target=worker, daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Knowflix dev server su http://127.0.0.1:{args.port}  "
          f"(modello: {os.getenv('MODEL', 'gemini/gemini-3.6-flash')}, TLS: {TLS_STORE})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
