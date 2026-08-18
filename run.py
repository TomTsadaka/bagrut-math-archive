#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""סוכן מאגר שאלוני הבגרות במתמטיקה — נקודת כניסה ראשית.

  python3 run.py discover                 גילוי כל השאלונים (2000–היום)
  python3 run.py fetch --limit 100        הורדת PDFים
  python3 run.py extract --limit 10       חילוץ וסיווג שאלות (דורש מפתח API)
  python3 run.py export                   ייצוא JSON/CSV/ניתוח שכיחות
  python3 run.py search "נגזרת" --units 5 חיפוש חופשי במאגר
  python3 run.py stats                    מצב המאגר
  python3 run.py all                      הרצת הצינור המלא
"""
import argparse, json, sys, os
import config, db


def cmd_stats(a):
    con = db.connect(); s = db.stats(con)
    print(f"""
מצב המאגר
─────────────────────────────
שאלונים בקטלוג   {s['papers']:>6}
הורדו             {s['fetched']:>6}
חולצו             {s['extracted']:>6}
שאלות             {s['questions']:>6}
סעיפים            {s['parts']:>6}
טווח שנים         {s['year_min']}–{s['year_max']}""")
    print("\nלפי רמה:")
    for r in con.execute("SELECT units u, COUNT(*) n, SUM(status='extracted') e "
                         "FROM papers GROUP BY units ORDER BY units DESC"):
        print(f"  {r['u'] or '?'} יח\"ל: {r['n']:>4} שאלונים, {r['e'] or 0} חולצו")
    print("\nלפי תוכנית לימודים:")
    for r in con.execute("SELECT program p, COUNT(*) n, MIN(year) a, MAX(year) b "
                         "FROM papers GROUP BY program ORDER BY n DESC"):
        print(f"  {r['p']:<8} {r['n']:>4} שאלונים ({r['a']}–{r['b']})")


def cmd_search(a):
    con = db.connect()
    sql = ("SELECT q.question_id, q.number, q.topic, q.difficulty, q.body, "
           "p.year, p.code, p.units, p.moed "
           "FROM questions_fts f JOIN questions q ON q.question_id=f.question_id "
           "JOIN papers p ON p.paper_id=q.paper_id WHERE questions_fts MATCH ?")
    args = [a.query]
    if a.units:  sql += " AND p.units=?";      args.append(a.units)
    if a.topic:  sql += " AND q.topic=?";      args.append(a.topic)
    if a.year:   sql += " AND p.year=?";       args.append(a.year)
    if a.difficulty: sql += " AND q.difficulty=?"; args.append(a.difficulty)
    sql += " ORDER BY p.year DESC LIMIT ?"; args.append(a.limit)
    rows = con.execute(sql, args).fetchall()
    print(f"נמצאו {len(rows)} תוצאות\n")
    for r in rows:
        body = (r["body"] or "").replace("\n", " ")[:160]
        print(f"[{r['year']} | {r['code']} | {r['units']} יח\"ל | {r['topic']} | "
              f"קושי {r['difficulty']}]  שאלה {r['number']}")
        print(f"   {body}…\n")


def cmd_topics(a):
    print("טקסונומיית הנושאים\n" + "─" * 40)
    for t, subs in config.TOPICS.items():
        print(f"\n{t}")
        for s in subs:
            print(f"    · {s}")
    print(f"\n\nסולם הקושי\n{'─'*40}\n{config.DIFFICULTY_RUBRIC}")
    print(f"סוגי שאלות: {', '.join(config.QUESTION_TYPES)}")


def cmd_all(a):
    import discover, fetch, extract, export, backfill
    discover.run()
    backfill.run()
    fetch.run(limit=a.limit)
    if os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
        extract.run(limit=a.limit, model=a.model)
    else:
        print("\n⚠ דילוג על שלב החילוץ — לא הוגדר ANTHROPIC_API_KEY")
    export.run()


def main():
    ap = argparse.ArgumentParser(description="מאגר שאלוני בגרות במתמטיקה")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("discover", help="גילוי שאלונים")
    p.add_argument("--from", dest="year_from", type=int, default=2000)
    p.add_argument("--to", dest="year_to", type=int, default=2100)
    p.add_argument("--skip-wayback", action="store_true")
    p.set_defaults(func=lambda a: __import__("discover").run(a.year_from, a.year_to, a.skip_wayback))

    p = sub.add_parser("fetch", help="הורדת PDFים")
    p.add_argument("--limit", type=int); p.add_argument("--workers", type=int, default=6)
    p.set_defaults(func=lambda a: __import__("fetch").run(a.limit, a.workers))

    p = sub.add_parser("extract", help="חילוץ וסיווג שאלות")
    p.add_argument("--limit", type=int); p.add_argument("--model", default=config.DEFAULT_MODEL)
    p.add_argument("--effort", default="high")
    p.add_argument("--year-from", type=int); p.add_argument("--redo", action="store_true")
    p.set_defaults(func=lambda a: __import__("extract").run(
        a.limit, a.model, a.effort, a.redo, a.year_from))

    p = sub.add_parser("export", help="ייצוא ודוחות")
    p.set_defaults(func=lambda a: __import__("export").run())

    p = sub.add_parser("backfill", help="השלמת מטא-דאטה")
    p.set_defaults(func=lambda a: __import__("backfill").run())

    p = sub.add_parser("search", help="חיפוש במאגר")
    p.add_argument("query"); p.add_argument("--units", type=int)
    p.add_argument("--topic"); p.add_argument("--year", type=int)
    p.add_argument("--difficulty", type=int); p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("topics", help="הצגת הטקסונומיה")
    p.set_defaults(func=cmd_topics)

    p = sub.add_parser("stats", help="מצב המאגר")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("all", help="הצינור המלא")
    p.add_argument("--limit", type=int); p.add_argument("--model", default=config.DEFAULT_MODEL)
    p.set_defaults(func=cmd_all)

    a = ap.parse_args(); a.func(a)


if __name__ == "__main__":
    main()
