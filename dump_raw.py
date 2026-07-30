import pdfplumber
import os

PDF_PATH = r"C:\Users\bolli\Downloads\PQ Order 2003.pdf"
OUT_ROOT = "raw"

SCHEDULES = {
    "IV": (46, 49),
    "V": (50, 58),
    "VI": (59, 320),
    "VII": (321, 334),
}

def schedule_for_page(page_num):
    for sched, (start, end) in SCHEDULES.items():
        if start <= page_num <= end:
            return sched
    return None

def main():
    for sched in SCHEDULES:
        os.makedirs(os.path.join(OUT_ROOT, sched), exist_ok=True)
    os.makedirs(os.path.join(OUT_ROOT, "other"), exist_ok=True)

    counts = {sched: 0 for sched in SCHEDULES}
    counts["other"] = 0

    with pdfplumber.open(PDF_PATH) as pdf:
        total_pages = len(pdf.pages)
        print(f"Total pages in PDF: {total_pages}")
        for i, page in enumerate(pdf.pages):
            page_num = i + 1  # 1-indexed to match PDF page numbers
            text = page.extract_text() or ""
            sched = schedule_for_page(page_num)
            folder = sched if sched else "other"
            fname = os.path.join(OUT_ROOT, folder, f"page_{page_num:03d}.txt")
            with open(fname, "w", encoding="utf-8") as f:
                f.write(text)
            counts[folder] += 1

    print("Page counts per folder:")
    for k, v in counts.items():
        print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
