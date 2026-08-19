# -*- coding: utf-8 -*-
"""בונה אתר סטטי לפריסה בוורסל.

בניגוד לדף ה-Artifact (קובץ אחד, מוגבל 16MB), כאן הנתונים נטענים
מקבצי JSON נפרדים, והשרטוטים מוגשים כקבצים — כך זה מתרחב לאלפי שאלות.
"""
import json, os, shutil, sys
import db, figures, topic_tag, fix_encoding

SITE = os.path.join(os.path.dirname(__file__), "site")


def _sol_for(sols, paper_id, number, site):
    """מעתיק את תמונת הפתרון לאתר ומחזיר את הנתיב היחסי."""
    for e in sols.get(paper_id, []):
        if e["number"] == number:
            src = os.path.join(os.path.dirname(__file__), "exports",
                               "solutions_img", e["file"])
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(site, "s", e["file"]))
                return "s/" + e["file"]
    return None


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

    # --- שאלות חתוכות כתמונה (ללא מודל שפה) ---
    sol_path = os.path.join(os.path.dirname(__file__), "data", "cropped_solutions.json")
    sols = json.load(open(sol_path, encoding="utf-8")) if os.path.exists(sol_path) else {}
    if sols:
        os.makedirs(os.path.join(SITE, "s"), exist_ok=True)
    crop_path = os.path.join(os.path.dirname(__file__), "data", "cropped_questions.json")
    scanned = []
    if os.path.exists(crop_path):
        cropped = json.load(open(crop_path, encoding="utf-8"))
        meta = {r["paper_id"]: dict(r) for r in con.execute(
            "SELECT paper_id, code, year, units, program, moed, solution_url FROM papers")}
        os.makedirs(os.path.join(SITE, "q"), exist_ok=True)
        n_img = 0
        for pid, qs in cropped.items():
            m = meta.get(pid)
            if not m:
                continue
            for q in qs:
                src = os.path.join(os.path.dirname(__file__), "exports", "questions_img", q["file"])
                if not os.path.exists(src):
                    continue
                shutil.copy2(src, os.path.join(SITE, "q", q["file"]))
                n_img += 1
                txt = q.get("text", "")
                if fix_encoding.is_broken(txt):
                    txt = fix_encoding.repair(txt)
                scanned.append({
                    "id": pid + "_q" + q["number"], "paper_id": pid,
                    "number": q["number"], "img": "q/" + q["file"],
                    "w": q["w"], "h": q["h"], "text": txt,
                    "topics": q.get("topics") or topic_tag.tag(txt, q.get("chapter")),
                    "chapter": q.get("chapter"),
                    "sol": _sol_for(sols, pid, q["number"], SITE),
                    "year": m["year"], "code": m["code"], "units": m["units"],
                    "program": m["program"], "moed": m["moed"],
                    "solution_url": m["solution_url"],
                })
        print(f"    שאלות כתמונה: {n_img}")
    scanned.sort(key=lambda x: (-x["year"], x["code"], int(x["number"] or 0)))
    json.dump(scanned, open(os.path.join(SITE, "data", "scans.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))

    stats = db.stats(con)
    stats["scanned"] = len(scanned)
    stats["tagged"] = sum(1 for x in scanned if x.get("topics"))
    stats["with_sol"] = sum(1 for x in scanned if x.get("sol"))
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
