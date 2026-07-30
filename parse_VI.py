import pdfplumber
import re
import sys
import json

PDF_PATH = r"C:\Users\bolli\Downloads\PQ Order 2003.pdf"

ROMAN_MARKER_RE = re.compile(r"^\(([ivxlcdm]+)\)\s*", re.IGNORECASE)
SLNO_RE = re.compile(r"^(\d+)\.?$")

HEADER_ROW_MARKERS = {"Sl. No.", "Sl.No.", "Sl. No"}
COLUMN_NUM_MARKER_ROW = {"(1)", "(2)", "(3)", "(4)", "(5)", "(6)"}

# A handful of Sl.No cells render as garbled glyphs due to a font-encoding quirk in the source
# PDF rather than any ambiguity in the underlying document (confirmed by context: sequential
# numbering and the entry's position make the intended number unambiguous). Keyed by
# (page_num, garbled_text) so each fix is tied to the exact spot it was found and verified.
SLNO_GLYPH_FIXES = {
    (139, "py."): "262.",
}


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


def parse_pages(start_page, end_page, idx_start=0, carry_forward=None):
    """carry_forward: optional {'sl_no', 'species', 'material'} from the previous
    batch's last row, so a species/material that continues across a batch
    boundary (the table itself only shows it once, then leaves the cell blank
    for however many rows follow) is correctly attributed instead of coming
    out as an orphan row with no sl_no/species."""
    rows = []
    idx_holder = [idx_start]

    carry_forward = carry_forward or {}
    cur_sl_no = carry_forward.get("sl_no")
    cur_species = carry_forward.get("species")
    cur_material = carry_forward.get("material")

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
                    if (page_num, sl_no_clean) in SLNO_GLYPH_FIXES:
                        sl_no_clean = SLNO_GLYPH_FIXES[(page_num, sl_no_clean)]
                    species_clean = clean(species_cell)
                    material_clean = clean(material_cell)
                    country_entries_raw = split_countries(country_cell or "")
                    decl_clean = clean(decl_cell)
                    cond_clean = clean(cond_cell)

                    # A material/species cell can contain ONLY an amendment reference (the source
                    # relies on the reader inferring the material is unchanged from the row above,
                    # e.g. a cell reading just "(vide S.O. 3246(E) dated 20.07.2023)"). Extract the
                    # amendment first so the carried-forward value isn't overwritten with nothing.
                    species_clean_final, species_clean_amend = (extract_amendment(species_clean) if species_clean else (None, None))
                    material_clean_final, material_clean_amend = (extract_amendment(material_clean) if material_clean else (None, None))

                    if sl_no_clean and SLNO_RE.match(sl_no_clean):
                        cur_sl_no = sl_no_clean.rstrip(".")
                        cur_species = species_clean_final or cur_species
                        cur_material = material_clean_final or cur_material
                    else:
                        if species_clean_final:
                            cur_species = species_clean_final
                        if material_clean_final:
                            cur_material = material_clean_final

                    has_country_content = any(c for c in country_entries_raw)
                    if not any([has_country_content, decl_clean, cond_clean, material_clean, species_clean]):
                        continue
                    # A row with a species/material label but no country, declarations, or
                    # conditions at all is a pure category-header artifact (e.g. "Flower bulbs:"
                    # introducing a group of lettered sub-species that carry the real data on the
                    # rows below) -- not a data row, so skip emitting it.
                    if not has_country_content and not decl_clean and not cond_clean:
                        continue

                    species_final, species_amend = cur_species, species_clean_amend
                    material_final, material_amend = cur_material, material_clean_amend
                    decl_final, decl_amend = extract_amendment(decl_clean or None)
                    cond_final, cond_amend = extract_amendment(cond_clean or None)
                    amendment_ref = " | ".join(
                        a for a in [species_amend, material_amend, decl_amend, cond_amend] if a
                    ) or None

                    for country_entry_raw in country_entries_raw:
                        country_entry = clean(country_entry_raw) or None
                        if country_entry:
                            country_entry = country_entry.rstrip(",;").strip() or None
                        # pdfplumber sometimes splits an unusually tall cell (long declarations/
                        # conditions text) into an extra table row with no country/sl_no of its
                        # own -- that's a continuation of the immediately preceding row, not a
                        # new entry, so fold its text back in rather than emit a bare-country row.
                        if country_entry is None and sl_no_clean == "" and not material_clean and rows:
                            prev = rows[-1]
                            for field, val in (("declarations", decl_final), ("conditions", cond_final)):
                                if val:
                                    prev[field] = ((prev[field] or "") + " " + val).strip()
                            if amendment_ref:
                                prev["amendment_ref"] = " | ".join(
                                    a for a in [prev["amendment_ref"], amendment_ref] if a
                                )
                            continue
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
