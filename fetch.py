# -*- coding: utf-8 -*-
"""שלב 2 — הורדה: מוריד את קובצי ה-PDF (שאלון + פתרון רשמי), עם מטמון."""
import os, time, hashlib, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
import config, db

CACHE = os.path.join(os.path.dirname(__file__), "cache")
H = {"User-Agent": config.UA, "Referer": config.MINISTRY_REFERER}


def _path(paper_id, kind):
    d = os.path.join(CACHE, kind)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{paper_id}.pdf")


def download(url, dest, retries=3):
    """מוריד PDF; מחזיר True אם הקובץ תקין."""
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return True
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=H)
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            if data[:4] != b"%PDF":
                return False           # דף שגיאה / HTML
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except urllib.error.HTTPError as e:
            if e.code in (404, 403):
                return False
            last = e
        except Exception as e:
            last = e
        time.sleep(2 * (i + 1))
    return False


def _one(row):
    pid = row["paper_id"]
    res = {"paper_id": pid, "q": False, "s": False}
    if row["question_url"]:
        qp = _path(pid, "questions")
        if download(row["question_url"], qp):
            res["q"], res["question_pdf"] = True, qp
    if row["solution_url"]:
        sp = _path(pid, "solutions")
        if download(row["solution_url"], sp):
            res["s"], res["solution_pdf"] = True, sp
    return res


def run(limit=None, workers=6, only_missing=True):
    con = db.connect()
    q = "SELECT * FROM papers"
    if only_missing:
        q += " WHERE question_pdf IS NULL OR question_pdf=''"
    q += " ORDER BY year DESC, code"
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = con.execute(q).fetchall()
    print(f"שלב 2/4 — הורדת {len(rows)} שאלונים ({workers} במקביל)")

    ok = sol = fail = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_one, r): r for r in rows}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
            except Exception as e:
                fail += 1; continue
            if r["q"]:
                ok += 1
                con.execute("UPDATE papers SET question_pdf=?, solution_pdf=?, status='fetched'"
                            " WHERE paper_id=?",
                            (r.get("question_pdf"), r.get("solution_pdf"), r["paper_id"]))
                if r["s"]:
                    sol += 1
            else:
                fail += 1
                con.execute("UPDATE papers SET status='failed', note=COALESCE(note,'')||' | הורדה נכשלה'"
                            " WHERE paper_id=?", (r["paper_id"],))
            if i % 25 == 0:
                con.commit()
                print(f"  {i}/{len(rows)}  ✓{ok} פתרונות:{sol} ✗{fail}")
    con.commit()
    print(f"\n  ✓ הורדו {ok} שאלונים, מתוכם {sol} עם פתרון רשמי. נכשלו: {fail}")
    return {"ok": ok, "solutions": sol, "failed": fail}


if __name__ == "__main__":
    import sys
    run(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
