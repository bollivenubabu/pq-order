import sys
import json
import re
import os
from parse_VI import parse_pages

OUT_FILE = "schedule_VI.json"
MULTI_ROMAN_RE = re.compile(r"\([ivxlcdm]+\)", re.IGNORECASE)


def renumber(rows, start_idx):
    for i, r in enumerate(rows, start=start_idx + 1):
        r["id"] = f"S6-{i:04d}"
    return rows


def flag_needs_review(rows):
    for r in rows:
        reasons = []
        if r["sl_no"] is None:
            reasons.append("no_sl_no")
        country = r.get("country") or ""
        markers = MULTI_ROMAN_RE.findall(country)
        if len(markers) > 1:
            reasons.append("multiple_country_markers_merged")
        if r.get("species") and re.search(r"\d+\.\s", r["species"]):
            reasons.append("possible_embedded_sl_no_in_species")
        if r.get("species") and re.match(r"^\([ivxlcdm]+\)", r["species"], re.IGNORECASE):
            reasons.append("nested_sub_genus_in_species_column")
        if reasons:
            r["needs_review"] = True
            r["_review_reasons"] = reasons
    return rows


def main():
    start_page = int(sys.argv[1])
    end_page = int(sys.argv[2])

    existing = []
    if os.path.exists(OUT_FILE):
        with open(OUT_FILE, encoding="utf-8") as f:
            existing = json.load(f)

    carry_forward = None
    if existing:
        last = existing[-1]
        carry_forward = {
            "sl_no": last.get("sl_no"),
            "species": last.get("species"),
            "material": last.get("material"),
        }

    new_rows = parse_pages(start_page, end_page, idx_start=0, carry_forward=carry_forward)
    flag_needs_review(new_rows)

    all_rows = existing + new_rows
    all_rows = renumber(all_rows, 0)

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)

    # Report
    batch_rows = all_rows[len(existing):]
    sl_nos_in_batch = [r["sl_no"] for r in batch_rows if r["sl_no"] is not None]
    seen_order = []
    for sl in sl_nos_in_batch:
        if not seen_order or seen_order[-1] != sl:
            seen_order.append(sl)

    print(f"Batch pages {start_page}-{end_page}")
    if carry_forward:
        print(f"Carried forward into this batch: sl_no={carry_forward['sl_no']!r} species={carry_forward['species']!r} material={carry_forward['material']!r}")
    print(f"Rows added this batch: {len(new_rows)}")
    print(f"Total rows so far: {len(all_rows)}")
    print(f"Distinct Sl.No sequence in this batch: {seen_order[0] if seen_order else None} ... {seen_order[-1] if seen_order else None} ({len(seen_order)} distinct species)")
    print("Full Sl.No sequence:", seen_order)
    # gap check within this batch's species numbers
    int_seq = [int(x) for x in seen_order]
    gaps = []
    for i in range(1, len(int_seq)):
        if int_seq[i] != int_seq[i-1] + 1:
            gaps.append((int_seq[i-1], int_seq[i]))
    print("Gaps/jumps in Sl.No within batch:", gaps if gaps else "none")

    review_rows = [r for r in batch_rows if r.get("needs_review")]
    print(f"needs_review rows in this batch: {len(review_rows)}")
    for r in review_rows:
        print(f"  {r['id']} sl_no={r['sl_no']} reasons={r.get('_review_reasons')} country={r.get('country')!r}")


if __name__ == "__main__":
    main()
