# CLAUDE.md — Knowflix Engine

> Guida di riferimento per assistenti AI. Leggere **prima** di toccare qualsiasi
> file del progetto.

---

## 1 · Cos'è Knowflix Engine

Un progetto **CrewAI Flow** che riceve un documento scientifico già segmentato
(tesi, paper) e ne estrae un profilo strutturato di competenze tecniche,
sintesi e keyword. L'output è pensato per essere consumato da un backend e un
frontend downstream.

---

## 2 · Architettura del Flow

```
                  ┌──────────┐
                  │  ingest  │   valida ParsedDocument
                  └────┬─────┘
                       │
                  ┌────▼─────┐
                  │ dispatch │   router Python (job_type)
                  └──┬────┬──┘
                     │    │
          ┌──────────▼┐  ┌▼────────────┐
          │ "document" │  │  "company"  │
          │ run_document│  │ run_company │
          └──────┬─────┘  └──────┬──────┘
                 │               │
                 └───────┬───────┘
                    ┌────▼────┐
                    │finalize │   linking tassonomia + cover (persistenza: TODO)
                    └─────────┘
```

### Passaggi chiave del ramo `document`

| Step | Cosa fa |
|------|---------|
| `ingest` | Valida l'input (`parser_version` se presente, schema `ParsedDocument`, contenuto non vuoto); in caso di errore registra un `EngineError` e i rami successivi non lanciano crew |
| `dispatch` | **Router deterministico Python** — legge `state.job_type` e instrada |
| `run_document` | Passa al guardrail le sole sezioni `SKILL_KINDS`, lancia `DocumentCrew` (progress 0/33/66/100), assembla il `ReviewedProfile` assegnando `section_kind` dalla sezione in cui l'evidence è trovata |
| `finalize` | Punto di convergenza per tutti i rami; restituisce l'`EngineError` se il job è fallito, altrimenti chiama `link_profile` (se ci sono skill), calcola `taxonomy_coverage` e imposta `taxonomy_version`; persistenza ed evento di indicizzazione restano TODO |

### Pipeline della DocumentCrew (sequential)

```
analyst → summarize (→ SummaryOutput)
skill_extractor → extract_skills (→ ExtractedSkills, guardrail: evidence)
reviewer → review (→ ReviewDraft, guardrail: evidence, context: summarize + extract_skills)
```

- **analyst / summarize**: produce `one_liner`, `abstract_150`, `keywords` a
  partire da `SUMMARY_KINDS` (abstract + introduction + conclusions).
- **skill_extractor / extract_skills**: estrae competenze (label, evidence
  verbatim, confidence) da `SKILL_KINDS` (methodology + results +
  discussion). Non produce `section_kind`.
- **reviewer / review**: unisce sintesi e competenze, scarta le generiche,
  produce un `ReviewDraft`. Il motore lo trasforma in `ReviewedProfile`
  (`main.assemble_profile`).
- Il guardrail `evidence_guardrail` è applicato sia a `extract_skills` sia a
  `review` (max 2 retry ciascuno): la garanzia sulle evidence vale sul
  profilo finale. Stessa struttura nella `ScoutCrew`.

---

## 3 · Mappa dei moduli

```
src/knowflix_engine/
├── main.py                     # Flow (KnowflixFlow), stato, entry-point CLI
├── llms.py                     # Istanze LLM condivise (LLM_MAIN, LLM_CHEAP)
├── config.py                   # ENGINE_VERSION (chiave cache), TAXONOMY_VERSION,
│                               # SUPPORTED_PARSER_VERSIONS, tabella prezzi
├── taxonomy.py                 # link_profile: linking deterministico skill → tassonomia
├── cover.py                    # pick_cover/score_figure: scoring deterministico figure
├── feedback.py                 # log_correction: logging correzioni umane in JSONL
├── schemas/
│   └── models.py               # Modelli Pydantic, SectionKind, SUMMARY/SKILL_KINDS,
│                               # EngineError: contratto dati pubblico ⚠️
├── guardrails/
│   └── evidence.py             # Guardrail evidence + locate_evidence (section_kind)
├── crews/
│   ├── document_crew/
│   │   ├── document_crew.py    # Crew @CrewBase, agenti, task, guardrail wiring
│   │   └── config/
│   │       ├── agents.yaml     # Ruoli/goal/backstory dei 3 agenti
│   │       └── tasks.yaml      # Descrizioni task con interpolazione {lang}, {text_*}
│   └── scout_crew/
│       ├── scout_crew.py       # Crew @CrewBase, stessa struttura a 3 task di document_crew
│       └── config/
│           ├── agents.yaml     # analyst, tech_scout, reviewer
│           └── tasks.yaml      # Interpolazione {lang}, {text_company}
├── tools/
│   ├── __init__.py
│   └── custom_tool.py          # Tool di esempio (template scaffold)
└── eval/
    └── measure.py              # Batch runner su fixtures/ con metriche aggregate
```

File nella root:

| File | Ruolo |
|------|-------|
| `fixtures/doc_test.json` | Documento di test usato come input di default |
| `prova_crew.py` | Script manuale per testare la crew isolata |
| `prova_company.py` | Script manuale per testare il ramo `company` |
| `scripts/gen_schema.py` | Genera `docs/schema/*.schema.json` e `docs/ENGINE_CONTRACT.md` dal codice (`--check` per verificare) |
| `scripts/gen_example_output.py` | Run reale sul fixture → `docs/schema/example_output.json` |
| `docs/` | Documentazione del contratto, **generata**: non modificarla a mano |
| `pyproject.toml` | Metadata progetto, entry-point, tipo `flow` |
| `.env` | Chiavi API e configurazione modello (git-ignored) |

---

## 4 · Contratto dati

### `ParsedDocument` (input)

```python
class ParsedDocument(BaseModel):
    doc_id: str
    lang: str = "it"
    meta: dict = {}
    sections: list[Section]     # kind: SectionKind, vedi sotto
    figures: list[dict] = []
    parser_version: str = "1.0" # facoltativo, vedi sotto
    bibliography: str = ""
```

`SectionKind` = `abstract`, `introduction`, `methodology`, `results`,
`discussion`, `conclusions`, `bibliography`, `appendix`, `other`.

- `SUMMARY_KINDS` = abstract, introduction, conclusions → sintesi.
- `SKILL_KINDS` = methodology, results, discussion → estrazione competenze
  e unico perimetro in cui il guardrail cerca le evidence.
- `bibliography`, `appendix`, `other` sono accettate in ingresso ma escluse
  da sintesi ed estrazione.

`parser_version` è facoltativo: se assente il payload è accettato; se
presente deve stare in `config.SUPPORTED_PARSER_VERSIONS`, altrimenti
`unsupported_payload_version`. Non trasformarlo in un gate obbligatorio: il
backend oggi non lo invia.

Metodi helper: `text_of(kinds)` e `full_text()`.

Il JSON di input (prodotto dal preprocessor PyMuPDF a monte) deve rispettare
questo schema. Se nessuna sezione usata dal motore contiene testo il job
fallisce con `empty_content`.

### `ReviewedProfile` (output)

```python
class ReviewedProfile(BaseModel):
    one_liner: str
    abstract_150: str
    keywords: list[str]
    skills: list[Skill]         # Skill = label + evidence + section_kind
                                #         (SectionKind) + confidence + skill_id?
    rejected: list[str] = []
    review_notes: str = ""
    cover_figure_id: str | None = None
    taxonomy_version: str | None = None
    taxonomy_coverage: float | None = None
    public_card: PublicCard     # solo `abstract`, non popolato
```

`Skill.section_kind` è assegnato dal motore (`locate_evidence`: la sezione in
cui l'evidence è trovata), **mai** generato dall'LLM.

Questo è l'output finale del Flow, serializzato in `state.profile` come dict
e stampato su stdout. `skill_id` su ogni `Skill` è popolato in `finalize` da
`taxonomy.link_profile` (lookup statico + fuzzy-match, mai LLM); resta `None`
se non c'è match sopra soglia. `cover_figure_id` è popolato in `run_document`
da `cover.pick_cover` sulle `figures` del documento, stesso criterio
deterministico. `taxonomy_coverage` è la quota di skill con `skill_id` non
nullo (null senza skill); `taxonomy_version` è `config.TAXONOMY_VERSION`.

Se il job fallisce, il Flow restituisce invece un `EngineError`
(`code`, `message`, `retryable`) in `state.error`, con `state.profile`
null: mai un profilo parziale. Solo `rate_limited`, `provider_unavailable` e
`timeout` sono `retryable`.

I modelli intermedi `SummaryOutput`, `ExtractedSkills` e `ReviewDraft` sono
usati come `output_pydantic` nelle singole task per forzare output
strutturato. `SkillsOutput` non è più usato dalle crew.

Il contratto completo è in `docs/ENGINE_CONTRACT.md`, generato da
`scripts/gen_schema.py`; `tests/test_contract_docs.py` fallisce se resta
indietro rispetto ai modelli.

---

## 5 · Come si lancia il progetto

### Prerequisiti

- Python ≥ 3.10, < 3.14
- [uv](https://docs.astral.sh/uv/) installato
- Un provider LLM configurato: Gemini (chiave `GEMINI_API_KEY`) oppure
  Ollama locale (`MODEL=ollama/...`, `API_BASE=http://localhost:11434`)

### Setup

```bash
uv sync                           # installa dipendenze
cp .env.example .env              # se esiste, altrimenti crea .env manualmente
# popola .env con MODEL e chiave API
```

### Run

```bash
# Modo 1: via entry-point crewai
crewai run

# Modo 2: via script registrato
uv run kickoff                     # usa fixtures/doc_test.json
uv run kickoff path/to/doc.json   # documento specifico

# Modo 3: direttamente
uv run python -m knowflix_engine.main

# Batch evaluation
uv run python -m knowflix_engine.eval.measure "fixtures/*.json"

# Visualizzazione grafo del flow
uv run plot
```

### Output

- Profilo JSON su `stdout`
- Metriche (secondi, token) su `stderr` / stdout
- Batch: risultati salvati in `metriche.json`

---

## 6 · Invarianti — File che NON vanno modificati senza discussione

> **Regola generale**: prima di modificare uno qualsiasi di questi file, apri
> una discussione col maintainer. Non fare refactor "di passaggio".

### 6.1 · `schemas/models.py` — Contratto pubblico

`schemas/models.py` è il **contratto dati condiviso con backend e frontend**.

- ✅ Si può **estendere**: aggiungere campi opzionali (con default), nuovi
  modelli, nuovi metodi helper.
- ❌ **Non si modifica** la shape dei modelli esistenti: non rinominare campi,
  non cambiarne il tipo, non rimuoverli.
- ❌ Non spostare il modulo né cambiarne il path di import.
- ❌ Non togliere né rinominare valori di `SectionKind` o `ErrorCode`, e non
  cambiare quali codici sono in `RETRYABLE_CODES`: il backend ci si appoggia.
- ✅ Dopo ogni modifica ai modelli: `uv run python scripts/gen_schema.py` e
  commit dei file in `docs/` generati.

### 6.2 · `guardrails/evidence.py` — Soglia evidence

Il guardrail `evidence_guardrail` verifica che ogni evidence sia una
citazione testuale presente **dentro una singola sezione** tra `SKILL_KINDS`
(methodology, results, discussion), con fuzzy match ≥ 0.90. Un'evidence che
scavalca due sezioni o viene da altre sezioni è rifiutata. È applicato sia a
`extract_skills` sia a `review` (e agli omologhi della `ScoutCrew`), così la
garanzia vale sul profilo finale.

- ❌ **Non si allenta la soglia** per far passare più competenze.
- ❌ Non si disabilita il guardrail su nessuna delle due task, e non si
  alzano i `guardrail_max_retries` oltre un livello ragionevole.
- ❌ Non si allarga il perimetro di ricerca oltre `SKILL_KINDS` (es. al
  full-text): `section_kind` deve restare la sezione di provenienza reale.
- ✅ Si può rendere il matching più robusto (normalizzazione, encoding), ma
  mai meno restrittivo.

### 6.3 · Router del Flow (`main.py` → `dispatch`)

```python
@router(ingest)
def dispatch(self, previous_result):
    return self.state.job_type
```

- ❌ Il routing **resta codice Python deterministico**, mai una decisione LLM.
- ✅ Si possono aggiungere nuovi rami (es. `"portfolio"`), ma sempre come
  `if`/`return` esplicito su `job_type`.

### 6.4 · Matching e linking tassonomia

Implementato in `taxonomy.py` (`link_profile`) e chiamato da `finalize` in
`main.py`. Lookup esatto su label/sinonimi + fuzzy-match (`SequenceMatcher`,
soglia 0.85) su una tabella statica `TAXONOMY`. **Resta deterministico**:
nessuna chiamata LLM.

- ❌ Mai delegare il matching a un agente LLM.
- ✅ Strumenti ammessi: embedding similarity, dizionari, tabelle di mapping.
- ❌ `link_profile` **non va mai chiamato** su un profilo degradato
  (`metrics["failed"]`) o senza skill: altrimenti una metrica di copertura
  tassonomica risulterebbe fuorviante (1.0 su un fallimento). La guardia è
  in `finalize` — non rimuoverla aggiungendo nuovi punti di chiamata.

### 6.5 · Nessuna chiave o token nei file versionati

- ❌ Mai committare chiavi API, token, credenziali in nessun file tracciato
  da git.
- ✅ Usare `.env` (git-ignored) e variabili d'ambiente.
- ✅ Nei file di esempio usare placeholder: `YOUR_API_KEY_HERE`.

---

## 7 · Note operative per l'assistente AI

1. **Prima di scrivere codice CrewAI**, verifica la versione installata e
   consulta la doc aggiornata (vedi AGENTS.md).
2. I nomi dei metodi `@agent` e `@task` **devono corrispondere** alle chiavi
   nei YAML.
3. Le variabili `{lang}`, `{text_summary}`, `{text_skills}` nei YAML vengono
   interpolate da `crew.kickoff(inputs=...)` — non rinominarle senza
   aggiornare `main.py`.
4. `LLM_MAIN` e `LLM_CHEAP` in `llms.py` sono le uniche istanze LLM: non
   crearne di nuove senza motivo.
5. Il ramo `company` / `scout_crew` usa `ScoutCrew` (3 task sequenziali
   analoghi a `DocumentCrew`), **senza ricerca web**: lavora solo sul testo
   ottenuto appiattendo i campi stringa di `company_raw`. L'`evidence` delle
   skill deve essere verbatim rispetto a quel testo (stesso
   `evidence_guardrail`, invariante 6.2) — non sulla conoscenza generale
   del modello sull'azienda. Se `company_raw` contiene solo il nome
   azienda, è corretto che la crew non estragga skill: significa che non
   ci sono dati sufficienti, non è un bug.
6. `tools/custom_tool.py` è un placeholder dallo scaffold crewai — non è
   usato da nessuna crew.
7. **Invariante**: la task `extract_skills` in `document_crew.py` ha
   `context=[]` esplicito. Serve a impedire che la crew inietti di default
   l'output di `summarize` nel contesto dell'estrazione competenze — le
   competenze devono derivare solo da `{text_skills}` (methodology/results/
   discussion), non dalla sintesi. Non rimuovere `context=[]` per "comodità"
   di condividere contesto tra task.
8. `feedback.py` (`log_correction`) appende correzioni umane in
   `feedback/corrections.jsonl`. Non ha ancora un chiamante nel repo: va
   invocato dal backend/UI quando un reviewer corregge un profilo.
