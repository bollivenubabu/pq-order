import pdfplumber
import re
import sys
import json

PDF_PATH = r"C:\Users\bolli\Downloads\PQ Order 2003.pdf"

# The leading "(" is occasionally missing from an enumeration marker due to a font/extraction
# quirk in the source PDF (confirmed: species 458's country cell reads "i) Netherlands\nii) USA..."
# with no opening parens at all) -- make it optional rather than required.
ROMAN_MARKER_RE = re.compile(r"^\(?([ivxlcdm]+)\)\s*", re.IGNORECASE)
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

# 4 pages (out of 262) have a genuinely malformed table grid: a spurious extra column from a
# faint/missing gridline, whose position isn't consistent even in pdfplumber's own per-cell
# bounding boxes (confirmed by direct inspection -- cells report merged/overlapping geometry
# there). Rather than guess positionally and risk silently misattributing data, these pages'
# rows are hand-transcribed from raw/VI/page_NNN.txt and substituted whole, replacing whatever
# pdfplumber's table extraction returns for that page. Each row is
# [sl_no, species, material, country, declarations, conditions], matching table.extract()'s
# format (None for a blank/continuing cell); "\n" marks a line-wrap within a cell exactly as
# extract() would.
PAGE_ROW_OVERRIDES = {
    227: [
        [None, None, "(ii) Seeds for sowing",
         "(i) Europe\n(ii) South Africa\n(iii) Canada\n(iv) Australia\n(v) New Zealand\n(vi) Kazakhstan\n(vii) Turkey",
         "Free from Arabis Mosaic Nepho Virus",
         "(i) Free from quarantine weed\nseeds.\n(ii) Crop inspection and\ncertification for free from\nArabis mosaic nepho virus."],
        [None, None, None, "South America",
         "Free from Andean Potato Virus (stain)",
         "(i) Free from quarantine weed\nseeds.\n(ii) Crop inspection and\ncertification for free from\nAndean Potato Virus (stain)"],
        [None, None, None, "(ix) USA\n(x) Japan",
         "Free from Pseudomonas viridiflava (Bacterial leaf\nblight of tomato)",
         "Free from quarantine weed seeds."],
        [None, None, None, "(xi) Guatemala", "Nil", "Free from quarantine weed seeds"],
        ["515.", "Petunia axillaris,\nP. integrifolia\n(Petunia)",
         "Cuttings/ planting\nmaterial/ rooted\nplants for\npropagation",
         "(i) Germany",
         "Free from:\n(a) Peridroma saucia (Pearly moth)\n(b) Phytonemus pallidus (Mite)\n(c) Erwinia chrysanthemi pv. dieffenbachiae(Stem\nrot)\n(d) Pseudomonas viridiflava\n(e) Phytophthora cryptogea (Foot rot)\n(f) Petunia asteroid mosaic virus\n(g) Petunia flower mottle virus\n(h) Petunia vein clearing virus",
         "(i) Free from soil.\n(ii) Post-entry quarantine growing\nfor one growth season."],
        [None, None, None, "(ii) The\nNetherlands",
         "Free from:\n(a) Peridroma saucia (Pearly moth)\n(b) Phytonemus pallidus (Mite)\n(c) Pseudomonas viridiflava\n(d) Phytophthora cryptogea (Foot rot)",
         "(i) Free from soil.\n(ii) Post-entry quarantine growing\nfor one growth season."],
        [None, None, None, "(iii) USA",
         "Free from:\n(a) Anthonomus eugenii (Pepper weevil)\n(b) Exomala orientalis (Oriental beetle)\n(c) Heliothis virescens\n(d) Peridroma saucia (Pearly moth)\n(e) Phytonemus pallidus (mite)\n(f) Erwinia chrysanthemi pv. Dieffenbachiae\n(Stem rot)\n(g) Pseudomonas viridiflava\n(h) Phytophthora cryptogea (Foot rot)\n(i) Rhizobium rhizogenes",
         None],
        ["516.", "Philotheca myoporoides\n(Wax flower)", "Plants/cuttings for\npropagation",
         "USA", "Nil", "(i) Post-entry quarantine for a\nperiod of 6 months.\n(ii) Free from soil."],
    ],
    277: [
        [None, None, None, "(iii) USA", "Free from quarantine weed seeds.", "Nil"],
        [None, None, "(ii) Tissue cultured\nplants", "Germany",
         "Certified that the tissue cultured plants obtained from\nmother stock tested and maintained free from virus.",
         "Nil"],
        ["612.", "Sisymbrium irio", "Seeds for Medicinal\npurpose", "China",
         "Free from quarantine weed seeds\nand other plant debris.", "Nil"],
        ["613.", "Small fruit plant species:", None, None, None, None],
        [None, "(a) Blue berry and Cranberry\n(Vaccinium spp.)",
         "(i) Cuttings\nRooted/\nunrooted/\nGrafts / Bud\nwood/ Saplings\nfor planting",
         "Any Country",
         "Free from:\n(a) Leaf rust (Pucciniastrum myrtili)\n(b) Red leaf (Exobasidium vaccinii)\n(c) Red gall (Synchytrium vaccinii)\n(d) Witches‟broom (Pucciniastrum goeppertianum)\n(e) Straw berry weevils (Anthonomus signatus and\nA. bisignifer)\n(f) Blue berry viruses viz., blue berry mosaic, shoe-\nstring, red (necrotic) ring spot, leaf mottle, peach\nrosette and tomato ring spot\n(g) Phytoplasmas (blueberry stunt, witches‟broom\nand cranberry false blossom",
         "(i) Import subject to prior\napproval of Department of\nAgriculture, Cooperation and\nFarmers Welfare in the\nMinistry of Agriculture\n(Omitted vide Gazette\nNotification S.O. 2221(E) dated\n07th June, 2024)\n(ii) Post-entry quarantine for a\nperiod of 9-12 months;\n(iii) Free from soil\n(iv)Dormant cuttings shall be\nAppropriately treated or\nfumigated at the country of\norigin prior to shipment and\nthe treatment shall be\nendorsed on Phytosanitary\nCertificate."],
        [None, None, "(ii) Seeds for\nsowing", "Any Country",
         "Free from:\n(a) Mummy berry (Monilia vacciniicorymbasi)\n(b) Viruses affecting blueberry and cranberry as per\nitem (f) above.",
         "As per conditions (i) and (ii)\nstated above."],
        [None, None, "(iii) Tissue cultured\nplants", "Any Country",
         "Certified that the tissue-cultured plants are obtained\nfrom mother stock tested/indexed and maintained\nvirus-free.",
         "As per condition (i) stated above."],
        [None, None, "(iv) Fresh fruit for\nconsumption", "(i) Canada",
         "Free from:-\n(i) Grapholita packardi ( Cherry fruitworm)\n(ii) Rhagoletis mendax ( Blueberry fruit fly)\n(iii) Spodoptera frugiperda (Fall armyworm)\n(iv) Diaporthe vaccinii (Phomopsis twig blight of\nblueberry)\n(v) Peach rosettemosaic virus (rosette mosaic of\npeach)\n(vi) Tomato ringspot virus (ringspot of tomato)",
         "Pest free status for Rhagoletis\nmendax (Blueberry fruit fly) as\nper international standards Or\n(a) Methyl bromide fumigation\n@ 32 g/m3 for 2 hrs at 210C\nor above at NAP or\nequivalent thereof against\nBlueberry fruit fly. Or\n(b) Pre-shipment cold treatment\nat 00C or below for 10 days;\n0.550C or below for 11 days;\n1.10C or below for 12 days\nplus in-transit refrigeration"],
    ],
    284: [
        ["616.", "Solanum melongena\n(Brinjal/ Eggplant/\nAubergine)", "(i) Seeds for sowing",
         "(i) China", "Free from Pythium spinosum (root rot)",
         "(i) Free from soil contamination.\n(ii)Free from quarantine weed\nseeds."],
        [None, None, None, "(ii) Europe",
         "Free from:\n(a) Pepino mosaic virus\n(b) Tomato bushy stunt virus (Lycopersicon virus 4)\n(c) Tomato black ring nephovirus",
         "(i) Free from quarantine weed\nseeds.\n(ii) Crop inspection and\ncertification for free from\nPepino mosaic virus, Tomato\nbushy stunt virus\n(Lycopersicon virus 4) and\nTomato black ring nephovirus"],
        [None, None, None, "(iii) Japan\n(iv) Vietnam\n(v) Philippines\n(vi)Thailand",
         "Nil", "Free from quarantine weed seeds."],
        [None, None, None, "(vii) USA",
         "Free from Tomato bushy stunt virus (Lycopersicon\nvirus 4)",
         "(i) Free from quarantine weed\nseeds.\n(ii) Crop inspection and\ncertification for free from\ntomato bushy stunt virus."],
        [None, None, None, "(viii) Jordan\n(ix) Israel",
         "Free from:\n(a) Peronospora hyoscyami f. sp. tabacina (angular\ntobacco leaf spot)\n(b) Eggplant mottled dwarf virus (hibiscus vein\nyellowing virus)",
         "(i) Free from quarantine weeds\nseeds.\n(ii) Crop inspection and\ncertification for free from eggplant\nmottled dwarf virus."],
        [None, None, None, "(x) Russia\n(xi)Taiwan",
         "Free from:\n(a) Peronospora hyoscyami f.sp. tabacina\n(b) Pepino mosaic virus\n(c) Tomato bushy stunt virus",
         "(i) Freedom from quarantine\nweed seeds\n(ii) Post-entry quarantine\ngrowing for 2-3 months\n(iii) Crop inspection and\ncertification for freedom from\nPepino mosaic virus\nandTomato bushy stunt virus"],
        [None, None, "(ii) Vegetables for\nconsumption", "Thailand",
         "Free from:\n(a) Bactrocera papayae (papaya fruit fly)\n(b) Pseudococcus jackbeardsleyi (Jack Beardsley\nmealybug)\n(c) Tetranychus marianae\n(d) Tetranychus truncatus",
         "Pest-free area status for papaya\nfruit fly (Bactrocera papayae ) as\nper international standards."],
        ["617.", "Solanum muricatum\n(Pepino)", "(i) Seeds for sowing",
         "(i) Italy\n(ii) Spain\n(iii) USA", "Nil", "Free from quarantine weed seeds."],
        [None, None, "(ii) Cuttings", None, None,
         "(i) Free from soil.\n(ii) Post-entry quarantine for one\ngrowth season except for\nresearch"],
        [None, None, "(iii) Plants/", "(iv) Israel", "Nil", "(i) Free from soil."],
    ],
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


def normalize_row(raw_row):
    """A continuation table row missing leading columns (Sl.No/species blank) is safely
    assumed to be missing exactly those leading ones, since country/declarations/conditions
    are consistently present as explicit text (even "Nil") rather than truly blank in this
    schedule -- left-padding is reliable here and is the common case.

    A handful of pages (confirmed: 4 out of 262 -- see PAGE_ROW_OVERRIDES) have a spurious
    extra table column from a faint/missing gridline, at inconsistent positions that even
    pdfplumber's own per-cell bounding boxes don't resolve cleanly (verified by direct
    inspection: cells report merged/overlapping geometry on these specific pages). Rather
    than build fragile positional-guessing logic for a few dozen rows, those pages are
    hand-transcribed from the source text and substituted whole via PAGE_ROW_OVERRIDES.
    """
    if len(raw_row) < 6:
        raw_row = [None] * (6 - len(raw_row)) + raw_row
    return raw_row[:6]


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
            if page_num in PAGE_ROW_OVERRIDES:
                all_table_rows = [PAGE_ROW_OVERRIDES[page_num]]
            else:
                tables = page.find_tables()
                all_table_rows = [table.extract() for table in tables]
            for table_rows in all_table_rows:
                for raw_row in table_rows:
                    raw_row = normalize_row(raw_row)
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
                        # conditions/country text, e.g. a country name with a long embedded
                        # amendment reference) into an extra table row with no sl_no/material of
                        # its own -- that's a continuation of the immediately preceding row, not a
                        # new entry. A continuation fragment either has no country at all, or a
                        # country-cell remnant that starts lowercase (mid-sentence/mid-parenthetical,
                        # e.g. "dated 29th August, 2019)" finishing "Chile (S.O. 3141 (E)" from the
                        # row above) rather than a genuine new country name.
                        # A row with country=None is usually this kind of split artifact (confirmed:
                        # e.g. species 613's Raspberry material "(i) Cuttings Rooted/un-" / "rooted)/
                        # Bud wood..." is one material description split mid-word across two table
                        # rows) -- UNLESS the material text itself starts with its own roman-numeral
                        # marker, which means it's a genuinely new, complete material entry that
                        # simply has no country listed in the source (e.g. species 617's "(ii)
                        # Cuttings"), not a wrapped fragment of the previous material. A
                        # lowercase-starting country fragment is the same continuation phenomenon
                        # but only when material is also blank, since a genuinely new material row
                        # always pairs with a genuinely new (capitalized) country.
                        material_is_fresh_entry = bool(material_clean) and bool(ROMAN_MARKER_RE.match(material_clean))
                        is_continuation_fragment = (
                            (country_entry is None and not material_is_fresh_entry)
                            or (not material_clean and country_entry and country_entry[0].islower())
                        )
                        if is_continuation_fragment and sl_no_clean == "" and rows:
                            prev = rows[-1]
                            if country_entry:
                                prev["country"] = ((prev["country"] or "") + " " + country_entry).strip()
                            if material_clean and material_final and not (prev["material"] or "").endswith(material_final):
                                prev["material"] = ((prev["material"] or "") + " " + material_final).strip()
                                # cur_material got set to just this fragment above (before we knew
                                # it was a split artifact) -- restore it to the full merged text so
                                # any later row still under the same material carries it correctly.
                                cur_material = prev["material"]
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
