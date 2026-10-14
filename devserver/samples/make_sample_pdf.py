"""Genera devserver/samples/tesi_esempio.pdf, un PDF di prova per il banco.

    uv run python devserver/samples/make_sample_pdf.py

Il PDF e' costruito per esercitare il parser (ingest/parser.py):
- titoli di sezione con font piu' grande e numerazione "1 Introduzione"
  (il parser non riconosce "1. Introduzione": dopo la rimozione del numero
  resta ". introduzione");
- nessun sottotitolo con font maggiorato dentro le sezioni, altrimenti il
  parser apre una sezione "other";
- intestazione e numero di pagina ripetuti, che il parser deve rimuovere;
- una figura con didascalia "Figura 1", per la scelta della cover;
- Appendice prima della Bibliografia: dopo "Bibliografia" il parser manda
  tutto nel campo bibliography.
"""
from pathlib import Path

import pymupdf

OUT = Path(__file__).with_name("tesi_esempio.pdf")

W, H = 595, 842  # A4 in punti
MARGIN = 72
BODY, TITLE, HEADING = 10.5, 17, 15
HEADER = "Università degli Studi di Esempio - Tesi di Laurea Magistrale in Ingegneria Informatica"

FRONT = [
    ("title", "Previsione dei consumi di un campus universitario"),
    ("body", "Modelli di gradient boosting per la gestione dei picchi di potenza"),
    ("body", "Candidato: Mario Esempio"),
    ("body", "Relatore: Prof.ssa Anna Prova"),
    ("body", "Anno accademico 2025/2026"),
]

SECTIONS = [
    ("Abstract", [
        "La tesi affronta la previsione a breve termine dei consumi elettrici di un campus universitario "
        "composto da quattordici edifici. L'obiettivo è fornire all'ufficio tecnico una stima oraria dei "
        "consumi delle successive quarantotto ore, utile a pianificare l'avvio degli impianti di "
        "climatizzazione e a ridurre i picchi di potenza contrattuale. Il lavoro confronta modelli di "
        "regressione lineare, random forest e gradient boosting su tre anni di misure reali, integrate con "
        "dati meteorologici e con il calendario accademico. Il modello finale riduce l'errore percentuale "
        "medio rispetto alla previsione attualmente in uso ed è stato messo in esercizio in un cruscotto "
        "consultato quotidianamente dal personale tecnico.",
    ]),
    ("1 Introduzione", [
        "Gli edifici universitari presentano profili di consumo fortemente legati al calendario: lezioni, "
        "sessioni d'esame e chiusure estive producono variazioni che i modelli basati sulla sola stagionalità "
        "settimanale non riescono a cogliere. L'ufficio tecnico dell'ateneo pianifica oggi l'accensione degli "
        "impianti sulla base dell'esperienza degli operatori e di una media mobile dei consumi delle settimane "
        "precedenti, con frequenti superamenti della potenza impegnata nei mesi estivi.",
        "La letteratura sulla previsione dei carichi elettrici degli edifici è ampia, ma la maggior parte dei "
        "lavori considera edifici residenziali o commerciali con occupazione regolare. Il caso di un campus, in "
        "cui l'occupazione dipende da eventi programmati e noti in anticipo, offre l'opportunità di sfruttare "
        "informazioni di calendario come variabili esplicative.",
    ]),
    ("2 Metodologia", [
        "I dati di consumo provengono dai contatori intelligenti installati nelle cabine di trasformazione "
        "dei quattordici edifici, con risoluzione di quindici minuti, per un periodo di tre anni. Le misure "
        "sono state estratte dal database PostgreSQL del sistema di telegestione mediante query SQL che "
        "aggregano i consumi a livello orario e segnalano gli intervalli con dati mancanti.",
        "La preparazione dei dati è stata implementata in Python con la libreria pandas. Gli intervalli "
        "mancanti inferiori alle due ore sono stati ricostruiti per interpolazione lineare, mentre i giorni con "
        "lacune più estese sono stati esclusi dall'addestramento. I valori anomali dovuti a errori di "
        "comunicazione dei contatori sono stati individuati con il criterio dello scarto interquartile e "
        "sostituiti con la mediana della stessa ora nelle quattro settimane precedenti.",
        "Le variabili esplicative comprendono la temperatura esterna e l'irraggiamento solare forniti dal "
        "servizio meteorologico regionale, l'ora del giorno e il giorno della settimana codificati in forma "
        "ciclica, i consumi ritardati di ventiquattro e centosessantotto ore e un indicatore di attività "
        "didattica ricavato dal calendario accademico. La selezione delle variabili è stata condotta tramite "
        "mutua informazione rispetto al consumo orario, mantenendo le diciotto variabili più informative.",
        "Sono stati confrontati tre modelli implementati con scikit-learn: una regressione lineare con "
        "regolarizzazione ridge come riferimento, una random forest e un modello di gradient boosting basato "
        "su istogrammi. Gli iperparametri sono stati scelti con una ricerca casuale su cinquanta "
        "configurazioni. La validazione è stata eseguita con una cross-validation a finestra temporale "
        "scorrevole su dodici partizioni, per evitare che informazioni future entrassero nell'addestramento. "
        "Le metriche adottate sono l'errore assoluto medio e l'errore percentuale assoluto medio.",
    ]),
    ("3 Risultati", [
        "Il modello di gradient boosting ha ottenuto un errore percentuale assoluto medio del 6,8 per cento "
        "sull'orizzonte di quarantotto ore, contro il 9,4 per cento della random forest e il 14,1 per cento "
        "della regressione ridge. La previsione basata sulla media mobile, attualmente in uso presso l'ufficio "
        "tecnico, presenta sullo stesso periodo un errore del 17,3 per cento.",
        "L'indicatore di attività didattica è risultato la terza variabile per importanza dopo il consumo "
        "ritardato di ventiquattro ore e la temperatura esterna. Nelle settimane di inizio semestre il suo "
        "contributo riduce l'errore di oltre quattro punti percentuali rispetto a un modello addestrato senza "
        "informazioni di calendario.",
        "Il modello è stato messo in esercizio con un'esecuzione notturna pianificata che scrive le previsioni "
        "in un database InfluxDB; le previsioni e i consumi misurati sono visualizzati in un cruscotto Grafana "
        "consultato quotidianamente dal personale dell'ufficio tecnico.",
    ]),
    ("4 Discussione", [
        "I risultati confermano che le informazioni di calendario sono decisive per gli edifici a occupazione "
        "programmata. Il principale limite riguarda gli eventi straordinari, come convegni o chiusure non "
        "previste, che non compaiono nel calendario accademico e producono gli errori più ampi. Un secondo "
        "limite è la dipendenza dalle previsioni meteorologiche, il cui errore si propaga direttamente sulla "
        "stima dei consumi nelle giornate più calde.",
        "L'integrazione di un registro degli eventi straordinari e la stima dell'incertezza tramite regressione "
        "quantile rappresentano le estensioni più promettenti per rendere la previsione utilizzabile anche "
        "nella gestione dei picchi di potenza.",
    ]),
    ("5 Conclusioni", [
        "Il lavoro ha prodotto un sistema di previsione dei consumi orari del campus che migliora "
        "sensibilmente la stima attualmente in uso ed è già impiegato dall'ufficio tecnico. Gli sviluppi futuri "
        "riguardano l'estensione ai consumi termici e l'uso delle previsioni per l'ottimizzazione automatica "
        "degli orari di accensione degli impianti.",
    ]),
    ("Appendice", [
        "Elenco delle variabili esplicative utilizzate dal modello finale, con la relativa unità di misura e "
        "la fonte del dato, e configurazione degli iperparametri selezionati dalla ricerca casuale.",
    ]),
    ("Bibliografia", [
        "Breiman L. Random forests. Machine Learning, 45(1), 2001.",
        "Friedman J. H. Greedy function approximation: a gradient boosting machine. Annals of Statistics, 2001.",
        "Hong T., Fan S. Probabilistic electric load forecasting: a tutorial review. International Journal of "
        "Forecasting, 32(3), 2016.",
    ]),
]

FIGURE_AFTER = "3 Risultati"  # la figura va dopo il primo paragrafo di questa sezione


def chart_png() -> bytes:
    """Grafico a linee disegnato con primitive vettoriali e rasterizzato in PNG."""
    doc = pymupdf.open()
    page = doc.new_page(width=420, height=200)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    for i in range(5):
        y = 30 + i * 35
        page.draw_line((40, y), (400, y), color=(0.85, 0.85, 0.85), width=0.5)
    page.draw_line((40, 170), (400, 170), color=(0.3, 0.3, 0.3), width=1)
    page.draw_line((40, 20), (40, 170), color=(0.3, 0.3, 0.3), width=1)
    import math
    measured = [(40 + x * 7.2, 110 - 45 * math.sin(x / 8) - 12 * math.sin(x / 1.7)) for x in range(51)]
    forecast = [(px, py + 6 * math.sin(i / 3)) for i, (px, py) in enumerate(measured)]
    page.draw_polyline(measured, color=(0.18, 0.36, 0.31), width=2)
    page.draw_polyline(forecast, color=(0.85, 0.45, 0.15), width=1.5, dashes="[4] 0")
    pix = page.get_pixmap(dpi=200)
    return pix.tobytes("png")


class Writer:
    def __init__(self, doc):
        self.doc, self.page, self.y = doc, None, 0
        self.new_page()

    def new_page(self):
        self.page = self.doc.new_page(width=W, height=H)
        n = len(self.doc)
        self.page.insert_text((MARGIN, 40), HEADER, fontsize=8, color=(0.4, 0.4, 0.4))
        self.page.insert_text((W / 2 - 20, H - 30), f"Pagina {n}", fontsize=8, color=(0.4, 0.4, 0.4))
        self.y = MARGIN

    def text(self, text, size=BODY, font="helv", gap=8, align=pymupdf.TEXT_ALIGN_JUSTIFY):
        for _ in range(2):
            rect = pymupdf.Rect(MARGIN, self.y, W - MARGIN, H - MARGIN)
            rc = self.page.insert_textbox(rect, text, fontsize=size, fontname=font, align=align)
            if rc >= 0:
                self.y += rect.height - rc + gap
                return
            self.new_page()  # non ci sta: nuova pagina e riprova
        raise RuntimeError("paragrafo piu' lungo di una pagina")

    def image(self, png, width=420, height=200, caption=""):
        if self.y + height + 40 > H - MARGIN:
            self.new_page()
        rect = pymupdf.Rect((W - width) / 2, self.y, (W + width) / 2, self.y + height)
        self.page.insert_image(rect, stream=png)
        self.y = rect.y1 + 8
        self.text(caption, size=9, font="heit", align=pymupdf.TEXT_ALIGN_CENTER, gap=14)


def main():
    doc = pymupdf.open()
    w = Writer(doc)
    for kind, text in FRONT:
        if kind == "title":
            w.y = 200
            w.text(text, size=TITLE, font="hebo", gap=40, align=pymupdf.TEXT_ALIGN_CENTER)
        else:
            w.text(text, align=pymupdf.TEXT_ALIGN_CENTER, gap=4)
    w.new_page()

    for heading, paragraphs in SECTIONS:
        if w.y > H - MARGIN - 120:
            w.new_page()
        w.text(heading, size=HEADING, font="hebo", gap=10, align=pymupdf.TEXT_ALIGN_LEFT)
        for i, p in enumerate(paragraphs):
            w.text(p, align=pymupdf.TEXT_ALIGN_LEFT if heading == "Bibliografia" else pymupdf.TEXT_ALIGN_JUSTIFY)
            if heading == FIGURE_AFTER and i == 0:
                w.image(chart_png(), caption="Figura 1: consumo orario misurato (linea continua) e "
                                             "previsto dal modello di gradient boosting (tratteggio) "
                                             "in una settimana di novembre.")
        w.y += 10

    doc.set_metadata({"title": "Tesi di esempio - Knowflix", "author": "Mario Esempio (fittizio)"})
    doc.save(OUT, garbage=3, deflate=True)
    print(f"scritto {OUT} ({len(doc)} pagine)")


if __name__ == "__main__":
    main()
