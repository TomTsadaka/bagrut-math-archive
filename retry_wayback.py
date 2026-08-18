# -*- coding: utf-8 -*-
"""ניסיון חוזר סבלני לשאלונים מארכיון האינטרנט.

ארכיון האינטרנט מגביל קצב ומחזיר 503 לסירוגין. לכן: עובד יחיד,
השהיה בין בקשות, וכמה סבבים. אפשר להריץ שוב ושוב — מדלג על מה שכבר ירד.
"""
import time, sys, os
import db, fetch

def run(rounds=3, delay=4.0, pause_between_rounds=60):
    con = db.connect()
    for rnd in range(1, rounds + 1):
        rows = con.execute(
            "SELECT paper_id, question_url FROM papers "
            "WHERE source='wayback' AND (question_pdf IS NULL OR question_pdf='')"
        ).fetchall()
        if not rows:
            print("אין מה להוריד — הכול כבר במטמון.")
            return 0
        print(f"\nסבב {rnd}/{rounds}: {len(rows)} שאלונים חסרים")
        ok = 0
        for i, r in enumerate(rows, 1):
            dest = fetch._path(r["paper_id"], "questions")
            if fetch.download(r["question_url"], dest, retries=2):
                con.execute("UPDATE papers SET question_pdf=?, status='fetched' "
                            "WHERE paper_id=?", (dest, r["paper_id"]))
                ok += 1
            if i % 20 == 0:
                con.commit()
                print(f"  {i}/{len(rows)} — ירדו {ok}")
            time.sleep(delay)
        con.commit()
        print(f"  סבב {rnd} הסתיים: {ok} הורדות חדשות")
        if ok == 0 and rnd < rounds:
            print(f"  אין התקדמות — ממתין {pause_between_rounds}s לפני הסבב הבא")
            time.sleep(pause_between_rounds)
    left = con.execute("SELECT COUNT(*) FROM papers WHERE source='wayback' "
                       "AND (question_pdf IS NULL OR question_pdf='')").fetchone()[0]
    print(f"\nנותרו חסרים: {left}")
    return left

if __name__ == "__main__":
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    run(rounds=rounds)
