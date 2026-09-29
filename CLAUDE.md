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
          │ "document" │  │  "company"  │  (stub)
          │ run_document│  │ run_company │
          └──────┬─────┘  └──────┬──────┘
                 │               │
                 └───────┬───────┘
                    ┌────▼────┐
                    │finalize │   linking tassonomia (TODO)
                    └─────────┘
```

### Passaggi chiave del ramo `document`

| Step | Cosa fa |
|------|---------|
| `ingest` | Deserializza il JSON di input in `ParsedDocument`, validando lo schema |
| `dispatch` | **Router deterministico Python** — legge `state.job_type` e instrada |
| `run_document` | Inietta il full-text nel contesto del guardrail, poi lancia `DocumentCrew` |
| `finalize` | Punto di convergenza per tutti i rami; placeholder per linking a tassonomia e persistenza |

### Pipeline della DocumentCrew (sequential)

```
analyst → summarize (→ SummaryOutput)
skill_extractor → extract_skills (→ SkillsOutput, guardrail: evidence)
reviewer → review (→ ReviewedProfile, context: summarize + extract_skills)
```

- **analyst / summarize**: produce `one_liner`, `abstract_150`, `keywords` a
  partire da abstract + intro + conclusion.
- **skill_extractor / extract_skills**: estrae competenze con evidence
  verbatim da method + results + discussion. Il guardrail `evidence_guardrail`
  verifica che ogni evidence sia realmente presente nel testo; se non lo è,
  rigetta l'output (max 2 retry).
- **reviewer / review**: unisce sintesi e competenze, scarta le generiche,
  produce il `ReviewedProfile` finale.

---

## 3 · Mappa dei moduli

```
src/knowflix_engine/
├── main.py                     # Flow (KnowflixFlow), stato, entry-point CLI
├── llms.py                     # Istanze LLM condivise (LLM_MAIN, LLM_CHEAP)
├── schemas/
│   └── models.py               # Modelli Pydantic: contratto dati pubblico ⚠️
├── guardrails/
│   └── evidence.py             # Guardrail evidence: verifica citazioni testuali
├── crews/
│   ├── document_crew/
│   │   ├── document_crew.py    # Crew @CrewBase, agenti, task, guardrail wiring
│   │   └── config/
│   │       ├── agents.yaml     # Ruoli/goal/backstory dei 3 agenti
│   │       └── tasks.yaml      # Descrizioni task con interpolazione {lang}, {text_*}
│   └── scout_crew/
│       └── config/             # Vuoto — ramo company non ancora implementato
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
    sections: list[Section]     # kind ∈ {abstract, intro, method, results,
                                #          discussion, conclusion, other}
    figures: list[dict] = []
```

Metodi helper: `text_of(kinds)` e `full_text()`.

Il JSON di input (prodotto dal preprocessor PyMuPDF a monte) deve rispettare
questo schema. `sections` è obbligatorio e non vuoto.

### `ReviewedProfile` (output)

```python
class ReviewedProfile(BaseModel):
    one_liner: str
    abstract_150: str
    keywords: list[str]
    skills: list[Skill]         # Skill = label + evidence + section_kind
                                #         + confidence + skill_id?
    rejected: list[str] = []
    review_notes: str = ""
```

Questo è l'output finale del Flow, serializzato in `state.profile` come dict
e stampato su stdout.

I modelli intermedi `SummaryOutput` e `SkillsOutput` sono usati come
`output_pydantic` nelle singole task per forzare output strutturato.

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

### 6.2 · `guardrails/evidence.py` — Soglia evidence

Il guardrail `evidence_guardrail` verifica che ogni `Skill.evidence` sia una
citazione testuale presente nel documento sorgente (fuzzy match ≥ 0.90).

- ❌ **Non si allenta la soglia** per far passare più competenze.
- ❌ Non si disabilita il guardrail o si alzano i `guardrail_max_retries`
  oltre un livello ragionevole.
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

Il futuro linking delle competenze alla tassonomia (oggi TODO in `finalize`)
**deve restare deterministico**: lookup, fuzzy-match, mapping statico.

- ❌ Mai delegare il matching a un agente LLM.
- ✅ Strumenti ammessi: embedding similarity, dizionari, tabelle di mapping.

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
5. Il ramo `company` / `scout_crew` è uno **stub**: prima di implementarlo,
   discutere il design.
6. `tools/custom_tool.py` è un placeholder dallo scaffold crewai — non è
   usato da nessuna crew.
