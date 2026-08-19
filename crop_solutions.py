# -*- coding: utf-8 -*-
"""חותך את הפתרון הרשמי של כל שאלה מטבלת התשובות של משרד החינוך.

הפתרונות ערוכים כטבלה בשני טורים ("מספר השאלה | התשובה הנכונה").
מספרי השאלות יושבים בקצה הימני של כל טור; מזהים את הטורים לפי
אשכולות ה-x של המספרים, ובכל טור חותכים ממסמן למסמן.
"""
import os, re, json, sys, collections
import fitz
import db

OUT = os.path.join(os.path.dirname(__file__), "exports", "solutions_img")
DPI = 130
NUM = re.compile(r'^\.?(\d{1,2})\.?$')


def _table_geometry(page):
    """גבולות הטבלאות מתוך הקווים עצמם, במקום לנחש לפי מיקומי מספרים."""
    vlines, hspans = [], collections.Counter()
    for dr in page.get_drawings():
        r = dr.get("rect")
        if not r:
            continue
        w, h = r.x1 - r.x0, r.y1 - r.y0
        if w < 3 and h > 50:
            vlines.append(r.x0)
        elif h < 3 and w > 80:
            hspans[(round(r.x0), round(r.x1))] += 1
    # רק טווחים שחוזרים הם שורות טבלה אמיתיות
    spans = [k for k, v in hspans.items() if v >= 2]
    return sorted(set(round(v) for v in vlines)), spans


def _marker_columns(page, max_q=14):
    """עמודות מסמנים: מספרים שיושבים צמוד לקו אנכי — קצה ימני של טבלה."""
    vlines, spans = _table_geometry(page)
    if not vlines:
        return []
    cand = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l.get("spans", []):
                t = sp["text"].strip()
                m = NUM.fullmatch(t)
                if not (m and sp["size"] >= 9 and 1 <= int(m.group(1)) <= max_q):
                    continue
                mx = sp["bbox"][2]
                # חייב קו אנכי צמוד מימין — כך נופלים מספרים שהם תוכן התשובה
                if not any(0 <= v - mx <= 16 for v in vlines):
                    continue
                cand.append({"n": int(m.group(1)), "y": sp["bbox"][1], "x": mx})
    if not cand:
        return []
    buckets = collections.defaultdict(list)
    for c in sorted(cand, key=lambda r: -r["x"]):
        for key in list(buckets):
            if abs(key - c["x"]) <= 14:
                buckets[key].append(c); break
        else:
            buckets[round(c["x"])].append(c)
    cols = []
    for key, items in buckets.items():
        items.sort(key=lambda r: r["y"])
        ns = [i["n"] for i in items]
        if ns != sorted(ns) or len(set(ns)) != len(ns):
            continue
        # שמאל הטבלה: טווח השורות שקצהו הימני קרוב ביותר משמאל למסמן
        left = 24
        below = [sp for sp in spans if sp[1] <= key + 2]
        if below:
            left = min(below, key=lambda sp: key - sp[1])[0] - 5
        cols.append({"x": key, "left": max(0, left), "items": items})
    cols.sort(key=lambda c: -c["x"])
    return cols


def crop_paper(pdf_path, paper_id, out_dir=OUT, dpi=DPI):
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    out, seen = [], set()
    for pno, page in enumerate(doc, 1):
        cols = _marker_columns(page)
        if not cols:
            continue
        for col in cols:
            items = col["items"]
            right, left = col["x"] + 14, col["left"]
            for i, m in enumerate(items):
                if m["n"] in seen:
                    continue
                top = max(0, m["y"] - 10)
                bottom = (items[i + 1]["y"] - 6) if i + 1 < len(items) \
                         else page.rect.y1 - 45
                if bottom - top < 25:
                    continue
                clip = fitz.Rect(left, top, right, bottom)
                pix = page.get_pixmap(clip=clip, dpi=dpi, colorspace=fitz.csGRAY)
                name = f"{paper_id}_s{m['n']}.png"
                pix.save(os.path.join(out_dir, name))
                seen.add(m["n"])
                out.append({"number": str(m["n"]), "page": pno, "file": name,
                            "w": pix.width, "h": pix.height})
    doc.close()
    return out


def run(limit=None):
    con = db.connect()
    q = ("SELECT paper_id, solution_pdf FROM papers "
         "WHERE solution_pdf IS NOT NULL AND solution_pdf<>'' ORDER BY year DESC")
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = con.execute(q).fetchall()
    print(f"חיתוך פתרונות מ-{len(rows)} שאלונים")
    idx, tot = {}, 0
    for i, r in enumerate(rows, 1):
        if not os.path.exists(r["solution_pdf"]):
            continue
        try:
            ss = crop_paper(r["solution_pdf"], r["paper_id"])
        except Exception as e:
            print(f"  ✗ {r['paper_id']}: {e}"); continue
        if ss:
            idx[r["paper_id"]] = ss
            tot += len(ss)
        if i % 50 == 0:
            print(f"  {i}/{len(rows)} — {tot} פתרונות")
    json.dump(idx, open(os.path.join(os.path.dirname(__file__), "data",
                                     "cropped_solutions.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    print(f"  ✓ {tot} פתרונות מ-{len(idx)} שאלונים")
    return tot


if __name__ == "__main__":
    run(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
