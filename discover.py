# -*- coding: utf-8 -*-
"""שלב 1 — גילוי: בונה קטלוג של כל שאלוני הבגרות במתמטיקה.

שני מקורות:
  A. API של משרד החינוך (meyda.education.gov.il/bagmgr) — 2011..היום,
     כולל קישור לפתרון הרשמי לכל שאלון.
  B. Wayback Machine CDX — 2000..2010, שם השאלונים הישנים כבר לא באתר החי.
"""
import json, re, time, urllib.request, urllib.error, urllib.parse
import config, db

H = {"User-Agent": config.UA, "Referer": config.MINISTRY_REFERER}


def _get(url, timeout=60, retries=3, backoff=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=H)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(backoff * (i + 1))
    raise last


# ------------------------------------------------------------- A. משרד החינוך
def discover_ministry(verbose=True):
    """מושך את כל השאלונים במתמטיקה מה-API הרשמי."""
    rows, page = [], 1
    while True:
        url = (f"{config.MINISTRY_API}?search=1&sheelon=&miktzoa={config.MATH_SUBJECT_CODE}"
               f"&safa=1&pagesize=100&page={page}")
        batch = json.loads(_get(url))
        if not batch:
            break
        rows += batch
        if verbose:
            print(f"  משרד החינוך: עמוד {page} -> {len(rows)} שאלונים")
        if len(batch) < 100:
            break
        page += 1
    return [_norm_ministry(r) for r in rows]


def _norm_ministry(r):
    code = str(r["semel_sheelon"]).lstrip("0")
    meta = config.questionnaire_meta(code)
    moed_code = str(r.get("code_moed") or "")
    year = int(r["shana"])
    # התוכנית תלויה גם בשנה, לא רק בקוד
    program = meta["program"]
    if program == "לא ידוע":
        program = "ישנה" if year <= 2014 else ("רפורמה" if year <= 2023 else "חדשה")
    return {
        "paper_id": f"{code}_{year}_{moed_code or '00'}",
        "code": code, "year": year,
        "moed": config.MOED_MAP.get(moed_code, r.get("moed")),
        "moed_code": moed_code, "hebrew_moed": r.get("moed"),
        "units": meta["units"], "program": program, "part": meta["part"],
        "source": "ministry",
        "question_url": r.get("question"), "solution_url": r.get("pitron"),
        "status": "discovered",
    }


# ------------------------------------------------------ B. ארכיון האינטרנט
CDX_URL_RE = re.compile(
    r"/sheeloney_bagrut/(\d{4})/(\d+)/HEB/(0?35\d{3})\.pdf", re.I)


def discover_wayback(year_from=2000, year_to=2010, verbose=True):
    """מוצא שאלוני מתמטיקה ישנים בארכיון האינטרנט.

    ה-CDX מחזיר את כל ה-URLים שנשמרו אי־פעם; מסננים לקודי מתמטיקה (35xxx)
    ולטווח השנים המבוקש.
    """
    q = urllib.parse.urlencode({
        "url": "meyda.education.gov.il/sheeloney_bagrut*",
        "output": "text", "fl": "original,timestamp",
        "filter": "statuscode:200", "collapse": "urlkey", "limit": "40000",
    })
    try:
        raw = _get(f"{config.WAYBACK_CDX}?{q}", timeout=240).decode("utf-8", "replace")
    except Exception as e:
        print(f"  ⚠ ארכיון האינטרנט לא זמין כרגע ({e}). דלג ונסה שוב מאוחר יותר.")
        return []
    if "<html" in raw[:200].lower():
        print("  ⚠ ארכיון האינטרנט מחזיר דף שגיאה (כנראה offline). נסה שוב מאוחר יותר.")
        return []

    seen, out = set(), []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        url, ts = parts[0], parts[1]
        m = CDX_URL_RE.search(url)
        if not m:
            continue
        year, moed_code, code = int(m.group(1)), m.group(2), m.group(3).lstrip("0")
        if not (year_from <= year <= year_to):
            continue
        pid = f"{code}_{year}_{moed_code}"
        if pid in seen:
            continue
        seen.add(pid)
        meta = config.questionnaire_meta(code)
        out.append({
            "paper_id": pid, "code": code, "year": year,
            "moed": config.MOED_MAP.get(moed_code, f"מועד {moed_code}"),
            "moed_code": moed_code, "hebrew_moed": None,
            "units": meta["units"],
            "program": meta["program"] if meta["known"] else "ישנה",
            "part": meta["part"], "source": "wayback",
            "question_url": f"https://web.archive.org/web/{ts}id_/{url}",
            "solution_url": None, "status": "discovered",
            "note": "מארכיון האינטרנט — ייתכן שהקובץ סרוק ואין פתרון רשמי",
        })
        if verbose and len(out) % 100 == 0:
            print(f"  ארכיון: {len(out)} שאלונים ישנים")
    return out


def run(year_from=2000, year_to=2100, skip_wayback=False):
    con = db.connect()
    print("שלב 1/4 — גילוי שאלונים")
    found = discover_ministry()
    print(f"  ✓ משרד החינוך: {len(found)} שאלונים")
    if not skip_wayback:
        old = discover_wayback(year_from, min(2010, year_to))
        print(f"  ✓ ארכיון האינטרנט: {len(old)} שאלונים")
        found += old
    kept = 0
    for p in found:
        if year_from <= p["year"] <= year_to:
            db.upsert_paper(con, p)
            kept += 1
    con.commit()
    s = db.stats(con)
    print(f"\nסה\"כ במאגר: {s['papers']} שאלונים, שנים {s['year_min']}–{s['year_max']}")
    return s


if __name__ == "__main__":
    run()
