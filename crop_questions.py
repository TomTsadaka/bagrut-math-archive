# -*- coding: utf-8 -*-
"""חותך כל שאלה מן ה-PDF כתמונה — בלי מודל שפה ובלי עלות.

הרעיון: מספרי השאלות מודגשים ויושבים בשוליים הימניים של העמוד.
מאתרים אותם, וכל שאלה משתרעת מן המספר שלה עד המספר הבא.

הטקסט הגולמי של האזור נשמר לחיפוש: סדר הקריאה שלו משובש (RTL),
אבל המילים עצמן תקינות — ולחיפוש זה כל מה שצריך.
"""
import os, re, json, sys
import fitz
import db

OUT = os.path.join(os.path.dirname(__file__), "exports", "questions_img")
DPI = 130
NUM_RE = re.compile(r'^\.?(\d{1,2})\.?$')
# כותרות תחתונות שאינן חלק מהשאלה
FOOTER = ("בהצלחה", "זכות היוצרים", "אין להעתיק", "המשך בעמוד",
          "/המשך", "בהצלחה!")


def markers(page):
    """מוצא מספרי שאלות: מודגשים, בשוליים הימניים."""
    W = page.rect.width
    found = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                t = s["text"].strip()
                m = NUM_RE.fullmatch(t)
                if not m:
                    continue
                if s["bbox"][2] < W * 0.80:        # חייב להיות בשוליים הימניים
                    continue
                if s["size"] < 9:                   # מספרי סעיפים קטנים אינם שאלות
                    continue
                found.append({"n": int(m.group(1)), "y": s["bbox"][1],
                              "x1": s["bbox"][2]})
    found.sort(key=lambda r: r["y"])
    return found


def _content_bottom(page, clip):
    """התחתית האמיתית של התוכן בתוך האזור — כדי לא לחתוך חצי עמוד ריק."""
    bottom = clip.y0
    for b in page.get_text("dict")["blocks"]:
        r = fitz.Rect(b["bbox"])
        if not r.intersects(clip):
            continue
        txt = "".join(sp["text"] for ln in b.get("lines", []) for sp in ln.get("spans", []))
        if any(f in txt for f in FOOTER):
            continue
        if r.y1 > bottom:
            bottom = min(r.y1, clip.y1)
    for d in page.get_drawings():
        r = d.get("rect")
        if r and not r.is_empty and r.intersects(clip) and r.y1 > bottom:
            bottom = min(r.y1, clip.y1)
    for img in page.get_images(full=True):
        try:
            for r in page.get_image_rects(img[0]):
                r = fitz.Rect(r)
                if r.intersects(clip) and r.y1 > bottom:
                    bottom = min(r.y1, clip.y1)
        except Exception:
            pass
    return bottom


def crop_paper(pdf_path, paper_id, out_dir=OUT, dpi=DPI):
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    W = doc[0].rect.width if len(doc) else 595
    # אוספים את כל המסמנים בכל העמודים
    all_m = []
    for pno, page in enumerate(doc, 1):
        for m in markers(page):
            m["page"] = pno
            all_m.append(m)
    # מסננים רצף לא הגיוני (כותרות, מספרי סעיפים שחמקו)
    seq, last = [], 0
    for m in all_m:
        if m["n"] == last + 1 or (last == 0 and m["n"] == 1):
            seq.append(m); last = m["n"]
    out = []
    for i, m in enumerate(seq):
        page = doc[m["page"] - 1]
        top = max(0, m["y"] - 8)
        nxt = seq[i + 1] if i + 1 < len(seq) else None
        bottom = (nxt["y"] - 6) if (nxt and nxt["page"] == m["page"]) \
                 else page.rect.y1 - 55          # עד תחתית העמוד, בלי הכותרת התחתונה
        if bottom - top < 40:
            continue
        clip = fitz.Rect(28, top, W - 24, bottom)
        real = _content_bottom(page, clip)
        if real > top + 30:
            clip = fitz.Rect(clip.x0, clip.y0, clip.x1, min(bottom, real + 10))
        pix = page.get_pixmap(clip=clip, dpi=dpi, colorspace=fitz.csGRAY)
        name = f"{paper_id}_q{m['n']}.png"
        pix.save(os.path.join(out_dir, name))
        raw = (page.get_textbox(clip) or "").replace("\n", " ")
        raw = re.sub(r"\s+", " ", raw).strip()
        out.append({"number": str(m["n"]), "page": m["page"], "file": name,
                    "w": pix.width, "h": pix.height, "text": raw})
    doc.close()
    return out


def run(limit=None, redo=False):
    con = db.connect()
    q = ("SELECT paper_id, question_pdf FROM papers "
         "WHERE question_pdf IS NOT NULL AND question_pdf<>''")
    q += " ORDER BY year DESC, code"
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = con.execute(q).fetchall()
    print(f"חיתוך שאלות מ-{len(rows)} שאלונים")
    tot, empty = 0, 0
    index = {}
    for i, r in enumerate(rows, 1):
        try:
            qs = crop_paper(r["question_pdf"], r["paper_id"])
        except Exception as e:
            print(f"  ✗ {r['paper_id']}: {e}")
            continue
        if not qs:
            empty += 1
        index[r["paper_id"]] = qs
        tot += len(qs)
        if i % 50 == 0:
            print(f"  {i}/{len(rows)} — {tot} שאלות")
    json.dump(index, open(os.path.join(os.path.dirname(__file__), "data",
                                       "cropped_questions.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"  ✓ {tot} שאלות מ-{len(rows)-empty} שאלונים ({empty} ללא זיהוי)")
    return tot


if __name__ == "__main__":
    run(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
