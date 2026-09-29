import fitz
import re
from knowflix_engine.schemas.models import ParsedDocument, Section

def normalize_hf(text: str) -> str:
    # Replace numbers with <NUM>, lowercase, strip
    s = re.sub(r'\d+', '<NUM>', text)
    return s.strip().lower()

def parse_pdf(pdf_path: str, doc_id: str) -> ParsedDocument:
    doc = fitz.open(pdf_path)
    num_pages = len(doc)
    
    # 1. Gather all blocks and calculate line frequencies for HF removal
    page_blocks = []
    line_counts = {}
    
    for page_num in range(num_pages):
        page = doc[page_num]
        p_dict = page.get_text("dict", sort=True)
        blocks = p_dict.get("blocks", [])
        page_blocks.append(blocks)
        
        # Count lines for HF
        seen_on_page = set()
        for b in blocks:
            if b.get("type") == 0:  # text block
                for line in b.get("lines", []):
                    line_text = "".join(s.get("text", "") for s in line.get("spans", []))
                    norm_line = normalize_hf(line_text)
                    if norm_line and norm_line not in seen_on_page:
                        seen_on_page.add(norm_line)
                        line_counts[norm_line] = line_counts.get(norm_line, 0) + 1

    hf_threshold = 0.6 * num_pages
    hf_lines = {k for k, v in line_counts.items() if v >= hf_threshold and len(k) > 2}
    
    # 2. Extract and clean text blocks, identify font sizes
    cleaned_blocks = [] 
    figures = []
    
    for page_num, blocks in enumerate(page_blocks):
        page = doc[page_num]
        page_area = page.rect.width * page.rect.height
        
        for b in blocks:
            if b.get("type") == 0: # text block
                block_lines = []
                max_font = 0
                for line in b.get("lines", []):
                    line_text = "".join(s.get("text", "") for s in line.get("spans", []))
                    norm_line = normalize_hf(line_text)
                    
                    if norm_line in hf_lines:
                        continue # Skip header/footer
                    
                    if not line_text.strip():
                        continue
                        
                    for s in line.get("spans", []):
                        if s.get("size", 0) > max_font:
                            max_font = s.get("size")
                            
                    block_lines.append(line_text.strip())
                
                if block_lines:
                    # De-hyphenation and recomposition
                    text_parts = []
                    for i, line in enumerate(block_lines):
                        if i > 0 and text_parts[-1].endswith("-") and line[0].islower():
                            text_parts[-1] = text_parts[-1][:-1] + line
                        else:
                            text_parts.append(line)
                    
                    block_text = " ".join(text_parts).strip()
                    if block_text:
                        cleaned_blocks.append({"text": block_text, "font": max_font, "bbox": b.get("bbox")})
            
            elif b.get("type") == 1: # image block
                bbox = b.get("bbox")
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                area = w * h
                area_ratio = area / page_area if page_area else 0
                figures.append({
                    "id": f"fig_{page_num}_{len(figures)}",
                    "page": page_num + 1,
                    "bbox": bbox,
                    "area_ratio": round(area_ratio, 3),
                    "has_caption": False,
                    "caption": ""
                })

    # Link captions to figures
    for fig in figures:
        fig_bbox = fig["bbox"]
        for cb in cleaned_blocks:
            cb_bbox = cb["bbox"]
            text_lower = cb["text"].lower()
            if text_lower.startswith(("fig", "tab", "figura", "figure")):
                # distance check (Y-axis)
                if abs(cb_bbox[1] - fig_bbox[3]) < 50 or abs(fig_bbox[1] - cb_bbox[3]) < 50:
                    fig["has_caption"] = True
                    fig["caption"] = cb["text"]
                    break
    
    # 3. Segmentation
    font_counts = {}
    for cb in cleaned_blocks:
        f = round(cb["font"])
        font_counts[f] = font_counts.get(f, 0) + len(cb["text"])
    
    body_font = max(font_counts, key=font_counts.get) if font_counts else 10
    
    sections = []
    current_kind = "other"
    current_text = []
    current_heading = None
    bibliography_text = []
    in_bibliography = False
    
    heading_map = {
        "abstract": "abstract",
        "introduzione": "intro",
        "introduction": "intro",
        "metodi": "method",
        "metodologia": "method",
        "methods": "method",
        "risultati": "results",
        "results": "results",
        "discussione": "discussion",
        "discussion": "discussion",
        "conclusioni": "conclusion",
        "conclusions": "conclusion",
        "bibliografia": "bibliography",
        "references": "bibliography"
    }
    
    def save_section():
        nonlocal current_text, current_kind, current_heading, sections
        if current_text:
            text = "\n\n".join(current_text)
            sections.append(Section(kind=current_kind, heading=current_heading, text=text))
            current_text = []
    
    for cb in cleaned_blocks:
        text = cb["text"]
        f = round(cb["font"])
        is_heading = False
        mapped_kind = None
        
        if len(text) < 150:
            t_lower = text.lower().strip()
            t_clean = re.sub(r'^\d+(\.\d+)*\s*', '', t_lower)
            if t_clean in heading_map:
                is_heading = True
                mapped_kind = heading_map[t_clean]
            elif f > body_font:
                is_heading = True
        
        if is_heading:
            if not in_bibliography:
                save_section()
            if mapped_kind == "bibliography":
                in_bibliography = True
            else:
                current_kind = mapped_kind if mapped_kind else "other"
                current_heading = text
                
        else:
            if in_bibliography:
                bibliography_text.append(text)
            else:
                current_text.append(text)
                
    if not in_bibliography:
        save_section()
        
    doc.close()
    
    return ParsedDocument(
        doc_id=doc_id,
        sections=sections,
        figures=figures,
        parser_version="1.0",
        bibliography="\n\n".join(bibliography_text)
    )
