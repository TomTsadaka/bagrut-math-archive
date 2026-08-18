# -*- coding: utf-8 -*-
"""מריץ זיהוי שרטוטים על כל השאלונים שירדו, ושומר במאגר."""
import os, sys
import db, figures

def run(limit=None, redo=False):
    con = db.connect()
    q = "SELECT paper_id, question_pdf FROM papers WHERE question_pdf IS NOT NULL AND question_pdf<>''"
    if not redo:
        q += " AND paper_id NOT IN (SELECT DISTINCT paper_id FROM figures)"
    q += " ORDER BY year DESC"
    if limit: q += f" LIMIT {int(limit)}"
    rows = con.execute(q).fetchall()
    print(f"זיהוי שרטוטים ב-{len(rows)} שאלונים")
    tot = 0
    for i, r in enumerate(rows, 1):
        if not os.path.exists(r["question_pdf"]):
            continue
        try:
            figs = figures.extract_paper_figures(r["question_pdf"], r["paper_id"])
        except Exception as e:
            print(f"  ✗ {r['paper_id']}: {e}"); continue
        for f in figs:
            db.upsert_figure(con, f)
        tot += len(figs)
        if i % 40 == 0:
            con.commit(); print(f"  {i}/{len(rows)} — {tot} שרטוטים")
    con.commit()
    print(f"  ✓ סה\"כ {tot} שרטוטים")
    return tot

if __name__ == "__main__":
    run(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
