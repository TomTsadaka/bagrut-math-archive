# -*- coding: utf-8 -*-
"""שלב 4 — ייצוא: JSON, CSV, וניתוח שכיחות נושאים לאורך השנים."""
import json, csv, os, collections
import db

OUT = os.path.join(os.path.dirname(__file__), "exports")


def _rows(con, sql, args=()):
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def export_json(con):
    qs = _rows(con, """
        SELECT q.*, p.year, p.code, p.units, p.program, p.moed, p.hebrew_moed
        FROM questions q JOIN papers p ON p.paper_id=q.paper_id
        ORDER BY p.year DESC, p.code, q.number""")
    figs_by_page = collections.defaultdict(list)
    for f in _rows(con, "SELECT paper_id, page, file FROM figures ORDER BY paper_id, page, idx"):
        figs_by_page[(f["paper_id"], f["page"])].append("figures/" + f["file"])
    parts = collections.defaultdict(list)
    for r in _rows(con, "SELECT * FROM parts"):
        for k in ("subtopics",):
            if r.get(k):
                try: r[k] = json.loads(r[k])
                except Exception: pass
        parts[r["question_id"]].append(r)
    for q in qs:
        for k in ("subtopics", "skills", "raw"):
            if q.get(k):
                try: q[k] = json.loads(q[k])
                except Exception: pass
        q["parts"] = sorted(parts.get(q["question_id"], []), key=lambda x: x.get("letter") or "")
        q["figures"] = figs_by_page.get((q["paper_id"], q.get("page_from")), [])
    path = os.path.join(OUT, "questions.json")
    os.makedirs(OUT, exist_ok=True)
    json.dump(qs, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return path, len(qs)


def export_csv(con):
    rows = _rows(con, """
        SELECT p.year AS שנה, p.code AS שאלון, p.units AS יחידות, p.program AS תוכנית,
               p.moed AS מועד, q.number AS מספר_שאלה, q.chapter AS פרק,
               q.topic AS נושא, q.subtopics AS תתי_נושאים, q.difficulty AS קושי,
               q.qtype AS סוג, q.points AS ניקוד, q.est_minutes AS זמן_דקות,
               q.n_parts AS מספר_סעיפים, q.has_figure AS יש_שרטוט,
               q.skills AS מיומנויות, q.body AS נוסח
        FROM questions q JOIN papers p ON p.paper_id=q.paper_id
        ORDER BY p.year DESC, p.code, q.number""")
    path = os.path.join(OUT, "questions.csv")
    os.makedirs(OUT, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    return path, len(rows)


def frequency_report(con, units=None):
    """מה באמת חוזר בבגרות — שכיחות נושאים לפי שנה ורמה.

    זה הניתוח בעל הערך הגבוה ביותר להוראה: לא 'מה בסילבוס' אלא
    'מה בפועל נשאל, כמה פעמים, ובאיזו רמת קושי'.
    """
    where = "WHERE p.units=?" if units else ""
    args = (units,) if units else ()
    by_topic = _rows(con, f"""
        SELECT q.topic AS נושא, COUNT(*) AS מספר_שאלות,
               ROUND(AVG(q.difficulty),2) AS קושי_ממוצע,
               ROUND(AVG(q.points),1) AS ניקוד_ממוצע,
               COUNT(DISTINCT p.year) AS שנים_שהופיע,
               MIN(p.year) AS משנת, MAX(p.year) AS עד_שנת
        FROM questions q JOIN papers p ON p.paper_id=q.paper_id
        {where}
        GROUP BY q.topic ORDER BY מספר_שאלות DESC""", args)
    by_sub = collections.Counter()
    for r in con.execute(f"""SELECT q.subtopics FROM questions q
                             JOIN papers p ON p.paper_id=q.paper_id {where}""", args):
        try:
            for s in json.loads(r[0] or "[]"): by_sub[s] += 1
        except Exception: pass
    by_year = _rows(con, f"""
        SELECT p.year AS שנה, q.topic AS נושא, COUNT(*) AS כמות
        FROM questions q JOIN papers p ON p.paper_id=q.paper_id
        {where} GROUP BY p.year, q.topic ORDER BY p.year DESC""", args)
    rep = {"נושאים": by_topic,
           "תתי_נושאים": [{"תת_נושא": k, "כמות": v} for k, v in by_sub.most_common()],
           "לפי_שנה": by_year}
    os.makedirs(OUT, exist_ok=True)
    name = f"frequency{'_' + str(units) + 'units' if units else ''}.json"
    path = os.path.join(OUT, name)
    json.dump(rep, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return path, rep


def coverage(con):
    """מה יש ומה חסר במאגר — שקיפות מלאה על הכיסוי."""
    return {
        "לפי_שנה": _rows(con, """
            SELECT year AS שנה, COUNT(*) AS שאלונים,
                   SUM(status='extracted') AS חולצו,
                   SUM(question_pdf IS NOT NULL) AS הורדו,
                   SUM(solution_url IS NOT NULL) AS עם_פתרון
            FROM papers GROUP BY year ORDER BY year DESC"""),
        "לפי_רמה": _rows(con, """
            SELECT COALESCE(units,0) AS יחידות, COUNT(*) AS שאלונים,
                   SUM(status='extracted') AS חולצו
            FROM papers GROUP BY units ORDER BY units DESC"""),
        "לפי_מקור": _rows(con, """
            SELECT source AS מקור, COUNT(*) AS שאלונים,
                   SUM(question_pdf IS NOT NULL) AS הורדו
            FROM papers GROUP BY source"""),
    }


def run():
    con = db.connect()
    os.makedirs(OUT, exist_ok=True)
    jp, nj = export_json(con); print(f"  ✓ {jp}  ({nj} שאלות)")
    cp, nc = export_csv(con);  print(f"  ✓ {cp}  ({nc} שורות)")
    fp, _  = frequency_report(con); print(f"  ✓ {fp}")
    cov = coverage(con)
    covp = os.path.join(OUT, "coverage.json")
    json.dump(cov, open(covp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  ✓ {covp}")
    return cov


if __name__ == "__main__":
    import sys
    cov = run()
    print("\nכיסוי לפי רמה:")
    for r in cov["לפי_רמה"]:
        print(f"  {r['יחידות'] or '?'} יח\"ל: {r['שאלונים']} שאלונים, {r['חולצו']} חולצו")
    print("\nכיסוי לפי מקור:")
    for r in cov["לפי_מקור"]:
        print(f"  {r['מקור']}: {r['שאלונים']} שאלונים, {r['הורדו']} הורדו")
