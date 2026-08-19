# -*- coding: utf-8 -*-
"""משחזר טקסט עברי מ-PDFים ישנים עם מיפוי גופן שבור.

ב-16% מהשאלות (בעיקר 2009-2011) שכבת הטקסט יוצאת כג'יבריש:
'ÌÈÏ˜˘' במקום 'שקלים'. הבתים תקינים — רק הקידוד שגוי.
mac_roman -> iso8859-8 משחזר את האותיות, ואז כל מילה הפוכה.

התצוגה לא נפגעה מעולם (היא תמונה); זה משפיע רק על חיפוש ותיוג.
"""
import json, os, re

HEB = re.compile(r'[֐-׿]')


def is_broken(t):
    if not t or len(t) < 20:
        return False
    return len(HEB.findall(t)) < len(t) * 0.15


def repair(t):
    try:
        out = t.encode('mac_roman', errors='ignore').decode('iso8859-8', errors='ignore')
    except Exception:
        return t
    if len(HEB.findall(out)) <= len(t) * 0.15:
        return t
    # כל מילה נשמרה הפוכה — היפוך המחרוזת מחזיר מילים תקינות
    return out[::-1]


def run():
    base = os.path.dirname(__file__)
    n_fix = 0
    # 1) המקור: cropped_questions.json
    p1 = os.path.join(base, "data", "cropped_questions.json")
    idx = json.load(open(p1, encoding="utf-8"))
    for pid, qs in idx.items():
        for q in qs:
            if is_broken(q.get("text", "")):
                q["text"] = repair(q["text"]); n_fix += 1
    json.dump(idx, open(p1, "w", encoding="utf-8"), ensure_ascii=False)
    # 2) הפלט לאתר
    p2 = os.path.join(base, "site", "data", "scans.json")
    if os.path.exists(p2):
        scans = json.load(open(p2, encoding="utf-8"))
        for s in scans:
            if is_broken(s.get("text", "")):
                s["text"] = repair(s["text"])
        json.dump(scans, open(p2, "w", encoding="utf-8"),
                  ensure_ascii=False, separators=(",", ":"))
    print(f"שוחזרו {n_fix} שאלות")
    return n_fix


if __name__ == "__main__":
    run()
