<!-- GENERATO da scripts/gen_schema.py — NON MODIFICARE A MANO.
     Per aggiornare: uv run python scripts/gen_schema.py -->

# Knowflix Engine — Contratto

## 1 · Versioni

| Cosa | Valore | Fonte |
|---|---|---|
| Motore (`ENGINE_VERSION`) | `2.2` | `config.py` |
| Tassonomia (`TAXONOMY_VERSION`) | `1.0` | `config.py` |
| `parser_version` supportate | `2.0`, `2.1` | `config.SUPPORTED_PARSER_VERSIONS` |
| Voci in tassonomia | 8 | `taxonomy.TAXONOMY` |

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
- esempio: [`schema/example_output.json`](schema/example_output.json) — output di un run reale sul fixture, generato da `scripts/gen_example_output.py` (metadati del run in [`schema/example_output.meta.json`](schema/example_output.meta.json)).

## 2 · Campi

### Input — `ParsedDocument`

| Campo | Tipo | Obbligatorio | Default | Significato |
|---|---|---|---|---|
| `doc_id` | `str` | sì | — | Identificativo del documento. Insieme a ENGINE_VERSION e a un'impronta del contenuto (lingua, sezioni, figure) forma la chiave di cache (`cache/{doc_id}_{ENGINE_VERSION}_{impronta}.json`): lo stesso doc_id con un testo diverso non riusa il profilo vecchio. |
| `lang` | `str` | no | `"it"` | Lingua del documento; passata ai prompt come `{lang}`. |
| `meta` | `dict` | no | `{}` | Metadati liberi del preprocessor. Non letti dal motore. |
| `sections` | `list[Section]` | sì | — | Testo segmentato per sezione; vedi tabella `Section`. Se nessuna sezione usata dal motore contiene testo il job fallisce con `empty_content`. |
| `figures` | `list[dict]` | no | `[]` | Figure estratte dal parser. Usate solo per scegliere `cover_figure_id` (chiavi lette: `id`, `area_ratio`, `has_caption`). |
| `parser_version` | `str` | no | `"1.0"` | Versione del preprocessor. **Facoltativo**: se assente il payload è accettato; se presente deve essere tra le versioni supportate (§1), altrimenti `unsupported_payload_version`. Il default dello schema si applica solo dopo il controllo. |
| `bibliography` | `str` | no | `""` | Bibliografia grezza come testo libero. Non letta dal motore. |

#### `Section`

| Campo | Tipo | Obbligatorio | Default | Significato |
|---|---|---|---|---|
| `kind` | `Literal['abstract', 'introduction', 'methodology', 'results', 'discussion', 'conclusions', 'bibliography', 'appendix', 'other']` | sì | — | Tipo di sezione; enum chiuso, vedi §3. |
| `heading` | `str \| None` | no | `null` | Titolo originale della sezione. Non letto dal motore. |
| `text` | `str` | sì | — | Testo della sezione. |

### Output — `ReviewedProfile`

| Campo | Tipo | Obbligatorio | Default | Significato |
|---|---|---|---|---|
| `one_liner` | `str` | sì | — | Sintesi in una frase (prompt: massimo 25 parole). |
| `abstract_150` | `str` | sì | — | Sintesi di circa 150 parole. |
| `keywords` | `list[str]` | sì | — | Termini tecnici specifici (prompt: 5-10). |
| `skills` | `list[Skill]` | sì | — | Competenze estratte e revisionate; vedi tabella `Skill`. |
| `rejected` | `list[str]` | no | `[]` | Competenze scartate, con motivo: dal reviewer (generiche, attribuite a terzi) o dal guardrail (evidence non trovata nel testo). |
| `review_notes` | `str` | no | `""` | Note libere del reviewer. |
| `cover_figure_id` | `str \| None` | no | `null` | `id` della figura scelta come cover (scoring deterministico in `cover.py`); null se nessuna figura ha punteggio > 0. |
| `taxonomy_version` | `str \| None` | no | `null` | Versione della tassonomia usata per il linking (`TAXONOMY_VERSION`). Sempre valorizzato nel profilo restituito. |
| `taxonomy_coverage` | `float \| None` | no | `null` | Quota di `skills` con `skill_id` non nullo, arrotondata a 3 decimali; null se il profilo non ha skill. Vedi §4. |
| `public_card` | `PublicCard` | no | `{"abstract": null}` | Scheda pubblica; vedi tabella `PublicCard`. Presente nel contratto ma **non popolata** in questa versione. |
| `engine_version` | `str \| None` | no | `null` | Versione del motore che ha prodotto il profilo (`ENGINE_VERSION`). Sempre valorizzato nel profilo restituito; serve a capire quale deploy ha eseguito il job. |

#### `Skill`

| Campo | Tipo | Obbligatorio | Default | Significato |
|---|---|---|---|---|
| `label` | `str` | sì | — | Nome della competenza come prodotto dall'LLM. |
| `evidence` | `str` | sì | — | Citazione dal documento sorgente che giustifica la competenza; vedi §7. |
| `section_kind` | `Literal['abstract', 'introduction', 'methodology', 'results', 'discussion', 'conclusions', 'bibliography', 'appendix', 'other']` | sì | — | Sezione di input in cui il motore ha trovato l'evidence. Assegnato dal motore, mai generato dall'LLM; vedi §7. |
| `confidence` | `float` | sì | — | Confidenza dichiarata dall'LLM. Il motore non la calcola né la valida (nessun vincolo di range). |
| `skill_id` | `str \| None` | no | `null` | Id canonico in tassonomia, o null; vedi §4. |

#### `PublicCard`

| Campo | Tipo | Obbligatorio | Default | Significato |
|---|---|---|---|---|
| `abstract` | `str \| None` | no | `null` | Non popolato in questa versione: sempre null. Usare `abstract_150`. |

`public_card` contiene il solo campo `abstract`, **non popolato in questa
versione**: il motore non fa nessuna generazione aggiuntiva per la scheda.

### Output — `EngineError`

| Campo | Tipo | Obbligatorio | Default | Significato |
|---|---|---|---|---|
| `code` | `Literal['invalid_payload', 'unsupported_payload_version', 'unauthorized', 'empty_content', 'rate_limited', 'provider_unavailable', 'timeout', 'internal_error']` | sì | — | Codice dell'errore; vedi tabella in §6. |
| `message` | `str` | sì | — | Descrizione leggibile. Non stabile: non va interpretata dal consumer. |
| `retryable` | `bool` | sì | — | true se ripetere lo stesso job più tardi può riuscire. Determinato dal `code`, mai indipendente. |
| `engine_version` | `str \| None` | no | `null` | Versione del motore che ha prodotto l'errore (`ENGINE_VERSION`). Sempre valorizzato negli errori restituiti dal Flow. |

## 3 · Sezioni accettate

`Section.kind` accetta esattamente questi valori (qualsiasi altro valore dà
`invalid_payload`):

| `kind` | Usata per la sintesi (`text_summary`) | Usata per le competenze (`text_skills`) |
|---|---|---|
| `abstract` | sì | — |
| `introduction` | sì | — |
| `methodology` | — | sì |
| `results` | — | sì |
| `discussion` | — | sì |
| `conclusions` | sì | — |
| `bibliography` | — | — |
| `appendix` | — | — |
| `other` | — | — |

- Le competenze sono estratte **solo** da: `methodology`, `results`, `discussion`.
  La task `extract_skills` ha `context=[]`: non vede la sintesi.
- Sezioni accettate ma escluse sia dalla sintesi sia dall'estrazione
  competenze: `bibliography`, `appendix`, `other`. Un'evidenza presa da queste sezioni viene
  rifiutata (§7).

## 4 · `skill_id` e copertura tassonomica

`skill_id` è assegnato in `finalize` da `taxonomy.link_profile`, in modo
deterministico (nessun LLM): match esatto su label/sinonimi, poi fuzzy-match
`SequenceMatcher` con soglia **0.85**.

`skill_id: null` significa che la `label` non ha un match sopra soglia nella
tassonomia `1.0`. **Non** è un giudizio sulla competenza:
il linking guarda solo la `label` e non tocca né filtra le skill, che passano
la stessa verifica delle evidenze di quelle linkate (§7). La tassonomia
corrente contiene solo queste voci:

| `skill_id` | Label |
|---|---|
| `tax-python` | Python |
| `tax-data-analysis` | Data Analysis |
| `tax-machine-learning` | Machine Learning |
| `tax-signal-processing` | Signal Processing |
| `tax-feature-engineering` | Feature Engineering |
| `tax-model-validation` | Model Validation |
| `tax-sql` | SQL |
| `tax-data-visualization` | Data Visualization |

`taxonomy_coverage` = numero di skill con `skill_id` non nullo / numero di
skill, arrotondato a 3 decimali. Su un profilo senza skill vale **null**
(non 0 e non 1): `link_profile` non viene eseguito e il rapporto non è
definito. Una copertura bassa indica una tassonomia incompleta per il
dominio del documento, non competenze meno affidabili.

## 5 · Progress

Il Flow emette un avanzamento ai confini dei task della crew
(`summarize`, `extract_skills`, `review`):

| Valore | Fase |
|---|---|
| `0` | Avvio della crew, prima del primo task |
| `33` | Fine del task `summarize` |
| `66` | Fine del task `extract_skills` |
| `100` | Fine del task `review` |

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
{"code": "rate_limited", "message": "<descrizione>", "retryable": true}
```

| `code` | `retryable` | Quando |
|---|---|---|
| `invalid_payload` | false | Il payload non rispetta lo schema (`ParsedDocument`, o `company_raw` non è un oggetto), oppure `job_type` non è supportato. Il messaggio elenca i campi non validi. |
| `unsupported_payload_version` | false | `parser_version` è presente ma non è tra le versioni supportate. |
| `unauthorized` | false | Il provider LLM rifiuta le credenziali (HTTP 401/403, chiave non valida). |
| `empty_content` | false | Nessun testo nelle sezioni usate dal motore (documento), o nessun campo testuale in `company_raw`. |
| `rate_limited` | **true** | Il provider LLM limita le richieste (HTTP 429, quota esaurita). |
| `provider_unavailable` | **true** | Il provider LLM non è raggiungibile o è in errore (HTTP 5xx, errore di connessione, sovraccarico). |
| `timeout` | **true** | La chiamata al provider LLM è scaduta (HTTP 408/504, timeout). |
| `internal_error` | false | Qualsiasi altro errore non classificato. |

- `retryable` è derivato dal codice (`provider_unavailable`, `rate_limited`, `timeout` → true,
  tutti gli altri → false); il modello rifiuta combinazioni incoerenti.
- Prima di restituire un errore ritentabile, il motore ha già ritentato
  internamente fino a 3 volte con backoff esponenziale (base
  2.0s). Un `retryable: true` significa "riprova più tardi", non
  "riprova subito".
- La classificazione usa lo status HTTP dell'eccezione quando c'è, altrimenti
  frasi non ambigue nel messaggio; tutto ciò che non è riconosciuto è
  `internal_error`.
- I profili in errore non vengono salvati in cache.

## 7 · Evidenze: cosa è garantito e cosa no

Il guardrail delle evidenze è applicato a `extract_skills` (max 2 retry), `review` (max 2 retry): la verifica
vale quindi sul **profilo finale**, non solo sull'output intermedio. Se il
modello produce un'evidenza non presente nel testo, il guardrail la rifiuta e
la task viene ritentata; se i retry si esauriscono, le sole competenze ancora
non verificate vengono **rimosse** dal profilo e riportate in `rejected` come
`"<label>: evidence non trovata nel testo"`. Il job non fallisce per questo
motivo.

Garantito, per ogni `Skill.evidence` del profilo restituito:
- compare dentro **una singola sezione** tra `methodology`, `results`, `discussion`. Un'evidenza
  che scavalca due sezioni, o che viene da altre sezioni
  (`bibliography`, `appendix`, `other`, `abstract`, `introduction`, `conclusions`), viene rifiutata. Unico margine:
  la tolleranza del fuzzy match, che in teoria può lasciar passare uno
  sconfinamento di pochi caratteri nella sezione adiacente;
- il confronto avviene dopo normalizzazione (minuscole, spazi collassati,
  a-capo e sillabazione `-\n` rimossi): match esatto oppure fuzzy ≥
  **0.9** su una finestra della stessa lunghezza;
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
