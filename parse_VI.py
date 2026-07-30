import pdfplumber
import re
import sys
import json

PDF_PATH = r"C:\Users\bolli\Downloads\PQ Order 2003.pdf"

ROMAN_MARKER_RE = re.compile(r"^\(([ivxlcdm]+)\)\s*", re.IGNORECASE)
SLNO_RE = re.compile(r"^(\d+)\.?$")

HEADER_ROW_MARKERS = {"Sl. No.", "Sl.No.", "Sl. No"}
COLUMN_NUM_MARKER_ROW = {"(1)", "(2)", "(3)", "(4)", "(5)", "(6)"}


def is_header_row(row):
    """Only the two literal header rows (column titles, and the (1)-(6) markers)
    should be filtered -- never a substring match, since phrases like 'Country of
    Origin/re-export' legitimately appear inside ordinary conditions-column text."""
    first_cell = (row[0] or "").strip()
    if first_cell in HEADER_ROW_MARKERS:
        return True
    non_empty = [(c or "").strip() for c in row if (c or "").strip()]
    if non_empty and all(c in COLUMN_NUM_MARKER_ROW for c in non_empty):
        return True
    return False


def clean(cell):
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", cell.replace("\n", " ")).strip()


def split_countries(country_cell):
    """Split a country cell into individual country entries. The cell may contain
    several roman-numeral-marked countries stacked with newlines; a country's own
    name can itself wrap across multiple newlines (continuation), which must be
    re-joined rather than treated as a separate entry."""
    if not country_cell:
        return [None]
    lines = [l.strip() for l in country_cell.split("\n") if l.strip()]
    if not lines:
        return [None]
    entries = []
    current = None
    for line in lines:
        if ROMAN_MARKER_RE.match(line):
            if current is not None:
                entries.append(current)
            current = ROMAN_MARKER_RE.sub("", line, count=1)
        else:
            if current is None:
                current = line
            else:
                current = current + " " + line
    if current is not None:
        entries.append(current)
    return entries if entries else [None]


def extract_amendment(text):
    """Pull a trailing/embedded '(vide S.O. ...)' or '(Omitted vide ...)' style
    gazette reference out of a text field, returning (clean_text, amendment_ref)."""
    if not text:
        return text, None
    m = re.search(r"\((?:vide\s+)?(?:Gazette Notification\s+)?S\.O\.[^()]*(?:\([^()]*\)[^()]*)*\)", text)
    if not m:
        m = re.search(r"\(Omitted[^()]*(?:\([^()]*\)[^()]*)*\)", text)
    if m:
        ref = m.group(0)[1:-1].strip()
        remaining = (text[:m.start()] + text[m.end():]).strip()
        remaining = re.sub(r"\s+", " ", remaining)
        return remaining or None, ref
    return text, None


def parse_pages(start_page, end_page, idx_start=0):
    rows = []
    idx_holder = [idx_start]

    cur_sl_no = None
    cur_species = None
    cur_material = None

    with pdfplumber.open(PDF_PATH) as pdf:
        for page_num in range(start_page, end_page + 1):
            page = pdf.pages[page_num - 1]
            tables = page.find_tables()
            for table in tables:
                table_rows = table.extract()
                for raw_row in table_rows:
                    if len(raw_row) < 6:
                        # a continuation table sometimes starts without the Sl.No/species
                        # columns visible; pad on the left
                        raw_row = [None] * (6 - len(raw_row)) + raw_row
                    raw_row = raw_row[-6:]
                    if is_header_row(raw_row):
                        continue
                    sl_no_cell, species_cell, material_cell, country_cell, decl_cell, cond_cell = raw_row

                    sl_no_clean = clean(sl_no_cell)
                    species_clean = clean(species_cell)
                    material_clean = clean(material_cell)
                    country_entries_raw = split_countries(country_cell or "")
                    decl_clean = clean(decl_cell)
                    cond_clean = clean(cond_cell)

                    if sl_no_clean and SLNO_RE.match(sl_no_clean):
                        cur_sl_no = sl_no_clean.rstrip(".")
                        cur_species = species_clean or cur_species
                        cur_material = material_clean or cur_material
                    else:
                        if species_clean:
                            cur_species = species_clean
                        if material_clean:
                            cur_material = material_clean

                    has_country_content = any(c for c in country_entries_raw)
                    if not any([has_country_content, decl_clean, cond_clean, material_clean, species_clean]):
                        continue

                    species_final, species_amend = extract_amendment(cur_species)
                    material_final, material_amend = extract_amendment(cur_material)
                    decl_final, decl_amend = extract_amendment(decl_clean or None)
                    cond_final, cond_amend = extract_amendment(cond_clean or None)
                    amendment_ref = " | ".join(
                        a for a in [species_amend, material_amend, decl_amend, cond_amend] if a
                    ) or None

                    for country_entry_raw in country_entries_raw:
                        country_entry = clean(country_entry_raw) or None
                        idx_holder[0] += 1
                        rows.append({
                            "id": f"S6-{idx_holder[0]:04d}",
                            "schedule": "VI",
                            "sl_no": cur_sl_no,
                            "species": species_final,
                            "material": material_final,
                            "country": country_entry,
                            "declarations": decl_final,
                            "conditions": cond_final,
                            "justification": None,
                            "responsible_institute": None,
                            "amendment_ref": amendment_ref,
                            "source_page": page_num,
                            "needs_review": False,
                        })

    return rows


if __name__ == "__main__":
    start_page = int(sys.argv[1])
    end_page = int(sys.argv[2])
    idx_start = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    result = parse_pages(start_page, end_page, idx_start)
    print(json.dumps(result, ensure_ascii=False, indent=2))
