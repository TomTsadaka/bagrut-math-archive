# -*- coding: utf-8 -*-
"""שלב 3 — חילוץ וסיווג: PDF -> תמונות -> Claude vision -> שאלות מסווגות.

למה vision ולא שכבת הטקסט של ה-PDF: בשאלוני הבגרות העברית יוצאת הפוכה
ומשובשת, והנוסחאות מתפרקות לתווים בודדים בשורות נפרדות. קריאה ויזואלית
היא הדרך היחידה לקבל נוסח נאמן למקור.
"""
import os, io, json, base64, argparse, sys, time
import fitz  # PyMuPDF
import config, db

MAX_PAGES = 14
DPI = 140

SYSTEM = """אתה מומחה לבחינות הבגרות במתמטיקה בישראל, ומתמחה בקטלוג שאלות.
אתה מקבל צילומי עמודים של שאלון בגרות אחד, ומחזיר את כל השאלות שבו בצורה מובנית.

כללי תמלול:
- תמלל את נוסח השאלה במלואו ובעברית, נאמן למקור. אל תקצר ואל תנסח מחדש.
- נוסחאות מתמטיות: כתוב ב-LaTeX בתוך $...$. לדוגמה: $f(x)=3x^2-5x+2$.
- אם יש שרטוט/גרף שאי אפשר לתמלל, סמן has_figure=true ותאר אותו במשפט בתוך
  הטקסט בסוגריים מרובעים, למשל: [שרטוט: טרפז ABCD שבו AB מקביל ל-DC].
- שמור על חלוקה לסעיפים (א, ב, ג...) והחזר כל סעיף בנפרד במערך parts.

כללי סיווג:
- topic: בחר נושא-על אחד בלבד מהרשימה המדויקת שתקבל.
- subtopics: 1-3 תתי-נושאים מהרשימה המדויקת. אם אין התאמה טובה — החזר מערך ריק.
- difficulty: {DIF}
- qtype: סוג השאלה.
- skills: 2-5 מיומנויות ספציפיות שהתלמיד חייב לשלוט בהן כדי לפתור
  (למשל "פתרון משוואה ריבועית", "גזירת מנה", "משפט הסינוסים"). בעברית, קצר.
- est_minutes: הערכת זמן פתרון בדקות לתלמיד ממוצע ברמה הזו.
- points: הניקוד שמצוין בשאלון. אם לא מצוין — null.
- בפרק שאלות קצרות כל סעיף הוא לרוב נושא אחר לגמרי. לכן סווג topic
  ו-subtopics גם ברמת הסעיף ולא רק ברמת השאלה. ברמת השאלה בחר את הנושא
  הדומיננטי, או את זה של הסעיף הראשון אם אין דומיננטי.

אל תמציא מידע. אם עמוד הוא נוסחאון או הוראות בלבד — התעלם ממנו.""".replace(
    "{DIF}", config.DIFFICULTY_RUBRIC.replace("\n", " "))

SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "string"},
                    "chapter": {"type": ["string", "null"]},
                    "body": {"type": "string"},
                    "points": {"type": ["number", "null"]},
                    "has_figure": {"type": "boolean"},
                    "page_from": {"type": ["integer", "null"]},
                    "topic": {"type": "string", "enum": list(config.TOPICS.keys())},
                    "subtopics": {"type": "array", "items":
                                  {"type": "string", "enum": config.ALL_SUBTOPICS}},
                    "difficulty": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                    "qtype": {"type": "string", "enum": config.QUESTION_TYPES},
                    "skills": {"type": "array", "items": {"type": "string"}},
                    "est_minutes": {"type": ["integer", "null"]},
                    "needs_formula_sheet": {"type": "boolean"},
                    "parts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "letter": {"type": "string"},
                                "body": {"type": "string"},
                                "points": {"type": ["number", "null"]},
                                "difficulty": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                                "topic": {"type": "string", "enum": list(config.TOPICS.keys())},
                                "subtopics": {"type": "array", "items":
                                              {"type": "string", "enum": config.ALL_SUBTOPICS}},
                            },
                            "required": ["letter", "body", "points", "difficulty",
                                         "topic", "subtopics"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["number", "chapter", "body", "points", "has_figure",
                             "page_from", "topic", "subtopics", "difficulty", "qtype",
                             "skills", "est_minutes", "needs_formula_sheet", "parts"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


def render(pdf_path, dpi=DPI, max_pages=MAX_PAGES):
    """PDF -> רשימת PNG בבסיס 64."""
    doc = fitz.open(pdf_path)
    imgs = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pix = page.get_pixmap(dpi=dpi)
        imgs.append(base64.standard_b64encode(pix.tobytes("png")).decode())
    n = len(doc); doc.close()
    return imgs, n


def client():
    try:
        import anthropic
    except ImportError:
        sys.exit("חסרה חבילה: pip install anthropic")
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        sys.exit("חסר ANTHROPIC_API_KEY. הגדר אותו לפני הרצת שלב החילוץ:\n"
                 "  export ANTHROPIC_API_KEY=sk-ant-...")
    return anthropic.Anthropic()


def extract_paper(cl, row, model=config.DEFAULT_MODEL, with_solution=True, effort="high"):
    """מחלץ את כל השאלות משאלון אחד."""
    imgs, n_pages = render(row["question_pdf"])
    if not imgs:
        raise RuntimeError("לא ניתן היה לרנדר את ה-PDF")

    meta = (f"שאלון {row['code']} | {row['units'] or '?'} יחידות לימוד | "
            f"{row['hebrew_moed'] or row['year']} | {row['moed'] or ''} | "
            f"תוכנית {row['program']}")
    content = [{"type": "text",
                "text": f"שאלון בגרות במתמטיקה.\n{meta}\n\n"
                        f"רשימת נושאי-העל המותרים: {', '.join(config.TOPICS.keys())}\n\n"
                        f"להלן {len(imgs)} עמודי השאלון:"}]
    for im in imgs:
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": im}})

    if with_solution and row["solution_pdf"] and os.path.exists(row["solution_pdf"]):
        sol, _ = render(row["solution_pdf"], dpi=120, max_pages=8)
        if sol:
            content.append({"type": "text",
                            "text": "להלן הפתרון הרשמי של משרד החינוך — "
                                    "השתמש בו כדי לדייק את הסיווג ואת הערכת הקושי:"})
            for im in sol:
                content.append({"type": "image", "source": {"type": "base64",
                                "media_type": "image/png", "data": im}})

    content.append({"type": "text",
                    "text": "החזר את כל השאלות בשאלון, לפי הסדר, במבנה המבוקש."})

    with cl.messages.stream(
        model=model, max_tokens=32000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        msg = stream.get_final_message()

    if msg.stop_reason == "refusal":
        raise RuntimeError("המודל סירב לבקשה")
    text = next(b.text for b in msg.content if b.type == "text")
    data = json.loads(text)
    return data.get("questions", []), n_pages, msg.usage


def run(limit=None, model=config.DEFAULT_MODEL, effort="high", redo=False, year_from=None):
    con = db.connect()
    cl = client()
    q = ("SELECT * FROM papers WHERE question_pdf IS NOT NULL AND question_pdf<>'' "
         + ("" if redo else "AND status<>'extracted' "))
    if year_from:
        q += f"AND year>={int(year_from)} "
    q += "ORDER BY year DESC, code"
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = con.execute(q).fetchall()
    print(f"שלב 3/4 — חילוץ שאלות מ-{len(rows)} שאלונים (מודל: {model}, effort={effort})")

    tot_q = tot_in = tot_out = 0
    for i, row in enumerate(rows, 1):
        pid = row["paper_id"]
        try:
            t0 = time.time()
            qs, n_pages, usage = extract_paper(cl, row, model, effort=effort)
            for qi, qd in enumerate(qs, 1):
                qid = f"{pid}_q{qd.get('number') or qi}"
                db.upsert_question(con, {
                    "question_id": qid, "paper_id": pid,
                    "number": qd.get("number"), "chapter": qd.get("chapter"),
                    "body": qd.get("body"), "points": qd.get("points"),
                    "n_parts": len(qd.get("parts") or []),
                    "has_figure": qd.get("has_figure"), "page_from": qd.get("page_from"),
                    "topic": qd.get("topic"), "subtopics": qd.get("subtopics"),
                    "difficulty": qd.get("difficulty"), "qtype": qd.get("qtype"),
                    "skills": qd.get("skills"), "est_minutes": qd.get("est_minutes"),
                    "needs_formula_sheet": qd.get("needs_formula_sheet"),
                    "confidence": None, "raw": qd,
                })
                for p in (qd.get("parts") or []):
                    db.upsert_part(con, {
                        "part_id": f"{qid}_{p.get('letter')}", "question_id": qid,
                        "letter": p.get("letter"), "body": p.get("body"),
                        "points": p.get("points"), "difficulty": p.get("difficulty"),
                        "topic": p.get("topic"), "subtopics": p.get("subtopics"),
                    })
            con.execute("UPDATE papers SET status='extracted', n_pages=? WHERE paper_id=?",
                        (n_pages, pid))
            con.commit()
            tot_q += len(qs)
            tot_in += usage.input_tokens; tot_out += usage.output_tokens
            print(f"  [{i}/{len(rows)}] {pid}: {len(qs)} שאלות "
                  f"({time.time()-t0:.0f}s, {usage.input_tokens+usage.output_tokens:,} טוקנים)")
        except Exception as e:
            con.execute("UPDATE papers SET status='failed', note=? WHERE paper_id=?",
                        (str(e)[:300], pid)); con.commit()
            print(f"  [{i}/{len(rows)}] {pid}: ✗ {e}")

    print(f"\n  ✓ חולצו {tot_q} שאלות. טוקנים: {tot_in:,} קלט / {tot_out:,} פלט")
    return tot_q


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model", default=config.DEFAULT_MODEL)
    ap.add_argument("--effort", default="high", choices=["low","medium","high","xhigh","max"])
    ap.add_argument("--year-from", type=int)
    ap.add_argument("--redo", action="store_true")
    a = ap.parse_args()
    run(a.limit, a.model, a.effort, a.redo, a.year_from)
