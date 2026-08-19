# -*- coding: utf-8 -*-
"""טוען חילוץ שאלות מקובץ JSON אל תוך המאגר.

מבנה הקובץ: {"paper_id": [...שאלות...], ...}
כל שאלה יכולה לכלול "figure_files" — שיוך מפורש של שרטוטים,
עדיף על שיוך אוטומטי לפי מספר עמוד.
"""
import json, sys, os
import db

def run(path):
    data = json.load(open(path, encoding="utf-8"))
    con = db.connect()
    n_q = n_p = 0
    for paper_id, questions in data.items():
        for qi, qd in enumerate(questions, 1):
            qid = f"{paper_id}_q{qd.get('number') or qi}"
            db.upsert_question(con, {
                "question_id": qid, "paper_id": paper_id,
                "number": qd.get("number"), "chapter": qd.get("chapter"),
                "body": qd.get("body"), "points": qd.get("points"),
                "n_parts": len(qd.get("parts") or []),
                "has_figure": 1 if qd.get("figure_files") else 0,
                "page_from": qd.get("page_from"),
                "topic": qd.get("topic"), "subtopics": qd.get("subtopics"),
                "difficulty": qd.get("difficulty"), "qtype": qd.get("qtype"),
                "skills": qd.get("skills"), "est_minutes": qd.get("est_minutes"),
                "needs_formula_sheet": qd.get("needs_formula_sheet"),
                "confidence": qd.get("confidence"),
                "figure_files": qd.get("figure_files"), "raw": qd,
            })
            n_q += 1
            for p in (qd.get("parts") or []):
                db.upsert_part(con, {
                    "part_id": f"{qid}_{p.get('letter')}", "question_id": qid,
                    "letter": p.get("letter"), "body": p.get("body"),
                    "points": p.get("points"), "difficulty": p.get("difficulty"),
                    "topic": p.get("topic"), "subtopics": p.get("subtopics"),
                })
                n_p += 1
        con.execute("UPDATE papers SET status='extracted' WHERE paper_id=?", (paper_id,))
    con.commit()
    print(f"נטענו {n_q} שאלות ו-{n_p} סעיפים מתוך {len(data)} שאלונים")
    return n_q

if __name__ == "__main__":
    run(sys.argv[1])
