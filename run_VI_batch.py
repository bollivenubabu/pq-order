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
        if r.get("country") is None:
            reasons.append("no_country_in_source")
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

    # A row with country=None and no sl_no is always a split-cell continuation of the
    # immediately preceding row (verified: every such occurrence found across the whole
    # dataset is this pattern, e.g. a material description split mid-word across a spurious
    # extra table row). Within a single batch this merges automatically; at a batch boundary
    # the "immediately preceding row" is the previous batch's last row, which isn't visible
    # inside that parse_pages() call, so do the same merge here.
    merged_boundary_note = None
    if (existing and new_rows and new_rows[0]["country"] is None
            and new_rows[0]["sl_no"] == existing[-1]["sl_no"]):
        first = new_rows.pop(0)
        last = existing[-1]
        if first.get("material") and not (last.get("material") or "").endswith(first["material"]):
            last["material"] = ((last.get("material") or "") + " " + first["material"]).strip()
        for field in ("declarations", "conditions"):
            if first.get(field):
                last[field] = ((last.get(field) or "") + " " + first[field]).strip()
        if first.get("amendment_ref"):
            last["amendment_ref"] = " | ".join(a for a in [last.get("amendment_ref"), first["amendment_ref"]] if a)
        merged_boundary_note = f"Merged cross-batch split-cell continuation from page {first['source_page']} into {last['id']} (sl_no {last['sl_no']})"

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
    if merged_boundary_note:
        print(merged_boundary_note)
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
