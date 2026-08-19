# -*- coding: utf-8 -*-
"""משייך לכל שאלה את הפרק שהיא נמצאת בו בשאלון.

שאלוני הבגרות מכריזים על הפרק ("פרק שני – גאומטרייה וטריגונומטרייה
במישור"), וזו הצהרה רשמית על הנושא — חזקה בהרבה מניחוש לפי מילות מפתח.
כל שאלה שייכת לכותרת האחרונה שלפניה במסמך.
"""
import os, re, json
import fitz
import db, fix_encoding, crop_questions as cq

HDR = re.compile(r'(?:פרק\s+(?:ראשון|שני|שלישי|רביעי|חמישי)|אשכול)\b')
# כותרת שימושית חייבת לתאר נושא, לא רק "פרק שני"
TOPIC_WORD = re.compile(r'גאומטרי|גיאומטרי|טריגונומטרי|דיפרנציאלי|אינטגרלי|סדרות|'
                        r'הסתברות|אלגברה|וקטורים|פונקצי|גדילה|אנליטי|חברה|פיננסי|'
                        r'התמצאות|קצרות|סטטיסטיק|מרוכבים|אינדוקצי')


def headers(pdf_path):
    """כותרות פרקים משמעותיות עם מיקומן. ברמת בלוק, כדי לתפוס כותרת שנשברה לשורות."""
    doc = fitz.open(pdf_path)
    out = []
    for pno, page in enumerate(doc, 1):
        for b in page.get_text("dict")["blocks"]:
            txt = "".join(sp["text"] for l in b.get("lines", []) for sp in l.get("spans", []))
            if fix_encoding.is_broken(txt):
                txt = fix_encoding.repair(txt)
            t = re.sub(r'\s+', ' ', txt).strip()
            if not (6 <= len(t) <= 200) or not HDR.search(t):
                continue
            if not TOPIC_WORD.search(t):      # "פרק שני" בלי נושא — עמוד הוראות
                continue
            out.append({"page": pno, "y": b["bbox"][1], "text": t[:120]})
    doc.close()
    out.sort(key=lambda h: (h["page"], h["y"]))
    return out


def question_positions(pdf_path):
    """מיקומי מספרי השאלות, כדי לדעת איזו כותרת קודמת לכל שאלה."""
    doc = fitz.open(pdf_path)
    seq, last = [], 0
    for pno, page in enumerate(doc, 1):
        for m in cq.markers(page):
            if m["n"] == last + 1:
                seq.append({"n": m["n"], "page": pno, "y": m["y"]})
                last = m["n"]
    doc.close()
    return {str(s["n"]): (s["page"], s["y"]) for s in seq}


def run():
    con = db.connect()
    path = os.path.join(os.path.dirname(__file__), "data", "cropped_questions.json")
    idx = json.load(open(path, encoding="utf-8"))
    pdfs = {r["paper_id"]: r["question_pdf"] for r in
            con.execute("SELECT paper_id, question_pdf FROM papers "
                        "WHERE question_pdf IS NOT NULL AND question_pdf<>''")}
    n_ch = 0
    for i, (pid, qs) in enumerate(idx.items(), 1):
        p = pdfs.get(pid)
        if not p or not os.path.exists(p):
            continue
        try:
            hs = headers(p)
            pos = question_positions(p)
        except Exception:
            continue
        for q in qs:
            xy = pos.get(q["number"])
            if not xy:
                q["chapter"] = None; continue
            best = None
            for h in hs:
                if (h["page"], h["y"]) < (xy[0], xy[1]):
                    best = h["text"]
            q["chapter"] = best
            if best:
                n_ch += 1
        if i % 150 == 0:
            print(f"  {i}/{len(idx)}")
    json.dump(idx, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    tot = sum(len(v) for v in idx.values())
    print(f"שאלות ששויכו לפרק: {n_ch}/{tot} ({n_ch/tot:.0%})")
    return n_ch


if __name__ == "__main__":
    run()
