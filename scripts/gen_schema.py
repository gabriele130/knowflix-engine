"""Genera la documentazione del contratto del motore in docs/.

Produce, a partire dal codice (mai a mano):
  - docs/schema/parsed_document.schema.json   (input)
  - docs/schema/reviewed_profile.schema.json  (output in caso di successo)
  - docs/schema/engine_error.schema.json      (output in caso di errore)
  - docs/ENGINE_CONTRACT.md

Uso:
    uv run python scripts/gen_schema.py           # rigenera i file
    uv run python scripts/gen_schema.py --check   # exit 1 se i file sono obsoleti

docs/schema/example_output.json NON e' prodotto qui: viene da un run reale
(scripts/gen_example_output.py). Questo script si limita a citarlo.
"""
from __future__ import annotations

import ast
import inspect
import json
import sys
import typing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from knowflix_engine import config, main, taxonomy  # noqa: E402
from knowflix_engine.crews.document_crew.document_crew import DocumentCrew  # noqa: E402
from knowflix_engine.guardrails import evidence  # noqa: E402
from knowflix_engine.schemas.models import (  # noqa: E402
    RETRYABLE_CODES,
    SKILL_KINDS,
    SUMMARY_KINDS,
    EngineError,
    ErrorCode,
    ParsedDocument,
    PublicCard,
    ReviewedProfile,
    Section,
    SectionKind,
    Skill,
)

DOCS = ROOT / "docs"
SCHEMA_DIR = DOCS / "schema"

SCHEMAS = {
    "parsed_document.schema.json": ParsedDocument,
    "reviewed_profile.schema.json": ReviewedProfile,
    "engine_error.schema.json": EngineError,
}

# Significato dei campi. I modelli in schemas/models.py non hanno (quasi)
# description, quindi il testo vive qui. Il test di allineamento fallisce se
# un campo del modello non ha una voce in questa tabella, o se qui c'e' una
# voce per un campo che non esiste piu'.
MEANINGS: dict[str, dict[str, str]] = {
    "ParsedDocument": {
        "doc_id": "Identificativo del documento. Insieme a ENGINE_VERSION forma la chiave di cache (`cache/{doc_id}_{ENGINE_VERSION}.json`).",
        "lang": "Lingua del documento; passata ai prompt come `{lang}`.",
        "meta": "Metadati liberi del preprocessor. Non letti dal motore.",
        "sections": "Testo segmentato per sezione; vedi tabella `Section`. Se nessuna sezione usata dal motore contiene testo il job fallisce con `empty_content`.",
        "figures": "Figure estratte dal parser. Usate solo per scegliere `cover_figure_id` (chiavi lette: `id`, `area_ratio`, `has_caption`).",
        "parser_version": "Versione del preprocessor. **Facoltativo**: se assente il payload è accettato; se presente deve essere tra le versioni supportate (§1), altrimenti `unsupported_payload_version`. Il default dello schema si applica solo dopo il controllo.",
        "bibliography": "Bibliografia grezza come testo libero. Non letta dal motore.",
    },
    "Section": {
        "kind": "Tipo di sezione; enum chiuso, vedi §3.",
        "heading": "Titolo originale della sezione. Non letto dal motore.",
        "text": "Testo della sezione.",
    },
    "ReviewedProfile": {
        "one_liner": "Sintesi in una frase (prompt: massimo 25 parole).",
        "abstract_150": "Sintesi di circa 150 parole.",
        "keywords": "Termini tecnici specifici (prompt: 5-10).",
        "skills": "Competenze estratte e revisionate; vedi tabella `Skill`.",
        "rejected": "Competenze scartate, con motivo: dal reviewer (generiche, attribuite a terzi) o dal guardrail (evidence non trovata nel testo).",
        "review_notes": "Note libere del reviewer.",
        "cover_figure_id": "`id` della figura scelta come cover (scoring deterministico in `cover.py`); null se nessuna figura ha punteggio > 0.",
        "taxonomy_version": "Versione della tassonomia usata per il linking (`TAXONOMY_VERSION`). Sempre valorizzato nel profilo restituito.",
        "taxonomy_coverage": "Quota di `skills` con `skill_id` non nullo, arrotondata a 3 decimali; null se il profilo non ha skill. Vedi §4.",
        "public_card": "Scheda pubblica; vedi tabella `PublicCard`. Presente nel contratto ma **non popolata** in questa versione.",
    },
    "Skill": {
        "label": "Nome della competenza come prodotto dall'LLM.",
        "evidence": "Citazione dal documento sorgente che giustifica la competenza; vedi §7.",
        "section_kind": "Sezione di input in cui il motore ha trovato l'evidence. Assegnato dal motore, mai generato dall'LLM; vedi §7.",
        "confidence": "Confidenza dichiarata dall'LLM. Il motore non la calcola né la valida (nessun vincolo di range).",
        "skill_id": "Id canonico in tassonomia, o null; vedi §4.",
    },
    "PublicCard": {
        "abstract": "Non popolato in questa versione: sempre null. Usare `abstract_150`.",
    },
    "EngineError": {
        "code": "Codice dell'errore; vedi tabella in §6.",
        "message": "Descrizione leggibile. Non stabile: non va interpretata dal consumer.",
        "retryable": "true se ripetere lo stesso job più tardi può riuscire. Determinato dal `code`, mai indipendente.",
    },
}

MODELS = {"ParsedDocument": ParsedDocument, "Section": Section,
          "ReviewedProfile": ReviewedProfile, "Skill": Skill,
          "PublicCard": PublicCard, "EngineError": EngineError}

# Quando viene emesso ciascun codice. Stesso controllo di copertura di MEANINGS.
ERROR_MEANINGS: dict[str, str] = {
    "invalid_payload": "Il payload non rispetta lo schema (`ParsedDocument`, o `company_raw` non è un oggetto), oppure `job_type` non è supportato. Il messaggio elenca i campi non validi.",
    "unsupported_payload_version": "`parser_version` è presente ma non è tra le versioni supportate.",
    "unauthorized": "Il provider LLM rifiuta le credenziali (HTTP 401/403, chiave non valida).",
    "empty_content": "Nessun testo nelle sezioni usate dal motore (documento), o nessun campo testuale in `company_raw`.",
    "rate_limited": "Il provider LLM limita le richieste (HTTP 429, quota esaurita).",
    "provider_unavailable": "Il provider LLM non è raggiungibile o è in errore (HTTP 5xx, errore di connessione, sovraccarico).",
    "timeout": "La chiamata al provider LLM è scaduta (HTTP 408/504, timeout).",
    "internal_error": "Qualsiasi altro errore non classificato.",
}


# --------------------------------------------------------------- schema JSON

def render_schema(model) -> str:
    return json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n"


# --------------------------------------------------------- lettura dal codice

def section_kinds() -> list[str]:
    return list(typing.get_args(SectionKind))


def error_codes() -> list[str]:
    return list(typing.get_args(ErrorCode))


def crew_tasks(crew_cls) -> list[str]:
    """Nomi dei metodi @task della crew, nell'ordine in cui sono definiti."""
    tree = ast.parse(inspect.getsource(sys.modules[crew_cls.__module__]))
    return [node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and any(isinstance(d, ast.Name) and d.id == "task" for d in node.decorator_list)]


def guardrail_retries(crew_cls, task_name: str) -> int | None:
    """guardrail_max_retries della task, letto dal sorgente; None se la task non ha guardrail."""
    tree = ast.parse(inspect.getsource(sys.modules[crew_cls.__module__]))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == task_name:
            kws = {k.arg: k.value for n in ast.walk(node) if isinstance(n, ast.Call)
                   for k in n.keywords}
            if "guardrail" not in kws:
                return None
            value = kws["guardrail_max_retries"]
            if isinstance(value, ast.Name):  # costante importata, es. GUARDRAIL_MAX_RETRIES
                return getattr(sys.modules[crew_cls.__module__], value.id)
            return ast.literal_eval(value)
    raise RuntimeError(f"task {task_name} non trovata")


def evidence_threshold() -> float:
    return inspect.signature(evidence._present).parameters["threshold"].default


def _codes(items) -> str:
    return ", ".join(f"`{k}`" for k in items)


# ------------------------------------------------------------------ markdown

def _type_str(annotation) -> str:
    s = str(annotation) if not isinstance(annotation, type) else annotation.__name__
    return (s.replace("typing.", "").replace("knowflix_engine.schemas.models.", "")
             .replace("NoneType", "None").replace("|", "\\|"))


def _default_str(field) -> str:
    if field.default_factory is not None:
        value = field.default_factory()
        value = value.model_dump() if hasattr(value, "model_dump") else value
    else:
        value = field.default
    return f"`{json.dumps(value, ensure_ascii=False)}`"


def field_table(name: str) -> str:
    model = MODELS[name]
    rows = ["| Campo | Tipo | Obbligatorio | Default | Significato |",
            "|---|---|---|---|---|"]
    for fname, f in model.model_fields.items():
        required = f.is_required()
        default = "—" if required else _default_str(f)
        rows.append(f"| `{fname}` | `{_type_str(f.annotation)}` | "
                    f"{'sì' if required else 'no'} | {default} | {MEANINGS[name][fname]} |")
    return "\n".join(rows)


def render_contract() -> str:
    kinds = section_kinds()
    unused = [k for k in kinds if k not in SKILL_KINDS and k not in SUMMARY_KINDS]
    kind_rows = "\n".join(
        f"| `{k}` | {'sì' if k in SUMMARY_KINDS else '—'} | {'sì' if k in SKILL_KINDS else '—'} |"
        for k in kinds)
    tax_rows = "\n".join(f"| `{sid}` | {e['label']} |" for sid, e in taxonomy.TAXONOMY.items())

    tasks = crew_tasks(DocumentCrew)
    if len(tasks) != len(main._TASK_PROGRESS):
        raise RuntimeError(f"task {tasks} e progress {main._TASK_PROGRESS} non allineati")
    progress_rows = "\n".join(
        [f"| `0` | Avvio della crew, prima del primo task |"]
        + [f"| `{p}` | Fine del task `{t}` |" for t, p in zip(tasks, main._TASK_PROGRESS)])

    guarded = [(t, guardrail_retries(DocumentCrew, t)) for t in tasks]
    guarded = [(t, r) for t, r in guarded if r is not None]
    guarded_str = ", ".join(f"`{t}` (max {r} retry)" for t, r in guarded)

    error_rows = "\n".join(
        f"| `{c}` | {'**true**' if c in RETRYABLE_CODES else 'false'} | {ERROR_MEANINGS[c]} |"
        for c in error_codes())

    example = SCHEMA_DIR / "example_output.json"
    example_line = (
        "[`schema/example_output.json`](schema/example_output.json) — output di un run "
        "reale sul fixture, generato da `scripts/gen_example_output.py` (metadati del run in "
        "[`schema/example_output.meta.json`](schema/example_output.meta.json))."
        if example.exists() else
        "_Nessun esempio presente: eseguire `scripts/gen_example_output.py`._")

    return f"""<!-- GENERATO da scripts/gen_schema.py — NON MODIFICARE A MANO.
     Per aggiornare: uv run python scripts/gen_schema.py -->

# Knowflix Engine — Contratto

## 1 · Versioni

| Cosa | Valore | Fonte |
|---|---|---|
| Motore (`ENGINE_VERSION`) | `{config.ENGINE_VERSION}` | `config.py` |
| Tassonomia (`TAXONOMY_VERSION`) | `{config.TAXONOMY_VERSION}` | `config.py` |
| `parser_version` supportate | {_codes(config.SUPPORTED_PARSER_VERSIONS)} | `config.SUPPORTED_PARSER_VERSIONS` |
| Voci in tassonomia | {len(taxonomy.TAXONOMY)} | `taxonomy.TAXONOMY` |

`ENGINE_VERSION` è anche parte della chiave di cache: un cambio di versione
invalida i profili salvati in `cache/`. `TAXONOMY_VERSION` è restituita in
ogni profilo come `taxonomy_version`.

`parser_version` è **facoltativo**: un payload che non lo contiene viene
accettato; un valore presente e non supportato viene rifiutato con
`unsupported_payload_version`.

JSON Schema:
- input: [`schema/parsed_document.schema.json`](schema/parsed_document.schema.json)
- output, successo: [`schema/reviewed_profile.schema.json`](schema/reviewed_profile.schema.json)
- output, errore: [`schema/engine_error.schema.json`](schema/engine_error.schema.json)
- esempio: {example_line}

## 2 · Campi

### Input — `ParsedDocument`

{field_table("ParsedDocument")}

#### `Section`

{field_table("Section")}

### Output — `ReviewedProfile`

{field_table("ReviewedProfile")}

#### `Skill`

{field_table("Skill")}

#### `PublicCard`

{field_table("PublicCard")}

`public_card` contiene il solo campo `abstract`, **non popolato in questa
versione**: il motore non fa nessuna generazione aggiuntiva per la scheda.

### Output — `EngineError`

{field_table("EngineError")}

## 3 · Sezioni accettate

`Section.kind` accetta esattamente questi valori (qualsiasi altro valore dà
`invalid_payload`):

| `kind` | Usata per la sintesi (`text_summary`) | Usata per le competenze (`text_skills`) |
|---|---|---|
{kind_rows}

- Le competenze sono estratte **solo** da: {_codes(SKILL_KINDS)}.
  La task `extract_skills` ha `context=[]`: non vede la sintesi.
- Sezioni accettate ma escluse sia dalla sintesi sia dall'estrazione
  competenze: {_codes(unused)}. Un'evidenza presa da queste sezioni viene
  rifiutata (§7).

## 4 · `skill_id` e copertura tassonomica

`skill_id` è assegnato in `finalize` da `taxonomy.link_profile`, in modo
deterministico (nessun LLM): match esatto su label/sinonimi, poi fuzzy-match
`SequenceMatcher` con soglia **{taxonomy._FUZZY_THRESHOLD}**.

`skill_id: null` significa che la `label` non ha un match sopra soglia nella
tassonomia `{config.TAXONOMY_VERSION}`. **Non** è un giudizio sulla competenza:
il linking guarda solo la `label` e non tocca né filtra le skill, che passano
la stessa verifica delle evidenze di quelle linkate (§7). La tassonomia
corrente contiene solo queste voci:

| `skill_id` | Label |
|---|---|
{tax_rows}

`taxonomy_coverage` = numero di skill con `skill_id` non nullo / numero di
skill, arrotondato a 3 decimali. Su un profilo senza skill vale **null**
(non 0 e non 1): `link_profile` non viene eseguito e il rapporto non è
definito. Una copertura bassa indica una tassonomia incompleta per il
dominio del documento, non competenze meno affidabili.

## 5 · Progress

Il Flow emette un avanzamento ai confini dei task della crew
({_codes(tasks)}):

| Valore | Fase |
|---|---|
{progress_rows}

- Lettura: `state.progress` (ultimo valore emesso, null prima dell'avvio) o
  callback `KnowflixFlow(on_progress=fn)`, chiamata con il valore.
- Monotono: se un errore transitorio fa ripartire la crew dal primo task, il
  valore non torna indietro.
- Profilo in cache: vengono emessi solo `0` e `100`.
- Errore: il progress si ferma all'ultimo valore emesso (o non viene emesso
  affatto se il payload è rifiutato in `ingest`); il risultato è l'oggetto
  errore (§6).
- Il ramo `company` emette gli stessi valori sui suoi tre task.

## 6 · Errori

Se il job fallisce, `finalize` restituisce un `EngineError` **invece** del
profilo: `state.error` contiene l'oggetto e `state.profile` è null. Non
viene mai restituito un `ReviewedProfile` parziale.

```json
{{"code": "rate_limited", "message": "<descrizione>", "retryable": true}}
```

| `code` | `retryable` | Quando |
|---|---|---|
{error_rows}

- `retryable` è derivato dal codice ({_codes(sorted(RETRYABLE_CODES))} → true,
  tutti gli altri → false); il modello rifiuta combinazioni incoerenti.
- Prima di restituire un errore ritentabile, il motore ha già ritentato
  internamente fino a {main._MAX_RETRIES} volte con backoff esponenziale (base
  {main._BASE_DELAY}s). Un `retryable: true` significa "riprova più tardi", non
  "riprova subito".
- La classificazione usa lo status HTTP dell'eccezione quando c'è, altrimenti
  frasi non ambigue nel messaggio; tutto ciò che non è riconosciuto è
  `internal_error`.
- I profili in errore non vengono salvati in cache.

## 7 · Evidenze: cosa è garantito e cosa no

Il guardrail delle evidenze è applicato a {guarded_str}: la verifica
vale quindi sul **profilo finale**, non solo sull'output intermedio. Se il
modello produce un'evidenza non presente nel testo, il guardrail la rifiuta e
la task viene ritentata; se i retry si esauriscono, le sole competenze ancora
non verificate vengono **rimosse** dal profilo e riportate in `rejected` come
`"<label>: evidence non trovata nel testo"`. Il job non fallisce per questo
motivo.

Garantito, per ogni `Skill.evidence` del profilo restituito:
- compare dentro **una singola sezione** tra {_codes(SKILL_KINDS)}. Un'evidenza
  che scavalca due sezioni, o che viene da altre sezioni
  ({_codes(unused + list(SUMMARY_KINDS))}), viene rifiutata. Unico margine:
  la tolleranza del fuzzy match, che in teoria può lasciar passare uno
  sconfinamento di pochi caratteri nella sezione adiacente;
- il confronto avviene dopo normalizzazione (minuscole, spazi collassati,
  a-capo e sillabazione `-\\n` rimossi): match esatto oppure fuzzy ≥
  **{evidence_threshold()}** su una finestra della stessa lunghezza;
- evidenze più corte di 10 caratteri (normalizzate) sono rifiutate;
- `section_kind` è la sezione in cui l'evidenza è stata trovata (la prima,
  in ordine di documento, se compare in più sezioni). Lo assegna il motore,
  non l'LLM.

Ramo `company`: l'intero testo di `company_raw` è un'unica sezione e
`section_kind` vale sempre `other`.

Non garantito:
- che l'evidenza sia una copia **byte per byte**: con il fuzzy match possono
  differire maiuscole, spazi e fino a ~10% dei caratteri;
- che l'evidenza **sostenga** semanticamente la `label` (il guardrail verifica
  la presenza della citazione, non la pertinenza);
- `confidence`: valore dichiarato dall'LLM, non calibrato.
"""


# -------------------------------------------------------------------- entry

def build_artifacts() -> dict[Path, str]:
    """Contenuto atteso di ogni file generato, indicizzato per path."""
    out = {SCHEMA_DIR / name: render_schema(model) for name, model in SCHEMAS.items()}
    out[DOCS / "ENGINE_CONTRACT.md"] = render_contract()
    return out


def check_meanings() -> list[str]:
    errors = []
    for name, model in MODELS.items():
        fields, documented = set(model.model_fields), set(MEANINGS.get(name, {}))
        errors += [f"{name}.{f}: manca il significato in MEANINGS" for f in fields - documented]
        errors += [f"{name}.{f}: in MEANINGS ma non nel modello" for f in documented - fields]
    codes, documented = set(error_codes()), set(ERROR_MEANINGS)
    errors += [f"errore {c}: manca in ERROR_MEANINGS" for c in codes - documented]
    errors += [f"errore {c}: in ERROR_MEANINGS ma non in ErrorCode" for c in documented - codes]
    return errors


def stale_files() -> list[Path]:
    return [p for p, content in build_artifacts().items()
            if not p.exists() or p.read_text(encoding="utf-8") != content]


def main_cli(argv: list[str]) -> int:
    errors = check_meanings()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if "--check" in argv:
        stale = stale_files()
        for p in stale:
            print(f"obsoleto: {p.relative_to(ROOT)}", file=sys.stderr)
        return 1 if stale else 0
    for path, content in build_artifacts().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"scritto: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli(sys.argv[1:]))
