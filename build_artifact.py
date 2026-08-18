# -*- coding: utf-8 -*-
"""בונה דף עצמאי לפרסום: קטלוג כל השאלונים + הדגמת שאלה מקוטלגת עם שרטוט."""
import json, os, base64
import db

OUT = os.path.join(os.path.dirname(__file__), "exports", "artifact.html")

ERAS = [
    ("חדשה",  "תוכנית הלימודים החדשה", "תשפ\"ד ואילך",
     "שאלונים 171/172, 371/372, 471/472, 571/572"),
    ("רפורמה", "רפורמת 2015", "תשע\"ה–תשפ\"ג",
     "שאלונים 181/182, 381/382, 481/482, 581/582"),
    ("ישנה",   "התוכנית הישנה", "עד תשע\"ה",
     "שאלונים 801–807 והמספור התלת-ספרתי 311–317"),
]


def collect():
    con = db.connect()
    papers = [dict(r) for r in con.execute("""
        SELECT paper_id, code, year, moed, units, program, source,
               question_url, solution_url,
               (question_pdf IS NOT NULL AND question_pdf<>'') AS have
        FROM papers ORDER BY year DESC, units DESC, code""")]
    q = con.execute("SELECT * FROM questions LIMIT 1").fetchone()
    sample = dict(q) if q else None
    if sample:
        for k in ("subtopics", "skills"):
            try: sample[k] = json.loads(sample[k] or "[]")
            except Exception: sample[k] = []
        sample["parts"] = []
        for p in con.execute("SELECT * FROM parts WHERE question_id=? ORDER BY letter",
                             (sample["question_id"],)):
            d = dict(p)
            try: d["subtopics"] = json.loads(d["subtopics"] or "[]")
            except Exception: d["subtopics"] = []
            sample["parts"].append(d)
        figs = con.execute(
            "SELECT file, path, w, h FROM figures WHERE paper_id=? AND page=2 ORDER BY idx",
            (sample["paper_id"],)).fetchall()
        sample["figures"] = []
        for f in figs:
            if os.path.exists(f["path"]) and os.path.getsize(f["path"]) < 700_000:
                b64 = base64.b64encode(open(f["path"], "rb").read()).decode()
                sample["figures"].append({"src": "data:image/png;base64," + b64,
                                          "w": f["w"], "h": f["h"]})
    stats = db.stats(con)
    stats["with_solution"] = con.execute(
        "SELECT COUNT(*) FROM papers WHERE solution_url IS NOT NULL").fetchone()[0]
    stats["figures_files"] = len(os.listdir(os.path.join("exports", "figures"))) \
        if os.path.isdir(os.path.join("exports", "figures")) else 0
    return papers, sample, stats


def build():
    papers, sample, stats = collect()
    tpl = open(os.path.join(os.path.dirname(__file__), "assets", "artifact.html"),
               encoding="utf-8").read()
    html = (tpl
            .replace("__PAPERS__", json.dumps(papers, ensure_ascii=False))
            .replace("__SAMPLE__", json.dumps(sample, ensure_ascii=False))
            .replace("__STATS__", json.dumps(stats, ensure_ascii=False))
            .replace("__ERAS__", json.dumps(ERAS, ensure_ascii=False)))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"  ✓ {OUT}  ({os.path.getsize(OUT)/1024:.0f} KB, {len(papers)} שאלונים)")
    return OUT


if __name__ == "__main__":
    build()
