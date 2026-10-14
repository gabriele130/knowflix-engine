"""Genera devserver/samples/tesi_esempio_2.pdf, secondo PDF di prova per il banco.

    uv run python devserver/samples/make_sample_pdf_2.py

Stessa impaginazione e stessi vincoli del parser di make_sample_pdf.py (titoli
"1 Introduzione", nessun sottotitolo maggiorato, Appendice prima della
Bibliografia, una figura con didascalia "Figura 1"), con un tema diverso:
ispezione visiva di saldature con reti convoluzionali.
"""
import math
from pathlib import Path

import pymupdf

from make_sample_pdf import H, HEADING, MARGIN, TITLE, Writer

OUT = Path(__file__).with_name("tesi_esempio_2.pdf")

FRONT = [
    ("title", "Ispezione visiva automatica dei cordoni di saldatura"),
    ("body", "Reti neurali convoluzionali per il controllo qualità in una linea di carpenteria metallica"),
    ("body", "Candidata: Giulia Esempio"),
    ("body", "Relatore: Prof. Luca Prova"),
    ("body", "Anno accademico 2025/2026"),
]

SECTIONS = [
    ("Abstract", [
        "La tesi propone un sistema di ispezione visiva automatica dei cordoni di saldatura prodotti da una "
        "cella robotizzata in un'azienda di carpenteria metallica. Oggi il controllo è affidato a un operatore "
        "che esamina a campione i pezzi a fine linea, con tempi elevati e valutazioni non sempre uniformi. Il "
        "lavoro descrive l'acquisizione di un dataset di immagini industriali, l'addestramento di reti "
        "neurali convoluzionali per la classificazione di quattro tipologie di difetto e l'integrazione del "
        "modello nella linea tramite un servizio di inferenza. Il sistema finale ispeziona ogni pezzo prodotto "
        "e segnala all'operatore solo i casi dubbi, riducendo il tempo dedicato al controllo manuale.",
    ]),
    ("1 Introduzione", [
        "Le saldature eseguite da robot sono generalmente ripetibili, ma variazioni nella preparazione dei "
        "lembi, nell'usura della torcia o nel flusso del gas di protezione producono difetti come porosità, "
        "incisioni marginali, mancanza di penetrazione e spruzzi. Un difetto non individuato in fabbrica "
        "comporta resi costosi e, nei componenti strutturali, rischi per la sicurezza.",
        "Le tecniche di visione artificiale tradizionali, basate su soglie e regole geometriche, si adattano "
        "male alla variabilità delle superfici metalliche e ai riflessi. L'apprendimento profondo consente "
        "invece di imparare direttamente dalle immagini le caratteristiche che distinguono un cordone "
        "conforme da uno difettoso, a condizione di disporre di un dataset etichettato sufficientemente ampio.",
    ]),
    ("2 Metodologia", [
        "Le immagini sono state acquisite con una telecamera industriale monocromatica da cinque megapixel "
        "montata a valle della cella di saldatura, con illuminazione a luce diffusa per attenuare i riflessi. "
        "L'acquisizione è sincronizzata con il PLC della linea tramite protocollo OPC UA, così che ogni "
        "immagine sia associata al codice del pezzo e ai parametri di saldatura registrati dal robot.",
        "Il dataset comprende circa novemila immagini raccolte in quattro mesi di produzione. L'etichettatura "
        "è stata svolta con lo strumento open source CVAT da due operatori del controllo qualità, e i casi di "
        "disaccordo sono stati risolti da un tecnico esperto. Le etichette e i metadati sono archiviati in un "
        "database PostgreSQL interrogato con query SQL per costruire le partizioni di addestramento.",
        "La preparazione delle immagini è stata implementata in Python con OpenCV: ritaglio della regione del "
        "cordone, normalizzazione del contrasto con equalizzazione adattiva dell'istogramma e "
        "ridimensionamento a 384 per 384 pixel. Per compensare lo sbilanciamento tra classi, molto marcato "
        "per la mancanza di penetrazione, sono state applicate tecniche di data augmentation con rotazioni, "
        "variazioni di luminosità e rumore gaussiano, oltre a una funzione di perdita pesata per classe.",
        "Sono state confrontate tre architetture implementate in PyTorch: una rete convoluzionale progettata "
        "da zero come riferimento, una ResNet-50 e una EfficientNet-B2, entrambe inizializzate con pesi "
        "preaddestrati su ImageNet e adattate con transfer learning. La validazione è stata eseguita con una "
        "cross-validation stratificata a cinque partizioni, separando i pezzi per lotto di produzione per "
        "evitare che immagini dello stesso lotto comparissero sia in addestramento sia in validazione. Le "
        "metriche adottate sono il richiamo sui pezzi difettosi e il punteggio F1 macro.",
    ]),
    ("3 Risultati", [
        "La EfficientNet-B2 ha ottenuto un punteggio F1 macro di 0,91 e un richiamo del 97 per cento sui pezzi "
        "difettosi, contro uno F1 di 0,88 della ResNet-50 e di 0,74 della rete progettata da zero. Il "
        "transfer learning ha inoltre ridotto il numero di epoche necessarie alla convergenza da circa "
        "sessanta a quindici.",
        "Le mappe di attivazione calcolate con Grad-CAM mostrano che il modello concentra l'attenzione sul "
        "bordo del cordone e sulle zone di raccordo con il materiale base, coerentemente con il giudizio degli "
        "operatori. Gli errori residui riguardano soprattutto spruzzi di piccole dimensioni scambiati per "
        "porosità superficiali.",
        "Il modello è stato esportato in formato ONNX e servito da un'applicazione FastAPI eseguita in un "
        "container Docker su un PC industriale con GPU a bordo linea. Il tempo medio di inferenza è di "
        "quarantadue millisecondi per immagine, compatibile con il ritmo produttivo della cella.",
    ]),
    ("4 Discussione", [
        "I risultati indicano che il transfer learning da modelli preaddestrati compensa in buona parte la "
        "dimensione limitata del dataset industriale. Il principale limite è la dipendenza dalle condizioni "
        "di illuminazione: un cambio di lampade durante la sperimentazione ha ridotto temporaneamente il "
        "richiamo di sei punti percentuali, recuperati solo dopo un nuovo addestramento.",
        "Un secondo limite riguarda i difetti interni, come la mancanza di fusione, che non sono visibili in "
        "superficie e richiedono tecniche di controllo non distruttivo. L'integrazione con i parametri di "
        "processo registrati dal robot rappresenta l'estensione più promettente per anticipare questi casi.",
    ]),
    ("5 Conclusioni", [
        "Il lavoro ha prodotto un sistema di ispezione che controlla ogni pezzo della linea e indirizza "
        "l'attenzione degli operatori sui soli casi dubbi. Gli sviluppi futuri riguardano il monitoraggio "
        "della deriva dei dati per pianificare i riaddestramenti e l'estensione ad altre celle di saldatura "
        "dello stabilimento.",
    ]),
    ("Appendice", [
        "Distribuzione delle immagini per classe di difetto e per lotto di produzione, configurazione degli "
        "iperparametri di addestramento e matrice di confusione del modello finale sul set di validazione.",
    ]),
    ("Bibliografia", [
        "He K., Zhang X., Ren S., Sun J. Deep residual learning for image recognition. CVPR, 2016.",
        "Tan M., Le Q. EfficientNet: rethinking model scaling for convolutional neural networks. ICML, 2019.",
        "Selvaraju R. R. et al. Grad-CAM: visual explanations from deep networks via gradient-based "
        "localization. ICCV, 2017.",
    ]),
]

FIGURE_AFTER = "3 Risultati"


def chart_png() -> bytes:
    """Curve di perdita in addestramento e validazione, rasterizzate in PNG."""
    doc = pymupdf.open()
    page = doc.new_page(width=420, height=200)
    page.draw_rect(page.rect, color=None, fill=(1, 1, 1))
    for i in range(5):
        y = 30 + i * 35
        page.draw_line((40, y), (400, y), color=(0.85, 0.85, 0.85), width=0.5)
    page.draw_line((40, 170), (400, 170), color=(0.3, 0.3, 0.3), width=1)
    page.draw_line((40, 20), (40, 170), color=(0.3, 0.3, 0.3), width=1)
    train = [(40 + x * 7.2, 40 + 120 * (1 - math.exp(-x / 6))) for x in range(51)]
    val = [(px, py - 8 + 3 * math.sin(i / 2)) for i, (px, py) in enumerate(train)]
    # asse y verso il basso: la perdita decresce, quindi capovolgo le curve
    train = [(px, 210 - py) for px, py in train]
    val = [(px, 210 - py) for px, py in val]
    page.draw_polyline(train, color=(0.18, 0.36, 0.31), width=2)
    page.draw_polyline(val, color=(0.85, 0.45, 0.15), width=1.5, dashes="[4] 0")
    pix = page.get_pixmap(dpi=200)
    return pix.tobytes("png")


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
                w.image(chart_png(), caption="Figura 1: perdita in addestramento (linea continua) e in "
                                             "validazione (tratteggio) della EfficientNet-B2 nelle prime "
                                             "cinquanta epoche.")
        w.y += 10

    doc.set_metadata({"title": "Tesi di esempio 2 - Knowflix", "author": "Giulia Esempio (fittizia)"})
    doc.save(OUT, garbage=3, deflate=True)
    print(f"scritto {OUT} ({len(doc)} pagine)")


if __name__ == "__main__":
    main()
