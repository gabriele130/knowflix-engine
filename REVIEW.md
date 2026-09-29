# Code Review Report - Knowflix Engine

Di seguito la revisione critica del codice attuale, strutturata in categorie e classificata per severità (Bloccante, Importante, Minore). Non è stata apportata alcuna modifica al codice.

## 1. Coerenza con `CLAUDE.md`

Tutti gli invarianti architetturali principali sono rispettati:
- **Minore**: `context=[]` è rispettato. In `document_crew.py`, il task `extract_skills` non riceve alcun contesto dalle task precedenti, lavorando isolato sul `text_skills`.
- **Minore**: Il routing è deterministico. In `main.py`, il nodo `dispatch` decide sulla base di una variabile locale `self.state.job_type` senza invocare LLM.
- **Minore**: Il guardrail `evidence.py` è stringente (`threshold = 0.90`), non allentato, e non si usano LLM per il check delle evidence.
- **Minore**: Il linking è lasciato come "TODO", confermando l'assenza di agenti LLM usati impropriamente per questo scopo.

---

## 2. Gestione Errori

- **Bloccante**: `src/knowflix_engine/main.py:140`
  Il ramo `run_company` genera un profilo vuoto/stub, ma **non imposta** `self.state.metrics["failed"] = True`. Un fallimento non gestito (o un ramo non implementato) risulterà come `ok = True` nello script di misurazione batch.
  *Correzione proposta*: Aggiungere in `run_company` l'assegnazione `self.state.metrics = {"failed": True, "error": "not implemented"}`.

- **Importante**: `src/knowflix_engine/main.py:111`
  In caso di errore permanente (o esaurimento retry) nella crew `run_document`, le eccezioni vengono catturate, ma **non vengono tracciati i token** consumati prima del crash. Questo nasconde i costi monetari delle run fallite.
  *Correzione proposta*: Estrapolare comunque `usage` (se parzialmente disponibile nell'eccezione o da un callback LiteLLM) e registrarlo nelle metriche anche quando `failed` è True.

---

## 3. Contaminazione delle Metriche

- **Importante**: `src/knowflix_engine/eval/measure.py:76`
  Il calcolo delle proiezioni dei costi mensili si basa unicamente su `med_cost`, che viene estratto dai *soli documenti con `ok = True`*. Se una fetta del batch fallisce consumando token, il costo non viene proiettato. Questo falsa la stima dei costi al ribasso, perché assume che su 10.000 documenti non ci siano fallimenti costosi.
  *Correzione proposta*: Stimare il costo medio totale dividendo la somma assoluta del batch per il numero di documenti totali (inclusi i falliti), oppure spalmare il costo dei falliti sui documenti andati a buon fine.

---

## 4. Contratto Dati

- **Minore**: `src/knowflix_engine/schemas/models.py`
  Le aggiunte al contratto dati sono tutte retrocompatibili.
  - `ParsedDocument.parser_version` aggiunto con default `"1.0"`.
  - `ParsedDocument.bibliography` aggiunto con default `""`.
  - `Skill.skill_id` aggiunto come `str | None = None`.
  Nessun endpoint già deployato si romperà leggendo o scrivendo questi dati.

---

## 5. Determinismo

- **Minore**:
  Tutti i passaggi ausiliari sembrano deterministici. L'estrazione delle immagini in `ingest/parser.py` usa l'algebra delle bounding boxes. La logica di cache dipende esclusivamente dall'MD5/nome file. Le sezioni del parser sono associate con algoritmi if-else e matching di stringhe.

---

## 6. Segreti e Dati Personali (PII)

- **Importante**: `src/knowflix_engine/ingest/parser.py` & `src/knowflix_engine/main.py`
  Non è stata implementata alcuna sanitizzazione dei dati personali (PII). Gli elaborati di studenti/tesisti contengono frequentemente Nome, Cognome, Matricola e relatore. Questi dati:
  1. Vengono letti dal parser e passati al LLM per intero (problema di privacy/GDPR se la API non ha zero-retention policy).
  2. Rischiano di essere "allucinati" dall'agente all'interno dei campi `one_liner` o `review_notes` del JSON finale.
  3. Finierebbero archiviati in chiaro nella directory `cache/`.
  *Correzione proposta*: Introdurre una regex base o un layer di PII-scrubbing prima dell'invio in `run_document` per anonimizzare matricole e nomi nella prima pagina.

---

## 7. Costi Nascosti

- **Bloccante**: `src/knowflix_engine/main.py:42`
  La funzione `_call_crew_with_retry` implementa il backoff esponenziale avvolgendo l'**intero metodo `.kickoff()`** della Crew. Se la crew fallisce all'ultimo task (`reviewer`), il retry farà ricominciare il processo dal task `analyst`, re-inviando l'intero testo lungo e sprecando un'enorme quantità di token su task che in realtà avevano avuto successo. LiteLLM (incluso in CrewAI) gestisce già internamente i rate-limits (429).
  *Correzione proposta*: Rimuovere il retry custom avvolto attorno a `kickoff()` e fare affidamento esclusivo sul parametro globale di retry dei LLM, oppure isolare l'esecuzione delle task usando l'avvio asincrono / singolo task di CrewAI.

- **Importante**: `src/knowflix_engine/crews/document_crew/document_crew.py:18`
  Il task `summarize` (agente `analyst`) utilizza `LLM_MAIN` (un modello ad alta capacità). Per scrivere un abstract di 150 parole e le keywords non servono capacità logiche di altissimo livello. 
  *Correzione proposta*: Assegnare `LLM_CHEAP` all'agente `analyst`. Questo dimezzerebbe quasi il costo dell'input processing, considerando che `text_summary` contiene intro + abstract + conclusioni e pesa svariati K token.

---

### Cosa NON è stato verificato e perché
1. **Accuratezza effettiva del Parser PyMuPDF**: Non ho potuto ispezionare visualmente il mapping delle coordinate, la gestione dei layout complessi (es. tabelle intricate e note a piè pagina sovrapposte) e l'efficacia del De-hyphenator senza eseguire test intensivi su un PDF campione reale.
2. **Robustezza di `_present` (Evidence Guardrail)**: Lo script usa un fuzzy matching basato su `SequenceMatcher`. Con testi scientifici contenenti formule, caratteri greci, o parsing OCR rumoroso, un match al `90%` di soglia (hardcodato) potrebbe generare molti Falsi Negativi.
3. **Telemetry CrewAI**: Non è stato disattivato in modo esplicito (a meno che non sia stato settato in `.env`). I log di esecuzione mostrano tentativi verso `telemetry.crewai.com`, il che potrebbe rivelare metadata del job all'esterno se non regolamentato dal firewall locale.
