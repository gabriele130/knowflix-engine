"""Segmentazione del parser PDF: capitoli con titolo libero, in grassetto alla
stessa dimensione del corpo (caso di tesi reali)."""
import pytest

fitz = pytest.importorskip("fitz")

from knowflix_engine.config import SUPPORTED_PARSER_VERSIONS
from knowflix_engine.ingest.parser import parse_pdf

BODY = ("Questo paragrafo e' testo del corpo della tesi, abbastanza lungo da "
        "rendere il carattere normale quello piu' usato nel documento. ") * 3


def make_pdf(path, blocks):
    """blocks: (testo, grassetto). Tutto a 12 pt; una pagina per blocco, perche'
    il parser scarta come intestazione le righe ripetute su molte pagine."""
    doc = fitz.open()
    for text, bold in blocks:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(60, 60, 540, 300), text, fontsize=12,
                            fontname="hebo" if bold else "helv")
    doc.save(path)


def test_free_title_chapters_become_discussion(tmp_path):
    pdf = tmp_path / "tesi.pdf"
    make_pdf(pdf, [
        ("INTRODUZIONE", True), (BODY, False),
        ("CAPITOLO 1", True), ("PSICOLOGIA ED ECONOMIA", True), (BODY, False),
        ("CAPITOLO 2 Metodologia", True), (BODY, False),
        ("CONCLUSIONI", True), (BODY, False),
    ])
    parsed = parse_pdf(str(pdf), "tesi")
    kinds = [s.kind for s in parsed.sections]
    assert kinds == ["introduction", "discussion", "methodology", "conclusions"]
    assert parsed.parser_version in SUPPORTED_PARSER_VERSIONS


def test_chapter_mention_in_body_text_is_not_a_heading(tmp_path):
    pdf = tmp_path / "tesi.pdf"
    make_pdf(pdf, [("INTRODUZIONE", True), (BODY, False),
                   ("capitolo 2", False), (BODY, False)])
    parsed = parse_pdf(str(pdf), "tesi")
    assert [s.kind for s in parsed.sections] == ["introduction"]
