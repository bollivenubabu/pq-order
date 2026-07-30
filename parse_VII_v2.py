import pdfplumber
import re
import json

PDF_PATH = r"C:\Users\bolli\Downloads\PQ Order 2003.pdf"
PAGES = range(321, 335)  # 1-indexed inclusive 321-334
COL_SPLIT_X = 260  # words left of this = species column, right of this = material column
SLNO_MAX_X = 95    # Sl.No column is left of this
LINE_TOL = 3.0     # vertical tolerance (pt) to consider words on the same visual line

sl_no_re = re.compile(r"^(\d+)\.?$")


def cluster_lines(words):
    """Group words into visual lines by proximity in 'top', not a fixed grid."""
    ws = sorted(words, key=lambda w: w["top"])
    lines = []
    current = []
    last_top = None
    for w in ws:
        if last_top is None or (w["top"] - last_top) <= LINE_TOL:
            current.append(w)
        else:
            lines.append(current)
            current = [w]
        last_top = w["top"]
    if current:
        lines.append(current)
    return lines


def main():
    rows_raw = []

    with pdfplumber.open(PDF_PATH) as pdf:
        for page_num in PAGES:
            page = pdf.pages[page_num - 1]
            words = [w for w in page.extract_words() if w["text"] != str(page_num)]
            lines = cluster_lines(words)

            # skip header/title lines: anything before the first line containing a Sl.No marker
            first_data_idx = None
            for i, line_words in enumerate(lines):
                if any(w["x0"] < SLNO_MAX_X and sl_no_re.match(w["text"]) for w in line_words):
                    first_data_idx = i
                    break

            current = None
            for line_words in lines[first_data_idx:] if first_data_idx is not None else []:
                line_words = sorted(line_words, key=lambda w: w["x0"])
                sl_no_word = None
                rest_words = []
                for w in line_words:
                    if sl_no_word is None and w["x0"] < SLNO_MAX_X and sl_no_re.match(w["text"]):
                        sl_no_word = w["text"].rstrip(".")
                    else:
                        rest_words.append(w)

                if sl_no_word:
                    if current:
                        rows_raw.append(current)
                    current = {
                        "sl_no": sl_no_word,
                        "species_words": [],
                        "material_words": [],
                        "source_page": page_num,
                    }
                if current is None:
                    continue
                for w in rest_words:
                    if w["x0"] < COL_SPLIT_X:
                        current["species_words"].append(w["text"])
                    else:
                        current["material_words"].append(w["text"])
            if current:
                rows_raw.append(current)
                current = None

    def extract_amendment(material):
        if not material or not material.endswith(")"):
            return material, None
        for marker in ("(vide S.O.", "(S.O."):
            idx = material.rfind(marker)
            if idx != -1:
                amendment_ref = material[idx + 1:-1].strip()
                remaining = material[:idx].strip()
                return (remaining or None), amendment_ref
        return material, None

    # Source PDF renders these genus+species with no inter-word space (font kerning artifact,
    # confirmed present in the raw pdfplumber text dump too). Restoring the space; flagged for review.
    SPACING_FIXES = {
        "Camelliasinensis": "Camellia sinensis",
        "Asclepiasincarnata": "Asclepias incarnata",
        "Comocladiadentata": "Comocladia dentata",
        "Oxydendrumarboreum": "Oxydendrum arboreum",
    }

    output = []
    for idx, r in enumerate(rows_raw, start=1):
        species = " ".join(r["species_words"]).strip()
        spacing_fixed = species in SPACING_FIXES
        if spacing_fixed:
            species = SPACING_FIXES[species]
        material = " ".join(r["material_words"]).strip() or None
        material, amendment_ref = extract_amendment(material)
        output.append({
            "id": f"S7-{idx:03d}",
            "schedule": "VII",
            "sl_no": r["sl_no"],
            "species": species,
            "material": material,
            "country": None,
            "declarations": None,
            "conditions": None,
            "justification": None,
            "responsible_institute": None,
            "amendment_ref": amendment_ref,
            "source_page": r["source_page"],
            "needs_review": (material is None) or spacing_fixed,
        })

    with open("schedule_VII.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Total entries: {len(output)}")
    print(f"needs_review: {sum(1 for r in output if r['needs_review'])}")
    sl_nos = [int(r["sl_no"]) for r in output]
    for i in range(1, len(sl_nos)):
        if sl_nos[i] != sl_nos[i - 1] + 1:
            print(f"Sl.No jump: {sl_nos[i-1]} -> {sl_nos[i]} at row {i+1} (page {output[i]['source_page']})")


if __name__ == "__main__":
    main()
