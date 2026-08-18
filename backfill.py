# -*- coding: utf-8 -*-
"""משלים units/program/part לשאלונים שהקוד שלהם זוהה בדיעבד."""
import config, db

def run():
    con = db.connect()
    fixed = 0
    for r in con.execute("SELECT paper_id, code, year FROM papers").fetchall():
        m = config.questionnaire_meta(r["code"])
        if not m["known"]:
            continue
        prog = m["program"]
        if prog == "לא ידוע":
            prog = "ישנה" if r["year"] <= 2014 else ("רפורמה" if r["year"] <= 2023 else "חדשה")
        cur = con.execute("SELECT units FROM papers WHERE paper_id=?", (r["paper_id"],)).fetchone()
        if cur["units"] is None:
            fixed += 1
        con.execute("UPDATE papers SET units=?, program=?, part=? WHERE paper_id=?",
                    (m["units"], prog, m["part"], r["paper_id"]))
    con.commit()
    print(f"הושלמו {fixed} שאלונים")
    return fixed

if __name__ == "__main__":
    run()
