# -*- coding: utf-8 -*-
"""בונה אתר סטטי לפריסה בוורסל.

בניגוד לדף ה-Artifact (קובץ אחד, מוגבל 16MB), כאן הנתונים נטענים
מקבצי JSON נפרדים, והשרטוטים מוגשים כקבצים — כך זה מתרחב לאלפי שאלות.
"""
import json, os, shutil, sys
import db, figures

SITE = os.path.join(os.path.dirname(__file__), "site")


def build(include_all_figures=False):
    con = db.connect()
    os.makedirs(os.path.join(SITE, "data"), exist_ok=True)
    os.makedirs(os.path.join(SITE, "figures"), exist_ok=True)

    papers = [dict(r) for r in con.execute("""
        SELECT paper_id, code, year, moed, units, program,
               question_url, solution_url,
               (question_pdf IS NOT NULL AND question_pdf<>'') AS have
        FROM papers ORDER BY year DESC, units DESC, code""")]
    json.dump(papers, open(os.path.join(SITE, "data", "papers.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    # שאלות + שרטוטים מקושרים
    import collections
    figs_by_page = collections.defaultdict(list)
    for f in con.execute("SELECT paper_id, page, file, path FROM figures ORDER BY paper_id, page, idx"):
        figs_by_page[(f["paper_id"], f["page"])].append((f["file"], f["path"]))

    parts = collections.defaultdict(list)
    for r in con.execute("SELECT * FROM parts"):
        d = dict(r)
        try: d["subtopics"] = json.loads(d["subtopics"] or "[]")
        except Exception: d["subtopics"] = []
        parts[d["question_id"]].append(d)

    questions, needed = [], set()
    for r in con.execute("""SELECT q.*, p.year, p.code, p.units, p.program, p.moed
                            FROM questions q JOIN papers p ON p.paper_id=q.paper_id
                            ORDER BY p.year DESC, p.code, q.number"""):
        q = dict(r)
        for k in ("subtopics", "skills"):
            try: q[k] = json.loads(q[k] or "[]")
            except Exception: q[k] = []
        q.pop("raw", None)
        q["parts"] = sorted(parts.get(q["question_id"], []), key=lambda x: x.get("letter") or "")
        # שיוך מפורש גובר על ניחוש לפי מספר עמוד
        explicit = q.pop("figure_files", None)
        try:
            explicit = json.loads(explicit) if isinstance(explicit, str) else explicit
        except Exception:
            explicit = None
        if explicit:
            by_name = {f: p for v in figs_by_page.values() for f, p in v}
            fl = [(f, by_name[f]) for f in explicit if f in by_name]
        else:
            fl = figs_by_page.get((q["paper_id"], q.get("page_from")), [])
        q["figures"] = ["figures/" + f for f, _ in fl]
        needed.update(fl)
        questions.append(q)
    json.dump(questions, open(os.path.join(SITE, "data", "questions.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    # מעתיקים רק שרטוטים שמקושרים לשאלה — אין טעם לשלוח 4,500 קבצים לשווא
    src = figs_by_page and None
    copy = [(f, p) for f, p in (needed if not include_all_figures else
            {t for v in figs_by_page.values() for t in v})]
    n_copied = 0
    for fname, path in copy:
        if os.path.exists(path):
            shutil.copy2(path, os.path.join(SITE, "figures", fname))
            n_copied += 1

    stats = db.stats(con)
    stats["with_solution"] = con.execute(
        "SELECT COUNT(*) FROM papers WHERE solution_url IS NOT NULL").fetchone()[0]
    json.dump(stats, open(os.path.join(SITE, "data", "stats.json"), "w", encoding="utf-8"),
              ensure_ascii=False)

    shutil.copy2(os.path.join(os.path.dirname(__file__), "assets", "site.html"),
                 os.path.join(SITE, "index.html"))
    json.dump({"cleanUrls": True,
               "headers": [{"source": "/figures/(.*)",
                            "headers": [{"key": "Cache-Control",
                                         "value": "public, max-age=31536000, immutable"}]}]},
              open(os.path.join(SITE, "vercel.json"), "w"), indent=2)

    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(SITE) for f in fs)
    print(f"  ✓ {SITE}")
    print(f"    {len(papers)} שאלונים · {len(questions)} שאלות · {n_copied} שרטוטים")
    print(f"    גודל האתר: {size/1024/1024:.1f} MB")
    return SITE


if __name__ == "__main__":
    build(include_all_figures="--all-figures" in sys.argv)
