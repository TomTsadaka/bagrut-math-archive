# -*- coding: utf-8 -*-
"""זיהוי וחיתוך שרטוטים מתוך שאלוני הבגרות.

השרטוטים בשאלונים הם ציורים וקטוריים (קווים, מעגלים, קשתות) ולא תמונות
מוטמעות, ולכן get_images() מחזיר ריק. הפתרון: לאסוף את הנתיבים הוקטוריים,
לסנן קווי-הדגשה של טקסט, לאשכל את השאר לפי קרבה, ולחתוך כל אשכול כתמונה.
"""
import os, json
import fitz

FIG_DIR = os.path.join(os.path.dirname(__file__), "exports", "figures")
MIN_W, MIN_H = 45, 45      # מתחת לזה זה קו או סימן, לא שרטוט
MERGE_GAP = 26             # מרחק בנקודות שמתחתיו שני נתיבים נחשבים לאותו שרטוט
PAD = 10                   # שוליים סביב החיתוך
MAX_FRAC = 0.45            # שרטוט אמיתי לא מכסה חצי עמוד — מעבר לזה זה טופס
MAX_PATHS = 150            # אשכול עם מאות נתיבים הוא סריקה או רשת טופס

# עמודים טכניים בחוברת הבחינה שאין בהם שרטוטים
FORM_MARKERS = ("לא לכתוב באזור זה", "מדבקת משגיח", "גיליון תשובות",
                "ملصقة مراقب", "טופס תשובות")


def _is_rule(r):
    """קו אופקי/אנכי דק — קו הדגשה מתחת לטקסט, לא חלק משרטוט."""
    w, h = r.x1 - r.x0, r.y1 - r.y0
    return (h < 2.5 and w > 25) or (w < 2.5 and h > 25 and w * h < 60)


def _merge(rects, gap=MERGE_GAP):
    """מאחד מלבנים חופפים או סמוכים לאשכולות."""
    boxes = [fitz.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out = []
        while boxes:
            b = boxes.pop()
            hit = None
            for i, o in enumerate(out):
                grown = fitz.Rect(b.x0 - gap, b.y0 - gap, b.x1 + gap, b.y1 + gap)
                if grown.intersects(o):
                    hit = i
                    break
            if hit is None:
                out.append(b)
            else:
                out[hit] = out[hit] | b
                changed = True
        boxes = out
    return boxes



LABEL_GAP_X = 22    # מרחק אופקי מרבי של תווית מהשרטוט
LABEL_GAP_UP = 14   # כלפי מעלה רק תוויות צמודות (y), אחרת נבלע השרטוט שמעל
LABEL_GAP_DOWN = 58 # כלפי מטה מרחיבים — שם יושבות התוויות (I, II, גרף א)
LABEL_MAXLEN = 18   # תווית היא טקסט קצר (A, y, גרף I), לא פסקה


def _with_labels(page, box):
    """מרחיב את התיבה כדי לכלול תוויות קצרות שצמודות לשרטוט."""
    grown = fitz.Rect(box)
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        t = (text or "").strip()
        if not t or len(t) > LABEL_MAXLEN or "\n" in t.strip("\n"):
            continue
        r = fitz.Rect(x0, y0, x1, y1)
        near = fitz.Rect(box.x0 - LABEL_GAP_X, box.y0 - LABEL_GAP_UP,
                         box.x1 + LABEL_GAP_X, box.y1 + LABEL_GAP_DOWN)
        if near.intersects(r):
            grown = grown | r
    return grown

def _key(r):
    return (round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1))

def _score(page, box, paths):
    """מאפייני האשכול, לצורך הבחנה בין שרטוט אמיתי למסגרת/חותמת."""
    inside = [p for p in paths if box.intersects(p["rect"])]
    items = sum(len(p.get("items") or []) for p in inside)
    curves = sum(1 for p in inside for it in (p.get("items") or []) if it[0] == "c")
    text = (page.get_textbox(box) or "").strip()
    return len(inside), items, curves, len(text)


def _is_form_page(page):
    t = page.get_text() or ""
    return any(m in t for m in FORM_MARKERS)


def detect(page):
    """מחזיר רשימת מלבנים של שרטוטים בעמוד."""
    if _is_form_page(page):
        return []
    paths = []
    for d in page.get_drawings():
        r = d.get("rect")
        if r is None or r.is_empty:
            continue
        paths.append(d)
    if not paths:
        return []
    # קווים דקים (צירים או קווי הדגשה) לא פותחים אשכול בעצמם, אבל כן
    # מצטרפים לאשכול קיים — כך הצירים נשארים והקו שמתחת לכותרת נופל.
    seeds = [p["rect"] for p in paths if not _is_rule(p["rect"])]
    if not seeds:
        return []
    boxes = _merge(seeds)
    # תמונות רסטר מוטמעות (צילומים, איורים סרוקים) הן שרטוטים לכל דבר,
    # והן אינן נתיבים וקטוריים — לכן נאספות בנפרד
    for img in page.get_images(full=True):
        try:
            for r in page.get_image_rects(img[0]):
                if (r.x1 - r.x0) >= MIN_W and (r.y1 - r.y0) >= MIN_H:
                    boxes.append(fitz.Rect(r))
        except Exception:
            pass
    rules = [p["rect"] for p in paths if _is_rule(p["rect"])]
    for i, b in enumerate(boxes):
        for r in rules:
            grown = fitz.Rect(b.x0 - MERGE_GAP, b.y0 - MERGE_GAP,
                              b.x1 + MERGE_GAP, b.y1 + MERGE_GAP)
            if grown.intersects(r):
                boxes[i] = boxes[i] | r
                b = boxes[i]
    is_raster = {}
    for img in page.get_images(full=True):
        try:
            for r in page.get_image_rects(img[0]):
                is_raster[_key(fitz.Rect(r))] = True
        except Exception:
            pass
    keep = []
    for b in boxes:
        if (b.x1 - b.x0) < MIN_W or (b.y1 - b.y0) < MIN_H:
            continue
        frac = ((b.x1 - b.x0) * (b.y1 - b.y0)) / (page.rect.width * page.rect.height)
        if frac > MAX_FRAC:
            continue
        n_paths, items, curves, n_text = _score(page, b, paths)
        if n_paths > MAX_PATHS:
            continue
        if is_raster.get(_key(b)):
            b = _with_labels(page, b)
            b = fitz.Rect(max(0, b.x0 - PAD), max(0, b.y0 - PAD),
                          min(page.rect.x1, b.x1 + PAD), min(page.rect.y1, b.y1 + PAD))
            keep.append(b)
            continue
        # מסגרת ריקה או חותמת: נתיב בודד עם פריט או שניים
        if items <= 2:
            continue
        # מסגרת סביב טקסט: מעט גיאומטריה והרבה טקסט
        if curves == 0 and n_paths <= 2 and n_text > 60:
            continue
        b = _with_labels(page, b)
        b = fitz.Rect(max(0, b.x0 - PAD), max(0, b.y0 - PAD),
                      min(page.rect.x1, b.x1 + PAD),
                      min(page.rect.y1, b.y1 + PAD))
        keep.append(b)
    keep.sort(key=lambda r: (r.y0, r.x0))
    return keep


def extract_paper_figures(pdf_path, paper_id, dpi=150, out_dir=FIG_DIR, gray=True):
    """חותך את כל השרטוטים בשאלון ושומר כ-PNG. מחזיר רשימת מטא-דאטה."""
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    figs = []
    for pno, page in enumerate(doc, 1):
        for i, box in enumerate(detect(page), 1):
            # ציורי קו: גווני אפור מקטינים את הקובץ פי ~3 בלי אובדן קריאות
            pix = page.get_pixmap(clip=box, dpi=dpi,
                                  colorspace=fitz.csGRAY if gray else fitz.csRGB)
            name = f"{paper_id}_p{pno}_f{i}.png"
            path = os.path.join(out_dir, name)
            pix.save(path)
            figs.append({
                "figure_id": f"{paper_id}_p{pno}_f{i}",
                "paper_id": paper_id, "page": pno, "idx": i,
                "path": path, "file": name,
                "x0": round(box.x0, 1), "y0": round(box.y0, 1),
                "x1": round(box.x1, 1), "y1": round(box.y1, 1),
                "w": pix.width, "h": pix.height,
            })
    doc.close()
    return figs


if __name__ == "__main__":
    import sys
    pdf = sys.argv[1] if len(sys.argv) > 1 else "cache/questions/35571_2026_01.pdf"
    pid = os.path.splitext(os.path.basename(pdf))[0]
    figs = extract_paper_figures(pdf, pid)
    print(f"נמצאו {len(figs)} שרטוטים ב-{pid}")
    for f in figs:
        print(f"  עמוד {f['page']} #{f['idx']}: {f['w']}x{f['h']}px  -> {f['file']}")
